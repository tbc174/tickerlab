"""Monta contagem sem identificação dos movimentos de sócios PF (linha 1104).

    python -m scripts.montar_movimento_socios_pf --cnpj <base do CNPJ> --destino <acervo>/base [--ensaio]

Lê somente vigente/qsa e mudancas/qsa já pseudonimizados e a lista de empresas
sem pessoa do mesmo retrato. Processa uma partição de raiz por vez, sem arquivos
temporários com pessoas. Não lê arquivos restritos, ZIPs, nomes, CPF nem segredos.
Grava só contagens, com manifesto e versões; repetir o retrato não regrava dados
iguais. Freio de disco antes de montar e de cada gravação. Nenhuma carga real
foi executada neste PR; não há agendamento novo.

Roda: manual pela Diretoria; coberto por test_montar_movimento_socios_pf.py.
"""

import argparse
import json
from collections import Counter
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow.parquet as pq

from base import socios_pf
from base.arquivo.coleta import FreioDeDisco, conferir_freio, espaco_do_disco
from base.parquet import gravar_se_mudou, gravar_tabela
from base.porta.duckdb import arquivos_da_tabela
from base.receita_retrato import ErroDeLayout
from scripts.carga_receita_mes import MANIFESTO
from scripts.montar_empresas_pj import ESTABELECIMENTOS
from scripts.montar_historico_do_cnpj import CARIMBOS, _origens, _zips_do_mes
from src.versao_do_codigo import VersaoDesconhecidaError, exigir_versao_do_codigo

COLUNAS_QSA = ["cnpj_basico", "tipo_socio", "id_pessoa"]
COLUNAS_MUDANCAS = [*COLUNAS_QSA, "mes", "tipo"]
# Limites provisórios conservadores do molde PJ, não uma faixa medida de PF.
# O ensaio imprime antes de aplicar a guarda; a Diretoria medirá antes da carga.
MAXIMO_POR_MES = {"socios_pf_entraram": 30_000, "socios_pf_sairam": 10_000}
ORDEM = [socios_pf.EMPRESA, socios_pf.RETRATO]
Resumo = Counter[tuple[str, str]]


@dataclass(frozen=True)
class Retratos:
    """Caminhos e linhagem da série, sem dados individuais."""

    meses: list[str]
    vigente: list[Path]
    mudancas: list[Path]
    listas: dict[str, Path]
    origens: list[dict[str, str]]


def _freio(pasta: Path) -> None:
    conferir_freio(*espaco_do_disco(pasta))


def _ler(arquivos: list[Path], colunas: list[str], prefixo: str) -> pd.DataFrame:
    partes = [
        pd.read_parquet(
            a,
            columns=colunas,
            filters=[
                ("tipo_socio", "==", "2"),
                ("cnpj_basico", ">=", prefixo),
                ("cnpj_basico", "<", prefixo + "~"),
            ],
        )
        for a in arquivos
    ]
    return (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=colunas)
    )


def _conferir_fontes(cnpj: Path, manifesto: dict) -> tuple[list[Path], list[Path]]:
    vigente = arquivos_da_tabela(cnpj / "vigente" / "qsa", "*.parquet")
    if not vigente:
        raise ErroDeLayout("QSA vigente ausente")
    mudancas = []
    for mes, dados in manifesto["meses"].items():
        pasta = cnpj / "mudancas" / "qsa"
        arquivos = arquivos_da_tabela(pasta, f"{mes}.parquet") + arquivos_da_tabela(
            pasta / mes, "*.parquet"
        )
        esperado = dados["mudancas"]["qsa"]
        if sum(pq.ParquetFile(a).metadata.num_rows for a in arquivos) != esperado:
            raise ErroDeLayout("mudanças do QSA incompletas; conferir manifesto")
        mudancas.extend(arquivos)
    return vigente, mudancas


def _listas(destino: Path, mes: str) -> list[Path]:
    arquivos = arquivos_da_tabela(destino / ESTABELECIMENTOS, "*.parquet")
    if not arquivos:
        raise ErroDeLayout("lista sem pessoa ausente; rode montar_empresas_pj")
    for arquivo in arquivos:
        meses = set(pd.read_parquet(arquivo, columns=["mes_do_retrato"]).mes_do_retrato)
        if meses and meses != {mes}:
            raise ErroDeLayout("lista sem pessoa de outro mês; rode montar_empresas_pj")
    return arquivos


def _fontes(cnpj: Path, destino: Path) -> Retratos:
    manifesto = json.loads((cnpj / MANIFESTO).read_text(encoding="utf-8"))
    meses = sorted(manifesto["meses"])
    socios_pf.conferir_meses(meses)
    vigente, mudancas = _conferir_fontes(cnpj, manifesto)
    listas = _listas(destino, meses[-1])
    origens = _origens({m: _zips_do_mes(manifesto, m, "Socios") for m in meses})
    return Retratos(meses, vigente, mudancas, {a.stem: a for a in listas}, origens)


