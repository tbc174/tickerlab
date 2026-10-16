"""Coleta a carteira mensal dos fundos na CVM (CDA): quem tem cada ação da B3 (Research R3).

    python -m scripts.atualizar_fundos_cvm             (os 4 meses mais recentes)
    python -m scripts.atualizar_fundos_cvm --meses 12  (primeira carga)

Roda fora do app (no servidor, uma vez por dia); o app só lê. O arquivo de um mês sai cerca de 40
dias depois e é refeito quando fundos atrasados entregam, por isso os meses recentes são lidos de
novo a cada coleta (o mais novo substitui o guardado). Mês que ainda não existe é pulado.
"""

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa

from src import fundos_cvm as cda
from src import rede
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.detentores import gravar_competencia
from src.configuracao import url_do_banco
from src.detentores import informantes

log = logging.getLogger("tickerlab.fundos")
MESES_PADRAO = 4
MAX_MESES = 24
NAO_ENCONTRADO = 404


def _baixar_da_fonte(url: str) -> bytes | None:
    """O arquivo da CVM, ou None se ele ainda não existe (404)."""
    resposta = rede.obter(
        url, timeout=300, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


# cada arquivo baixado fica no registro de coletas (Radar, PR 1)
baixar = com_registro("cvm-cda", _baixar_da_fonte)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--meses", type=int, default=MESES_PADRAO, help=f"meses (1 a {MAX_MESES})"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    meses = cda.meses_recentes(hoje, max(1, min(opcoes.meses, MAX_MESES)))
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        for ano, mes in meses:
            conteudo = baixar(cda.URL_DO_CDA.format(ano=ano, mes=mes))
            if conteudo is None:
                log.info("CDA %s/%02d ainda não existe na CVM: pulado", ano, mes)
                continue
            posicoes = cda.ler_posicoes(conteudo)
            with motor.begin() as conexao:
                acoes = gravar_competencia(
                    conexao,
                    cda.resumir(posicoes),
                    cda.maiores(posicoes),
                    informantes(posicoes),
                )
            log.info(
                "CDA %s/%02d: %s posições, %s ações", ano, mes, len(posicoes), acoes
            )
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
