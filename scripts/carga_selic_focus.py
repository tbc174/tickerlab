"""Carga da tabela `bcb_selic_focus` (meta da Selic e Focus Selic anual) a partir do que o arquivista guardou.

Lê os originais de `bcb-sgs-selic-meta` e `bcb-focus-selic-anual` (`base/arquivo/lote_selic.py`), monta o
mesmo quadro de observações que o banco de produção guarda e grava `<acervo>/base/bcb_selic_focus/`.
Não baixa nada. Roda no servidor de casa (`carga-serie4.sh selic-focus`).

Roda: manual (python -m scripts.carga_selic_focus); sem uso registrado em 05/11/2026.
"""

import argparse
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import bcb_selic_focus
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("carga_selic_focus")

FONTE_DA_META = "bcb-sgs-selic-meta"
FONTE_DO_FOCUS = "bcb-focus-selic-anual"
LEITORES: dict[str, Callable[[bytes, datetime], pd.DataFrame]] = {
    FONTE_DA_META: bcb_selic_focus.observacoes_da_meta,
    FONTE_DO_FOCUS: bcb_selic_focus.observacoes_do_focus,
}


def reunir_observacoes(conexao: sa.Connection) -> pd.DataFrame:
    """Todas as safras guardadas das duas fontes, num quadro só (uma linha por safra)."""
    partes = []
    for fonte, ler in LEITORES.items():
        for linha in originais_mais_recentes(conexao, fonte):
            conteudo = acervo.ler_original(linha.caminho_do_original)
            if conteudo is None:
                raise FileNotFoundError(f"original fora do acervo: {linha.url}")
            partes.append(ler(conteudo, linha.baixado_em))
    if not partes:
        return pd.DataFrame(columns=bcb_selic_focus.COLUNAS_DAS_OBSERVACOES)
    quadro = pd.concat(partes, ignore_index=True)
    return quadro.sort_values("registrado_em").drop_duplicates(
        ["serie", "referencia", "divulgado_em"], keep="last"
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    base = opcoes.base or (None if raiz is None else raiz / "base")
    if base is None:
        argumentos.error("acervo desligado: informe --base")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            observacoes = reunir_observacoes(conexao)
    finally:
        motor.dispose()
    linhas = bcb_selic_focus.gravar(observacoes, base, datetime.now(UTC))
    log.info("bcb_selic_focus: %d linhas", linhas)
    return 0 if linhas else 1


if __name__ == "__main__":
    sys.exit(main())
