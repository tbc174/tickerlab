"""Carga do informe mensal dos Fiagro da CVM para a base: a tabela `cvm_fiagro` de `base/cvm_fiagro.py`.

    python -m scripts.carga_cvm_fiagro                    (todos os ZIPs guardados)
    python -m scripts.carga_cvm_fiagro --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_cvm_fiagro --refazer          (relê mesmo sem ZIP novo: código novo)

Lê os ZIPs mensais que o arquivista já guardou no acervo (fonte `cvm-fiagro`; não baixa nada) e grava
`<TICKERLAB_ACERVO>/base/cvm_fiagro/informe.parquet`: uma linha por classe, mês e versão do informe. Só
classe com CNPJ de dígito certo entra; contato, administrador e gestor por nome ficam de fora (ADR 0075).
Feita para o servidor de casa (ADR 0031), depois do arquivista; recusa rodar sem a versão do código
(exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhum ZIP da CVM guardado.

Roda: manual no servidor de casa (python -m scripts.carga_cvm_fiagro), uma vez por montagem autorizada; citado em cvm_fiagro.py.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import cvm_fiagro
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_cvm_fiagro")


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
        resumo = cvm_fiagro.montar(
            conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
        )
    if not resumo:
        log.warning("nenhum ZIP do informe dos Fiagro guardado no acervo")
        return 1
    for arquivo, contagem in resumo.items():
        log.info("%s: %s", arquivo, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
