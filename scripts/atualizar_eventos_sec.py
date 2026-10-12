"""Coleta da SEC para as empresas dos EUA: eventos, balanços (fundamentos) e Form 4.

    python -m scripts.atualizar_eventos_sec            (eventos de 400 dias, Form 4 de 90)
    python -m scripts.atualizar_eventos_sec --dias 730 --dias-form4 400 --max-form4 0

Form 4: cada um é uma consulta a mais, então a coleta lê só os que ainda não leu (com ou sem
negociação), no máximo `--max-form4` por vez (0 = sem limite; a primeira carga leva horas).

Empresas: as ações dos EUA do catálogo do app (o S&P 500). Regras de acesso da SEC: cada consulta
diz quem é e um e-mail de contato (`TICKERLAB_CONTATO`, no .env, fora do Git) e no máximo 10
consultas por segundo (aqui, ~8). Sem o contato, não consulta nada e sai com erro. Uma empresa que
falhar é pulada; as outras seguem. Não apaga nada.
"""

import argparse
import logging
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from src import catalogo, fundamentos_sec
from src import eventos_sec as sec
from src import negociacoes as ng
from src import negociacoes_sec as form4
from src.banco.conexao import criar_engine, migrar_para
from src.banco.demonstracoes import (
    gravar_demonstracoes,
    gravar_setor,
    referencias_guardadas,
)
from src.banco.eventos import (
    ORIGEM_SEC,
    gravar_eventos,
    gravar_tickers,
    versoes_gravadas,
)
from src.banco.negociacoes import gravar_negociacoes, ja_lidos, marcar_como_lidos
from src.configuracao import contato, url_do_banco

log = logging.getLogger("tickerlab.sec")
PAUSA_ENTRE_CONSULTAS = 0.125  # 8 por segundo, abaixo do limite de 10 da SEC
DIAS_PADRAO = 400
DIAS_DO_FORM4 = 90
MAX_FORM4 = 3_000  # por execução: ~6 min a 8 consultas por segundo
SEM_CONTATO = 2  # código de saída: falta configurar o e-mail


def baixar(url: str, agente: str) -> bytes:
    resposta = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": agente, "Accept-Encoding": "gzip, deflate"},
    )
    resposta.raise_for_status()
    return resposta.content


def so_participacoes_na_empresa(
    tabela: pd.DataFrame, cik: int, agente: str, ja_gravados: set[str]
) -> pd.DataFrame:
    """Tira os 13D/13G que a própria empresa entregou sobre outras (confere o cabeçalho de cada
    um que ainda não está no banco)."""
    manter = []
    for linha in tabela.itertuples(index=False):
        if not sec.e_participacao(linha.categoria) or linha.protocolo in ja_gravados:
            manter.append(True)
            continue
        time.sleep(PAUSA_ENTRE_CONSULTAS)
        endereco = sec.URL_DO_CABECALHO.format(
            cik=cik, pasta=linha.protocolo.replace("-", ""), protocolo=linha.protocolo
        )
        cabecalho = baixar(endereco, agente).decode("latin-1")
        manter.append(sec.empresa_alvo(cabecalho) == cik)
    return tabela[manter]


def gravar_eventos_da_empresa(
    motor: sa.Engine, conteudo: bytes, cik: int, agente: str, desde: date
) -> int:
    """Grava os eventos novos de uma empresa. Devolve quantos entraram."""
    tabela = sec.ler_documentos(conteudo, desde)
    with motor.connect() as conexao:
        ja_gravados = set(versoes_gravadas(conexao, sec.FONTE_SEC, tabela["protocolo"]))
    tabela = so_participacoes_na_empresa(tabela, cik, agente, ja_gravados)
    with motor.begin() as conexao:
        return gravar_eventos(conexao, tabela, fonte=sec.FONTE_SEC)[0]


def ler_um_form4(
    cik: int, protocolo: str, entregue_em: date, documento: str, agente: str
) -> pd.DataFrame:
    """Baixa e lê um Form 4; um XML quebrado vira tabela vazia (e fica marcado como lido)."""
    pasta = protocolo.replace("-", "")
    time.sleep(PAUSA_ENTRE_CONSULTAS)
    conteudo = baixar(
        sec.URL_DO_ARQUIVO.format(
            cik=cik, pasta=pasta, documento=form4.xml_puro(documento)
        ),
        agente,
    )
    link = sec.URL_DO_ARQUIVO.format(cik=cik, pasta=pasta, documento=documento)
    try:
        return form4.ler_form4(conteudo, cik, protocolo, entregue_em, link)
    except ET.ParseError:
        log.warning("Form 4 %s ilegível: pulado", protocolo)
        return ng.tabela_vazia()