def _contar_prefixo(
    prefixo: str, fontes: Retratos, bruto: Resumo | None
) -> pd.DataFrame:
    raizes = (
        set(
            pd.read_parquet(fontes.listas[prefixo], columns=["cnpj_basico"]).cnpj_basico
        )
        if prefixo in fontes.listas
        else set()
    )
    vigente = _ler(
        [a for a in fontes.vigente if a.stem == prefixo], COLUNAS_QSA, prefixo
    )
    mudancas = _ler(fontes.mudancas, COLUNAS_MUDANCAS, prefixo)
    if bruto is not None:
        _somar(
            bruto,
            socios_pf.contar_movimentos(vigente, mudancas, fontes.meses, raizes, {}),
        )
    return socios_pf.contar_movimentos(vigente, mudancas, fontes.meses, raizes)


def _somar(resumo: Resumo, tabela: pd.DataFrame) -> None:
    for mes, linha in (
        tabela.groupby(socios_pf.RETRATO)[socios_pf.CONTAGENS].sum().iterrows()
    ):
        for coluna, quantidade in linha.items():
            resumo[str(mes), str(coluna)] += int(quantidade)


def _relatar(resumo: Resumo, rotulo: str) -> None:
    for mes in sorted({m for m, _ in resumo}):
        print(
            f"{rotulo} {mes}: entraram={resumo[mes, 'socios_pf_entraram']} "
            f"sairam={resumo[mes, 'socios_pf_sairam']} no_fim={resumo[mes, 'socios_pf_no_fim']}"
        )


def _meses_gravados(pasta: Path) -> set[str]:
    return {
        str(mes)
        for arquivo in arquivos_da_tabela(pasta, "*.parquet")
        for mes in pd.read_parquet(arquivo, columns=[socios_pf.RETRATO])[
            socios_pf.RETRATO
        ].unique()
    }


def _conferir_faixa(resumo: Resumo, primeiro_mes: str, gravados: set[str]) -> None:
    for (mes, coluna), quantidade in sorted(resumo.items()):
        if (
            mes != primeiro_mes
            and mes not in gravados
            and coluna in MAXIMO_POR_MES
            and quantidade > MAXIMO_POR_MES[coluna]
        ):
            print(f"FAIXA: {mes} {coluna}={quantidade} limite={MAXIMO_POR_MES[coluna]}")
            raise ValueError(
                "mês novo fora da faixa; a tabela publicada fica como estava"
            )


def _publicar(trabalho: Path, destino: Path, origens: list[dict[str, str]]) -> None:
    for arquivo in sorted(trabalho.glob("*.parquet")):
        _freio(destino)
        gravar_se_mudou(
            pd.read_parquet(arquivo),
            destino / arquivo.stem,
            origens,
            ORDEM,
            carimbos=CARIMBOS,
        )


def montar(cnpj: Path, destino: Path, agora: datetime, gravar: bool = True) -> int:
    """Monta agregados temporários; só publica depois da guarda mensal, sem chaves PF."""
    versao = exigir_versao_do_codigo()
    _freio(destino)
    fontes = _fontes(cnpj, destino)
    pasta = destino / socios_pf.TABELA
    prefixos = set(fontes.listas) | {
        a.stem for a in arquivos_da_tabela(pasta, "*.parquet")
    }
    resumo: Resumo = Counter(
        {
            (mes, coluna): 0
            for mes in fontes.meses
            if mes not in socios_pf.RETRATOS_COM_DEFEITO
            for coluna in socios_pf.CONTAGENS
        }
    )
    bruto: Resumo | None = (
        Counter(
            {(mes, coluna): 0 for mes in fontes.meses for coluna in socios_pf.CONTAGENS}
        )
        if not gravar
        else None
    )
    total = 0
    # Só agregados no temporário, também com manifesto; o ensaio não grava arquivo.
    with (
        TemporaryDirectory(prefix="movimento-pf-", dir=destino)
        if gravar
        else nullcontext(None)
    ) as trabalho:
        for prefixo in sorted(prefixos):
            tabela = _contar_prefixo(prefixo, fontes, bruto)
            total += len(tabela)
            _somar(resumo, tabela)
            if trabalho is not None:
                _freio(destino)
                gravar_tabela(
                    tabela.assign(
                        montado_em=agora.isoformat(), versao_do_codigo=versao
                    ),
                    Path(trabalho) / prefixo,
                    fontes.origens,
                    ORDEM,
                )
        if bruto is not None:
            _relatar(bruto, "sem_correcao")
        _relatar(resumo, "com_correcao")
        _conferir_faixa(resumo, fontes.meses[0], _meses_gravados(pasta))
        if trabalho is not None:
            _publicar(Path(trabalho), pasta, fontes.origens)
    return total


def main(
    argv: list[str] | None = None,
    agora: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """CLI sem rede; erros não reproduzem valores lidos do QSA."""
    parser = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    parser.add_argument("--cnpj", type=Path, required=True)
    parser.add_argument("--destino", type=Path, required=True)
    parser.add_argument("--ensaio", action="store_true")
    opcoes = parser.parse_args(argv)
    try:
        total = montar(opcoes.cnpj, opcoes.destino, agora(), gravar=not opcoes.ensaio)
    except (
        ErroDeLayout,
        FreioDeDisco,
        VersaoDesconhecidaError,
        KeyError,
        ValueError,
        OSError,
    ):
        print(
            "FALHAS: contagem PF interrompida; conferir versão, disco, esquema, faixa e completude dos retratos"
        )
        return 1
    print(f"movimento_de_socios_pf: {total} linhas agregadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
