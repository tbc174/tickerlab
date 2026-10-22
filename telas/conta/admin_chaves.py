"""Administração das organizações e chaves da API externa, dentro da página do admin (N7, linha 169).

Cola fina: a regra e as consultas ficam em `src/administracao_das_chaves.py`. A chave nova aparece
**uma vez**, na execução do clique que a emitiu, e não vai para o `st.session_state`, para log nem
para a auditoria: no clique seguinte a página roda de novo e ela some. As ações rodam antes das
listas para que a tela já mostre o resultado. Regra de `telas/`: nenhum estado mutável no módulo.
"""

import logging
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from src import administracao_das_chaves as adc
from src.administracao import PermissaoNegadaError
from src.banco import chaves_da_api as cb
from src.banco.conexao import obter_engine
from src.banco.modelo import MOTIVOS_DA_SUSPENSAO, PLANOS_DA_API
from src.chaves_da_api import ChaveNova

log_da_conta = logging.getLogger("tickerlab.conta")

AVISO = "chaves_aviso"  # só texto de resultado, nunca uma chave
ERRO_GENERICO = "Não consegui fazer agora. Tente de novo em instantes."


def _quando(momento):
    return f"{momento:%d/%m/%Y %H:%M}" if momento else "—"


def _estado_da_chave(chave):
    if chave.revogada_em is not None:
        return f"revogada em {chave.revogada_em:%d/%m/%Y}"
    if chave.expira_em is not None:
        return f"de saída, vale até {chave.expira_em:%d/%m/%Y %H:%M} UTC"
    return "ativa"


def _executar(acao, *argumentos, **nomeados):
    """Roda a ação numa transação; devolve (resultado, None) ou (None, mensagem de erro)."""
    try:
        with obter_engine().begin() as conexao:
            return acao(conexao, *argumentos, **nomeados), None
    except (PermissaoNegadaError, *adc.ERROS_ESPERADOS) as erro:
        return None, str(erro)
    except Exception:
        log_da_conta.exception("Falha na administração das chaves da API")
        return None, ERRO_GENERICO


def _mostrar_a_chave(nova: ChaveNova, titulo: str):
    st.success(f"{titulo} (prefixo {nova.prefixo})")
    st.code(nova.valor, language=None)
    st.warning(
        "Esta chave aparece só agora: copie e entregue ao cliente. Ela não fica guardada "
        "em lugar nenhum e não dá para ver de novo."
    )


def _resultado_simples(resultado, erro, texto_ok):
    if erro:
        st.error(erro)
    elif resultado:
        st.success(texto_ok)
    else:
        st.info("Nada mudou: já estava assim.")


def _nova_organizacao(usuario):
    with st.expander("Nova organização"):
        nome = st.text_input("Nome", key="chaves_nome")
        cnpj = st.text_input("CNPJ (opcional)", key="chaves_cnpj")
        plano = st.selectbox("Plano da API", list(PLANOS_DA_API), key="chaves_plano")
        if st.button("Criar organização", key="chaves_criar"):
            criada, erro = _executar(
                adc.criar_organizacao,
                usuario.id,
                nome=nome,
                cnpj=cnpj,
                plano_da_api=plano,
            )
            if criada is None:
                st.error(erro)
            else:
                st.success(f"Organização criada. Escolha-a na lista: {criada.nome}.")


def _escolher_organizacao(organizacoes):
    por_id = {o.id: o for o in organizacoes}
    escolhida = st.selectbox(
        "Organização",
        list(por_id),
        format_func=lambda i: (
            por_id[i].nome + (" (suspensa)" if por_id[i].suspensa_em else "")
        ),
        key="chaves_organizacao",
    )
    return por_id[escolhida]


def _acoes_da_chave(usuario, visao):
    organizacao = visao.organizacao
    st.markdown("**Chaves**")
    if st.button("Emitir chave nova", key="chaves_emitir"):
        nova, erro = _executar(adc.emitir_chave, usuario.id, organizacao.id)
        if nova is None:
            st.error(erro)
        else:
            _mostrar_a_chave(nova, "Chave emitida")
    giraveis = [c for c in visao.chaves if c.revogada_em is None]
    if not giraveis:
        return
    por_id = {c.id: c for c in giraveis}
    chave_id = st.selectbox(
        "Chave",
        list(por_id),
        format_func=lambda i: f"{por_id[i].prefixo} ({_estado_da_chave(por_id[i])})",
        key="chaves_alvo",
    )
    confirmado = st.checkbox("Confirmo a ação sobre esta chave", key="chaves_confirmo")
    colunas = st.columns(2)
    if colunas[0].button(
        "Rotacionar", key="chaves_rotacionar", disabled=not confirmado
    ):
        nova, erro = _executar(
            adc.rotacionar_chave, usuario.id, organizacao.id, chave_id
        )
        if nova is None:
            st.error(erro)
        else:
            _mostrar_a_chave(
                nova,
                f"Chave rotacionada: a antiga vale mais {cb.PRAZO_DA_ROTACAO.days} dias",
            )
    if colunas[1].button("Revogar", key="chaves_revogar", disabled=not confirmado):
        resultado, erro = _executar(
            adc.revogar_chave, usuario.id, organizacao.id, chave_id
        )
        _resultado_simples(resultado, erro, "Chave revogada: ela não entra mais.")


