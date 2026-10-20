"""Página Relatório da empresa (série 2 da base de ML, PR 7; ADR 0032).

A tela só lê do banco e desenha o `Relatorio` de `src/relatorio_empresa.py`, seção por seção, na
mesma ordem do PDF e da futura API. Por enquanto só as empresas da B3 (os padrões e o FRE são da CVM).
O relatório é montado com o plano de quem vê: as seções do dossiê da base chegam trancadas (só o
título e o convite) para quem não é Pro.
"""

import logging
import re
from dataclasses import replace

import pandas as pd
import streamlit as st
from sqlalchemy import exc as sa_exc

from src import dossie, eventos_sec, graficos, relatorios
from src import o_que_os_dados_mostram as leitura_da_ficha
from src.analise_escrita.exibicao import com_analise
from src.analise_escrita.modelo_da_tela import AnaliseDaTela, ParteDaTela
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.dados_do_usuario import registrar_relatorio
from src.banco.pdfs_originais import guardar_pdf_original
from src.banco.relatorio_empresa import entradas_do_relatorio
from src.dados import normalizar_ticker
from src.fundamentos import VERSAO_DOS_FUNDAMENTOS
from src.moedas import moeda_do_ticker
from src.padroes import VERSAO_DOS_PADROES
from src.planos import LimiteDoPlanoError
from src.rastro import Rastro, como_foi_calculado
from src.relatorio_empresa import (
    Item,
    Premissas,
    Relatorio,
    Secao,
    escrever_celula,
    montar,
    nome_da_tabela,
    rotulo_da_coluna,
)
from src.relatorio_empresa_pdf import relatorio_da_empresa
from telas.comum import (
    PAGINAS_DO_MENU,
    cabecalho_da_pagina,
    carregar_contexto,
    mostrar_grafico,
    plano_atual,
)
from telas.research.comum import _ainda_nao_coletado, _sem_banco_agora

ITENS_POR_LINHA = 3
COMO_FOI_CALCULADO = "Como foi calculado"
MARCAS_DO_MARKDOWN = re.compile(r"[\\`*_\[\]$#<>|~]")
GRAFICOS = {"cascata": True, "ponte": False}  # tabela que vira gráfico → subir é bom?
CHAVE_DO_PDF = "relatorio_empresa_pdf"
SO_B3 = (
    "O relatório completo por enquanto é só das empresas da B3 (os padrões por setor e os "
    "proventos do FRE vêm da CVM). Escolha um ticker da B3 no topo; para empresas dos EUA, "
    "use a página Fundamentos."
)


def _ler(ticker: str, preco: float | None, fechamentos: pd.Series):
    """As entradas do relatório, ou None quando a página já explicou o motivo."""
    try:
        with obter_engine().connect() as conexao:
            entradas = entradas_do_relatorio(
                conexao, ticker, preco=preco, fechamentos=fechamentos
            )
    except (sa_exc.OperationalError, sa_exc.ProgrammingError) as erro:
        if tabela_inexistente(erro):
            st.info(
                _ainda_nao_coletado(
                    "As demonstrações ainda não foram coletadas neste servidor.",
                    ["python -m scripts.atualizar_fundamentos --anos 6"],
                ),
                icon=":material/schedule:",
            )
            return None
        logging.getLogger(__name__).exception("Falha ao ler o relatório da empresa")
        st.error(_sem_banco_agora("os dados da empresa"))
        return None
    if entradas is None or entradas.cnpj.startswith(eventos_sec.PREFIXO_DO_CIK):
        st.info(SO_B3, icon=":material/info:")
        return None
    if entradas.dados.contas.empty:
        st.info(
            f"Ainda não há demonstrações coletadas da {entradas.empresa}. A coleta roda uma vez "
            "por dia.",
            icon=":material/schedule:",
        )
        return None
    return entradas


def _origem(item: Item) -> str:
    """De quando é e de onde veio (a ajuda do número), e por que não compara, quando não compara."""
    partes = [
        f"Base: {item.base}." if item.base else "",
        f"Fonte: {item.fonte}." if item.fonte else "",
    ]
    return " ".join([p for p in partes if p] + [item.sem_comparacao])


def _literal(texto: str) -> str:
    """O texto sem virar Markdown (o "R$" da fórmula não abre LaTeX, o "*" não vira negrito)."""
    return MARCAS_DO_MARKDOWN.sub(r"\\\g<0>", texto)


def _como_foi_calculado(coluna, rastro: Rastro) -> None:
    """O rastro do número em um clique (item 7 do lançamento): fórmula, versão, fonte, publicação
    e o link de cada documento usado."""
    with coluna.popover(COMO_FOI_CALCULADO, icon=":material/functions:"):
        for linha in como_foi_calculado(rastro):
            texto = _literal(linha.texto)
            if linha.url:
                texto += f" ([abrir o original]({linha.url}))"
            st.markdown(f"**{linha.rotulo}:** {texto}")


