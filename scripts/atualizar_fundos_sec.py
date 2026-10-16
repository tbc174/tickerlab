"""Coleta o 13F da SEC: quem tem cada ação dos EUA entre os grandes gestores (Research R3).

    python -m scripts.atualizar_fundos_sec              (a base trimestral mais nova)
    python -m scripts.atualizar_fundos_sec --bases 3    (primeira carga: as 3 mais novas)

Baixa a lista de bases da página da SEC e lê só as que ainda não leu (cada uma tem ~100 MB e
sai por trimestre). O código CUSIP vira ticker pelos arquivos de "falhas de entrega" da SEC dos
últimos meses. Exige `TICKERLAB_CONTATO`, como as outras coletas da SEC.
"""

import argparse
import logging
import sys
import time

import requests
import sqlalchemy as sa

from src import catalogo, rede
from src import fundos_sec as f13
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.detentores import gravar_competencia
from src.banco.negociacoes import ja_lidos, marcar_como_lidos
from src.configuracao import contato, url_do_banco
from src.detentores import informantes

log = logging.getLogger("tickerlab.13f")
PAUSA_ENTRE_CONSULTAS = 0.125
BASES_PADRAO = 1
ARQUIVOS_DE_FALHAS = 6  # ~3 meses (dois por mês): cobre quase todo o S&P 500
LIDAS = "sec_13f_base"  # marca das bases já lidas em `documentos_lidos`
SEM_CONTATO = 2


def _baixar_da_fonte(url: str, agente: str) -> bytes:
    time.sleep(PAUSA_ENTRE_CONSULTAS)
    resposta = rede.obter(
        url,
        timeout=600,
        headers={"User-Agent": agente, "Accept-Encoding": "gzip, deflate"},
    )
    resposta.raise_for_status()
    return resposta.content


# cada arquivo baixado fica no registro de coletas (Radar, PR 1)
baixar = com_registro("sec-13f", _baixar_da_fonte)


def nome_da_base(link: str) -> str:
    """`.../01jun2026-31aug2026_form13f.zip` → `01jun2026-31aug2026_form13f.zip` (cabe no banco)."""
    return link.rsplit("/", 1)[-1][:60]


def tickers_dos_eua() -> set[str]:
    tabela = catalogo.carregar()
    return set(tabela.index[tabela["bolsa"] == "EUA"])


def mapa_de_cusips(agente: str) -> dict[str, str]:
    pagina = baixar(f13.URL_DA_PAGINA_DAS_FALHAS, agente).decode("utf-8", "replace")
    links = f13.links_da_pagina(pagina, "cnsfails")[:ARQUIVOS_DE_FALHAS]
    return f13.ler_mapa_de_cusips(
        (baixar(link, agente) for link in links), tickers_dos_eua()
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--bases", type=int, default=BASES_PADRAO, help="bases trimestrais"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    email = contato()
    if email is None:
        log.error(
            "Falta TICKERLAB_CONTATO (a SEC exige um e-mail de contato): nada consultado."
        )
        return SEM_CONTATO
    agente = f"TickerLab {email}"
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        pagina = baixar(f13.URL_DA_PAGINA_DO_13F, agente).decode("utf-8", "replace")
        bases = f13.links_da_pagina(pagina, "form13f")[: max(1, opcoes.bases)]
        with motor.connect() as conexao:
            lidas = ja_lidos(conexao, LIDAS, [nome_da_base(b) for b in bases])
        novas = [b for b in bases if nome_da_base(b) not in lidas]
        if not novas:
            log.info("13F: nenhuma base nova")
            return 0
        mapa = mapa_de_cusips(agente)
        log.info("CUSIP → ticker: %s ações", len(mapa))
        for base in novas:
            conteudo = baixar(base, agente)
            competencia = f13.trimestre_da_base(conteudo)
            posicoes = f13.ler_posicoes(conteudo, competencia, mapa)
            del conteudo  # ~100 MB: libera antes de gravar
            with motor.begin() as conexao:
                acoes = gravar_competencia(
                    conexao,
                    f13.resumir(posicoes),
                    f13.maiores(posicoes),
                    informantes(posicoes),
                )
                marcar_como_lidos(conexao, LIDAS, [nome_da_base(base)])
            log.info(
                "13F %s (%s): %s posições, %s ações",
                nome_da_base(base),
                competencia,
                len(posicoes),
                acoes,
            )
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        sa.exc.SQLAlchemyError,
    ) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
