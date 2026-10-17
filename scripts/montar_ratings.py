"""Montagem da tabela `ratings` da base com os documentos de rating já baixados (`base/ratings.py`).

    python -m scripts.montar_ratings                    (o que o coletor já trouxe)
    python -m scripts.montar_ratings --pasta /tmp/base  (outra pasta de saída)

Lê os arquivos anuais do IPE (`cvm-hist-ipe`) e os documentos que o coletor guardou no acervo
(`cvm-ipe-rating`; não baixa nada). Uma linha por documento lido, com a situação da extração
(`extraido`, `nao_extraido`, `nao_e_pdf`); o mesmo evento em dois documentos vira uma linha. Saída
padrão: `<TICKERLAB_ACERVO>/base/ratings/ratings.parquet`, com manifesto (só regrava o que mudou).
Feita para o servidor de casa (ADR 0031), depois das rodadas do coletor; recusa rodar sem a versão do
código (exigência 13 da ADR 0055). Saída 0 tudo certo, mesmo sem nenhum documento baixado ainda.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import ratings
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_ratings")


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
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
        resumo = ratings.montar(conexao, pasta, datetime.now(UTC))
    log.info("Ratings: %s documentos lidos, %s", sum(resumo.values()), resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
