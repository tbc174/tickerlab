"""Research: Alertas compostos (etapa 6): condições sobre indicadores, avaliadas sob demanda.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import pandas as pd
import streamlit as st
from sqlalchemy import exc as sa_exc

from src import alertas
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.dados_do_usuario import (
    DadosInvalidosError,
    apagar_alerta,
    listar_alertas,
    salvar_alerta,
)
from src.dados import DadosIndisponiveisError
from src.planos import LimiteDoPlanoError, limites_do
from telas.comum import cabecalho_da_pagina, carregar_dados, plano_atual
from telas.conta.guarda import conta_da_sessao_valendo
from telas.research.comum import _listas_do_research, _sem_banco_agora

PERIODO_DOS_ALERTAS = "2y"  # o bastante para médias de 200 pregões e 50 semanas


MAX_ATIVOS_NOS_ALERTAS = 20


NOMES_DAS_PERIODICIDADES = {alertas.DIARIO: "Diário", alertas.SEMANAL: "Semanal"}


NOMES_DOS_MODOS = {
    alertas.TODAS: "Todas as condições (e)",
    alertas.QUALQUER: "Qualquer uma (ou)",
}


RESULTADOS = {True: "Disparou", False: "Não", None: "Sem dados"}


def _alertas_salvos(usuario):
    """[(id ou None, Regra)]: da conta, ou desta visita no modo local. None se o banco falhou."""
    if usuario is None:
        return [(None, regra) for regra in st.session_state.get("alertas_locais", [])]
    try:
        with obter_engine().connect() as conexao:
            return [(a.id, a.regra) for a in listar_alertas(conexao, usuario.id)]
    except (sa_exc.OperationalError, sa_exc.ProgrammingError) as erro:
        if tabela_inexistente(erro):
            return []
        logging.getLogger(__name__).exception("Falha ao ler os alertas")
        return (
            None  # quem chama diz que não conseguiu ler, nunca "você não tem alertas"
        )


def _formatar_valor_do_alerta(avaliacao):
    if avaliacao.valor is None:
        return "—"
    tipo, valor = avaliacao.condicao.tipo, avaliacao.valor
    if tipo in ("preco_acima_da_media", "preco_abaixo_da_media", "media_de_alta"):
        return f"{(valor - 1) * 100:+.1f}% da média".replace(".", ",")
    if tipo in ("queda_do_topo", "volatilidade_acima"):
        return f"{valor:.1f}%".replace(".", ",")
    if tipo == "volume_relativo_acima":
        return f"{valor:.2f}×".replace(".", ",")
    return f"{valor:.2f}".replace(".", ",")


def _detalhe_do_alerta(resultado):
    marcas = {True: "✔", False: "✘", None: "—"}
    partes = [
        f"{marcas[a.satisfeita]} {a.condicao.descrever()}: {_formatar_valor_do_alerta(a)}"
        + (f" ({a.motivo})" if a.motivo else "")
        for a in resultado.avaliacoes
    ]
    return " · ".join(partes)


def _mostrar_resultados_dos_alertas(salvos, tickers):
    linhas, avisos, falharam = [], set(), []
    for ticker in tickers[:MAX_ATIVOS_NOS_ALERTAS]:
        try:
            dados = carregar_dados(ticker, PERIODO_DOS_ALERTAS)
        except (DadosIndisponiveisError, ValueError):
            falharam.append(ticker)
            continue
        for _, regra in salvos:
            resultado = alertas.avaliar(regra, dados)
            avisos.update(a.aviso for a in resultado.avaliacoes if a.aviso)
            linhas.append(
                {
                    "Ativo": ticker.removesuffix(".SA"),
                    "Alerta": regra.nome,
                    "Resultado": RESULTADOS[resultado.disparou],
                    "Condições": _detalhe_do_alerta(resultado),
                    "Fechamento usado": max(
                        (a.barra for a in resultado.avaliacoes if a.barra), default=None
                    ),
                }
            )
    if linhas:
        tabela = pd.DataFrame(linhas)
        tabela["Fechamento usado"] = [
            f"{d:%d/%m/%Y}" if d else "—" for d in tabela["Fechamento usado"]
        ]
        disparou = int((tabela["Resultado"] == RESULTADOS[True]).sum())
        st.markdown(
            f"**{disparou}** de {len(tabela)} combinações de ativo e alerta dispararam."
        )
        st.dataframe(tabela, hide_index=True, width="stretch")
    st.caption(
        "Cada alerta usa o último fechamento disponível; ele só vale a partir do pregão "
        "seguinte. Um alerta é contexto, não ordem de compra ou venda."
    )
    for aviso in sorted(avisos):
        st.caption(aviso)
    if falharam:
        st.caption("Sem preços agora: " + ", ".join(falharam) + ".")
    if len(tickers) > MAX_ATIVOS_NOS_ALERTAS:
        st.caption(f"Só os {MAX_ATIVOS_NOS_ALERTAS} primeiros ativos da lista entram.")


def _campos_da_condicao(i):
    col_tipo, col_per, col_janela, col_limiar = st.columns([3, 1.4, 1.2, 1.2])
    tipo = col_tipo.selectbox(
        f"Condição {i + 1}",
        list(alertas.TIPOS),
        format_func=lambda c: alertas.TIPOS[c].rotulo,
        key=f"alerta_tipo_{i}",
    )
    t = alertas.TIPOS[tipo]
    periodicidade = col_per.selectbox(
        "Horizonte",
        list(NOMES_DAS_PERIODICIDADES),
        format_func=NOMES_DAS_PERIODICIDADES.get,
        key=f"alerta_periodicidade_{i}",
    )
    janela = limiar = None
    if t.janela_padrao is not None:
        janela = col_janela.number_input(
            "Janela" if tipo != "media_de_alta" else "Média rápida",
            2, 500, t.janela_padrao, key=f"alerta_janela_{i}_{tipo}",
        )  # fmt: skip
    if t.limiar_padrao is not None:
        limiar = col_limiar.number_input(
            "Média lenta" if tipo == "media_de_alta" else f"Limiar {t.unidade_do_limiar}".strip(),
            value=float(t.limiar_padrao), key=f"alerta_limiar_{i}_{tipo}",
        )  # fmt: skip
    st.caption(t.explicacao)
    return alertas.Condicao(tipo, periodicidade, janela, limiar)


def _guardar_alerta(usuario, regra):
    try:
        if usuario is None:
            regra = alertas.validar(regra)
            locais = st.session_state.setdefault("alertas_locais", [])
            if any(r.nome.lower() == regra.nome.lower() for r in locais):
                raise DadosInvalidosError(
                    f'Você já tem um alerta chamado "{regra.nome}".'
                )
            locais.append(regra)
        else:
            with obter_engine().begin() as conexao:
                salvar_alerta(conexao, usuario.id, regra, plano=usuario.plano)
    except (
        DadosInvalidosError,
        LimiteDoPlanoError,
        alertas.RegraInvalidaError,
    ) as erro:
        st.error(str(erro))
        return
    st.toast("Alerta salvo.", icon=":material/check_circle:")
    st.rerun()


def _montar_alerta(usuario, limites, quantos):
    if usuario is not None and quantos >= limites.alertas:
        st.info(
            f"O plano {limites.nome} permite {limites.alertas} "
            f"{'alerta' if limites.alertas == 1 else 'alertas'}. Apague um para criar outro.",
            icon=":material/workspace_premium:",
        )
        return
    nome = st.text_input("Nome do alerta", key="alerta_nome", max_chars=80)
    col_modo, col_quantas = st.columns([2, 1])
    modo = col_modo.radio(
        "Dispara quando",
        list(NOMES_DOS_MODOS),
        format_func=NOMES_DOS_MODOS.get,
        horizontal=True,
        key="alerta_modo",
    )
    quantas = col_quantas.number_input(
        "Condições", 1, alertas.MAXIMO_DE_CONDICOES, 2, key="alerta_quantas"
    )
    condicoes = tuple(_campos_da_condicao(i) for i in range(int(quantas)))
    if st.button(
        "Salvar alerta", icon=":material/notification_add:", key="alerta_salvar"
    ):
        _guardar_alerta(usuario, alertas.Regra(nome, condicoes, modo))


def _apagar_alerta(usuario, alerta_id, nome):
    if usuario is None:
        st.session_state["alertas_locais"] = [
            r for r in st.session_state.get("alertas_locais", []) if r.nome != nome
        ]
        return
    if not conta_da_sessao_valendo(usuario):
        return
    with obter_engine().begin() as conexao:
        apagar_alerta(conexao, usuario.id, alerta_id)


def pagina_alertas():
    cabecalho_da_pagina("alertas")
    usuario = st.session_state.get("usuario")
    limites = limites_do(plano_atual())
    salvos = _alertas_salvos(usuario)
    if salvos is None:
        st.error(_sem_banco_agora("os seus alertas"))
        return
    listas = _listas_do_research(usuario)
    nomes = [lista[0] for lista in listas]
    escolhida = st.selectbox("Avaliar nos ativos da lista", nomes, key="alertas_lista")
    _, tickers, _ = listas[nomes.index(escolhida)]
    if salvos:
        _mostrar_resultados_dos_alertas(salvos, tickers)
        with st.expander(f"Seus alertas ({len(salvos)})"):
            for i, (alerta_id, regra) in enumerate(salvos):
                col_texto, col_apagar = st.columns([5, 1], vertical_alignment="center")
                col_texto.markdown(
                    f"**{regra.nome}** · {NOMES_DOS_MODOS[regra.modo].lower()}  \n"
                    + "  \n".join(c.descrever() for c in regra.condicoes)
                )
                col_apagar.button(
                    "Apagar", key=f"alerta_apagar_{i}", icon=":material/delete:",
                    on_click=_apagar_alerta, args=(usuario, alerta_id, regra.nome),
                )  # fmt: skip
    else:
        st.info(
            'Você ainda não tem alertas. Monte o primeiro abaixo; por exemplo: "média semanal '
            'de alta" e "preço diário abaixo de um valor".',
            icon=":material/notifications:",
        )
    with st.expander("Montar um alerta", expanded=not salvos):
        _montar_alerta(usuario, limites, len(salvos))
    if usuario is None:
        st.caption("Sem conta, os alertas ficam só nesta visita.")
    with st.expander("Como os alertas funcionam"):
        st.markdown(
            "- **Condições:** cada uma olha o **diário** ou o **semanal** (a semana termina na "
            "sexta; enquanto ela não termina, a última barra semanal ainda pode mudar).\n"
            '- **Todas (e) ou qualquer uma (ou):** com "todas", basta uma condição sem dados '
            "para o alerta não disparar.\n"
            "- **Atraso:** usa o último fechamento disponível; vale a partir do pregão seguinte.\n"
            "- **Sem dados suficientes** (janela maior que o histórico, ativo sem volume), a "
            'condição aparece como "—" com o motivo, nunca como "sim".\n'
            "- Os números padrão são didáticos, não parâmetros comprovadamente bons. Um alerta "
            "não diz que algo vai acontecer e não é recomendação."
        )
