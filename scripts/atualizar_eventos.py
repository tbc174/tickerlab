"""Coleta os eventos públicos da CVM e o mapa ticker → CNPJ para o Research.

    python -m scripts.atualizar_eventos            (ano atual; em janeiro, também o anterior)
    python -m scripts.atualizar_eventos --anos 2   (os 2 últimos anos de eventos)

Roda fora do app (no servidor, uma vez por dia); o app só lê o que foi gravado. Usa o banco de
`TICKERLAB_DATABASE_URL` (o mesmo do app) e aplica as migrações antes. Se a CVM falhar, não apaga
nada e sai com erro (o próximo dia tenta de novo).
"""

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from src import eventos as ev
from src.banco.conexao import criar_engine, migrar_para
from src.banco.eventos import gravar_eventos, gravar_tickers
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.eventos")
ANOS_DE_FCA = 4  # o FCA só é reenviado quando algo muda: junta os últimos anos


def baixar(url: str) -> bytes:
    resposta = requests.get(
        url, timeout=180, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    resposta.raise_for_status()
    return resposta.content


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument(
        "--anos", type=int, default=None, help="anos de eventos (1 a 5)"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    anos = opcoes.anos or (2 if hoje.month == 1 else 1)
    anos = max(1, min(anos, 5))
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        fcas = []
        for ano in range(hoje.year - ANOS_DE_FCA + 1, hoje.year + 1):
            try:
                fcas.append(baixar(ev.URL_DO_FCA.format(ano=ano)))
            except requests.HTTPError as erro:
                log.warning("FCA de %s indisponível: %s", ano, erro)
        tickers = ev.ler_tickers_do_fca(fcas)
        with motor.begin() as conexao:
            total = gravar_tickers(conexao, tickers)
        log.info("Mapa ticker → CNPJ: %s códigos", total)
        for ano in range(hoje.year - anos + 1, hoje.year + 1):
            tabela = ev.ler_ipe(baixar(ev.URL_DO_IPE.format(ano=ano)))
            with motor.begin() as conexao:
                novos, atualizados = gravar_eventos(conexao, tabela)
            log.info(
                "IPE %s: %s eventos lidos, %s novos, %s atualizados",
                ano,
                len(tabela),
                novos,
                atualizados,
            )
    except (requests.RequestException, ValueError) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
