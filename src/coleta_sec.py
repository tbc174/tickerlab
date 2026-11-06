"""A coleta de uma empresa dos EUA na SEC: eventos, balanços e Form 4 (Research).

Usada pela coleta diária (`scripts/atualizar_eventos_sec.py`) e pela **busca na hora** do app
(R4): quando alguém abre uma ação dos EUA fora do S&P 500, o app busca a empresa na SEC naquele
momento, guarda tudo e a coloca na coleta diária (`tickers_sob_demanda`).

Toda consulta passa pelo `ClienteSec`, que identifica o TickerLab (nome e e-mail de contato, regra
da SEC) e respeita o ritmo de no máximo ~8 consultas por segundo (o limite da SEC é 10).
"""

import json
import logging
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import sqlalchemy as sa
from defusedxml import DefusedXmlException

from src import eventos_sec as sec
from src import fundamentos_sec, leitura, rede
from src import negociacoes as ng
from src import negociacoes_sec as form4
from src.banco import leituras as repo_leituras
from src.banco import sob_demanda
from src.banco.demonstracoes import (
    gravar_demonstracoes,
    gravar_setor,
    referencias_guardadas,
)
from src.banco.eventos import gravar_eventos, versoes_gravadas
from src.banco.negociacoes import gravar_negociacoes, ja_lidos, marcar_como_lidos

log = logging.getLogger("tickerlab.sec")
PAUSA_ENTRE_CONSULTAS = 0.125  # 8 por segundo, abaixo do limite de 10 da SEC
ERROS_DE_UMA_EMPRESA = (requests.RequestException, ValueError, KeyError)
# páginas antigas da lista de documentos (cada uma com até ~1.000; a 001 é a mais recente)
URL_DA_PAGINA_ANTIGA = "https://data.sec.gov/submissions/{nome}"
MAX_PAGINAS_ANTIGAS = 2  # sem 10-K em 2 páginas, a empresa não entrega 10-K todo ano


def baixar_da_sec(url: str, agente: str) -> bytes:
    resposta = rede.obter(
        url,
        timeout=60,
        headers={"User-Agent": agente, "Accept-Encoding": "gzip, deflate"},
    )
    resposta.raise_for_status()
    return resposta.content


@dataclass(frozen=True)
class ClienteSec:
    """Quem consulta a SEC: identificação (`agente`), ritmo (`pausa`) e o transporte."""

    agente: str
    pausa: float = PAUSA_ENTRE_CONSULTAS
    transporte: Callable[[str, str], bytes] = baixar_da_sec

    def baixar(self, url: str) -> bytes:
        time.sleep(self.pausa)
        return self.transporte(url, self.agente)


@dataclass(frozen=True)
class Janelas:
    """Desde quando ler eventos e Form 4, e quantos Form 4 baixar nesta vez (0 = nenhum)."""

    eventos: date
    form4: date
    limite_form4: int


def _so_participacoes_na_empresa(
    cliente: ClienteSec, tabela: pd.DataFrame, cik: int, ja_gravados: set[str]
) -> pd.DataFrame:
    """Tira os 13D/13G que a própria empresa entregou sobre outras (confere o cabeçalho de cada
    um que ainda não está no banco)."""
    manter = []
    for linha in tabela.itertuples(index=False):
        if not sec.e_participacao(linha.categoria) or linha.protocolo in ja_gravados:
            manter.append(True)
            continue
        endereco = sec.URL_DO_CABECALHO.format(
            cik=cik, pasta=linha.protocolo.replace("-", ""), protocolo=linha.protocolo
        )
        cabecalho = cliente.baixar(endereco).decode("latin-1")
        manter.append(sec.empresa_alvo(cabecalho) == cik)
    return tabela[manter]


def gravar_eventos_da_empresa(
    motor: sa.Engine, cliente: ClienteSec, conteudo: bytes, cik: int, desde: date
) -> int:
    """Grava os eventos novos de uma empresa. Devolve quantos entraram."""
    tabela = sec.ler_documentos(conteudo, desde)
    with motor.connect() as conexao:
        ja_gravados = set(versoes_gravadas(conexao, sec.FONTE_SEC, tabela["protocolo"]))
    tabela = _so_participacoes_na_empresa(cliente, tabela, cik, ja_gravados)
    with motor.begin() as conexao:
        return gravar_eventos(conexao, tabela, fonte=sec.FONTE_SEC)[0]


