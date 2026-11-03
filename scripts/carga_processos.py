"""Carga dos processos judiciais por CNPJ para a base: as tabelas `processos_comunicacoes` e
`processos_partes` (`base/processos.py`).

    python -m scripts.carga_processos                    (todas as consultas guardadas)
    python -m scripts.carga_processos --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_processos --refazer          (relê mesmo sem consulta nova: código novo)

Lê as consultas do DJEN por companhia (`djen-partes`) e o cadastro da CVM que o arquivista já guardou
no acervo (não baixa nada). Nome de pessoa física nunca entra na tabela. Saída padrão:
`<TICKERLAB_ACERVO>/base/processos_comunicacoes/djen.parquet` e `.../processos_partes/djen.parquet`.
Feita para o servidor de casa (ADR 0031), toda semana depois do arquivista; recusa rodar sem a versão
do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhuma consulta do DJEN guardada.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import processos
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_processos")


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
        resumo = processos.montar(
            conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
        )
    if not resumo:
        log.warning("nenhuma consulta do DJEN guardada no acervo")
        return 1
    log.info("processos: %s", resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
