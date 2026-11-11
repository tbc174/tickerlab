"""Monta a tabela de entradas e saídas de sócio PJ (linha 810, PR 2; `base/socios_pj.py`). Roda no servidor de casa.

    python -m scripts.montar_entradas_de_socio_pj --cnpj <base do CNPJ> --destino <acervo>/base [--ensaio]

Lê do disco, sem rede, o QSA vigente e as mudanças de cada mês (só as linhas de sócio do tipo 1) e a lista
sem pessoa do CNPJ (`cnpj_estabelecimentos_pj`, que `scripts/montar_empresas_pj.py` grava), e grava
`entradas_de_socio_pj/<2 primeiros caracteres da raiz>.parquet` em `--destino`. A lista sem pessoa tem de
ser do mesmo mês do QSA vigente: senão, para (rode antes o `montar_empresas_pj`).

**Só acrescenta uma tabela nova:** não toca nas outras pastas de `--destino`. Remontar o mesmo mês não regrava
nada (`gravar_se_mudou`). `--ensaio` monta e conta, sem gravar. Saída 0 tudo certo; 1 falha (última linha
`FALHAS:`). `--se-houver-mes-novo` (o do cron diário) sai com 0 sem montar nada se a tabela já tem o último mês
do QSA ou se a lista sem pessoa ainda é de outro mês: assim a montagem roda logo depois do `montar_empresas_pj`.

**Guarda de faixa:** um mês que ainda não está na tabela gravada (fora o primeiro da série, que traz as sócias
que já estavam) com mais entradas ou saídas que `MAXIMO_POR_MES` não substitui a tabela: a saída é de falha,
com o mês e a contagem, e a ficha da coleta abre. Foi assim que o retrato de 2024-09 apareceu.

Roda: cron de casa (VM), todo dia às 8h10 com --se-houver-mes-novo (rodar-tarefa.sh entradas-socio-pj; "pode"
da Diretoria de 11/11/2026), e manual; coberto por test_montar_entradas_de_socio_pj.py; ver dicionario-da-base.md.
"""

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import socios_pj
from base.parquet import gravar_se_mudou
from base.porta.duckdb import arquivos_da_tabela
from base.receita_diff import ENTROU, SAIU, TIPO_PESSOA_JURIDICA
from base.receita_retrato import ErroDeLayout
from scripts import carga_receita_mes as carga
from scripts.montar_empresas_pj import ESTABELECIMENTOS
from scripts.montar_historico_do_cnpj import CARIMBOS, PREFIXO, _origens, _zips_do_mes
from src.versao_do_codigo import versao_do_codigo

log = logging.getLogger("tickerlab.montar_entradas_de_socio_pj")

COLUNAS_DO_QSA = [
    "cnpj_basico",
    "tipo_socio",
    "raiz_socio_pj",
    "data_entrada",
    "qualificacao",
]
LADOS = ("antes", "depois")
COLUNAS_DAS_MUDANCAS = [
    "mes",
    "tipo",
    "cnpj_basico",
    "tipo_socio",
    "raiz_socio_pj",
    *(
        f"{coluna}_{lado}"
        for coluna in ("data_entrada", "qualificacao")
        for lado in LADOS
    ),
]
ZIPS_DE_SOCIOS = "Socios"
TAMANHO_MAXIMO_DO_RESUMO = 300
# Guarda de faixa (Diretoria, 11/11/2026): de 2023-06 a 2026-10 o mês mais cheio teve 15.470 entradas e 3.485
# saídas (2024-10, com setembro junto); os outros, de 4,4 a 12,2 mil entradas e de 1,1 a 2,9 mil saídas.
MAXIMO_POR_MES = {ENTROU: 30_000, SAIU: 10_000}


def _ler_socios_pj(pasta: Path, colunas: list[str]) -> pd.DataFrame:
    """As linhas de sócio PJ dos Parquets de `pasta` (um arquivo por prefixo ou por mês, ou pastas de partes)."""
    partes = [
        pd.read_parquet(
            arquivo,
            columns=colunas,
            filters=[("tipo_socio", "==", TIPO_PESSOA_JURIDICA)],
        )
        for arquivo in arquivos_da_tabela(pasta, "**/*.parquet")
    ]
    return (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=colunas)
    )


def _pessoas_juridicas(destino: Path, mes: str, raizes: set[str]) -> set[str]:
    """As `raizes` que estão na lista sem pessoa do CNPJ, que tem de ser do `mes` do QSA vigente.

    Lê uma partição por vez e guarda só as raízes que aparecem no QSA PJ: a lista inteira (21 milhões de
    raízes em 11/2026) não cabia em 8 GB, e o filtro da tabela olha só essas raízes."""
    arquivos = arquivos_da_tabela(destino / ESTABELECIMENTOS, "*.parquet")
    if not arquivos:
        raise ErroDeLayout(
            f"{ESTABELECIMENTOS} ausente em {destino}: rode antes o montar_empresas_pj"
        )
    meses: set[str] = set()
    na_lista: set[str] = set()
    for arquivo in arquivos:
        parte = pd.read_parquet(arquivo, columns=["cnpj_basico", "mes_do_retrato"])
        meses.update(parte["mes_do_retrato"].unique())
        na_lista.update(parte.loc[parte["cnpj_basico"].isin(raizes), "cnpj_basico"])
    if meses != {mes}:
        raise ErroDeLayout(
            f"{ESTABELECIMENTOS} é de {sorted(meses)} e o QSA vigente de {mes}: rode antes o montar_empresas_pj"
        )
    return na_lista