def _ler_um_form4(
    cliente: ClienteSec, cik: int, protocolo: str, entregue_em: date, documento: str
) -> pd.DataFrame:
    """Baixa e lê um Form 4; um XML quebrado vira tabela vazia (e fica marcado como lido)."""
    pasta = protocolo.replace("-", "")
    conteudo = cliente.baixar(
        sec.URL_DO_ARQUIVO.format(
            cik=cik, pasta=pasta, documento=form4.xml_puro(documento)
        )
    )
    link = sec.URL_DO_ARQUIVO.format(cik=cik, pasta=pasta, documento=documento)
    try:
        return form4.ler_form4(conteudo, cik, protocolo, entregue_em, link)
    except (ET.ParseError, DefusedXmlException):  # quebrado ou malicioso
        log.warning("Form 4 %s ilegível: pulado", protocolo)
        return ng.tabela_vazia()


def gravar_form4_da_empresa(
    motor: sa.Engine,
    cliente: ClienteSec,
    conteudo: bytes,
    cik: int,
    desde: date,
    limite: int,
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
            tabela = _ler_um_form4(cliente, cik, protocolo, entregue_em, documento)
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
    motor: sa.Engine, cliente: ClienteSec, conteudo: bytes, cik: int, hoje: date
) -> int:
    """Baixa os balanços (`companyfacts`) só se há 10-K ou 10-Q novo. Devolve documentos gravados."""
    chave = sec.cik_como_chave(cik)
    ultimo, setor = fundamentos_sec.ultimo_relatorio(conteudo)
    with motor.connect() as conexao:
        guardadas = referencias_guardadas(conexao, chave)
    if ultimo is None or ultimo in guardadas:
        return 0
    fatos = cliente.baixar(fundamentos_sec.URL_DOS_FATOS.format(cik=cik))
    contas, documentos = fundamentos_sec.ler_companyfacts(fatos, hoje)
    with motor.begin() as conexao:
        gravar_setor(conexao, chave, setor)
        return gravar_demonstracoes(conexao, contas, documentos)


def _10k_da_lista(colunas: dict) -> list[tuple[str, date | None, str]]:
    """(protocolo, data-base, documento) dos 10-K de uma lista da SEC, do mais novo ao mais velho
    (sem as retificações, 10-K/A)."""
    anuais = []
    for i, formulario in enumerate(colunas.get("form", [])):
        if formulario == "10-K" and colunas["primaryDocument"][i]:
            data = pd.to_datetime(colunas["reportDate"][i] or None, errors="coerce")
            anuais.append(
                (
                    colunas["accessionNumber"][i],
                    None if pd.isna(data) else data.date(),
                    colunas["primaryDocument"][i],
                )
            )
    return anuais


def _10k_anterior(
    cliente: ClienteSec, paginas: list[dict]
) -> tuple[str, date | None, str] | None:
    """O 10-K mais recente das páginas antigas da lista (a SEC só põe ~1.000 documentos na
    principal: num banco que entrega milhares de prospectos, o 10-K do ano anterior fica fora)."""
    for pagina in paginas[:MAX_PAGINAS_ANTIGAS]:
        colunas = json.loads(
            cliente.baixar(URL_DA_PAGINA_ANTIGA.format(nome=pagina["name"]))
        )
        anuais = _10k_da_lista(colunas)
        if anuais:
            return anuais[0]
    return None


def gravar_leitura_do_10k(
    motor: sa.Engine, cliente: ClienteSec, conteudo: bytes, cik: int
) -> bool:
    """Compara os fatores de risco dos dois últimos 10-K (R5), uma vez por 10-K novo.

    Devolve True se gravou. Sem a seção nos dois, grava o motivo (para não baixar de novo).
    """
    lista = json.loads(conteudo).get("filings", {})
    anuais = _10k_da_lista(lista.get("recent", {}))
    if not anuais:
        return False
    protocolo = anuais[0][0]
    with motor.connect() as conexao:
        if repo_leituras.lidos(
            conexao, sec.FONTE_SEC, repo_leituras.RISCOS, [protocolo]
        ):
            return False
    if len(anuais) < 2:
        anterior = _10k_anterior(cliente, lista.get("files", []))
        if anterior is None:
            return False
        anuais.append(anterior)
    anuais = anuais[:2]
    (_, referencia, _), (protocolo_antes, referencia_antes, _) = anuais
    links, textos = [], []
    for numero, _, documento in anuais:
        link = sec.URL_DO_ARQUIVO.format(
            cik=cik, pasta=numero.replace("-", ""), documento=documento
        )
        links.append(link)
        textos.append(
            leitura.fatores_de_risco(cliente.baixar(link).decode("utf-8", "replace"))
        )
    agora, antes = textos
    resultado = (
        leitura.comparar_riscos(antes, agora).para_guardar()
        if agora and antes
        else {
            "motivo": "Não achei a seção de fatores de risco nos dois 10-K.",
            "versao": leitura.VERSAO,
        }
    )
    resultado |= {
        "link_agora": links[0],
        "link_antes": links[1],
        "referencia_antes": referencia_antes.isoformat() if referencia_antes else None,
        "protocolo_antes": protocolo_antes,
    }
    with motor.begin() as conexao:
        repo_leituras.gravar_leitura(
            conexao,
            sec.FONTE_SEC,
            protocolo,
            repo_leituras.RISCOS,
            sec.cik_como_chave(cik),
            referencia,
            resultado,
        )
    return True


