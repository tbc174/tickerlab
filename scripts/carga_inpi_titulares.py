"""Carga das empresas do INPI (marcas, patentes, desenhos e programas) para a base: as tabelas
`inpi_marcas_titulares`, `inpi_patentes_depositantes`, `inpi_desenhos_depositantes` e
`inpi_programas_titulares` (`base/inpi_titulares.py`), linha 904 (lote 2).

    python -m scripts.carga_inpi_titulares                    (todos os retratos guardados)
    python -m scripts.carga_inpi_titulares --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_inpi_titulares --refazer          (relê mesmo sem retrato novo: código novo)

Lê os arquivos de titulares do INPI (`inpi-marcas`, `inpi-patentes-partes`, `inpi-desenhos`,
`inpi-programas`) que o arquivista já guardou no acervo (não baixa nada). Só pessoa jurídica com CNPJ de dígito certo entra; nome, CPF, inventor e procurador nunca (ADR 0075).
Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/titulares.parquet`. Os arquivos de marcas têm
milhões de linhas: roda no servidor de casa (ADR 0031), com a memória dele, e recusa rodar sem a versão do
código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhum arquivo dessas fontes guardado.

Roda: manual, no servidor de casa; sem agendamento registrado em 13/11/2026 (o cron só entra com o pode da Diretoria).
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import inpi_titulares
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_inpi_titulares")


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
    agora = datetime.now(UTC)
    with obter_engine().connect() as conexao:
        resumo = inpi_titulares.montar(conexao, pasta, agora, refazer=opcoes.refazer)
    if not resumo:
        log.warning("nenhum arquivo de titulares do INPI guardado no acervo")
        return 1
    for cadastro, contagem in resumo.items():
        log.info("%s: %s", cadastro, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
