"""Carga noturna do texto das notas explicativas da DFP, do PDF do ENET (linha 135 da fila).

    python -m scripts.carga_enet_notas                          (2010 até o ano atual, até as 6h)
    python -m scripts.carga_enet_notas --desde 2024 --parar-as 05:30

Roda no servidor de casa, de madrugada (ADR 0031), no mesmo molde da `scripts/carga_enet.py`: um
pacote por vez, com pausa, do DFP mais novo para o mais velho; o que já está guardado é pulado e o que
falhou fica para a noite seguinte. Diferente da outra carga, baixa **todas as versões** da DFP (cada
uma é um documento, com a própria entrega) e guarda só o texto por página, sem o PDF
(`base/enet_notas.py`). O pacote tem de 13 a 33 MB: a primeira carga completa é pesada, por isso a
janela da madrugada e o `--desde`.

Saída 0 tudo certo; 1 se nada veio e algo falhou (o Kuma avisa).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime

import requests
import sqlalchemy as sa

from base.enet_coleta import Baixador, baixar_em_fila
from base.enet_notas import guardar_notas, ja_guardadas
from scripts.carga_enet import (
    PARAR_AS,
    PRIMEIRO_ANO,
    ResumoDaCarga,
    _avisar_que_nada_veio,
    _indice,
    agora,
    fim_da_janela,
)
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.carga_enet_notas")
DOCUMENTO = "DFP"


def _carregar_ano(
    motor: sa.Engine, ano: int, baixador: Baixador, fim: datetime
) -> tuple[ResumoDaCarga, bool]:
    """Baixa o texto do que falta de um ano. Devolve o resumo e se a janela acabou."""
    resumo = ResumoDaCarga()
    indice = _indice(motor, DOCUMENTO, ano)
    if indice is None:
        log.info("%s %s não existe na CVM: pulado", DOCUMENTO, ano)
        return resumo, False
    with motor.connect() as conexao:
        feitos = ja_guardadas(conexao)

    def ao_baixar(link: str, pacote: bytes) -> None:
        with motor.begin() as conexao:
            guardar_notas(conexao, link, pacote, datetime.now(UTC))

    resultado = baixar_em_fila(
        indice["link"].dropna().drop_duplicates(),
        baixador.baixar,
        feitos,
        ao_baixar,
        continuar=lambda: agora() < fim,
    )
    for link, erro in resultado.falhas.items():
        log.warning("ENET: %s não veio (%s); fica para a próxima noite", link, erro)
    resumo.baixadas = len(resultado.baixados)
    resumo.falhas_de_formato = len(resultado.falhas_de_formato)
    resumo.falhas_de_rede = len(resultado.falhas) - len(resultado.falhas_de_formato)
    log.info(
        "%s %s: %s baixadas, %s já estavam, %s falharam",
        DOCUMENTO, ano, resumo.baixadas, resultado.pulados, len(resultado.falhas),
    )  # fmt: skip
    return resumo, resultado.interrompida


def carregar(motor: sa.Engine, desde: int, ate: int, parar_as: str) -> ResumoDaCarga:
    """Baixa o que falta, do ano mais novo ao mais velho."""
    fim = fim_da_janela(agora(), parar_as)
    baixador = Baixador()
    total = ResumoDaCarga()
    for ano in range(ate, desde - 1, -1):
        resumo, interrompida = _carregar_ano(motor, ano, baixador, fim)
        total.baixadas += resumo.baixadas
        total.falhas_de_formato += resumo.falhas_de_formato
        total.falhas_de_rede += resumo.falhas_de_rede
        if interrompida:
            log.info(
                "Janela acabou (%s): %s baixadas nesta noite", parar_as, total.baixadas
            )
            return total
    log.info("Carga em dia: %s baixadas nesta noite", total.baixadas)
    return total


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    argumentos.add_argument("--ate", type=int, help="o ano mais novo (padrão: o atual)")
    argumentos.add_argument(
        "--parar-as", default=PARAR_AS, help="hora de não começar mais"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        resumo = carregar(
            motor, opcoes.desde, opcoes.ate or agora().year, opcoes.parar_as
        )
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Carga interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    if resumo.falhas and not resumo.baixadas:
        _avisar_que_nada_veio(resumo)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