def coletar_empresa(
    motor: sa.Engine, cliente: ClienteSec, cik: int, janelas: Janelas, hoje: date
) -> tuple[int, int]:
    """Eventos, balanços e Form 4 de uma empresa (uma consulta à lista de documentos dela).

    Devolve (eventos novos, Form 4 baixados). Falha nos balanços não impede os Form 4.
    """
    conteudo = cliente.baixar(sec.URL_DOS_DOCUMENTOS.format(cik=cik))
    eventos = gravar_eventos_da_empresa(motor, cliente, conteudo, cik, janelas.eventos)
    try:
        gravar_fundamentos_da_empresa(motor, cliente, conteudo, cik, hoje)
    except ERROS_DE_UMA_EMPRESA as erro:
        log.warning("Balanços de CIK %s pulados: %s", cik, erro.__class__.__name__)
    try:
        gravar_leitura_do_10k(motor, cliente, conteudo, cik)
    except ERROS_DE_UMA_EMPRESA as erro:
        log.warning(
            "Leitura do 10-K de CIK %s pulada: %s", cik, erro.__class__.__name__
        )
    if janelas.limite_form4 <= 0:
        return eventos, 0
    lidos = gravar_form4_da_empresa(
        motor, cliente, conteudo, cik, janelas.form4, janelas.limite_form4
    )
    return eventos, lidos


# --- busca na hora (R4) ----------------------------------------------------------------------
BUSCAS_POR_HORA = 30  # ações novas por hora no servidor inteiro: protege o acesso à SEC
# cada ação buscada fica na coleta diária; sem teto, a coleta das 7h20 (500 empresas do S&P 500)
# cresceria sem limite (revisão de 12/10/2026, achado 1)
MAXIMO_SOB_DEMANDA = 300
FORM4_NA_BUSCA = 10  # os mais recentes; o resto vem na coleta diária
DIAS_DE_EVENTOS = 400
DIAS_DO_FORM4 = 90
UMA_HORA = timedelta(hours=1)


class BuscaRecusada(Exception):
    """A busca não pode ser feita agora (ticker fora da SEC ou limite da hora atingido)."""


def buscar_agora(
    motor: sa.Engine,
    cliente: ClienteSec,
    ticker: str,
    mapa: pd.DataFrame,
    agora: datetime,
) -> tuple[str, int, int]:
    """Busca na SEC uma ação dos EUA que ainda não está na base e a põe na coleta diária.

    `mapa`: o `company_tickers.json` lido (`eventos_sec.ler_tickers`). Devolve (empresa, eventos
    novos, Form 4 lidos). Levanta `BuscaRecusada` se o ticker não está na SEC, se a coleta diária
    já tem `MAXIMO_SOB_DEMANDA` ações buscadas ou se o servidor já fez `BUSCAS_POR_HORA` buscas na
    última hora.
    """
    linha = mapa[mapa["ticker"] == ticker]
    if linha.empty:
        raise BuscaRecusada(f"{ticker} não está na lista de empresas da SEC.")
    with motor.connect() as conexao:
        if sob_demanda.total(conexao) >= MAXIMO_SOB_DEMANDA:
            raise BuscaRecusada(
                "A coleta diária já tem o máximo de ações buscadas na hora "
                f"({MAXIMO_SOB_DEMANDA}). Esta ação ainda não pode entrar."
            )
        if sob_demanda.pedidos_desde(conexao, agora - UMA_HORA) >= BUSCAS_POR_HORA:
            raise BuscaRecusada(
                "Muitas buscas novas nesta hora (limite que protege o acesso à SEC). "
                "Tente de novo daqui a pouco."
            )
    chave, empresa = linha["cnpj"].iloc[0], linha["empresa"].iloc[0]
    hoje = agora.date()
    janelas = Janelas(
        hoje - timedelta(days=DIAS_DE_EVENTOS),
        hoje - timedelta(days=DIAS_DO_FORM4),
        FORM4_NA_BUSCA,
    )
    cik = int(chave.removeprefix(sec.PREFIXO_DO_CIK))
    eventos, lidos = coletar_empresa(motor, cliente, cik, janelas, hoje)
    with motor.begin() as conexao:
        sob_demanda.registrar(conexao, ticker, chave, empresa)
    return empresa, eventos, lidos
