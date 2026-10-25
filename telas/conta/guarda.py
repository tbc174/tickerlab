"""A conta ainda vale? Conferida no próprio callback das ações que apagam, exportam, publicam ou
mexem na cobrança (linha 306; achado P0 da revisão cruzada do Codex no #659).

O Streamlit roda os callbacks antes do corpo do app, e é no corpo que a sessão relê a conta (a cada
minuto) e para na conta bloqueada ou apagada. Sem esta conferência, uma aba aberta antes do bloqueio
ainda apagaria a conta, exportaria os dados ou criaria um link público com um clique.

Regra de `telas/`: nenhum estado mutável no módulo.
"""

import functools
import logging
import uuid
from collections.abc import Callable

import streamlit as st

from src.banco.conexao import obter_engine
from src.banco.usuarios import esta_valendo

log = logging.getLogger(__name__)


def conta_valendo(usuario_id: uuid.UUID) -> bool:
    """Relê a conta no banco. Falha ao ler conta como não: a ação espera o próximo clique."""
    try:
        with obter_engine().connect() as conexao:
            return esta_valendo(conexao, usuario_id)
    except Exception:
        log.exception("Falha ao conferir a conta antes de uma ação")
        return False


def so_com_a_conta_valendo[**P](callback: Callable[P, None]) -> Callable[P, None]:
    """Envolve o callback: sem a conta da sessão valendo, ele não roda, e o corpo do app relê a
    conta já nesta execução (e para na tela da conta bloqueada ou apagada)."""

    @functools.wraps(callback)
    def conferido(*args: P.args, **kwargs: P.kwargs) -> None:
        usuario = st.session_state.get("usuario")
        if usuario is None or not conta_valendo(usuario.id):
            st.session_state["usuario_em"] = 0
            return
        callback(*args, **kwargs)

    return conferido
