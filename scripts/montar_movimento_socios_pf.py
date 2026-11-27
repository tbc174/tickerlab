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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from base import socios_pf
from base.arquivo.coleta import FreioDeDisco, conferir_freio, espaco_do_disco
from base.parquet import gravar_se_mudou
from base.porta.duckdb import arquivos_da_tabela
from base.receita_retrato import ErroDeLayout
from scripts.carga_receita_mes import MANIFESTO
from scripts.montar_empresas_pj import ESTABELECIMENTOS
from scripts.montar_historico_do_cnpj import CARIMBOS, _origens, _zips_do_mes
from src.versao_do_codigo import versao_do_codigo

COLUNAS_QSA = ["cnpj_basico", "tipo_socio", "id_pessoa"]
COLUNAS_MUDANCAS = [*COLUNAS_QSA, "mes", "tipo"]


def _freio(pasta: Path) -> None:
    while not pasta.exists():
        pasta = pasta.parent
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


def montar(cnpj: Path, destino: Path, agora: datetime, gravar: bool = True) -> int:
    """Monta por prefixo; devolve somente o número de linhas agregadas, nunca chaves PF."""
    _freio(destino)
    manifesto = json.loads((cnpj / MANIFESTO).read_text(encoding="utf-8"))
    meses = sorted(manifesto["meses"])
    socios_pf.conferir_meses(meses)
    vigente, mudancas = _conferir_fontes(cnpj, manifesto)
    listas = _listas(destino, meses[-1])
    pasta = destino / socios_pf.TABELA
    por_prefixo = {a.stem: a for a in listas}
    # Regrava vazias as partições que deixaram de ter empresas permitidas.
    prefixos = set(por_prefixo) | {
        a.stem for a in arquivos_da_tabela(pasta, "*.parquet")
    }
    origens = _origens({m: _zips_do_mes(manifesto, m, "Socios") for m in meses})
    total = 0
    for prefixo in sorted(prefixos):
        raizes = (
            set(
                pd.read_parquet(
                    por_prefixo[prefixo], columns=["cnpj_basico"]
                ).cnpj_basico
            )
            if prefixo in por_prefixo
            else set()
        )
        tabela = socios_pf.contar_movimentos(
            _ler([a for a in vigente if a.stem == prefixo], COLUNAS_QSA, prefixo),
            _ler(mudancas, COLUNAS_MUDANCAS, prefixo),
            meses,
            raizes,
        )
        total += len(tabela)
        if gravar:
            _freio(destino)
            gravar_se_mudou(
                tabela.assign(
                    montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
                ),
                pasta / prefixo,
                origens,
                [socios_pf.EMPRESA, socios_pf.RETRATO],
                carimbos=CARIMBOS,
            )
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
    except (ErroDeLayout, FreioDeDisco, KeyError, ValueError, OSError):
        print(
            "FALHAS: contagem PF interrompida; conferir disco, esquema e completude dos retratos"
        )
        return 1
    print(f"movimento_de_socios_pf: {total} linhas agregadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
