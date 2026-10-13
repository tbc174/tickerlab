"""Coleta da SEC para as empresas dos EUA: eventos, balanços (fundamentos) e Form 4.

    python -m scripts.atualizar_eventos_sec            (eventos de 400 dias, Form 4 de 90)
    python -m scripts.atualizar_eventos_sec --dias 730 --dias-form4 400 --max-form4 0

Form 4: cada um é uma consulta a mais, então a coleta lê só os que ainda não leu (com ou sem
negociação), no máximo `--max-form4` por vez (0 = sem limite; a primeira carga leva horas).

Empresas: as ações dos EUA do catálogo do app (o S&P 500) e as buscadas na hora por alguém no
app (R4, `tickers_sob_demanda`). A coleta de cada empresa está em `src/coleta_sec.py`. Regras de
acesso da SEC: cada consulta diz quem é e um e-mail de contato (`TICKERLAB_CONTATO`, no .env, fora
do Git) e no máximo 10 consultas por segundo (aqui, ~8). Sem o contato, não consulta nada e sai
com erro. Uma empresa que falhar é pulada; as outras seguem. Não apaga nada.
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa

from src import catalogo
from src import coleta_sec as coleta
from src import eventos_sec as sec
from src.banco import sob_demanda
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.eventos import ORIGEM_SEC, gravar_tickers
from src.configuracao import contato, url_do_banco

log = logging.getLogger("tickerlab.sec")
PAUSA_ENTRE_CONSULTAS = coleta.PAUSA_ENTRE_CONSULTAS
DIAS_PADRAO = 400
DIAS_DO_FORM4 = 90
MAX_FORM4 = 3_000  # por execução: ~6 min a 8 consultas por segundo
SEM_CONTATO = 2  # código de saída: falta configurar o e-mail


def _baixar_da_fonte(url: str, agente: str) -> bytes:
    return coleta.baixar_da_sec(url, agente)


# cada arquivo baixado fica no registro de coletas (Radar, PR 1)
baixar = com_registro("sec-eventos", _baixar_da_fonte)


def tickers_dos_eua() -> set[str]:
    tabela = catalogo.carregar()
    return set(tabela.index[tabela["bolsa"] == "EUA"])


def _opcoes(argv: list[str] | None) -> argparse.Namespace:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--dias", type=int, default=DIAS_PADRAO, help="janela em dias"
    )
    argumentos.add_argument(
        "--dias-form4", type=int, default=DIAS_DO_FORM4, help="janela dos Form 4"
    )
    argumentos.add_argument(
        "--max-form4",
        type=int,
        default=MAX_FORM4,
        help="Form 4 por vez (0 = sem limite)",
    )
    return argumentos.parse_args(argv)


def _coletar_todas(
    motor: sa.Engine,
    cliente: coleta.ClienteSec,
    ciks: list[int],
    opcoes: argparse.Namespace,
) -> None:
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    restantes = opcoes.max_form4 if opcoes.max_form4 > 0 else sys.maxsize
    novos = baixados = falhas = 0
    for cik in ciks:
        janelas = coleta.Janelas(
            hoje - timedelta(days=opcoes.dias),
            hoje - timedelta(days=opcoes.dias_form4),
            restantes,
        )
        try:
            eventos, lidos = coleta.coletar_empresa(motor, cliente, cik, janelas, hoje)
        except coleta.ERROS_DE_UMA_EMPRESA as erro:
            falhas += 1
            log.warning(
                "%s pulada: %s", sec.cik_como_chave(cik), erro.__class__.__name__
            )
            continue
        novos, baixados, restantes = (
            novos + eventos,
            baixados + lidos,
            restantes - lidos,
        )
    log.info(
        "SEC: %s empresas, %s eventos novos, %s Form 4 lidos, %s falhas",
        len(ciks), novos, baixados, falhas,
    )  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    opcoes = _opcoes(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    email = contato()
    if email is None:
        log.error(
            "Falta TICKERLAB_CONTATO (a SEC exige um e-mail de contato): nada consultado."
        )
        return SEM_CONTATO
    # o transporte chama `baixar` deste módulo na hora (os testes trocam essa função)
    cliente = coleta.ClienteSec(
        f"TickerLab {email}",
        PAUSA_ENTRE_CONSULTAS,
        lambda url, agente: baixar(url, agente),
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            pedidos = tickers_dos_eua() | sob_demanda.tickers(conexao)
        mapa = sec.ler_tickers(cliente.baixar(sec.URL_DOS_TICKERS), pedidos)
        with motor.begin() as conexao:
            log.info(
                "Mapa ticker → CIK: %s empresas",
                gravar_tickers(conexao, mapa, origem=ORIGEM_SEC),
            )
        ciks = sorted({int(c.removeprefix(sec.PREFIXO_DO_CIK)) for c in mapa["cnpj"]})
        _coletar_todas(motor, cliente, ciks, opcoes)
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
