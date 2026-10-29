"""Carga das licenças e registros por CNPJ para a base: as seis tabelas de `base/licencas.py`.

    python -m scripts.carga_licencas                    (todos os retratos guardados)
    python -m scripts.carga_licencas --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_licencas --refazer          (relê mesmo sem retrato novo: código novo)

Lê os cadastros da Anvisa, ANTT (RNTRC), MAPA (SIPEAGRO), Anatel, ANM e Ancine que o arquivista já
guardou no acervo (não baixa nada). Só CNPJ inteiro de dígito certo entra; nome e CPF nunca (ADR
0075). Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/<cadastro>.parquet`. Feita para o servidor de
casa (ADR 0031), todo dia depois do arquivista; recusa rodar sem a versão do código (exigência 13 da
ADR 0055). Saída 0 tudo certo; 1 nenhum cadastro de licença guardado.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import licencas
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_licencas")


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
        resumo = licencas.montar(
            conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
        )
    if not resumo:
        log.warning("nenhum cadastro de licença guardado no acervo")
        return 1
    for cadastro, contagem in resumo.items():
        log.info("%s: %s", cadastro, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
