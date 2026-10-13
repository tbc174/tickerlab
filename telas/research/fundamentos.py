"""Research: Fundamentos (etapa 3c): demonstrações da CVM (B3) e do XBRL da SEC (EUA).

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging
from dataclasses import dataclass

import pandas as pd
import streamlit as st
from sqlalchemy import exc as sa_exc

from src import eventos_sec, fundamentos, graficos
from src import qualidade_texto as selo
from src.banco import leituras as repo_leituras
from src.banco import qualidade as repo_qualidade
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.demonstracoes import dados_da_empresa
from src.banco.eventos import empresas_dos_tickers
from src.dados import normalizar_ticker
from src.moedas import moeda_do_ticker
from telas.comum import (
    ajuda_do,
    avisar_parametros,
    cabecalho_da_pagina,
    carregar_contexto,
    formatar_pct,
    mostrar_grafico,
    parametros_em_vigor,
)
from telas.research.busca_na_sec import (
    mostrar_resultado_da_busca_na_sec,
    oferecer_busca_na_sec,
)
from telas.research.comum import (
    _ainda_nao_coletado,
    _dinheiro,
    _numero_br,
    _sem_banco_agora,
)

ACHADOS_A_MOSTRAR = 10  # os mais recentes; o resto fica num expansor
GRUPOS_DE_FUNDAMENTOS = (
    (
        "Resultado",
        ("receita", "lucro", "margem_bruta", "margem_ebit", "margem_liquida"),
    ),
    ("Retorno", ("roe", "roic", "conversao_de_caixa")),
    ("Endividamento", ("divida_bruta", "caixa", "divida_liquida", "divida_sobre_pl")),
    ("Crescimento", ("crescimento_receita", "crescimento_lucro")),
    ("Por ação e múltiplos", ("lpa", "vpa", "p_l", "p_vp")),
)


@dataclass(frozen=True)
class MercadoDosFundamentos:
    """O que muda na página Fundamentos entre a B3 (CVM) e os EUA (SEC)."""

    moeda: str
    simbolo: str
    regulador: str
    anual: str  # nome do relatório anual (DFP ou 10-K)
    trimestral: str
    identificador: str  # CNPJ ou CIK
    aliquota: float  # imposto usado no ROIC
    imposto: str


MERCADO_B3 = MercadoDosFundamentos(
    "BRL", "R$", "CVM", "DFP", "ITR", "CNPJ", fundamentos.ALIQUOTA_DE_IR_CS, "IR/CS"
)


MERCADO_EUA = MercadoDosFundamentos(
    "USD", "US$", "SEC", "10-K", "10-Q", "CIK", fundamentos.ALIQUOTA_DOS_EUA,
    "imposto federal",
)  # fmt: skip


def _mercado_da_empresa(chave):
    """CNPJ → B3; `CIK...` → EUA."""
    return MERCADO_EUA if chave.startswith(eventos_sec.PREFIXO_DO_CIK) else MERCADO_B3


def _nomes_dos_documentos(texto, mercado):
    """Os textos do cálculo falam em DFP e ITR; nos EUA, viram 10-K e 10-Q."""
    if mercado is MERCADO_B3 or not texto:
        return texto
    return texto.replace("DFP", mercado.anual).replace("ITR", mercado.trimestral)


def _formatar_indicador(indicador, mercado=MERCADO_B3):
    if not indicador.disponivel:
        return "—"
    valor = indicador.valor
    if indicador.unidade == fundamentos.FRACAO:
        return formatar_pct(valor)
    if indicador.unidade == fundamentos.REAIS:
        return _dinheiro(valor, mercado.simbolo)
    if indicador.unidade == fundamentos.REAIS_POR_ACAO:
        return f"{mercado.simbolo} {_numero_br(valor, 2)}"
    return _numero_br(valor, 2) + "×"


def _mostrar_grupo(titulo, chaves, resultado, mercado=MERCADO_B3):
    st.markdown(f"##### {titulo}")
    with st.container(horizontal=True):
        for chave in chaves:
            indicador = resultado[chave]
            explicacao = indicador.motivo or f"Base: {indicador.base}."
            st.metric(
                indicador.nome,
                _formatar_indicador(indicador, mercado),
                border=True,
                help=_nomes_dos_documentos(explicacao, mercado)
                + " "
                + (ajuda_do(indicador.nome) or ""),
            )
    motivos = {}
    for chave in chaves:
        indicador = resultado[chave]
        if not indicador.disponivel:
            motivos.setdefault(indicador.motivo, []).append(indicador.nome)
    for motivo, nomes in motivos.items():
        st.caption(f"{', '.join(nomes)}: {_nomes_dos_documentos(motivo, mercado)}")


def _tabela_anual_formatada(anual, simbolo="R$"):
    def coluna(nome):
        return [_dinheiro(v, simbolo) if pd.notna(v) else "—" for v in anual[nome]]

    tabela = pd.DataFrame(index=[str(a) for a in anual.index])
    tabela.index.name = "Ano"
    tabela["Receita"] = coluna("receita")
    tabela["Lucro dos acionistas"] = coluna("lucro")
    tabela["Margem líquida"] = [formatar_pct(v) for v in anual["margem_liquida"]]
    tabela["Patrimônio"] = coluna("patrimonio")
    if "divida_liquida" in anual:
        tabela["Dívida líquida"] = coluna("divida_liquida")
    return tabela


def _ler_fundamentos(ticker):
    """(empresa, dados) ou None quando a página já mostrou a mensagem do problema."""
    try:
        with obter_engine().connect() as conexao:
            empresa = empresas_dos_tickers(conexao, [ticker]).get(ticker)
            dados = dados_da_empresa(conexao, empresa[0]) if empresa else None
    except (sa_exc.OperationalError, sa_exc.ProgrammingError) as erro:
        if not tabela_inexistente(erro):
            logging.getLogger(__name__).exception("Falha ao ler as demonstrações")
            st.error(_sem_banco_agora("as demonstrações"))
            return None
        st.info(
            _ainda_nao_coletado(
                "As demonstrações ainda não foram coletadas neste servidor.",
                [
                    "python -m scripts.atualizar_fundamentos --anos 6",
                    "python -m scripts.atualizar_eventos_sec",
                ],
            ),
            icon=":material/schedule:",
        )
        return None
    except Exception:
        logging.getLogger(__name__).exception("Falha ao ler as demonstrações")
        st.error("Não consegui ler as demonstrações agora. Tente de novo em instantes.")
        return None
    if empresa is None or dados is None:  # com a empresa, os dados sempre vêm
        oferecer_busca_na_sec(ticker, "Os fundamentos")
        return None
    if dados.contas.empty:
        st.info(
            f"Ainda não há demonstrações coletadas da {empresa[1]}. A coleta roda uma vez por "
            "dia.",
            icon=":material/schedule:",
        )
        return None
    return empresa, dados


def _dia(data):
    """A data do balanço como `date` (o banco devolve `date`; o pandas, `Timestamp`)."""
    return pd.Timestamp(data).date()


def _ler_achados(chave, mercado):
    """Os achados abertos das regras de qualidade (só B3); sem a tabela ou sem banco, nenhum."""
    if mercado is not MERCADO_B3:
        return []
    try:
        with obter_engine().connect() as conexao:
            return repo_qualidade.achados_de(conexao, chave)
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        logging.getLogger(__name__).warning("Achados de qualidade indisponíveis")
        return []


def _dos_documentos_usados(achados, docs):
    usados = {
        (d, _dia(r)) for d, r in zip(docs["documento"], docs["referencia"], strict=True)
    }
    return [a for a in achados if (a.documento, a.referencia) in usados]


def _avisar_conferencia(usados):
    """O selo no topo: quantos números dos documentos usados nas contas estão em conferência."""
    if not usados:
        return
    n = len(usados)
    quantos = (
        "1 número dos documentos usados está"
        if n == 1
        else (f"{n} números dos documentos usados estão")
    )
    st.warning(
        f"{quantos} em conferência: uma regra automática pediu uma segunda olhada. Veja "
        f'"{selo.TITULO_DA_LISTA}" mais abaixo.',
        icon=":material/fact_check:",
    )


def _mostrar_dados_em_conferencia(achados):
    if not achados:
        return
    st.markdown(f"##### {selo.TITULO_DA_LISTA}")
    for achado in achados[:ACHADOS_A_MOSTRAR]:
        st.markdown(f"- {selo.texto_do_selo(achado)}")
    resto = achados[ACHADOS_A_MOSTRAR:]
    if resto:
        with st.expander(f"Mais {len(resto)} em conferência"):
            for achado in resto:
                st.markdown(f"- {selo.texto_do_selo(achado)}")
    st.caption(
        f"{selo.EXPLICACAO_DO_SELO} [As regras]({selo.URL_DAS_REGRAS}) são fixas e públicas."
    )


def _mostrar_documentos_usados(docs, mercado, achados=()):
    st.markdown("##### Documentos usados")
    contagem = selo.contagem_por_documento(achados)
    st.dataframe(
        pd.DataFrame(
            {
                "Documento": [
                    f"Anual ({mercado.anual})"
                    if d == "DFP"
                    else f"Trimestral ({mercado.trimestral})"
                    for d in docs["documento"]
                ],
                "Data do balanço": [f"{d:%d/%m/%Y}" for d in docs["referencia"]],
                f"Entregue à {mercado.regulador}": [
                    f"{d:%d/%m/%Y}" if pd.notna(d) else "—" for d in docs["recebido_em"]
                ],
                "Versão": docs["versao"].astype(int),
                "Conferência": [
                    selo.selo_do_documento(contagem, d, _dia(r))
                    for d, r in zip(docs["documento"], docs["referencia"], strict=True)
                ],
                "Abrir": docs["link"],
            }
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "Abrir": st.column_config.LinkColumn(
                "Abrir", display_text=f"na {mercado.regulador}"
            )
        },
    )


def _mostrar_mudanca_nos_riscos(chave):
    """O que mudou nos fatores de risco entre os dois últimos 10-K (R5, algoritmo próprio)."""
    try:
        with obter_engine().connect() as conexao:
            achado = repo_leituras.ultima_de_riscos(conexao, chave)
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        achado = None
    if achado is None:
        return
    _, referencia, r = achado
    st.markdown("##### Fatores de risco: o que mudou no 10-K")
    if r.get("motivo"):
        st.caption(r["motivo"])
        return
    antes = r.get("referencia_antes") or "o anterior"
    with st.container(horizontal=True):
        st.metric(
            "Texto igual ao do ano anterior",
            formatar_pct(r["semelhanca"]),
            border=True,
            help="Semelhança entre as duas seções de risco (cosseno das frequências das "
            "palavras): 100% é o mesmo texto.",
        )
        st.metric("Frases novas", r["novas_no_total"], border=True)
        st.metric(
            "Tamanho da seção (palavras)",
            f"{r['palavras_agora']:,}".replace(",", "."),
            r["palavras_agora"] - r["palavras_antes"],
            border=True,
        )
    if r.get("palavras_em_alta"):
        st.caption(
            "Palavras que mais cresceram (vezes no ano anterior → agora): "
            + ", ".join(f"**{p}** ({a} → {b})" for p, a, b in r["palavras_em_alta"])
        )
    if r.get("frases_novas"):
        with st.expander("Algumas frases novas"):
            for frase in r["frases_novas"]:
                st.markdown(f"- {frase}")
    st.caption(
        f"10-K de {referencia:%d/%m/%Y} contra o de {antes} ([atual]({r['link_agora']}), "
        f"[anterior]({r['link_antes']})). Pesquisa: empresas que mudam muito o texto dos "
        "relatórios tiveram, em média, retornos piores depois (Cohen, Malloy e Nguyen, 2020, "
        '"Lazy Prices"). É um fato a conferir no texto, não uma recomendação.'
    )


def _metodologia_dos_fundamentos(mercado):
    if mercado is MERCADO_EUA:
        acoes = (
            "ações em circulação na capa do relatório mais recente, conferidas com o lucro "
            "por ação declarado pela empresa"
        )
        fonte = (
            "Fonte: SEC (os números marcados em XBRL nos relatórios 10-K e 10-Q, "
            "`companyfacts`). Valores em dólares. Bancos e seguradoras não têm margem bruta, EBIT "
            "nem dívida comparáveis. O ano fiscal pode não coincidir com o do calendário (o da "
            "Apple termina em setembro): os 12 meses usam as datas de cada relatório."
        )
    else:
        acoes = (
            "ações em circulação (sem as de tesouraria), conferidas com o lucro por ação "
            "declarado pela empresa"
        )
        fonte = (
            "Fonte: dados abertos da CVM (DFP, ITR e cadastro). Bancos e seguradoras não têm "
            "margem bruta, EBIT nem dívida comparáveis."
        )
    return (
        f"- **12 meses:** o último {mercado.anual} + o acumulado do ano no último "
        f"{mercado.trimestral} − o mesmo período do ano anterior.\n"
        "- **Margens:** resultado bruto, EBIT e lucro divididos pela receita dos 12 meses.\n"
        "- **ROE:** lucro dos acionistas (12 meses) ÷ patrimônio dos acionistas no último "
        "balanço.\n"
        f"- **ROIC:** EBIT × (1 − {mercado.aliquota:.0%} de {mercado.imposto}) ÷ "
        "(patrimônio + dívida bruta − caixa e aplicações).\n"
        "- **Dívida:** empréstimos e financiamentos de curto e longo prazo; dívida líquida "
        "desconta o caixa e as aplicações financeiras.\n"
        f"- **Crescimento:** taxa composta anual entre os {mercado.anual} do horizonte "
        "escolhido.\n"
        f"- **Por ação:** {acoes}.\n\n"
        f"{fonte} Nada aqui é recomendação."
    )


def pagina_fundamentos():
    cabecalho_da_pagina("fundamentos")
    mostrar_resultado_da_busca_na_sec()
    c = carregar_contexto()
    r = parametros_em_vigor(c.ticker)
    ticker = normalizar_ticker(c.ticker)
    lido = _ler_fundamentos(ticker)
    if lido is None:
        return
    empresa, dados = lido
    mercado = _mercado_da_empresa(empresa[0])
    preco = (
        float(c.fechamento.iloc[-1])
        if moeda_do_ticker(ticker) == mercado.moeda
        else None
    )
    resultado = fundamentos.calcular(
        dados,
        preco,
        anos=int(r["fundamentalista.anos"]),
        roic_minimo=float(r["fundamentalista.roic_minimo"]),
        pl_maximo=float(r["fundamentalista.pl_maximo"]),
        aliquota=mercado.aliquota,
    )
    identificador = (
        str(int(empresa[0].removeprefix(eventos_sec.PREFIXO_DO_CIK)))
        if mercado is MERCADO_EUA
        else empresa[0]
    )
    st.markdown(
        f"**{resultado.empresa}** · {resultado.setor or 'setor não informado'} · "
        f"{mercado.identificador} {identificador}"
    )
    if preco is not None:
        st.caption(
            f"Múltiplos com o fechamento de {c.fechamento.index[-1]:%d/%m/%Y} "
            f"({mercado.simbolo} {_numero_br(preco, 2)}) aplicado a todas as classes de ação "
            "da empresa (aproximação)."
        )
    achados = _ler_achados(empresa[0], mercado)
    usados = _dos_documentos_usados(achados, resultado.documentos)
    _avisar_conferencia(usados)
    for nota in resultado.notas:
        st.caption(nota)
    if resultado.financeira:
        st.info(
            fundamentos.NAO_SE_APLICA_A_FINANCEIRAS, icon=":material/account_balance:"
        )
    for titulo, chaves in GRUPOS_DE_FUNDAMENTOS:
        _mostrar_grupo(titulo, chaves, resultado, mercado)
    if resultado.filtros:
        st.markdown("##### Seus filtros educacionais")
        for frase in resultado.filtros:
            st.markdown(f"- {frase}")
        st.caption(
            "Os limites vêm da página Parâmetros. Dizem se o número passa do que você escolheu; "
            "não dizem se a ação é boa, cara ou barata, nem são recomendação."
        )
    if not resultado.anual.empty:
        st.markdown("##### Ano a ano (demonstrações anuais)")
        mostrar_grafico(
            graficos.criar_grafico_fundamentos_anuais(resultado.anual, mercado.simbolo)
        )
        st.dataframe(
            _tabela_anual_formatada(resultado.anual, mercado.simbolo), width="stretch"
        )
    if not resultado.documentos.empty:
        _mostrar_documentos_usados(resultado.documentos, mercado, achados)
    _mostrar_dados_em_conferencia(achados)
    if mercado is MERCADO_EUA:
        _mostrar_mudanca_nos_riscos(empresa[0])
    with st.expander("Como estes números são calculados"):
        st.markdown(_metodologia_dos_fundamentos(mercado))
    avisar_parametros(
        r,
        (
            "fundamentalista.anos",
            "fundamentalista.roic_minimo",
            "fundamentalista.pl_maximo",
        ),
    )