def gravar_form4_da_empresa(
    motor: sa.Engine, conteudo: bytes, cik: int, agente: str, desde: date, limite: int
) -> int:
    """Lê os Form 4 ainda não lidos (até `limite`) e grava as negociações e os eventos.

    Devolve quantos Form 4 foram baixados (para descontar do limite da execução).
    """
    lista = form4.formularios_4(conteudo, desde)
    with motor.connect() as conexao:
        lidos = ja_lidos(conexao, ng.FONTE_FORM4, [p for p, _, _ in lista])
    pendentes = [item for item in lista if item[0] not in lidos][:limite]
    for protocolo, entregue_em, documento in pendentes:
        try:
            tabela = ler_um_form4(cik, protocolo, entregue_em, documento, agente)
        except requests.RequestException as erro:
            # não marca como lido: tenta de novo na próxima coleta, sem travar os outros
            log.warning("Form 4 %s não baixou: %s", protocolo, erro.__class__.__name__)
            continue
        with motor.begin() as conexao:
            gravar_negociacoes(conexao, tabela)
            gravar_eventos(
                conexao, ng.eventos_das_negociacoes(tabela), fonte=ng.FONTE_FORM4
            )
            marcar_como_lidos(conexao, ng.FONTE_FORM4, [protocolo])
    return len(pendentes)


def gravar_fundamentos_da_empresa(
    motor: sa.Engine, conteudo: bytes, cik: int, agente: str
) -> int:
    """Baixa os balanços (`companyfacts`) só se há 10-K ou 10-Q novo. Devolve documentos gravados."""
    chave = sec.cik_como_chave(cik)
    ultimo, setor = fundamentos_sec.ultimo_relatorio(conteudo)
    with motor.connect() as conexao:
        guardadas = referencias_guardadas(conexao, chave)
    if ultimo is None or ultimo in guardadas:
        return 0
    time.sleep(PAUSA_ENTRE_CONSULTAS)
    fatos = baixar(fundamentos_sec.URL_DOS_FATOS.format(cik=cik), agente)
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    contas, documentos = fundamentos_sec.ler_companyfacts(fatos, hoje)
    with motor.begin() as conexao:
        gravar_setor(conexao, chave, setor)
        return gravar_demonstracoes(conexao, contas, documentos)


def coletar_empresa(
    motor: sa.Engine, cik: int, agente: str, janelas: tuple[date, date], limite: int
) -> tuple[int, int]:
    """Eventos e Form 4 de uma empresa (uma consulta à lista de documentos dela).

    Devolve (eventos novos, Form 4 baixados). Os balanços (fundamentos) vêm junto.
    """
    desde, desde_form4 = janelas
    time.sleep(PAUSA_ENTRE_CONSULTAS)
    conteudo = baixar(sec.URL_DOS_DOCUMENTOS.format(cik=cik), agente)
    eventos = gravar_eventos_da_empresa(motor, conteudo, cik, agente, desde)
    try:
        gravar_fundamentos_da_empresa(motor, conteudo, cik, agente)
    except (requests.RequestException, ValueError, KeyError) as erro:
        # os balanços falharem não impede os Form 4; tenta de novo na próxima coleta
        log.warning("Balanços de CIK %s pulados: %s", cik, erro.__class__.__name__)
    if limite <= 0:
        return eventos, 0
    return eventos, gravar_form4_da_empresa(
        motor, conteudo, cik, agente, desde_form4, limite
    )


def tickers_dos_eua() -> set[str]:
    tabela = catalogo.carregar()
    return set(tabela.index[tabela["bolsa"] == "EUA"])


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    janelas = (
        hoje - timedelta(days=opcoes.dias),
        hoje - timedelta(days=opcoes.dias_form4),
    )
    restantes = opcoes.max_form4 if opcoes.max_form4 > 0 else sys.maxsize
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        mapa = sec.ler_tickers(baixar(sec.URL_DOS_TICKERS, agente), tickers_dos_eua())
        with motor.begin() as conexao:
            log.info(
                "Mapa ticker → CIK: %s empresas",
                gravar_tickers(conexao, mapa, origem=ORIGEM_SEC),
            )
        novos = baixados = falhas = 0
        for cnpj in sorted(set(mapa["cnpj"])):
            cik = int(cnpj.removeprefix(sec.PREFIXO_DO_CIK))
            try:
                eventos, lidos = coletar_empresa(motor, cik, agente, janelas, restantes)
            except (requests.RequestException, ValueError, KeyError) as erro:
                falhas += 1
                log.warning("%s pulada: %s", cnpj, erro.__class__.__name__)
                continue
            novos, baixados, restantes = (
                novos + eventos,
                baixados + lidos,
                restantes - lidos,
            )
        log.info(
            "SEC: %s empresas, %s eventos novos, %s Form 4 lidos, %s falhas",
            len(set(mapa["cnpj"])), novos, baixados, falhas,
        )  # fmt: skip
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
