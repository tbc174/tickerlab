"""Estúdio de relatórios (blueprint, seção 12): modelos, seções, prévia e o PDF.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from src import analise as research_analise
from src import estilos_pdf, previa_pdf, relatorio_newsletter, relatorios
from src.backtest import CUSTO_PADRAO_POR_OPERACAO
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import (
    carregar_preferencias,
    contar_relatorios_recentes,
    registrar_relatorio,
    salvar_preferencias,
)
from src.banco.pdfs_originais import guardar_pdf_original, pode_guardar
from src.carteira_b3 import ArquivoDaB3Error, ler_carteira
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA, MIN_ATIVOS_NA_CARTEIRA
from src.comparacao import alinhar_fechamentos, escolher_ativos, interpretar_tickers
from src.dados import DadosIndisponiveisError
from src.estrategias import ESTRATEGIAS
from src.planos import LimiteDoPlanoError, limites_do
from telas.comum import (
    PAGINAS_DO_MENU,
    PERIODOS_DO_TOPO,
    carregar_dados,
    marcar_feito,
    plano_atual,
)
from telas.research.comum import _carteira_da_lista, _listas_do_research
from telas.research.newsletter import JANELAS_DA_NEWSLETTER, _edicao


def atalho_para_o_relatorio(tipo, rotulo="Gerar relatório desta análise", chave=None):
    """Botão que abre "Gerar relatório" já no tipo certo (páginas de análise e Início)."""

    def ir():
        st.session_state["tipo_de_relatorio"] = tipo
        st.session_state["ir_para_relatorio"] = True

    st.button(
        rotulo,
        icon=":material/picture_as_pdf:"
        if chave is None
        else ":material/arrow_forward:",
        key=chave or f"atalho_relatorio_{tipo}",
        on_click=ir,
        type="tertiary" if chave else "secondary",
    )
    if st.session_state.pop("ir_para_relatorio", False):
        st.switch_page(PAGINAS_DO_MENU["relatorio"])


def _uso_de_relatorios(usuario, limites):
    """Quantos relatórios a pessoa ainda pode gerar hoje (texto) e se já chegou ao limite."""
    if usuario is None or limites.relatorios_por_dia is None:
        return "Relatórios sem limite no seu plano.", False
    try:
        with obter_engine().connect() as conexao:
            feitos = contar_relatorios_recentes(conexao, usuario.id)
    except Exception:
        logging.getLogger(__name__).exception("Falha ao contar os relatórios")
        return "Não consegui conferir quantos relatórios você já gerou.", False
    maximo = limites.relatorios_por_dia
    texto = (
        f"Você gerou {feitos} de {maximo} relatórios nas últimas 24 horas "
        f"(plano {limites.nome})."
    )
    return texto, feitos >= maximo


def _baixar_fechamentos(tickers, periodo):
    fechamentos, falharam = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except (DadosIndisponiveisError, ValueError):
            falharam.append(ticker)
    return fechamentos, falharam


# Configurar → pré-visualizar → gerar → revisar → exportar. A prévia é o próprio PDF (só a capa e
# a primeira página) e não conta no limite do plano; só "Gerar relatório" conta.
PERSONALIZADO = "personalizado"


# parents[2]: a raiz do projeto (este arquivo está em telas/relatorios/; no Docker, /app)
ARQUIVO_DA_CARTEIRA_DE_EXEMPLO = (
    Path(__file__).parents[2] / "conteudo" / "carteira_de_exemplo.xlsx"
)


NOMES_DOS_MODELOS = {**relatorios.MODELOS, PERSONALIZADO: "Personalizado"}


PAGINAS_DA_PREVIA = 2


MAX_PREVIAS_GUARDADAS = 6


@dataclass
class PedidoDeRelatorio:
    """O que o estúdio precisa saber do relatório escolhido, antes de gerar."""

    tipo: str
    arquivo: str
    titulo: str
    parametros: dict  # vão para a biblioteca (da carteira da B3, nem os ativos)
    identidade: (
        str  # muda quando o conteúdo muda: chave da prévia e trava de clique duplo
    )
    montar: object  # (config, ao_avancar) -> bytes do PDF


def _pedido(tipo, c, arquivo, titulo, parametros, montar, extra=""):
    exemplo = bool(st.session_state.get("usar_exemplo"))
    identidade = json.dumps(
        {
            "tipo": tipo,
            "parametros": parametros,
            "taxa": c.taxa_livre_de_risco,
            "reais": bool(st.session_state.get("em_reais")),
            "exemplo": exemplo,
            "extra": extra,
            "dia": f"{relatorios.agora():%Y-%m-%d}",
        },
        sort_keys=True,
        default=str,
    )
    return PedidoDeRelatorio(tipo, arquivo, titulo, parametros, identidade, montar)


def _montar_relatorio(tipo, c):
    """Mostra os campos do tipo escolhido e devolve o pedido (ou None se faltar algo)."""
    exemplo = bool(st.session_state.get("usar_exemplo"))
    rotulo = PERIODOS_DO_TOPO.get(c.periodo, c.periodo)
    base = {
        "taxa_livre_de_risco": c.taxa_livre_de_risco,
        "periodo": rotulo,
        "exemplo": exemplo,
    }
    comuns = {"ticker": c.ticker, "periodo": c.periodo}
    if tipo == relatorios.MINHA_CARTEIRA:
        return _montar_minha_carteira(c, base)
    if tipo == relatorios.NEWSLETTER:
        return _montar_newsletter(c)
    if tipo == relatorios.ATIVO:
        return _montar_ativo(tipo, c, base, comuns, rotulo)
    if tipo == relatorios.COMPARACAO:
        return _montar_comparacao(tipo, c, base, comuns)
    if tipo == relatorios.BACKTEST:
        return _montar_backtest(tipo, c, base, comuns)
    return _montar_carteira(tipo, c, base)


def _montar_ativo(tipo, c, base, comuns, rotulo):
    """Relatório do ativo do topo: o ativo e o período vêm da página."""
    st.caption(f"Ativo e período do topo da página: **{c.ticker}**, {rotulo}.")

    def montar(config, ao_avancar):
        return relatorios.relatorio_do_ativo(
            c.ticker, c.dados, **base, config=config, ao_avancar=ao_avancar
        )

    return _pedido(
        tipo,
        c,
        f"tickerlab-{c.ticker}.pdf",
        f"{c.ticker}: retorno, risco e comportamento",
        comuns,
        montar,
    )


def _montar_comparacao(tipo, c, base, comuns):
    """Comparação do ativo do topo com outros (pelo menos um)."""
    texto = st.text_input(
        "Comparar com (separe por vírgula)",
        value="^BVSP, ^GSPC",
        key="relatorio_comparar_com",
        help="O ativo do topo entra primeiro. Exemplo: VALE3.SA, ^BVSP, AAPL.",
    )
    outros, _ = escolher_ativos([c.ticker], interpretar_tickers(texto))
    if len(outros) < 2:
        st.info("Escolha pelo menos um ativo para comparar.")
        return None

    def montar(config, ao_avancar):
        if ao_avancar:
            ao_avancar("Preparando dados")
        fechamentos, falharam = _baixar_fechamentos(outros, c.periodo)
        if falharam:
            st.warning(f"Sem dados, ficaram de fora: {', '.join(falharam)}.")
        alinhado, _ = alinhar_fechamentos(fechamentos)
        return relatorios.relatorio_de_comparacao(
            alinhado, **base, config=config, ao_avancar=ao_avancar
        )

    return _pedido(
        tipo,
        c,
        "tickerlab-comparacao.pdf",
        "Comparação: " + ", ".join(outros),
        {**comuns, "comparar_com": texto},
        montar,
    )


def _montar_backtest(tipo, c, base, comuns):
    """Backtest de uma estratégia com os parâmetros padrão e o custo escolhido."""
    col_estrategia, col_custo = st.columns([2, 1])
    nome = col_estrategia.selectbox(
        "Estratégia (com os parâmetros padrão)",
        [n for n in ESTRATEGIAS if n != "Comprar e segurar"],
        key="relatorio_estrategia",
        help="Para mudar os parâmetros, use a página Backtest; o relatório usa os padrões.",
    )
    custo = (
        col_custo.number_input(
            "Custo por operação (%)",
            min_value=0.0,
            max_value=2.0,
            value=CUSTO_PADRAO_POR_OPERACAO * 100,
            step=0.05,
            key="relatorio_custo",
        )
        / 100
    )

    def montar(config, ao_avancar):
        return relatorios.relatorio_de_backtest(
            c.ticker, c.dados, nome, {}, custo, **base, config=config,
            ao_avancar=ao_avancar,
        )  # fmt: skip

    return _pedido(
        tipo,
        c,
        f"tickerlab-backtest-{c.ticker}.pdf",
        f"Backtest: {nome} em {c.ticker}",
        {**comuns, "estrategia": nome, "custo": round(custo * 100, 4)},
        montar,
    )


def _montar_carteira(tipo, c, base):
    """Carteira com vários ativos e uma estratégia de carteira."""
    limites = limites_do(plano_atual())
    texto = st.text_input(
        f"Ativos da carteira (de {MIN_ATIVOS_NA_CARTEIRA} a {limites.ativos_na_carteira}, "
        "separe por vírgula)",
        value=f"{c.ticker}, VALE3.SA, ITUB4.SA, WEGE3.SA",
        key="relatorio_carteira_ativos",
    )
    ativos = list(dict.fromkeys(interpretar_tickers(texto)))[
        : limites.ativos_na_carteira
    ]
    nome = st.selectbox(
        "Estratégia da carteira",
        list(ESTRATEGIAS_DE_CARTEIRA),
        key="relatorio_carteira",
    )
    if len(ativos) < MIN_ATIVOS_NA_CARTEIRA:
        st.info(f"Escolha pelo menos {MIN_ATIVOS_NA_CARTEIRA} ativos.")
        return None

    def montar(config, ao_avancar):
        if ao_avancar:
            ao_avancar("Preparando dados")
        fechamentos, falharam = _baixar_fechamentos(ativos, c.periodo)
        if falharam:
            st.warning(f"Sem dados, ficaram de fora: {', '.join(falharam)}.")
        tabela = pd.DataFrame(fechamentos).dropna()
        return relatorios.relatorio_de_carteira(
            tabela, nome, {}, **base, config=config, ao_avancar=ao_avancar
        )

    return _pedido(
        tipo,
        c,
        "tickerlab-carteira.pdf",
        f"Carteira: {nome}",
        {"periodo": c.periodo, "ativos": texto, "estrategia_carteira": nome},
        montar,
    )


def _montar_newsletter(c):
    """Lista e período da edição; o PDF tem o mesmo conteúdo da página Newsletter."""
    listas = _listas_do_research(st.session_state.get("usuario"))
    nomes = [lista[0] for lista in listas]
    if st.session_state.get("relatorio_newsletter_lista") not in nomes:
        st.session_state.pop(
            "relatorio_newsletter_lista", None
        )  # lista apagada ou de outra conta
    st.session_state.setdefault("relatorio_newsletter_janela", 7)
    col_lista, col_janela = st.columns(2)
    escolhida = col_lista.selectbox("Lista", nomes, key="relatorio_newsletter_lista")
    janela = col_janela.selectbox(
        "Período",
        list(JANELAS_DA_NEWSLETTER),
        format_func=JANELAS_DA_NEWSLETTER.get,
        key="relatorio_newsletter_janela",
    )
    nome, tickers, _ = listas[nomes.index(escolhida)]
    carteira = _carteira_da_lista(nome)  # lida aqui, fora da montagem do PDF

    def montar(config, ao_avancar):
        if ao_avancar:
            ao_avancar("Lendo os documentos")
        edicao = _edicao(nome, tickers, janela, carteira)
        if edicao is None:
            raise ValueError("Os documentos ainda não foram coletados neste servidor.")
        return relatorio_newsletter.relatorio_da_newsletter(
            edicao, config=config, ao_avancar=ao_avancar
        )

    return _pedido(
        relatorios.NEWSLETTER,
        c,
        "tickerlab-newsletter.pdf",
        f"Newsletter: {nome}",
        {"lista": nome, "janela": janela},
        montar,
    )


def _montar_minha_carteira(c, base):
    """A carteira real da pessoa, pelo arquivo da Área do Investidor (lido só na memória)."""
    st.info(
        "**Conexão direta com a B3:** a API da Área do Investidor só atende empresas "
        "credenciadas (com CNPJ, certificado digital e contrato com a B3). Por enquanto, o "
        "caminho é o arquivo que você mesmo baixa.",
        icon=":material/link_off:",
    )
    st.markdown(
        "1. Entre na **Área do Investidor** da B3 (investidor.b3.com.br).\n"
        "2. Em **Extratos → Posição**, escolha a data e baixe a planilha em **Excel**.\n"
        "3. Envie o arquivo aqui. Ele é lido **só na memória**, para montar o relatório, e não "
        "fica guardado."
    )
    demonstracao = st.toggle(
        "Usar a carteira de exemplo (fictícia)",
        key="relatorio_carteira_exemplo",
        help="Uma posição inventada, para conhecer o relatório sem enviar a sua planilha. "
        "O PDF sai marcado como exemplo demonstrativo.",
    )
    if demonstracao:
        st.warning(
            "**Exemplo demonstrativo:** carteira fictícia, não é a sua. O PDF sai marcado "
            "como demonstração.",
            icon=":material/science:",
        )
        conteudo, nome_do_arquivo = (
            ARQUIVO_DA_CARTEIRA_DE_EXEMPLO.read_bytes(),
            (ARQUIVO_DA_CARTEIRA_DE_EXEMPLO.name),
        )
    else:
        arquivo = st.file_uploader(
            "Planilha de posição da B3", type=["xlsx", "csv"], key="arquivo_b3"
        )
        if arquivo is None:
            return None
        conteudo, nome_do_arquivo = arquivo.getvalue(), arquivo.name
    try:
        carteira = ler_carteira(conteudo, nome_do_arquivo)
    except ArquivoDaB3Error as erro:
        st.error(str(erro))
        return None
    for aviso in carteira.avisos:
        st.warning(aviso)
    if carteira.posicoes.empty:
        st.info(
            "O arquivo só tem Tesouro e renda fixa, sem ativos com cotação para analisar."
        )
        return None
    st.caption(
        f"{len(carteira.posicoes)} ativos com cotação e {len(carteira.sem_cotacao)} de "
        "Tesouro ou renda fixa encontrados no arquivo."
    )
    marcar_feito("carregou_a_carteira")

    def montar(config, ao_avancar):
        if ao_avancar:
            ao_avancar("Preparando dados")
        fechamentos, falharam = _baixar_fechamentos(
            list(carteira.posicoes["ticker"]), c.periodo
        )
        if falharam:
            st.warning(
                f"Sem histórico de preço, ficaram de fora da análise: {', '.join(falharam)}."
            )
        if not fechamentos:
            raise ValueError(
                "nenhum ativo da carteira tem histórico de preço no período"
            )
        ibovespa = _baixar_fechamentos(["^BVSP"], c.periodo)[0].get("^BVSP")
        return relatorios.relatorio_da_minha_carteira(
            carteira, pd.DataFrame(fechamentos), ibovespa, **base, config=config,
            ao_avancar=ao_avancar, demonstracao=demonstracao,
        )  # fmt: skip

    # a identidade usa um resumo do arquivo (não o conteúdo), só para saber se ele mudou
    resumo_do_arquivo = hashlib.sha256(conteudo).hexdigest()[:16]
    return _pedido(
        relatorios.MINHA_CARTEIRA,
        c,
        "tickerlab-minha-carteira.pdf",
        "Minha carteira (exemplo fictício)" if demonstracao else "Minha carteira (B3)",
        {"periodo": c.periodo, "carteira_de_exemplo": demonstracao},
        montar,
        extra=resumo_do_arquivo,
    )


# estado do estúdio: o modelo e o estilo são campos; as seções, uma ordem e uma caixa por seção
def _chave_da_secao(tipo, chave):
    return f"relatorio_secao_{tipo}_{chave}"


def _aplicar_secoes(tipo, ligadas):
    """Põe as seções `ligadas` (nesta ordem) no topo da lista; as outras seguem, desligadas."""
    todas = [s.chave for s in relatorios.SECOES[tipo]]
    ligadas = relatorios.normalizar_secoes(tipo, ligadas)
    st.session_state[f"relatorio_ordem_{tipo}"] = ligadas + [
        c for c in todas if c not in ligadas
    ]
    for chave in todas:
        st.session_state[_chave_da_secao(tipo, chave)] = chave in ligadas


def secoes_escolhidas(tipo):
    ordem = st.session_state.get(f"relatorio_ordem_{tipo}") or [
        s.chave for s in relatorios.SECOES[tipo]
    ]
    return relatorios.normalizar_secoes(
        tipo,
        [c for c in ordem if st.session_state.get(_chave_da_secao(tipo, c), True)],
    )


def _iniciar_estudio(tipo):
    """Na primeira vez de cada tipo na sessão: o modelo, o estilo e as seções salvos na conta
    (se houver) ou os padrões."""
    salvo = st.session_state.get("config_salva_do_relatorio") or {}
    if "relatorio_modelo" not in st.session_state:
        modelo = salvo.get("modelo")
        st.session_state["relatorio_modelo"] = (
            modelo if modelo in NOMES_DOS_MODELOS else relatorios.COMPLETO
        )
    if "relatorio_estilo" not in st.session_state:
        st.session_state["relatorio_estilo"] = estilos_pdf.estilo(
            salvo.get("estilo")
        ).chave
    if f"relatorio_ordem_{tipo}" not in st.session_state:
        guardadas = (salvo.get("secoes") or {}).get(tipo)
        modelo = st.session_state["relatorio_modelo"]
        _aplicar_secoes(
            tipo,
            guardadas
            if modelo == PERSONALIZADO and guardadas
            else relatorios.secoes_do_modelo(tipo, modelo),
        )


def _ao_trocar_o_modelo(tipo):
    modelo = st.session_state["relatorio_modelo"]
    if modelo != PERSONALIZADO:
        _aplicar_secoes(tipo, relatorios.secoes_do_modelo(tipo, modelo))


def _virou_personalizado():
    st.session_state["relatorio_modelo"] = PERSONALIZADO


def _mover_secao(tipo, chave, passo):
    ordem = list(st.session_state[f"relatorio_ordem_{tipo}"])
    i = ordem.index(chave)
    j = i + passo
    if 0 <= j < len(ordem):
        ordem[i], ordem[j] = ordem[j], ordem[i]
        st.session_state[f"relatorio_ordem_{tipo}"] = ordem
        _virou_personalizado()


def mostrar_secoes(tipo):
    """Uma linha por seção: caixa para incluir e botões para subir e descer (sem arrastar:
    botões funcionam com teclado e leitor de tela). As obrigatórias não podem sair."""
    obrigatorias = {s.chave for s in relatorios.SECOES[tipo] if s.obrigatoria}
    por_chave = {s.chave: s for s in relatorios.SECOES[tipo]}
    ordem = st.session_state[f"relatorio_ordem_{tipo}"]
    for i, chave in enumerate(ordem):
        secao = por_chave[chave]
        col_caixa, col_sobe, col_desce = st.columns(
            [8, 1, 1], vertical_alignment="center"
        )
        col_caixa.checkbox(
            secao.titulo + (" (obrigatória)" if chave in obrigatorias else ""),
            key=_chave_da_secao(tipo, chave),
            disabled=chave in obrigatorias,
            help=secao.descricao,
            on_change=_virou_personalizado,
        )
        col_sobe.button(
            ":material/arrow_upward:",
            key=f"estudio_sobe_{tipo}_{chave}",
            help=f"Subir {secao.titulo}",
            disabled=i == 0,
            on_click=_mover_secao,
            args=(tipo, chave, -1),
        )
        col_desce.button(
            ":material/arrow_downward:",
            key=f"estudio_desce_{tipo}_{chave}",
            help=f"Descer {secao.titulo}",
            disabled=i == len(ordem) - 1,
            on_click=_mover_secao,
            args=(tipo, chave, 1),
        )


def configuracao_atual(tipo):
    return relatorios.Configuracao(
        estilo=st.session_state.get("relatorio_estilo", "research"),
        secoes=tuple(secoes_escolhidas(tipo)),
        modelo=st.session_state.get("relatorio_modelo", relatorios.COMPLETO),
    )


def _identidade_completa(pedido, config):
    return f"{pedido.identidade}|{config.estilo}|{','.join(config.secoes or ())}"


def _previa(pedido, config):
    """O PDF da prévia (guardado na sessão: mudar de volta não gera de novo)."""
    guardadas = st.session_state.setdefault("relatorio_previas", {})
    chave = _identidade_completa(pedido, config)
    if chave not in guardadas:
        pdf = pedido.montar(config, None)
        guardadas[chave] = (
            previa_pdf.paginas_em_png(pdf, PAGINAS_DA_PREVIA),
            previa_pdf.contar_paginas(pdf),
        )
        while len(guardadas) > MAX_PREVIAS_GUARDADAS:
            guardadas.pop(next(iter(guardadas)))
    marcar_feito("viu_a_previa")
    return guardadas[chave]


def _salvar_configuracao(usuario, tipo):
    config = {
        "modelo": st.session_state.get("relatorio_modelo", relatorios.COMPLETO),
        "estilo": st.session_state.get("relatorio_estilo", "research"),
        "secoes": {
            **(
                (st.session_state.get("config_salva_do_relatorio") or {}).get("secoes")
                or {}
            ),
            tipo: secoes_escolhidas(tipo),
        },
    }
    try:
        with obter_engine().begin() as conexao:
            atuais = carregar_preferencias(conexao, usuario.id)
            salvar_preferencias(conexao, usuario.id, {**atuais, "relatorio": config})
    except Exception:
        logging.getLogger(__name__).exception("Falha ao salvar a configuração")
        st.toast("Não consegui salvar a configuração agora.", icon=":material/error:")
        return
    st.session_state["config_salva_do_relatorio"] = config
    st.toast(
        "Configuração salva: o estúdio abre assim da próxima vez.",
        icon=":material/bookmark_added:",
    )


def _guardar_original(usuario, relatorio_id, pdf, pedido):
    """Guarda o PDF como foi entregue, com as versões das fórmulas e o pedido (ADR 0021).

    Uma falha aqui não tira o PDF da pessoa: ele já está pronto para baixar; só avisa.
    """
    versoes = {
        **json.loads(pedido.identidade),
        "relatorios": relatorios.VERSAO_DOS_RELATORIOS,
        "formulas": research_analise.VERSOES_DAS_FORMULAS,
    }
    try:
        with obter_engine().begin() as conexao:
            guardar_pdf_original(
                conexao, usuario.id, relatorio_id, usuario.plano, pdf, versoes
            )
    except Exception:
        logging.getLogger(__name__).exception("Falha ao guardar o PDF original")
        st.warning(
            "O PDF está pronto, mas não consegui guardar o original na biblioteca agora."
        )


def _gerar(pedido, config, usuario):
    """Gera de verdade, mostrando as etapas reais, e registra na biblioteca."""
    with st.status("Gerando o relatório…", expanded=True) as status:

        def ao_avancar(etapa):
            status.write(f"{etapa}…")
            status.update(label=f"{etapa}…")

        try:
            ao_avancar("Preparando dados")
            pdf = pedido.montar(config, ao_avancar)
        except (DadosIndisponiveisError, ValueError) as erro:
            status.update(label="Não consegui montar o relatório", state="error")
            st.error(
                f"Não consegui montar o relatório: {erro}. Nada foi contado no seu limite; "
                "confira os campos e tente de novo."
            )
            return False
        relatorio_id = None
        if usuario is not None:  # conta só o que deu certo (o PDF já está pronto)
            status.write("Guardando na sua biblioteca…")
            parametros = {
                **pedido.parametros,
                "modelo": config.modelo,
                "estilo": config.estilo,
                "secoes": list(config.secoes or ()),
            }
            try:
                with obter_engine().begin() as conexao:
                    relatorio_id = registrar_relatorio(
                        conexao,
                        usuario.id,
                        pedido.tipo,
                        plano=usuario.plano,
                        titulo=pedido.titulo,
                        parametros=parametros,
                    )
            except LimiteDoPlanoError as erro:
                status.update(label="Limite do plano", state="error")
                st.warning(str(erro))
                return False
            except Exception:
                logging.getLogger(__name__).exception("Falha ao registrar o relatório")
                status.update(label="Não consegui registrar o relatório", state="error")
                st.error(
                    "Não consegui registrar o relatório agora. Nada foi contado no seu "
                    "limite; tente de novo em instantes."
                )
                return False
        if relatorio_id is not None and pode_guardar(pedido.tipo):
            status.write("Guardando o PDF original…")
            _guardar_original(usuario, relatorio_id, pdf, pedido)
        status.update(label="Concluído", state="complete", expanded=False)
    st.session_state["relatorio_gerado"] = {
        "identidade": _identidade_completa(pedido, config),
        "arquivo": pedido.arquivo,
        "pdf": pdf,
        "id": str(relatorio_id) if relatorio_id else None,
        "paginas": previa_pdf.contar_paginas(pdf),
    }
    st.toast("PDF pronto para baixar", icon=":material/check_circle:")
    return True


def mostrar_estudio(usuario, limites, c):
    tipo = st.segmented_control(
        "Tipo de relatório",
        list(relatorios.NOMES_DOS_RELATORIOS),
        format_func=relatorios.NOMES_DOS_RELATORIOS.get,
        default=relatorios.ATIVO,
        required=True,
        key="tipo_de_relatorio",
    )
    if tipo not in limites.tipos_de_relatorio:
        st.info(
            f"O plano {limites.nome} gera o relatório do ativo. "
            f"{relatorios.NOMES_DOS_RELATORIOS[tipo]} em PDF faz parte do plano Pro."
        )
        st.page_link(
            PAGINAS_DO_MENU["planos"],
            label="Conhecer o plano Pro",
            icon=":material/workspace_premium:",
        )
        return
    _iniciar_estudio(tipo)
    col_config, col_previa = st.columns([1, 1.15], gap="large")
    with col_config:
        st.markdown("##### 1 · Dados")
        pedido = _montar_relatorio(tipo, c)
        st.markdown("##### 2 · Modelo")
        modelo = st.segmented_control(
            "Modelo",
            list(NOMES_DOS_MODELOS),
            format_func=NOMES_DOS_MODELOS.get,
            required=True,
            key="relatorio_modelo",
            on_change=_ao_trocar_o_modelo,
            args=(tipo,),
            label_visibility="collapsed",
        )
        st.caption(
            relatorios.DESCRICAO_DOS_MODELOS.get(
                modelo, "As seções e a ordem que você escolheu abaixo."
            )
        )
        st.markdown("##### 3 · Estilo")
        estilo = st.segmented_control(
            "Estilo",
            list(estilos_pdf.ESTILOS),
            format_func=lambda e: estilos_pdf.ESTILOS[e].nome,
            required=True,
            key="relatorio_estilo",
            label_visibility="collapsed",
            on_change=marcar_feito,
            args=("trocou_o_estilo",),
        )
        st.caption(estilos_pdf.estilo(estilo).descricao + " Muda só as cores.")
        with st.expander("4 · Seções e ordem", expanded=modelo == PERSONALIZADO):
            st.caption(
                "Marque o que entra e use as setas para mudar a ordem. Mexer aqui transforma "
                "o modelo em Personalizado. Os números não mudam, só a organização."
            )
            mostrar_secoes(tipo)
    config = configuracao_atual(tipo)
    with col_previa:
        st.markdown("##### Prévia")
        if pedido is None:
            st.caption("Preencha os dados ao lado para ver a prévia.")
        else:
            try:
                imagens, total = _previa(pedido, config)
            except (DadosIndisponiveisError, ValueError) as erro:
                st.warning(f"Ainda não dá para montar a prévia: {erro}")
            else:
                st.caption(
                    f"A capa e a primeira página do PDF de verdade ({total} páginas no "
                    "total). Atualiza a cada mudança e não conta no seu limite."
                )
                with st.container(key="tl-previa"):
                    for coluna, imagem in zip(
                        st.columns(len(imagens)), imagens, strict=True
                    ):
                        coluna.image(imagem, width="stretch")
                titulos = {s.chave: s.titulo for s in relatorios.SECOES[tipo]}
                st.markdown(
                    "**Neste relatório:** "
                    + " · ".join(
                        f"{n}. {titulos[s]}" for n, s in enumerate(config.secoes, 1)
                    )
                )
    if pedido is None:
        return
    _, no_limite = _uso_de_relatorios(usuario, limites)
    gerado = st.session_state.get("relatorio_gerado")
    ja_gerado = bool(gerado) and gerado["identidade"] == _identidade_completa(
        pedido, config
    )
    with st.container(key="tl-barra-relatorio"):
        col_salvar, col_gerar, col_uso = st.columns(
            [1, 1, 2], vertical_alignment="center"
        )
        if usuario is not None:
            col_salvar.button(
                "Salvar configuração",
                icon=":material/bookmark:",
                key="estudio_salvar_config",
                help="Guarda o modelo, o estilo e as seções na sua conta.",
                on_click=_salvar_configuracao,
                args=(usuario, tipo),
                width="stretch",
            )
        if ja_gerado:
            # ja_gerado só é verdadeiro com o relatório guardado
            assert gerado is not None
            col_gerar.download_button(
                "Baixar PDF",
                data=gerado["pdf"],
                file_name=gerado["arquivo"],
                mime="application/pdf",
                icon=":material/download:",
                type="primary",
                key="baixar_pdf",
                width="stretch",
            )
        else:
            clicou = col_gerar.button(
                "Gerar relatório",
                type="primary",
                icon=":material/picture_as_pdf:",
                disabled=no_limite,
                key="gerar_pdf",
                width="stretch",
            )
        col_uso.caption(_uso_de_relatorios(usuario, limites)[0])
    if not ja_gerado and clicou and _gerar(pedido, config, usuario):
        st.rerun()  # a barra volta já com "Baixar PDF" e o uso atualizado
    if ja_gerado:
        assert gerado is not None  # idem
        col_nova, _ = st.columns([1, 3])
        if col_nova.button(
            "Nova versão",
            icon=":material/refresh:",
            key="estudio_nova_versao",
            disabled=no_limite,
            help="Gera de novo com os dados de agora (conta no limite do plano).",
        ):
            st.session_state.pop("relatorio_gerado", None)
            if _gerar(pedido, config, usuario):
                st.rerun()
        with st.expander(f"Revisar as {gerado['paginas']} páginas"):
            imagens = previa_pdf.paginas_em_png(gerado["pdf"], largura_px=420)
            for inicio in range(0, len(imagens), 3):
                for coluna, imagem in zip(
                    st.columns(3), imagens[inicio : inicio + 3], strict=False
                ):
                    coluna.image(imagem, width="stretch")