def _mostrar_item(coluna, item: Item) -> None:
    ajuda = " ".join(p for p in (_origem(item), item.nota_texto) if p)
    coluna.metric(item.nome, item.texto, help=ajuda or None)  # a explicação fica no (?)
    if item.comparacao is not None:
        coluna.caption(f"Contra {item.comparacao.contra}: {item.comparacao.texto}")
    if item.motivo:
        coluna.caption(item.motivo)
    if item.nota:
        coluna.caption(f"Nota: **{item.nota}**")
    if item.rastro is not None:
        _como_foi_calculado(coluna, item.rastro)


def _titulo_da_tabela(chave: str) -> str:
    if chave in dossie.TITULOS_DAS_TABELAS:
        return dossie.titulo_da_tabela(chave)
    return nome_da_tabela(chave)


def _mostrar_secao(secao: Secao) -> None:
    st.subheader(secao.titulo)
    if secao.trancada:
        for paragrafo in secao.paragrafos:
            st.info(paragrafo, icon=":material/workspace_premium:")
        return
    grupos = leitura_da_ficha.por_lado(secao.pontos)
    if grupos:
        for coluna, (titulo, pontos) in zip(
            st.columns(len(grupos)), grupos, strict=True
        ):
            coluna.markdown(f"**{titulo}**")
            coluna.markdown("\n".join(f"- {leitura_da_ficha.frase(p)}" for p in pontos))
    for inicio in range(0, len(secao.itens), ITENS_POR_LINHA):
        linha = secao.itens[inicio : inicio + ITENS_POR_LINHA]
        for coluna, item in zip(st.columns(ITENS_POR_LINHA), linha, strict=False):
            _mostrar_item(coluna, item)
    if secao.recolhida:
        with st.expander("Ver a explicação"):
            for paragrafo in secao.paragrafos:
                st.markdown(paragrafo)
    else:
        for paragrafo in secao.paragrafos:
            st.markdown(paragrafo)
    for chave, linhas in secao.tabelas.items():
        if not linhas:
            continue
        if chave in GRAFICOS:
            passos = [(linha["passo"], float(linha["valor"])) for linha in linhas]
            mostrar_grafico(
                graficos.criar_grafico_cascata(
                    passos, nome_da_tabela(chave), subir_e_bom=GRAFICOS[chave]
                )
            )
            continue
        with st.expander(_titulo_da_tabela(chave)):
            st.dataframe(_tabela_escrita(linhas), hide_index=True, width="stretch")


def _tabela_escrita(linhas: list[dict]) -> pd.DataFrame:
    """A tabela com as células escritas como no PDF (R$ 1,2 bi; 0,35; sim/não)."""
    tabela = pd.DataFrame(linhas)
    return pd.DataFrame(
        {rotulo_da_coluna(c): [escrever_celula(v) for v in tabela[c]] for c in tabela}
    )


def _texto_do_markdown(texto: str) -> str:
    """O texto da frase sem que o `$` do "R$" vire fórmula no Markdown da página."""
    return texto.replace("$", r"\$")


def _mostrar_parte_da_analise(analise: AnaliseDaTela, parte: ParteDaTela) -> None:
    st.subheader(parte.titulo)
    for paragrafo in parte.paragrafos:
        frases = " ".join(f.com_marcas() for f in paragrafo.frases)
        rotulo = f"**{paragrafo.rotulo}:** " if paragrafo.rotulo else ""
        st.markdown(_texto_do_markdown(rotulo + frases))
    notas = analise.notas_da_parte(parte)
    if notas:
        with st.expander(f"Notas desta parte ({len(notas)})"):
            for nota in notas:
                st.markdown(_texto_do_markdown(f"**[{nota.numero}]** {nota.legenda()}"))


def _mostrar_analise(analise: AnaliseDaTela) -> None:
    """A análise escrita pelo modelo, parte por parte; cada nota numerada abre o número de origem."""
    st.header("A análise")
    st.caption(analise.aviso)
    if analise.motivo:
        st.info(
            f"Texto de reserva por regras: {analise.motivo}.",
            icon=":material/edit_note:",
        )
    for parte in analise.partes:
        _mostrar_parte_da_analise(analise, parte)
    st.header("Os dados")


def _premissas() -> Premissas:
    """As premissas do DCF, que a pessoa pode trocar (o texto do valuation diz quais valeram)."""
    padrao = Premissas()
    with st.expander("Premissas do valuation (DCF)"):
        colunas = st.columns(4)
        desconto = colunas[0].number_input(
            "Desconto ao ano (%)", 1.0, 40.0, padrao.desconto * 100, 0.5,
            key="relatorio_empresa_desconto",
        )  # fmt: skip
        crescimento = colunas[1].number_input(
            "Crescimento ao ano (%)", -20.0, 40.0, padrao.crescimento * 100, 0.5,
            key="relatorio_empresa_crescimento",
        )  # fmt: skip
        perpetuidade = colunas[2].number_input(
            "Perpetuidade (%)", 0.0, 10.0, padrao.perpetuidade * 100, 0.5,
            key="relatorio_empresa_perpetuidade",
        )  # fmt: skip
        anos = colunas[3].number_input(
            "Anos", 3, 20, padrao.anos, 1, key="relatorio_empresa_anos"
        )
        st.caption(
            "O desconto precisa ser maior que a perpetuidade. São hipóteses suas, não "
            "previsões; a tabela de sensibilidade mostra quanto o valor muda com elas."
        )
    return Premissas(
        desconto=desconto / 100,
        perpetuidade=perpetuidade / 100,
        anos=int(anos),
        crescimento=crescimento / 100,
    )


