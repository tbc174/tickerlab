"""Carga das empresas do INPI (marcas, patentes, desenhos e programas) e dos inidôneos do TCU para a base:
as tabelas `inpi_marcas_titulares`, `inpi_patentes_depositantes`, `inpi_desenhos_depositantes`,
`inpi_programas_titulares` (`base/inpi_titulares.py`) e `tcu_inidoneos` (`base/inidoneos_tcu.py`), linha 904.

    python -m scripts.carga_inpi_e_tcu                    (todos os retratos guardados)
    python -m scripts.carga_inpi_e_tcu --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_inpi_e_tcu --refazer          (relê mesmo sem retrato novo: código novo)

Lê os arquivos de titulares do INPI (`inpi-marcas`, `inpi-patentes-partes`, `inpi-desenhos`,
`inpi-programas`) e a lista do TCU (`tcu-inidoneos`) que o arquivista já guardou no acervo (não baixa
nada). Só pessoa jurídica com CNPJ de dígito certo entra; nome, CPF, inventor e procurador nunca (ADR 0075).
Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/{titulares,inidoneos}.parquet`. Os arquivos de marcas têm
milhões de linhas: roda no servidor de casa (ADR 0031), com a memória dele, e recusa rodar sem a versão do
código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhum arquivo dessas fontes guardado.

Roda: manual, no servidor de casa; sem agendamento registrado em 13/11/2026 (o cron só entra com o pode da Diretoria).
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import inidoneos_tcu, inpi_titulares
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_inpi_e_tcu")


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
    resumo: dict[str, dict[str, int]] = {}
    with obter_engine().connect() as conexao:
        for modulo in (inpi_titulares, inidoneos_tcu):
            for cadastro, contagem in modulo.montar(
                conexao, pasta, agora, refazer=opcoes.refazer
            ).items():
                resumo[f"{modulo.__name__}:{cadastro}"] = contagem
    if not resumo:
        log.warning("nenhum arquivo do INPI ou do TCU guardado no acervo")
        return 1
    for cadastro, contagem in resumo.items():
        log.info("%s: %s", cadastro, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
