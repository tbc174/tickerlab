"""Research: Acontecimentos (etapa 2b): documentos da CVM e da SEC por ativo e por lista.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import TypeGuard

import streamlit as st
from sqlalchemy import exc as sa_exc

from src import catalogo, relatorios, research, topicos
from src.banco import leituras as repo_leituras
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.dados_do_usuario import (
    DadosInvalidosError,
    apagar_watchlist,
    salvar_watchlist,
)
from src.banco.eventos import empresas_dos_tickers, eventos_dos_tickers, ultima_coleta
from src.conteudo import proteger_cifrao
from src.eventos import FONTE_IPE
from src.planos import LimiteDoPlanoError, limites_do
from telas.comum import (
    PAGINAS_DO_MENU,
    cabecalho_da_pagina,
    parametros_em_vigor,
    plano_atual,
)
from telas.research.comum import (
    _ainda_nao_coletado,
    _carteira_da_lista,
    _listas_do_research,
    _sem_banco_agora,
)

JANELAS_DO_RESEARCH = {7: "7 dias", 30: "30 dias", 90: "90 dias"}


NOMES_DOS_TEMAS = {
    "resultados": "Resultados",
    "proventos": "Proventos",
    "eventos": "Eventos",
    "risco": "Risco",
    "tecnica": "Técnica",
    "valuation": "Valuation",
    "fundamentos": "Fundamentos",
    "participacoes": "Participações",
}


def _analisar_do_research(ticker):
    st.session_state["ticker"] = ticker
    st.session_state["ir_para_visao_geral"] = True


def _resumos_dos_itens(itens):
    """protocolo → resumo, para os fatos relevantes da CVM já lidos (R5)."""
    protocolos = [i.evento.protocolo for i in itens if i.evento.fonte == FONTE_IPE]
    try:
        with obter_engine().connect() as conexao:
            return repo_leituras.resumos(conexao, FONTE_IPE, protocolos)
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        return {}


FATO_RELEVANTE = topicos.ROTULO_DO_FATO_RELEVANTE
ORIGEM_DO_TOPICO = {
    topicos.REGRA_DO_TITULO: "pelo título",
    topicos.REGRA_DO_TEXTO: "pelo texto",
    "modelo": "pelo modelo de linguagem",
}


def _topicos_dos_itens(itens):
    """protocolo → assunto dos fatos relevantes da CVM (leitor v2, ADR 0069; só as regras)."""
    fatos = [
        (i.evento.protocolo, i.evento.assunto)
        for i in itens
        if i.evento.fonte == FONTE_IPE and i.evento.rotulo == FATO_RELEVANTE
    ]
    try:
        with obter_engine().connect() as conexao:
            return repo_leituras.topicos_dos_fatos(conexao, FONTE_IPE, fatos)
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        return {
            protocolo: topicos.topico_do_titulo(titulo) for protocolo, titulo in fatos
        }


def _com_assunto(
    topico: topicos.LeituraDoTopico | None,
) -> TypeGuard[topicos.LeituraDoTopico]:
    """O assunto só aparece quando o leitor achou um (em "Outros" não há selo)."""
    return topico is not None and topico.principal != topicos.OUTROS


def mostrar_resumo_do_documento(resumo):
    """O resumo do algoritmo próprio (R5): frases do documento, números e assuntos."""
    if not resumo:
        return
    with st.expander("Resumo automático do documento"):
        if resumo.get("motivo"):
            st.caption(resumo["motivo"])
            return
        for frase in resumo.get("frases", []):
            st.markdown(f"- {frase}")
        detalhes = []
        if resumo.get("numeros"):
            detalhes.append("Números citados: " + "; ".join(resumo["numeros"]))
        if resumo.get("assuntos"):
            detalhes.append("Assuntos: " + ", ".join(resumo["assuntos"]))
        for detalhe in detalhes:
            st.caption(detalhe)
        st.caption(
            "Frases tiradas do próprio documento por um algoritmo do TickerLab (sem inteligência "
            "artificial): nada foi reescrito. Confira no original."
        )


def _mostrar_item(item, chave, destaque=False, resumo=None, topico=None):
    e = item.evento
    codigo = e.ticker.removesuffix(".SA")
    with st.container(border=True, key=f"tl-evento-{chave}"):
        col_texto, col_acoes = st.columns([5, 2], vertical_alignment="top")
        col_texto.markdown(
            f"**{codigo}** · {e.rotulo} · {e.publicado_em:%d/%m/%Y}"
            + ("" if destaque else f" · relevância {item.relevancia:.0%}")
            + (
                f" :blue-badge[{topicos.TOPICOS[topico.principal]}]"
                if _com_assunto(topico)
                else ""
            )
        )
        col_texto.markdown(
            e.assunto or f"{e.rotulo} de {e.empresa} (sem assunto no cadastro)."
        )
        col_texto.caption(e.empresa)
        col_acoes.link_button(
            f"Abrir na {research.SIGLAS_DAS_FONTES.get(e.fonte, 'fonte')}",
            e.link,
            icon=":material/open_in_new:",
            width="stretch",
        )
        col_acoes.button(
            f"Analisar {codigo}",
            key=f"research_analisar_{chave}",
            on_click=_analisar_do_research,
            args=(e.ticker,),
            width="stretch",
        )
        mostrar_resumo_do_documento(resumo)
        with st.expander("Por que isso aparece?"):
            for razao in item.razoes:
                st.markdown(f"- {razao}")
            if _com_assunto(topico):
                origem = ORIGEM_DO_TOPICO.get(topico.metodo, "")
                st.markdown(f"- Assunto ({origem}): “{proteger_cifrao(topico.trecho)}”")
            st.caption(
                f"Relevância {item.relevancia:.0%}: soma dos componentes (0 a 1) vezes os seus "
                "pesos da página Parâmetros. Ordena a leitura; não é nota da empresa nem "
                "sinal de compra ou venda."
            )


def _filtrar_pelo_assunto(itens, assuntos):
    """Filtro pelo assunto dos fatos relevantes; só oferece os assuntos que aparecem na lista."""
    presentes = {t.principal for t in assuntos.values() if _com_assunto(t)}
    opcoes = [nome for codigo, nome in topicos.TOPICOS.items() if codigo in presentes]
    if not opcoes:
        return itens
    escolhidos = st.multiselect(
        "Assunto dos fatos relevantes",
        opcoes,
        key="research_topicos",
        placeholder="Todos os assuntos",
        help="Lido do título e do texto de cada fato relevante, por regras fixas (leitor do "
        "TickerLab). Com algum assunto marcado, só aparecem os fatos relevantes com ele.",
    )
    if not escolhidos:
        return itens
    return [
        i for i in itens
        if (t := assuntos.get(i.evento.protocolo)) and topicos.TOPICOS[t.principal] in escolhidos
    ]  # fmt: skip


def _mostrar_gestao_das_listas(usuario, limites, lista_atual):
    if usuario is None:
        st.caption("Entre com a sua conta para criar listas com nome.")
        return
    nome_atual, tickers_atuais, id_atual = lista_atual
    with st.expander("Minhas listas"):
        aba_nova, aba_editar = st.tabs(["Nova lista", "Editar a lista aberta"])
        with aba_nova:
            nome = st.text_input("Nome", key="research_nova_nome", max_chars=60)
            tickers = st.multiselect(
                f"Ativos (até {limites.ativos_por_watchlist})",
                catalogo.simbolos(),
                format_func=catalogo.rotulo,
                key="research_nova_tickers",
                max_selections=limites.ativos_por_watchlist,
            )
            if st.button(
                "Criar lista", key="rsb_criar", icon=":material/playlist_add:"
            ):
                _gravar_lista(usuario, nome, tickers, None)
        with aba_editar:
            if id_atual is None:
                st.caption(
                    f'"{nome_atual}" não é uma lista sua: a demonstração é fixa e os '
                    "favoritos mudam pela estrela no topo das páginas."
                )
                return
            novos = st.multiselect(
                "Ativos",
                sorted({*catalogo.simbolos(), *tickers_atuais}),
                default=tickers_atuais,
                format_func=catalogo.rotulo,
                key=f"research_editar_{id_atual}",
                max_selections=limites.ativos_por_watchlist,
            )
            col_salvar, col_apagar = st.columns(2)
            if col_salvar.button(
                "Salvar a lista", key="rsb_salvar", icon=":material/save:"
            ):
                _gravar_lista(usuario, nome_atual, novos, id_atual)
            with col_apagar.popover("Apagar a lista", icon=":material/delete:"):
                st.caption(
                    f'Apagar "{nome_atual}"? Os eventos continuam na CVM e na SEC.'
                )
                if st.button("Apagar de vez", key="rsb_apagar", type="primary"):
                    try:
                        with obter_engine().begin() as conexao:
                            apagar_watchlist(conexao, usuario.id, id_atual)
                    except Exception:
                        logging.getLogger(__name__).exception("Falha ao apagar a lista")
                        st.error("Não consegui apagar a lista agora. Tente de novo.")
                        return
                    st.session_state["research_lista_pendente"] = (
                        None  # volta à primeira
                    )
                    st.rerun()


def _gravar_lista(usuario, nome, tickers, watchlist_id):
    try:
        with obter_engine().begin() as conexao:
            salvar_watchlist(
                conexao, usuario.id, nome, tickers, plano=usuario.plano,
                watchlist_id=watchlist_id,
            )  # fmt: skip
    except (DadosInvalidosError, LimiteDoPlanoError) as erro:
        st.error(str(erro))
        return
    if watchlist_id is None:  # abre a lista nova (aplicado antes de desenhar o campo)
        st.session_state["research_lista_pendente"] = " ".join(nome.split())
    st.toast("Lista salva.", icon=":material/check_circle:")
    st.rerun()


def pagina_research():
    cabecalho_da_pagina("research")
    if st.session_state.pop("ir_para_visao_geral", False):
        st.switch_page(PAGINAS_DO_MENU["visao_geral"])
    usuario = st.session_state.get("usuario")
    limites = limites_do(plano_atual())
    listas = _listas_do_research(usuario)
    nomes = [lista[0] for lista in listas]
    if "research_lista_pendente" in st.session_state:
        st.session_state["research_lista"] = st.session_state.pop(
            "research_lista_pendente"
        )
    if st.session_state.get("research_lista") not in nomes:
        st.session_state["research_lista"] = nomes[0]
    col_lista, col_janela = st.columns([2, 1])
    escolhida = col_lista.selectbox("Lista", nomes, key="research_lista")
    lista = listas[nomes.index(escolhida)]
    nome, tickers, _ = lista
    janela = col_janela.segmented_control(
        "Período",
        list(JANELAS_DO_RESEARCH),
        format_func=JANELAS_DO_RESEARCH.get,
        default=30,
        required=True,
        key="research_janela",
    )
    r = parametros_em_vigor(None)
    temas_do_usuario = list(r["newsletter.temas"])
    temas = st.pills(
        "Temas",
        list(NOMES_DOS_TEMAS),
        format_func=NOMES_DOS_TEMAS.get,
        selection_mode="multi",
        default=temas_do_usuario,
        key="research_temas",
        help="Começa com os seus temas (página Parâmetros). Sem nenhum marcado, aparecem todos.",
    )
    if nome == research.NOME_DA_DEMONSTRACAO:
        st.caption(
            "Lista de demonstração: cinco empresas grandes da B3 e duas dos EUA, com eventos "
            "reais e públicos. "
            "Nada aqui é sobre a sua carteira."
        )
    carteira = _carteira_da_lista(nome)
    if carteira is not None:
        st.caption(
            f"Fotografia da sua carteira de {carteira.enviada_em:%d/%m/%Y}: as maiores "
            "posições pesam mais na ordem (página Minha carteira)."
        )
    hoje = datetime.now(relatorios.FUSO).date()
    try:
        with obter_engine().connect() as conexao:
            ultima = ultima_coleta(conexao)
            empresas = empresas_dos_tickers(conexao, tickers)
            eventos_da_lista = eventos_dos_tickers(
                conexao,
                tickers,
                hoje - timedelta(days=janela),
                temas=temas or None,
            )
    except Exception as erro:
        if not tabela_inexistente(erro):
            logging.getLogger(__name__).exception("Falha ao ler os eventos")
            st.error(_sem_banco_agora("os eventos"))
            return
        # banco sem as tabelas do Research (modo local sem migrar): é o mesmo que não coletado
        ultima, empresas, eventos_da_lista = None, {}, []
    if ultima is None:
        st.info(
            _ainda_nao_coletado(
                "Os eventos ainda não foram coletados neste servidor.",
                [
                    "python -m scripts.atualizar_eventos",
                    "python -m scripts.atualizar_eventos_sec",
                ],
            ),
            icon=":material/schedule:",
        )
        _mostrar_gestao_das_listas(usuario, limites, lista)
        return
    if (
        ultima.tzinfo is None
    ):  # o SQLite devolve a hora sem fuso: ela foi gravada em UTC
        ultima = ultima.replace(tzinfo=UTC)
    st.caption(
        "Fontes: dados abertos da CVM (empresas da B3: fatos relevantes, comunicados, avisos, "
        "proventos, resultados e balanços entregues fora do prazo) e da SEC (empresas dos EUA: "
        "8-K, 10-K, 10-Q, avisos de atraso e participações de 5% ou mais), coletados em"
        f" {ultima.astimezone(relatorios.FUSO):%d/%m/%Y às %H:%M}. "
        "A ordem segue os seus pesos de relevância (página Parâmetros)."
    )
    sem_cobertura = [t for t in tickers if t not in empresas]
    todos = st.toggle(
        f"Mostrar todos (sem limite de {research.MAXIMO_POR_EMPRESA} por empresa)",
        key="research_todos",
        help=f"Por padrão, uma empresa não ocupa mais de {research.MAXIMO_POR_EMPRESA} lugares, "
        "para nenhuma dominar a lista.",
    )
    itens = research.ordenar(
        eventos_da_lista,
        research.pesos_da_resolucao(r.valores("relevancia")),
        temas_do_usuario,
        hoje,
        janela,
        nome,
        maximo_por_ativo=None if todos else research.MAXIMO_POR_EMPRESA,
        carteira=carteira,
    )
    if not itens:
        st.info(
            f'Nenhum evento das empresas de "{nome}" nos últimos {janela} dias'
            + (" com esses temas." if temas else ".")
        )
    else:
        assuntos = _topicos_dos_itens(itens)
        itens = _filtrar_pelo_assunto(itens, assuntos)
        resumos = _resumos_dos_itens(itens)
        st.subheader("Em destaque")
        for i, item in enumerate(itens[:3]):
            p = item.evento.protocolo
            _mostrar_item(item, f"d{i}", True, resumos.get(p), assuntos.get(p))
        if len(itens) > 3:
            st.subheader(f"Os outros {len(itens) - 3}")
            for i, item in enumerate(itens[3:], start=3):
                p = item.evento.protocolo
                _mostrar_item(
                    item, f"o{i}", resumo=resumos.get(p), topico=assuntos.get(p)
                )
    if sem_cobertura:
        st.caption(
            "Sem cobertura ainda: "
            + ", ".join(t.removesuffix(".SA") for t in sem_cobertura)
            + ". O Research lê a CVM (empresas da B3) e a SEC (ações do S&P 500); fundos, "
            "ETFs, BDRs, índices e cripto dependem de outras fontes."
        )
    _mostrar_gestao_das_listas(usuario, limites, lista)