def _mostrar(relatorio: Relatorio) -> None:
    st.markdown(
        f"**{relatorio.empresa}** · {relatorio.setor or 'setor não informado'} · "
        f"CNPJ {relatorio.cnpj}"
    )
    if relatorio.em_conferencia:
        st.warning(
            "Há números desta empresa em conferência pelas regras de qualidade: veja a seção "
            "Qualidade dos dados.",
            icon=":material/fact_check:",
        )
    if relatorio.analise:
        _mostrar_analise(relatorio.analise)
    convidou = False
    for secao, seguinte in zip(
        relatorio.secoes, [*relatorio.secoes[1:], None], strict=True
    ):
        _mostrar_secao(secao)
        if secao.trancada and not (seguinte and seguinte.trancada) and not convidou:
            convidou = True
            st.page_link(  # um convite só, depois do 1º bloco de seções trancadas
                PAGINAS_DO_MENU["planos"],
                label="Conhecer o plano Pro",
                icon=":material/workspace_premium:",
            )
    st.caption("Fontes: " + "; ".join(relatorio.fontes) + ". Nada aqui é recomendação.")


def _registrar(usuario, relatorio: Relatorio, pdf: bytes) -> bool:
    """Conta o PDF no limite do plano e guarda o original (ADR 0021). False se o plano recusou
    ou o registro falhou (a página já explicou)."""
    try:
        with obter_engine().begin() as conexao:
            relatorio_id = registrar_relatorio(
                conexao,
                usuario.id,
                relatorios.EMPRESA,
                plano=usuario.plano,
                titulo=f"Relatório da empresa: {relatorio.empresa}",
                parametros={"ticker": relatorio.ticker},
            )
    except LimiteDoPlanoError as erro:
        st.warning(str(erro), icon=":material/workspace_premium:")
        st.page_link(PAGINAS_DO_MENU["planos"], label="Conhecer os planos")
        return False
    except Exception:
        logging.getLogger(__name__).exception(
            "Falha ao registrar o relatório da empresa"
        )
        st.error(
            "Não consegui registrar o relatório agora. Nada foi contado no seu limite."
        )
        return False
    versoes = {
        "relatorio": relatorios.EMPRESA,
        "ticker": relatorio.ticker,
        "relatorios": relatorios.VERSAO_DOS_RELATORIOS,
        "fundamentos": VERSAO_DOS_FUNDAMENTOS,
        "padroes": VERSAO_DOS_PADROES,
    }
    try:
        with obter_engine().begin() as conexao:
            guardar_pdf_original(
                conexao, usuario.id, relatorio_id, usuario.plano, pdf, versoes
            )
    except Exception:
        logging.getLogger(__name__).exception("Falha ao guardar o PDF original")
        st.warning(
            "O PDF está pronto, mas não consegui guardar o original na biblioteca."
        )
    return True


def _oferecer_o_pdf(relatorio: Relatorio) -> None:
    """Gera o PDF (as mesmas seções da página) e oferece o download; com conta, conta no limite."""
    if st.button(
        "Gerar o PDF",
        icon=":material/picture_as_pdf:",
        key="empresa_gerar_pdf",
    ):
        with st.spinner("Gerando o PDF…"):
            pdf = relatorio_da_empresa(relatorio)
        usuario = st.session_state.get("usuario")
        if usuario is None or _registrar(usuario, relatorio, pdf):
            st.session_state[CHAVE_DO_PDF] = {"ticker": relatorio.ticker, "pdf": pdf}
    gerado = st.session_state.get(CHAVE_DO_PDF)
    if gerado and gerado["ticker"] == relatorio.ticker:
        st.download_button(
            "Baixar o PDF",
            data=gerado["pdf"],
            file_name=f"tickerlab-empresa-{relatorio.ticker.removesuffix('.SA')}.pdf",
            mime="application/pdf",
            icon=":material/download:",
            on_click="ignore",
        )


def pagina_relatorio_empresa():
    cabecalho_da_pagina("relatorio_empresa")
    c = carregar_contexto()
    ticker = normalizar_ticker(c.ticker)
    preco = float(c.fechamento.iloc[-1]) if moeda_do_ticker(ticker) == "BRL" else None
    entradas = _ler(ticker, preco, c.fechamento if preco is not None else None)
    if entradas is None:
        return
    entradas = replace(entradas, premissas=_premissas())
    relatorio = com_analise(montar(entradas, plano_atual()), entradas, plano_atual())
    _oferecer_o_pdf(relatorio)
    _mostrar(relatorio)
    st.page_link(
        PAGINAS_DO_MENU["fundamentos"],
        label="Ver os fundamentos com os seus parâmetros",
        icon=":material/account_balance:",
    )
