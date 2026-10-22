"""Administração: planos e papéis dos usuários (só para admins).

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import json
import logging

import pandas as pd
import streamlit as st

from src import administracao as adm
from src import exportacao_do_acervo as exp
from src.administracao import OperacaoInvalidaError, PermissaoNegadaError
from src.autenticacao import emails_de_admin
from src.banco.conexao import obter_engine
from src.banco.modelo import PAPEIS, PLANOS
from telas.comum import cabecalho_da_pagina
from telas.conta.admin_chaves import secao_de_chaves

# o mesmo logger do telas/comum.py (o nome fixo faz o Python devolver o mesmo objeto)
log_da_conta = logging.getLogger("tickerlab.conta")


def _admin_aplicar(usuario, tipo):
    alvo_id = st.session_state.get("admin_alvo")
    valor = st.session_state.get(f"admin_{tipo}")
    try:
        with obter_engine().begin() as conexao:
            if tipo == "plano":
                adm.alterar_plano(conexao, usuario.id, alvo_id, valor)
            else:
                adm.alterar_papel(
                    conexao, usuario.id, alvo_id, valor, emails_de_admin()
                )
    except (PermissaoNegadaError, OperacaoInvalidaError) as erro:
        st.toast(str(erro))
        return
    except Exception:
        log_da_conta.exception("Falha ao aplicar uma mudança de administrador")
        st.toast("Não consegui aplicar agora. Tente de novo em instantes.")
        return
    st.toast("Pronto, mudança aplicada e registrada.")


def _preparar_exportacao(usuario):
    base = st.session_state.get("admin_exportar_base")
    formato = st.session_state.get("admin_exportar_formato")
    try:
        with obter_engine().begin() as conexao:
            st.session_state["admin_exportacao"] = exp.exportar(
                conexao, usuario.id, base, formato
            )
    except (PermissaoNegadaError, exp.ExportacaoInvalidaError) as erro:
        st.toast(str(erro))
    except Exception:
        log_da_conta.exception("Falha ao exportar o acervo")
        st.toast("Não consegui preparar o arquivo agora. Tente de novo em instantes.")


def _secao_de_exportacao(usuario):
    st.subheader("Exportar o acervo")
    st.caption(
        "Só fontes com licença que permite (CVM, SEC, Banco Central e Tesouro dos EUA), com "
        "todas as versões guardadas. Os preços do Yahoo nunca saem. O zip leva um LEIA-ME com "
        "a fonte e a licença de cada parte, e o pedido fica no registro de ações."
    )
    colunas = st.columns(2)
    colunas[0].selectbox(
        "Base",
        list(exp.BASES),
        format_func=lambda b: f"{exp.BASES[b].nome}: {exp.BASES[b].descricao}",
        key="admin_exportar_base",
    )
    colunas[1].radio(
        "Formato", exp.FORMATOS, horizontal=True, key="admin_exportar_formato"
    )
    st.button(
        "Preparar arquivo",
        key="admin_exportar",
        on_click=_preparar_exportacao,
        args=(usuario,),
    )
    pronto = st.session_state.get("admin_exportacao")
    if pronto:
        nome, conteudo = pronto
        st.download_button(
            f"Baixar {nome}", conteudo, file_name=nome, mime="application/zip"
        )


def _quando(momento):
    return f"{momento:%d/%m/%Y %H:%M}" if momento else "—"


def pagina_admin():
    cabecalho_da_pagina("admin")
    usuario = st.session_state.get("usuario")
    if usuario is None or not usuario.e_admin:
        st.error("Esta página é só para administradores.")
        return
    busca = st.text_input("Buscar por e-mail ou nome", key="admin_busca")
    try:
        with obter_engine().connect() as conexao:
            resumo = adm.resumo_geral(conexao, usuario.id)
            linhas = adm.listar_usuarios(conexao, usuario.id, busca)
            registros = adm.auditoria_recente(conexao, usuario.id, 30)
            eventos = adm.eventos_recentes_do_stripe(conexao, usuario.id, 15)
    except PermissaoNegadaError:
        st.error("Esta página é só para administradores.")
        return
    except Exception:
        log_da_conta.exception("Falha ao carregar o painel de administração")
        st.warning("Não consegui carregar o painel agora.")
        return

    primeira = st.columns(5)
    primeira[0].metric("Usuários", resumo["usuarios"])
    primeira[1].metric("Plano Plus", resumo["plus"])
    primeira[2].metric("Plano Pro", resumo["pro"])
    primeira[3].metric("Novos na semana", resumo["novos_na_semana"])
    primeira[4].metric("Ativos na semana", resumo["ativos_na_semana"])
    segunda = st.columns(4)
    segunda[0].metric("Plano Gratuito", resumo["gratuito"])
    segunda[1].metric(
        "Assinaturas ativas", resumo["assinaturas_por_status"].get("active", 0)
    )
    segunda[2].metric("Simulações salvas", resumo["simulacoes"])
    segunda[3].metric("Eventos do Stripe", resumo["eventos_do_stripe"])

    st.subheader("Usuários")
    if not linhas:
        st.info("Nenhum usuário encontrado.")
    else:
        st.dataframe(
            pd.DataFrame(
                {
                    "Nome": [l.nome or "—" for l in linhas],
                    "E-mail": [l.email for l in linhas],
                    "Plano": [l.plano for l in linhas],
                    "Papel": [l.papel for l in linhas],
                    "Assinatura": [l.status_da_assinatura or "—" for l in linhas],
                    "Simulações": [l.simulacoes for l in linhas],
                    "Criada em": [_quando(l.criado_em) for l in linhas],
                    "Último acesso": [_quando(l.ultimo_acesso) for l in linhas],
                }
            ),
            width="stretch",
            hide_index=True,
        )
        st.markdown("**Alterar um usuário**")
        por_id = {l.id: l for l in linhas}
        st.selectbox(
            "Usuário",
            list(por_id),
            format_func=lambda i: (
                f"{por_id[i].email} ({por_id[i].plano}, {por_id[i].papel})"
            ),
            key="admin_alvo",
        )
        col_plano, col_papel = st.columns(2)
        with col_plano:
            st.selectbox("Plano", list(PLANOS), key="admin_plano")
            st.button(
                "Aplicar plano",
                key="admin_aplicar_plano",
                on_click=_admin_aplicar,
                args=(usuario, "plano"),
            )
        with col_papel:
            st.selectbox("Papel", list(PAPEIS), key="admin_papel")
            st.button(
                "Aplicar papel",
                key="admin_aplicar_papel",
                on_click=_admin_aplicar,
                args=(usuario, "papel"),
            )
        st.caption(
            "Mudar o plano aqui não cria nem cancela assinatura no Stripe. Toda mudança "
            "fica no registro abaixo."
        )

    st.subheader("Registro de ações")
    if registros:
        st.dataframe(
            pd.DataFrame(
                {
                    "Quando": [_quando(r.criado_em) for r in registros],
                    "Ação": [r.acao for r in registros],
                    "Quem fez": [
                        str(r.ator_id)[:8] if r.ator_id else "—" for r in registros
                    ],
                    "Alvo": [
                        str(r.alvo_id)[:8] if r.alvo_id else "—" for r in registros
                    ],
                    "Detalhes": [
                        json.dumps(r.detalhes, ensure_ascii=False) for r in registros
                    ],
                }
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("Nada registrado ainda.")

    st.subheader("Últimos eventos do Stripe")
    if eventos:
        st.dataframe(
            pd.DataFrame(
                {
                    "Quando": [_quando(e[2]) for e in eventos],
                    "Tipo": [e[1] for e in eventos],
                    "Evento": [e[0] for e in eventos],
                }
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("Nenhum evento recebido ainda.")

    _secao_de_exportacao(usuario)
    secao_de_chaves(usuario)
