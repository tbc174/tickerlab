"""Monta `cnpj_nomes_pj` (linha 1033; `base/nomes_de_empresa.py`). Roda no servidor de casa.

    python -m scripts.montar_nomes_pj --destino <acervo>/base [--ensaio]

Roda **depois** de `montar_empresas_pj` (usa as duas listas sem pessoa de `--destino` e o mês delas). Baixa os
`Estabelecimentos*.zip` daquele mês (fonte oficial, alguns GB, apagados ao fim), lê só a raiz e o nome fantasia,
e grava `cnpj_nomes_pj/<xx>.parquet` com a razão social de hoje, os nomes fantasia e as razões sociais antigas
(do `cnpj_empresas_historico`, se `--destino` o tiver; sem ele a tabela sai sem nome antigo e o log avisa).

**Só acrescenta a tabela nova:** não grava nas outras pastas. Remontar o mesmo mês não regrava nada
(`gravar_se_mudou`). `--ensaio` só diz o mês. Saída 0 tudo certo; 1 falha (última linha `FALHAS:`).

Roda: manual (python -m scripts.montar_nomes_pj), na VM de casa, uma vez por mês de retrato novo, depois do
montar_empresas_pj; coberto por test_montar_nomes_pj.py; ver dicionario-da-base.md.
"""

import argparse
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import nomes_de_empresa as nomes
from base.parquet import arquivos_atuais, gravar_se_mudou
from base.receita_diff import disponivel_em
from base.receita_retrato import ErroDeLayout
from scripts import carga_receita_mes as carga
from scripts.montar_historico_do_cnpj import (
    CARIMBOS,
    TRABALHO,
    _arquivos,
    _carimbar,
    _ler,
    _origens,
    _repartir,
)

log = logging.getLogger("tickerlab.montar_nomes_pj")

NOMES = "cnpj_nomes_pj"
EMPRESAS = "cnpj_empresas_pj"
ESTABELECIMENTOS = "cnpj_estabelecimentos_pj"
HISTORICO = "cnpj_empresas_historico"
ZIP_DOS_ESTABELECIMENTOS = "Estabelecimentos"
TAMANHO_MAXIMO_DO_RESUMO = 300
Baixar = Callable[[str, Path], list[Path]]


class SemListaDeEmpresas(ValueError):
    """`--destino` não tem as listas sem pessoa, ou elas são de meses diferentes: sem elas não dá para saber
    quem é empresa."""


def _mes_da_lista(pasta: Path) -> str | None:
    """O mês do retrato mais novo nos arquivos atuais de uma lista (sem as versões guardadas)."""
    meses = [
        pd.read_parquet(arquivo, columns=["mes_do_retrato"])["mes_do_retrato"].max()
        for arquivo in arquivos_atuais(pasta)
    ]
    return str(max(meses)) if meses else None


def mes_das_empresas(destino: Path) -> str:
    """O mês do retrato das listas sem pessoa que `--destino` tem; as duas têm de ser do mesmo mês."""
    mes = _mes_da_lista(destino / EMPRESAS)
    da_vista = _mes_da_lista(destino / ESTABELECIMENTOS)
    if mes is None or da_vista is None:
        raise SemListaDeEmpresas(f"rode antes o montar_empresas_pj em {destino}")
    if da_vista != mes:
        raise SemListaDeEmpresas(
            f"a lista de empresas é de {mes} e a de estabelecimentos é de {da_vista}: "
            "rode o montar_empresas_pj de novo"
        )
    return mes


def _do_prefixo(
    destino: Path, prefixo: str, trabalho: Path, mes: str
) -> pd.DataFrame | None:
    """Os nomes de um prefixo de raiz no retrato `mes`; None se não há empresa sem pessoa nele.

    O histórico pode estar à frente das listas: versão de um mês depois de `mes` é futuro para o retrato.
    """
    arquivo = f"{prefixo}.parquet"
    empresas = _ler(_arquivos(destino / EMPRESAS / arquivo))
    vista = _ler(_arquivos(destino / ESTABELECIMENTOS / arquivo))
    if empresas is None or vista is None:
        return None
    if {str(t["mes_do_retrato"].max()) for t in (empresas, vista)} != {mes}:
        raise SemListaDeEmpresas(
            f"o prefixo {prefixo} das listas não é de {mes} (montagem pela metade): "
            "rode o montar_empresas_pj de novo"
        )
    empresas = empresas[empresas["cnpj_basico"].isin(set(vista["cnpj_basico"]))]
    fantasias = _ler(_arquivos(trabalho / prefixo))
    if fantasias is None:
        fantasias = pd.DataFrame(columns=["cnpj_basico", "nome_fantasia"])
    historico = _ler(_arquivos(destino / HISTORICO / arquivo))
    if historico is not None:
        historico = historico[historico["mes_do_retrato"] <= mes]
    return nomes.tabela_de_nomes(empresas, fantasias, historico)


