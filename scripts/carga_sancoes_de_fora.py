"""Carga das sanções internacionais de entidades para a base: a tabela `sancoes_de_fora`
(`base/sancoes_de_fora.py`).

    python -m scripts.carga_sancoes_de_fora                    (todos os arquivos guardados)
    python -m scripts.carga_sancoes_de_fora --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_sancoes_de_fora --refazer          (relê mesmo sem arquivo novo: código novo)

Lê os XML da OFAC, da União Europeia e do Reino Unido que o arquivista já guardou no acervo (não baixa
nada). Só entidade entra; pessoa física, navio, aeronave e registro sem tipo ficam fora. Saída padrão:
`<TICKERLAB_ACERVO>/base/sancoes_de_fora/<cadastro>.parquet`. Feita para o servidor de casa (ADR 0031),
depois do arquivista; recusa rodar sem a versão do código (exigência 13 da ADR 0055). Saída 0 tudo
certo; 1 nenhum arquivo de lista guardado.

Roda: manual (python -m scripts.carga_sancoes_de_fora), no servidor de casa, até entrar no
carga-conferencias.sh (agendar é passo da Diretoria; a conferir na fila).
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import sancoes_de_fora
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_sancoes_de_fora")


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
        resumo = sancoes_de_fora.montar(
            conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
        )
    if not resumo:
        log.warning("nenhum arquivo de lista de sanção de fora guardado no acervo")
        return 1
    for cadastro, contagem in resumo.items():
        log.info("%s: %s", cadastro, contagem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
