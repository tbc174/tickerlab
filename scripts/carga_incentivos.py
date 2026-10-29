"""Carga dos incentivos por CNPJ para a base: as três tabelas de `base/incentivos.py`.

    python -m scripts.carga_incentivos                    (todos os arquivos guardados)
    python -m scripts.carga_incentivos --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_incentivos --refazer          (relê mesmo sem arquivo novo: código novo)

Lê o REIDI (MME), os beneficiários da CDE (ANEEL) e o RDE-IED (BC) que o arquivista já guardou no
acervo (não baixa nada). Só CNPJ inteiro de dígito certo entra (no RDE, a raiz); nome e CPF nunca
(ADR 0075). Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/<arquivo>.parquet`. Feita para o
servidor de casa (ADR 0031), todo mês depois do arquivista; recusa rodar sem a versão do código
(exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhum arquivo de incentivo guardado.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import incentivos
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_incentivos")


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
        resumo = incentivos.montar(
            conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
        )
    if not resumo:
        log.warning("nenhum arquivo de incentivo guardado no acervo")
        return 1
    for arquivo, contagem in resumo.items():
        log.info("%s: %s", arquivo, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
