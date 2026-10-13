"""O que várias páginas do Research usam: listas, carteira da lista, avisos do banco e formatos.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import streamlit as st
from sqlalchemy import exc as sa_exc

from src import research
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import carregar_carteira, listar_watchlists
from src.dados import normalizar_ticker
from src.planos import CARTEIRA_NO_RESEARCH, pode_usar
from telas.comum import plano_atual


def _listas_do_research(usuario):
    """(nome, tickers, id da watchlist ou None): demonstração, favoritos e as listas com nome."""
    listas = [(research.NOME_DA_DEMONSTRACAO, list(research.DEMONSTRACAO), None)]
    favoritos = [normalizar_ticker(t) for t in st.session_state.get("favoritos", [])]
    if favoritos:
        listas.append((research.NOME_DOS_FAVORITOS, favoritos, None))
    carteira = _carteira_do_research(usuario)
    if carteira is not None:
        listas.append((research.NOME_DA_CARTEIRA, list(carteira.pesos), None))
    if usuario is not None:
        try:
            with obter_engine().connect() as conexao:
                listas += [
                    (w.nome, w.tickers, w.id)
                    for w in listar_watchlists(conexao, usuario.id)
                ]
        except Exception:
            logging.getLogger(__name__).exception("Falha ao ler as listas")
            st.warning("Não consegui ler as suas listas agora.")
    return listas


def _carteira_do_research(usuario):
    """A fotografia guardada (só pesos), se há conta, o plano permite e o consentimento vale."""
    if usuario is None or not pode_usar(plano_atual(), CARTEIRA_NO_RESEARCH):
        return None
    try:
        with obter_engine().connect() as conexao:
            return carregar_carteira(conexao, usuario.id)
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        return None  # banco sem a tabela (modo local sem migrar)


def _carteira_da_lista(nome):
    """A fotografia, quando a lista escolhida é a carteira (para pesar a exposição)."""
    if nome != research.NOME_DA_CARTEIRA:
        return None
    return _carteira_do_research(st.session_state.get("usuario"))


def _numero_br(valor, casas):
    return f"{valor:,.{casas}f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _dinheiro(valor, simbolo="R$"):
    """Em bilhões ou milhões, no formato brasileiro (R$ 1,2 bi; US$ 350,0 mi)."""
    for limite, sufixo in ((1e9, "bi"), (1e6, "mi")):
        if abs(valor) >= limite:
            return f"{simbolo} {_numero_br(valor / limite, 1)} {sufixo}"
    return f"{simbolo} {_numero_br(valor, 0)}"


def _sem_banco_agora(o_que):
    """A frase de quando o banco não respondeu: nunca "vazio" nem "não coletado" (achado D-2)."""
    return f"Não consegui ler {o_que} agora. Tente de novo em instantes."


def _ainda_nao_coletado(frase, comandos):
    """Base ainda vazia: para quem usa, a explicação; os comandos só para quem administra.

    Antes, qualquer pessoa via `python -m scripts...` na tela (achado D-3 do Master v3).
    """
    usuario = st.session_state.get("usuario")
    if (
        usuario is None or usuario.e_admin
    ):  # modo local (desenvolvimento) ou administrador
        return f"{frase} ({' e '.join(f'`{c}`' for c in comandos)})."
    return f"{frase} A coleta roda uma vez por dia."
