"""Montagem da tabela `ma_candidatos` da base: documentos do IPE que podem anunciar uma operação de M&A.

    python -m scripts.montar_ma_candidatos                    (todos os anos guardados)
    python -m scripts.montar_ma_candidatos --pasta /tmp/base  (outra pasta de saída)

Lê os arquivos anuais do IPE já guardados no acervo (`cvm-hist-ipe`; não baixa nada) e escolhe os
fatos relevantes, comunicados e editais de OPA candidatos (`base/ma_ipe.py`). Saída padrão:
`<TICKERLAB_ACERVO>/base/ma/candidatos/candidatos.parquet`, com manifesto (só regrava o que mudou).
Feita para o servidor de casa (ADR 0031); recusa rodar sem a versão do código (exigência 13 da ADR
0055). Saída 0 tudo certo.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import ma_ipe
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_ma_candidatos")


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
        resumo = ma_ipe.montar(conexao, pasta, datetime.now(UTC))
    log.info("Candidatos de M&A: %s documentos, %s", sum(resumo.values()), resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