def _mudou_a_suspensao(resultado, erro, texto_ok):
    """Depois de suspender ou reativar o botão certo é o outro: guarda o aviso e roda de novo."""
    if erro or not resultado:
        _resultado_simples(resultado, erro, texto_ok)
        return
    st.session_state[AVISO] = texto_ok
    st.rerun()


def _acoes_da_organizacao(usuario, organizacao):
    st.markdown("**Suspensão**")
    if organizacao.suspensa_em is None:
        motivo = st.selectbox("Motivo", list(MOTIVOS_DA_SUSPENSAO), key="chaves_motivo")
        if st.button("Suspender organização", key="chaves_suspender"):
            resultado, erro = _executar(
                adc.suspender_organizacao, usuario.id, organizacao.id, motivo
            )
            _mudou_a_suspensao(
                resultado, erro, "Organização suspensa: nenhuma chave entra."
            )
    elif st.button("Reativar organização", key="chaves_reativar"):
        resultado, erro = _executar(
            adc.reativar_organizacao, usuario.id, organizacao.id
        )
        _mudou_a_suspensao(resultado, erro, "Organização reativada: as chaves voltam.")


def _painel(visao):
    organizacao, consumo = visao.organizacao, visao.consumo
    estado = (
        f"suspensa em {_quando(organizacao.suspensa_em)} "
        f"({organizacao.motivo_da_suspensao})"
        if organizacao.suspensa_em
        else "ativa"
    )
    st.caption(f"Plano da API: {organizacao.plano_da_api} · {estado}")
    colunas = st.columns(3)
    colunas[0].metric("Pedidos no mês", consumo.pedidos)
    colunas[1].metric("Linhas servidas", consumo.linhas)
    colunas[2].metric("Pedidos negados", consumo.negados)
    st.caption("Mês corrente em UTC. Só pedidos aceitos contam para a quota.")
    if visao.chaves:
        st.dataframe(
            pd.DataFrame(
                {
                    "Prefixo": [c.prefixo for c in visao.chaves],
                    "Estado": [_estado_da_chave(c) for c in visao.chaves],
                    "Criada em": [_quando(c.criada_em) for c in visao.chaves],
                    "Último uso": [_quando(c.ultimo_uso) for c in visao.chaves],
                }
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("Nenhuma chave emitida ainda.")
    if visao.direitos:
        st.markdown("**Direitos vigentes**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Conjunto": [d.conjunto for d in visao.direitos],
                    "Finalidade": [d.finalidade for d in visao.direitos],
                    "Até": [str(d.vigente_ate or "sem fim") for d in visao.direitos],
                }
            ),
            width="stretch",
            hide_index=True,
        )


def secao_de_chaves(usuario):
    st.subheader("API externa: organizações e chaves")
    st.caption(
        "Cada organização tem chaves próprias. O valor da chave aparece uma vez, ao emitir ou "
        "rotacionar; depois só o prefixo. Quem concede direitos (contrato) ainda é o script."
    )
    aviso = st.session_state.pop(AVISO, None)
    if aviso:
        st.success(aviso)
    _nova_organizacao(usuario)
    organizacoes, erro = _executar(adc.listar_organizacoes, usuario.id)
    if erro:
        st.warning(erro)
        return
    if not organizacoes:
        st.caption("Nenhuma organização ainda.")
        return
    organizacao = _escolher_organizacao(organizacoes)
    hoje = datetime.now(UTC).date()
    visao, erro = _executar(adc.ver_organizacao, usuario.id, organizacao.id, hoje)
    if erro:
        st.warning(erro)
        return
    # as ações antes das listas: a tela já nasce com o resultado (e a chave, uma vez)
    _acoes_da_chave(usuario, visao)
    _acoes_da_organizacao(usuario, organizacao)
    visao, erro = _executar(adc.ver_organizacao, usuario.id, organizacao.id, hoje)
    if erro:
        st.warning(erro)
        return
    _painel(visao)
