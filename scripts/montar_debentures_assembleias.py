"""Montagem da tabela `debentures_assembleias` da base (`base/debentures.py`, modelo 18, PR 1).

    python -m scripts.montar_debentures_assembleias                    (pasta da base no acervo)
    python -m scripts.montar_debentures_assembleias --pasta /tmp/base  (outra pasta de saída)

Lê os arquivos anuais do IPE já guardados (`cvm-hist-ipe`; não baixa nada) e grava uma linha por
assembleia de debenturistas, aviso aos debenturistas e notificação do agente fiduciário, com os temas
lidos do assunto. Saída padrão: `<TICKERLAB_ACERVO>/base/debentures_assembleias/
debentures_assembleias.parquet`, com manifesto (só regrava o que mudou). Feita para o servidor de casa
(ADR 0031); recusa rodar sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import debentures
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_debentures_assembleias")


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
        resumo = debentures.montar(conexao, pasta, datetime.now(UTC))
    log.info("Assembleias de debenturistas: %s", resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
