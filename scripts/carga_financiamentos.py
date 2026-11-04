"""Carga dos financiamentos por CNPJ para a base: uma tabela por banco (`base/financiamentos.py`).

    python -m scripts.carga_financiamentos                    (todos os arquivos guardados)
    python -m scripts.carga_financiamentos --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_financiamentos --refazer          (relê mesmo sem arquivo novo: código novo)

Lê as operações não automáticas do BNDES e a planilha de contratações da Finep que o arquivista já
guardou no acervo (não baixa nada). Só crédito reembolsável e CNPJ inteiro de dígito certo; nome do
cliente, título e resumo nunca (ADR 0075). Saída padrão: `<TICKERLAB_ACERVO>/base/financiamentos_bndes/
bndes.parquet` e `financiamentos_finep/finep.parquet`. Feita para o servidor de casa (ADR 0031), todo mês depois do
arquivista; recusa rodar sem a versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1
nenhum arquivo de financiamento guardado.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import financiamentos
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_financiamentos")


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
        resumo = financiamentos.montar(
            conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
        )
    if not resumo:
        log.warning("nenhum arquivo de financiamento guardado no acervo")
        return 1
    for banco, contagem in resumo.items():
        log.info("%s: %s", banco, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
