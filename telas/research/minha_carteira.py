"""Research: Minha carteira (etapa 5, decisão 0020): só os pesos em %, com consentimento.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from src import carteira_research, relatorios
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import (
    DadosInvalidosError,
    revogar_carteira,
    salvar_carteira,
)
from src.carteira_b3 import ArquivoDaB3Error, ler_carteira
from src.planos import CARTEIRA_NO_RESEARCH, LimiteDoPlanoError, motivo_sem_acesso
from telas.comum import cabecalho_da_pagina, plano_atual
from telas.conta.guarda import so_com_a_conta_valendo
from telas.research.comum import _carteira_do_research


def guardar_fotografia(usuario, conteudo, nome_do_arquivo):
    """Lê a planilha na memória e guarda só os pesos. Devolve a mensagem para a tela."""
    hoje = datetime.now(relatorios.FUSO).date()
    try:
        foto = carteira_research.fotografia(
            ler_carteira(conteudo, nome_do_arquivo), hoje
        )
        with obter_engine().begin() as conexao:
            salvar_carteira(conexao, usuario.id, foto, plano_atual())
    except (ArquivoDaB3Error, DadosInvalidosError, LimiteDoPlanoError) as erro:
        return False, str(erro)
    return (
        True,
        f"Fotografia guardada: {len(foto.pesos)} ativos, sem quantidades nem valores.",
    )


def _guardar_da_tela(usuario):
    arquivo = st.session_state.get("minha_carteira_arquivo")
    if arquivo is None:
        return
    st.session_state["minha_carteira_mensagem"] = guardar_fotografia(
        usuario, arquivo.getvalue(), arquivo.name
    )


@so_com_a_conta_valendo
def _revogar_da_tela(usuario):
    with obter_engine().begin() as conexao:
        revogar_carteira(conexao, usuario.id)
    st.session_state["minha_carteira_mensagem"] = (
        True,
        "Consentimento revogado: a fotografia da carteira foi apagada.",
    )
    st.session_state["minha_carteira_confirma"] = False


def _mostrar_fotografia(foto):
    tabela = pd.DataFrame(
        {
            "Ativo": [t.removesuffix(".SA") for t in foto.pesos],
            "Peso na carteira": list(foto.pesos.values()),
        }
    )
    st.dataframe(
        tabela,
        hide_index=True,
        column_config={
            "Peso na carteira": st.column_config.ProgressColumn(
                format="percent", min_value=0.0, max_value=1.0
            )
        },
    )
    st.caption(
        f"Fotografia de {foto.enviada_em:%d/%m/%Y}. A soma fica abaixo de 100% quando há "
        'Tesouro ou renda fixa. Use a lista "Minha carteira" em Acontecimentos e na Newsletter.'
    )


def pagina_carteira_research():
    cabecalho_da_pagina("carteira_research")
    usuario = st.session_state.get("usuario")
    mensagem = st.session_state.pop("minha_carteira_mensagem", None)
    if mensagem is not None:
        (st.success if mensagem[0] else st.error)(mensagem[1])
    if usuario is None:
        st.info(
            "A fotografia da carteira fica guardada na sua conta: entre com o Google para usar "
            "esta página.",
            icon=":material/login:",
        )
    elif (motivo := motivo_sem_acesso(plano_atual(), CARTEIRA_NO_RESEARCH)) is not None:
        st.info(  # o mesmo texto da API v1 (src/planos.py, ADR 0062)
            f"{motivo} Sem ela, o Research usa as suas listas.",
            icon=":material/workspace_premium:",
        )
    else:
        foto = _carteira_do_research(usuario)
        if foto is None:
            st.info(
                "Você ainda não guardou a fotografia da carteira. Sem ela, o Research usa as "
                "suas listas, onde todo ativo pesa igual.",
                icon=":material/donut_large:",
            )
        else:
            _mostrar_fotografia(foto)
            with st.expander("Revogar o consentimento"):
                st.markdown(
                    "A fotografia é **apagada na hora**. Fica só um registro técnico, sem nome "
                    "nem e-mail, de quando o consentimento foi dado e revogado."
                )
                confirma = st.checkbox(
                    "Entendi: quero apagar a fotografia",
                    key="minha_carteira_confirma",
                )
                st.button(
                    "Revogar e apagar", icon=":material/delete:", disabled=not confirma,
                    key="minha_carteira_revogar", on_click=_revogar_da_tela, args=(usuario,),
                )  # fmt: skip
        with st.expander(
            "Atualizar a fotografia" if foto else "Enviar a planilha da B3",
            expanded=foto is None,
        ):
            st.markdown(
                "1. Entre na **Área do Investidor** da B3 (investidor.b3.com.br).\n"
                "2. Em **Extratos → Posição**, baixe a planilha em **Excel**.\n"
                "3. Envie aqui. Ela é lida **só na memória**: guardamos apenas o código e o "
                "peso de cada ativo."
            )
            arquivo = st.file_uploader(
                "Planilha de posição da B3",
                type=["xlsx", "csv"],
                key="minha_carteira_arquivo",
            )
            consentiu = st.checkbox(
                carteira_research.TEXTO_DO_CONSENTIMENTO,
                key="minha_carteira_consentimento",
            )
            st.button(
                "Guardar a fotografia", type="primary", icon=":material/save:",
                disabled=arquivo is None or not consentiu, key="minha_carteira_guardar",
                on_click=_guardar_da_tela, args=(usuario,),
            )  # fmt: skip
    with st.expander("O que é guardado e para quê"):
        st.markdown(
            "- **Guardado:** o código de cada ativo e o peso dele na carteira inteira (Tesouro "
            "e renda fixa entram no total), com a data da planilha e a versão do consentimento.\n"
            "- **Nunca guardado:** quantidades, valores em reais, preço médio e a própria "
            "planilha.\n"
            '- **Para quê:** no Research e na Newsletter, a lista "Minha carteira" põe na '
            'frente o que é das maiores posições e explica: "a posição era 12,0% da sua '
            'carteira".\n'
            "- **Revogar:** a qualquer momento, aqui mesmo; a fotografia é apagada na hora. "
            "Ela também sai na exportação dos seus dados e é apagada junto com a conta.\n"
            "- A ordem é uma regra editorial para organizar a leitura, não uma recomendação."
        )