def _raizes(*tabelas: pd.DataFrame) -> set[str]:
    """As raízes dos dois lados (empresa e sócia) das `tabelas` do QSA."""
    return {
        raiz
        for tabela in tabelas
        for coluna in ("cnpj_basico", "raiz_socio_pj")
        for raiz in tabela[coluna].dropna().unique()
    }


def montar(
    cnpj: Path, destino: Path, agora: datetime, gravar: bool = True
) -> dict[str, int]:
    """Monta a tabela com o QSA de `cnpj` e devolve as linhas de cada movimento."""
    manifesto = json.loads((cnpj / carga.MANIFESTO).read_text(encoding="utf-8"))
    meses = sorted(manifesto["meses"])
    vigente = _ler_socios_pj(cnpj / "vigente" / "qsa", COLUNAS_DO_QSA)
    mudancas = _ler_socios_pj(cnpj / "mudancas" / "qsa", COLUNAS_DAS_MUDANCAS)
    tabela = socios_pj.entradas_e_saidas(
        vigente,
        mudancas,
        meses[0],
        _pessoas_juridicas(destino, meses[-1], _raizes(vigente, mudancas)),
    )
    contagem = {str(k): int(v) for k, v in tabela["movimento"].value_counts().items()}
    log.info("entradas_de_socio_pj até %s: %s", meses[-1], contagem)
    _conferir_faixa(tabela, meses[0], _meses_gravados(destino))
    if gravar:
        _gravar(tabela, destino, manifesto, meses, agora)
    return contagem


def _sem_mes_novo(cnpj: Path, destino: Path) -> str | None:
    """Por que não há o que montar (a tabela já tem o último mês, ou a lista sem pessoa ainda é de outro), ou None.

    Para o cron diário: a montagem só roda depois que o `montar_empresas_pj` gravou a lista do retrato novo."""
    manifesto = json.loads((cnpj / carga.MANIFESTO).read_text(encoding="utf-8"))
    ultimo = max(manifesto["meses"])
    if ultimo in _meses_gravados(destino):
        return f"a tabela já tem {ultimo}"
    lista = {
        str(mes)
        for arquivo in arquivos_da_tabela(destino / ESTABELECIMENTOS, "*.parquet")
        for mes in pd.read_parquet(arquivo, columns=["mes_do_retrato"])[
            "mes_do_retrato"
        ].unique()
    }
    if lista != {ultimo}:
        return f"esperando o montar_empresas_pj de {ultimo} (a lista sem pessoa é de {sorted(lista)})"
    return None


def _meses_gravados(destino: Path) -> set[str]:
    """Os meses que a tabela gravada em `destino` já tem (nenhum, se ainda não foi montada)."""
    return {
        str(mes)
        for arquivo in arquivos_da_tabela(destino / socios_pj.TABELA, "*.parquet")
        for mes in pd.read_parquet(arquivo, columns=[socios_pj.MES])[
            socios_pj.MES
        ].unique()
    }


def _conferir_faixa(
    tabela: pd.DataFrame, primeiro_mes: str, gravados: set[str]
) -> None:
    """Para (ValueError) se um mês novo da `tabela` passa de `MAXIMO_POR_MES` em algum movimento."""
    meses = tabela[socios_pj.MES]
    novos = tabela[(meses != primeiro_mes) & ~meses.isin(gravados)]
    contagem = novos.groupby([socios_pj.MES, "movimento"]).size()
    fora = [
        f"{mes} {movimento} {quantos}"
        for (mes, movimento), quantos in contagem.items()
        if movimento in MAXIMO_POR_MES and quantos > MAXIMO_POR_MES[movimento]
    ]
    if fora:
        raise ValueError(
            f"mês novo fora da faixa {MAXIMO_POR_MES}: {', '.join(fora)}; "
            "a tabela gravada fica como estava (retrato da Receita com defeito?)"
        )


def _gravar(
    tabela: pd.DataFrame,
    destino: Path,
    manifesto: dict,
    meses: list[str],
    agora: datetime,
) -> None:
    origens = _origens({m: _zips_do_mes(manifesto, m, ZIPS_DE_SOCIOS) for m in meses})
    carimbada = tabela.assign(
        montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
    )
    pasta = destino / socios_pj.TABELA
    pasta.mkdir(parents=True, exist_ok=True)
    ordem = ["movimento", *socios_pj.IDENTIDADE, socios_pj.MES]
    for prefixo, parte in carimbada.groupby(carimbada["cnpj_basico"].str[:PREFIXO]):
        gravar_se_mudou(
            parte.reset_index(drop=True),
            pasta / str(prefixo),
            origens,
            ordem,
            carimbos=CARIMBOS,
        )


def main(
    argv: list[str] | None = None,
    agora: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    analisador.add_argument("--cnpj", type=Path, required=True)
    analisador.add_argument("--destino", type=Path, required=True)
    analisador.add_argument("--ensaio", action="store_true")
    analisador.add_argument("--se-houver-mes-novo", action="store_true")
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        if opcoes.se_houver_mes_novo:
            motivo = _sem_mes_novo(opcoes.cnpj, opcoes.destino)
            if motivo:
                print(f"nada a fazer: {motivo}")
                return 0
        print(montar(opcoes.cnpj, opcoes.destino, agora(), gravar=not opcoes.ensaio))
        return 0
    except (ErroDeLayout, KeyError, ValueError, OSError) as erro:
        resumo = f"FALHAS: entradas de sócio PJ: {type(erro).__name__}: {erro}"
        print(resumo[:TAMANHO_MAXIMO_DO_RESUMO])
        return 1


if __name__ == "__main__":
    sys.exit(main())
