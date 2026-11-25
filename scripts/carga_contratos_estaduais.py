"""Carga dos contratos, sanções e fornecedores dos estados por CNPJ para a base: as tabelas de `base/contratos_estaduais.py`.

    python -m scripts.carga_contratos_estaduais                    (todos os arquivos guardados)
    python -m scripts.carga_contratos_estaduais --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_contratos_estaduais --refazer          (relê mesmo sem arquivo novo: código novo)

Lê o que o arquivista já guardou dos estados (lote 1: o SIGA do RJ; não baixa nada). Só CNPJ inteiro de dígito
certo entra; nome do fornecedor, texto livre e CPF nunca (ADR 0075). Saída padrão:
`<TICKERLAB_ACERVO>/base/<tabela>/<arquivo>.parquet` de `rj_contratos`, `rj_sancoes_fornecedores` e
`rj_fornecedores`. Feita para o servidor de casa (ADR 0031), depois do arquivista; recusa rodar sem a versão do
código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhum arquivo estadual guardado.

Roda: manual (python -m scripts.carga_contratos_estaduais); ainda sem cron de casa: pedido à Diretoria pela fila
(linha 1075, Emenda 4 da ADR 0101); ver dicionario-da-base.md; citado em dicionario.py.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import contratos_estaduais
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_contratos_estaduais")


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
        resumo = contratos_estaduais.montar(
            conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
        )
    if not resumo:
        log.warning("nenhum arquivo estadual de contratos guardado no acervo")
        return 1
    for arquivo, contagem in resumo.items():
        log.info("%s: %s", arquivo, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
