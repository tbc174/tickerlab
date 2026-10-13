"""Tutorial por objetivo (blueprint, seção 4): as portas de entrada, os passos guiados e a lista de tarefas.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import streamlit as st

from src import indicadores as ind
from src import relatorios, tutorial
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import carregar_preferencias, salvar_preferencias
from src.dados import normalizar_ticker
from src.paginas import pagina
from telas.comum import (
    PAGINAS_DO_MENU,
    PERIODOS_DO_TOPO,
    _alternar_favorito_atual,
    formatar_pct,
    marcar_feito,
)
from telas.relatorios.estudio import _aplicar_secoes


def acoes_feitas():
    feitos = set(st.session_state.get("tutorial_feitos", set()))
    if st.session_state.get("favoritos"):
        feitos.add("salvou_favorito")
    return feitos


def _guardar_na_conta(chave, valor):
    """Grava uma preferência na conta, sem apagar as outras (sem conta, fica só na sessão)."""
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return
    try:
        with obter_engine().begin() as conexao:
            atuais = carregar_preferencias(conexao, usuario.id)
            salvar_preferencias(conexao, usuario.id, {**atuais, chave: valor})
    except Exception:
        logging.getLogger(__name__).exception("Falha ao salvar a preferência %s", chave)


def _preparar_o_estudio(tipo, modelo=relatorios.EXECUTIVO):
    st.session_state["tipo_de_relatorio"] = tipo
    st.session_state["relatorio_modelo"] = modelo
    _aplicar_secoes(tipo, relatorios.secoes_do_modelo(tipo, modelo))
    st.session_state.pop("relatorio_gerado", None)


def _comecar_tutorial(objetivo):
    st.session_state["tutorial"] = {"objetivo": objetivo, "passo": 0}
    if objetivo == tutorial.CARTEIRA:
        _preparar_o_estudio(relatorios.MINHA_CARTEIRA, relatorios.COMPLETO)
        st.session_state["tutorial_ir_para"] = "relatorio"
    elif objetivo == tutorial.RELATORIO:
        _preparar_o_estudio(relatorios.ATIVO)
        st.session_state["tutorial_ir_para"] = "relatorio"


def _encerrar_tutorial(concluiu):
    st.session_state.pop("tutorial", None)
    st.session_state["tutorial_visto"] = True
    _guardar_na_conta("tutorial_visto", True)
    if concluiu:
        st.toast(
            "Tutorial concluído. Dá para reabrir na página inicial.",
            icon=":material/school:",
        )


def _reabrir_tutorial():
    st.session_state["tutorial_visto"] = False
    st.session_state.pop("tutorial", None)
    st.session_state.pop("checklist_escondido", None)


def _andar_no_tutorial(passo):
    estado = st.session_state["tutorial"]
    total = len(tutorial.passos(estado["objetivo"]))
    novo = estado["passo"] + passo
    if novo >= total:
        _encerrar_tutorial(concluiu=True)
        return
    estado["passo"] = max(0, novo)
    atual = tutorial.passo_atual(estado["objetivo"], estado["passo"])
    if (
        atual.chave == "gere"
    ):  # o passo do relatório já abre o estúdio no modelo Executivo
        _preparar_o_estudio(relatorios.ATIVO)
        st.session_state["tutorial_ir_para"] = "relatorio"


def _ir_pelo_tutorial(chave_da_pagina):
    if (
        chave_da_pagina == "relatorio"
        and st.session_state.get("tutorial", {}).get("objetivo") == tutorial.ANALISAR
    ):
        _preparar_o_estudio(relatorios.ATIVO)
    st.session_state["tutorial_ir_para"] = chave_da_pagina


def _explicar_dois_numeros(c):
    """A mini-lição do passo "Leia dois números", com os números do ativo aberto."""
    total = float(ind.calcular_retorno_acumulado(c.retorno).iloc[-1])
    queda = float(ind.calcular_drawdown(c.fechamento).min())
    rotulo = PERIODOS_DO_TOPO.get(c.periodo, c.periodo)
    st.markdown(
        f"- **Retorno total ({formatar_pct(total, com_sinal=True)}):** quem comprou {c.ticker} no "
        f"primeiro dia dos últimos {rotulo} e vendeu no último teria essa variação, antes de "
        "impostos e custos.\n"
        f"- **Maior queda ({formatar_pct(queda)}):** em algum momento, quem tinha "
        "comprado no topo chegou a ver esse prejuízo no papel. É uma medida do susto, não "
        "do resultado final.\n\n"
        "Os dois descrevem o **passado**: não dizem o que vai acontecer."
    )


def mostrar_tutorial(pagina_atual, c=None):
    """A faixa do tutorial: passo atual, progresso, o que falta e os botões (sem bloquear a
    tela: a pessoa continua usando tudo normalmente)."""
    destino = st.session_state.pop("tutorial_ir_para", None)
    if destino and destino != pagina_atual:
        st.switch_page(PAGINAS_DO_MENU[destino])
    estado = st.session_state.get("tutorial")
    if not estado:
        return
    objetivo = tutorial.OBJETIVOS[estado["objetivo"]]
    roteiro = tutorial.passos(objetivo.chave)
    passo = tutorial.passo_atual(objetivo.chave, estado["passo"])
    feitos = acoes_feitas()
    cumprido = tutorial.pode_continuar(passo, feitos)
    with st.container(border=True, key="tl-tutorial"):
        st.caption(
            f"Tutorial · {objetivo.nome_do_roteiro} · passo {estado['passo'] + 1} de "
            f"{len(roteiro)}"
        )
        st.progress((estado["passo"] + 1) / len(roteiro))
        st.markdown(f"**{passo.titulo}**")
        st.markdown(passo.texto)
        if passo.chave == "explore" and c is not None and pagina_atual == "visao_geral":
            if st.button(
                "Mostrar como ler", icon=":material/lightbulb:", key="tut_ler"
            ):
                marcar_feito("leu_os_numeros")
                cumprido = True
            if "leu_os_numeros" in acoes_feitas():
                _explicar_dois_numeros(c)
        if passo.chave == "pronto" and objetivo.chave == tutorial.ANALISAR:
            col_fav, col_outro = st.columns(2)
            ticker = normalizar_ticker(st.session_state.get("ticker", ""))
            if ticker not in st.session_state.get("favoritos", []):
                col_fav.button(
                    f"Adicionar {ticker} aos favoritos",
                    icon=":material/star:",
                    key="tut_favoritar",
                    on_click=_alternar_favorito_atual,
                )
            col_outro.button(
                "Analisar outro ativo",
                icon=":material/search:",
                key="tut_outro",
                on_click=_ir_pelo_tutorial,
                args=("inicio",),
            )
        if not cumprido:
            st.caption(f"Falta: {passo.pendente}")
            if passo.pagina != pagina_atual:
                st.button(
                    f"Ir para {pagina(passo.pagina).titulo}",
                    icon=":material/arrow_forward:",
                    key="tut_ir",
                    on_click=_ir_pelo_tutorial,
                    args=(passo.pagina,),
                )
        col_voltar, col_seguir, col_pular = st.columns([1, 1, 1])
        col_voltar.button(
            "Voltar",
            icon=":material/arrow_back:",
            key="tut_voltar",
            disabled=estado["passo"] == 0,
            on_click=_andar_no_tutorial,
            args=(-1,),
            width="stretch",
        )
        ultimo = estado["passo"] == len(roteiro) - 1
        col_seguir.button(
            "Concluir" if ultimo else "Continuar",
            type="primary",
            icon=":material/check:" if ultimo else ":material/arrow_forward:",
            key="tut_seguir",
            disabled=not cumprido,
            on_click=_andar_no_tutorial,
            args=(1,),
            width="stretch",
        )
        col_pular.button(
            "Pular tutorial",
            key="tut_pular",
            on_click=_encerrar_tutorial,
            args=(False,),
            width="stretch",
        )
    destino = st.session_state.pop("tutorial_ir_para", None)
    if destino and destino != pagina_atual:
        st.switch_page(PAGINAS_DO_MENU[destino])


def mostrar_portas_de_entrada():
    """'O que você quer fazer hoje?': três objetivos, não três níveis técnicos."""
    st.subheader("O que você quer fazer hoje?")
    for i, (coluna, objetivo) in enumerate(
        zip(st.columns(3), tutorial.OBJETIVOS.values(), strict=True)
    ):
        with coluna, st.container(border=True, height=176, key=f"tl-cartao-porta-{i}"):
            st.markdown(f"#### {objetivo.icone} {objetivo.titulo}")
            st.caption(objetivo.descricao)
            st.button(
                "Começar",
                key=f"tut_porta_{objetivo.chave}",
                icon=":material/play_arrow:",
                on_click=_comecar_tutorial,
                args=(objetivo.chave,),
            )
    st.button(
        "Pular: já sei usar",
        key="tut_pular_portas",
        on_click=_encerrar_tutorial,
        args=(False,),
        type="tertiary",
    )


def mostrar_lista_de_tarefas():
    """Três primeiras ações, discretas; some quando tudo foi feito ou quando a pessoa esconde."""
    if st.session_state.get("checklist_escondido"):
        return
    feitos = acoes_feitas()
    if not tutorial.tarefas_pendentes(feitos):
        return
    with st.container(border=True, key="tl-primeiros-passos"):
        col_titulo, col_esconder = st.columns([4, 1], vertical_alignment="center")
        col_titulo.markdown(
            f"**Primeiros passos** · {len(tutorial.TAREFAS) - len(tutorial.tarefas_pendentes(feitos))} "
            f"de {len(tutorial.TAREFAS)}"
        )
        if col_esconder.button("Esconder", key="tut_esconder", type="tertiary"):
            st.session_state["checklist_escondido"] = True
            st.rerun()
        for tarefa in tutorial.TAREFAS:
            if tarefa.chave in feitos:
                st.markdown(f":material/check_circle: ~~{tarefa.rotulo}~~")
            else:
                st.page_link(
                    PAGINAS_DO_MENU[tarefa.pagina],
                    label=tarefa.rotulo,
                    icon=":material/radio_button_unchecked:",
                )
