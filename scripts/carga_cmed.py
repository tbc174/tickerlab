"""Carga dos preços máximos da CMED para a base: a tabela `cmed_precos` de `base/cmed.py`.

    python -m scripts.carga_cmed                    (todos os retratos guardados)
    python -m scripts.carga_cmed --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_cmed --refazer          (relê mesmo sem retrato novo: código novo)

Lê as duas listas da CMED (consumidor e governo) que o arquivista já guardou no acervo (não baixa
nada). Só CNPJ inteiro de dígito certo entra; o nome do laboratório nem chega ao acervo (ADR 0075).
Saída padrão: `<TICKERLAB_ACERVO>/base/cmed_precos/<lista>.parquet`; depois, se os medicamentos de
`anvisa_registros` já estiverem montados, diz quantas apresentações acham o produto registrado. Feita
para o servidor de casa (ADR 0031), depois do arquivista; recusa rodar sem a versão do código
(exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhuma lista da CMED guardada.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import cmed, licencas
from base.arquivo.fontes import ARQUIVOS_DA_CMED
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_cmed")


def resumo_da_ponte(pasta: Path) -> dict[str, dict[str, int]]:
    """A `cmed.resumo_da_ponte` das listas gravadas; vazio sem os medicamentos montados na `pasta`."""
    cadastro = licencas.CADASTROS["medicamentos"]
    medicamentos = pasta / cadastro.tabela / f"{cadastro.nome}.parquet"
    if not medicamentos.exists():
        return {}
    listas = {
        lista: pd.read_parquet(caminho)
        for lista in ARQUIVOS_DA_CMED
        if (caminho := pasta / cmed.TABELA / f"{lista}.parquet").exists()
    }
    return cmed.resumo_da_ponte(listas, pd.read_parquet(medicamentos))


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--refazer", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    with obter_engine().connect() as conexao:
        resumo = cmed.montar(conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer)
    if not resumo:
        log.warning("nenhuma lista da CMED guardada no acervo")
        return 1
    for lista, contagem in resumo.items():
        log.info("%s: %s", lista, contagem)
    for lista, ligadas in resumo_da_ponte(pasta).items():
        log.info("ponte %s: %s", lista, ligadas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