def montar(destino: Path, zips: list[Path], agora: datetime) -> dict[str, int]:
    """Grava `cnpj_nomes_pj` no mês das listas sem pessoa e devolve quantas linhas há de cada tipo de nome."""
    mes = mes_das_empresas(destino)
    if not _arquivos(destino / HISTORICO):
        log.warning(
            "sem %s em %s: a tabela sai sem razão social antiga", HISTORICO, destino
        )
    shas = {z.name: carga.sha256_do_arquivo(z) for z in zips}
    origens = _origens({mes: shas})
    trabalho = destino / NOMES / TRABALHO
    shutil.rmtree(trabalho, ignore_errors=True)
    contagem = dict.fromkeys(nomes.TIPOS_DE_NOME, 0)
    try:
        for numero, arquivo in enumerate(sorted(zips)):
            for parte_numero, parte in enumerate(nomes.ler_nomes_fantasia(arquivo)):
                parte = parte.drop_duplicates()
                _repartir(parte, trabalho, f"{numero:02d}-{parte_numero:04d}")
        for prefixo in [p.stem for p in arquivos_atuais(destino / EMPRESAS)]:
            tabela = _do_prefixo(destino, prefixo, trabalho, mes)
            if tabela is None or tabela.empty:
                continue
            datada = tabela.assign(
                mes_do_retrato=mes, disponivel_em=pd.Timestamp(disponivel_em(mes))
            )
            sha = pd.Series([origens[0]["sha256"] if origens else ""] * len(datada))
            gravar_se_mudou(
                _carimbar(datada, sha, agora),
                destino / NOMES / prefixo,
                origens,
                ["cnpj_basico", "tipo_de_nome", "nome_para_busca"],
                carimbos=CARIMBOS,
            )
            for tipo, linhas in tabela["tipo_de_nome"].value_counts().items():
                contagem[str(tipo)] += int(linhas)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    log.info("nomes_pj %s: %s", mes, contagem)
    return contagem


def carregar(
    destino: Path, baixar: Baixar, agora: Callable[[], datetime]
) -> dict[str, int]:
    """Baixa os ZIPs do mês das listas para uma pasta temporária e monta a tabela."""
    mes = mes_das_empresas(destino)
    with tempfile.TemporaryDirectory(dir=destino) as temporaria:
        return montar(destino, baixar(mes, Path(temporaria)), agora())


def _carregar_da_rede(destino: Path) -> dict[str, int]:  # pragma: no cover - rede
    from base.arquivo.cliente_http import ClienteHttp
    from base.arquivo.fontes import arquivos_do_mes
    from scripts import carga_receita_retrato as retrato

    cliente = ClienteHttp()

    def baixar(mes: str, temporaria: Path) -> list[Path]:
        zips = []
        alvos = arquivos_do_mes(cliente, mes, (ZIP_DOS_ESTABELECIMENTOS,))
        for alvo in retrato._sem_os_cortados(alvos):
            caminho = temporaria / retrato._nome_do_zip(alvo)
            retrato._baixar_zip_inteiro(cliente, alvo.url, caminho)
            zips.append(caminho)
        return zips

    return carregar(destino, baixar, lambda: datetime.now(UTC))


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    analisador.add_argument("--destino", type=Path, required=True)
    analisador.add_argument("--ensaio", action="store_true")
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        print(f"mês das listas sem pessoa: {mes_das_empresas(opcoes.destino)}")
        if not opcoes.ensaio:
            print(_carregar_da_rede(opcoes.destino))  # pragma: no cover - rede
        return 0
    except (SemListaDeEmpresas, ErroDeLayout, KeyError, ValueError, OSError) as erro:
        resumo = f"FALHAS: nomes PJ: {type(erro).__name__}: {erro}"
        print(resumo[:TAMANHO_MAXIMO_DO_RESUMO])
        return 1


if __name__ == "__main__":
    sys.exit(main())
