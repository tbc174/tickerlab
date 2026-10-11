"""Os relatórios em PDF do TickerLab: do ativo, de comparação, de backtest e de carteira.

Cada função recebe os dados já baixados e devolve os bytes do PDF. Os números saem das MESMAS
funções que o site usa (`indicadores`, `comparacao`, `backtest`, `metricas`, `carteiras`), então o
relatório bate com a tela. Não conhece o Streamlit: quem chama é o app.py.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src import graficos_pdf as gp
from src import indicadores as ind
from src import marca
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.carteira_b3 import (
    CarteiraB3,
    numero_efetivo_de_ativos,
    retorno_com_os_pesos_de_hoje,
)
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA, simular_carteira
from src.comparacao import montar_tabela_comparativa, rebasear_para_100
from src.conteudo import carregar_glossario, descrever_pior_drawdown
from src.estrategias import ESTRATEGIAS, gerar_posicao, posicao_comprar_e_segurar
from src.metricas import resumir_desempenho
from src.relatorio_pdf import RelatorioPDF

FUSO = ZoneInfo("America/Sao_Paulo")
ATIVO = "ativo"
COMPARACAO = "comparacao"
BACKTEST = "backtest"
CARTEIRA = "carteira"
MINHA_CARTEIRA = "minha_carteira"
NOMES_DOS_RELATORIOS = {
    ATIVO: "Relatório do ativo",
    COMPARACAO: "Comparação de ativos",
    BACKTEST: "Relatório de backtest",
    CARTEIRA: "Relatório de carteira",
    MINHA_CARTEIRA: "Minha carteira (B3)",
}
AVISO_DA_MINHA_CARTEIRA = (
    "Esta análise mostra como a carteira de HOJE, com os pesos de hoje, teria se comportado no "
    "passado. Não é o seu resultado real: você comprou em outras datas e preços, e pode ter "
    "mudado a carteira no caminho. Serve para entender o risco e a concentração do que você tem."
)
AVISO_DO_BACKTEST = (
    "Um bom resultado no passado pode ser sorte: com muitas estratégias e parâmetros, alguma "
    "sempre parece ótima. No site, a página Backtest tem a validação (treino e teste, "
    "walk-forward, teste contra o acaso e Sharpe deflacionado) para separar sorte de padrão."
)


def agora() -> datetime:
    return datetime.now(FUSO)


def _o_que_e(termos: list[str]) -> dict[str, str]:
    """A primeira frase ("O que é") de cada termo do glossário do site, sem a formatação."""
    glossario = carregar_glossario()
    saida = {}
    for termo in termos:
        texto = glossario.get(termo, "")
        for linha in texto.splitlines():
            if linha.startswith("**O que é:**"):
                limpo = (
                    linha.removeprefix("**O que é:**")
                    .replace("**", "")
                    .replace("`", "")
                )
                saida[termo] = limpo.strip()
                break
    return saida


def _cor(valor: float) -> str | None:
    if pd.isna(valor) or valor == 0:
        return None
    return marca.PAPEL_ALTA if valor > 0 else marca.PAPEL_QUEDA


def _variacao(valor: float, casas: int = 1) -> str:
    """Retorno com sinal e seta (a cor sozinha não basta para quem não distingue verde e vermelho)."""
    if pd.isna(valor):
        return "—"
    return f"{marca.seta(valor)} {gp.pct_br(valor, casas, sinal=True)}"


def _numero(valor: float, casas: int = 2) -> str:
    return "—" if pd.isna(valor) else gp.numero_br(valor, casas)


def _data(d: pd.Timestamp) -> str:
    return f"{d:%d/%m/%Y}"


def _intervalo(indice: pd.Index) -> str:
    return f"{_data(indice[0])} a {_data(indice[-1])}"


def _rodape_de_dados(exemplo: bool) -> list[tuple[str, str]]:
    return [
        ("Dados", "de exemplo, guardados no projeto" if exemplo else "Yahoo Finance")
    ]


# --- 1. do ativo ----------------------------------------------------------------------------
def relatorio_do_ativo(
    ticker: str,
    dados: pd.DataFrame,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
) -> bytes:
    gerado_em = gerado_em or agora()
    fechamento = dados["Close"].dropna()
    retorno = ind.calcular_retorno_diario(fechamento)
    total = float(ind.calcular_retorno_acumulado(retorno).iloc[-1])
    data_melhor, melhor = ind.encontrar_melhor_dia(retorno)
    data_pior, pior = ind.encontrar_pior_dia(retorno)
    queda = float(ind.calcular_drawdown(fechamento).min())

    pdf = RelatorioPDF(
        f"{ticker}: retorno, risco e comportamento",
        f"Relatório do ativo {ticker}" + (f", período de {periodo}" if periodo else ""),
        gerado_em,
    )
    pdf.capa(
        [
            ("Ativo", ticker),
            ("Período", _intervalo(fechamento.index)),
            ("Pregões analisados", str(len(fechamento))),
            ("Último fechamento", gp.numero_br(float(fechamento.iloc[-1]))),
            *_rodape_de_dados(exemplo),
            ("Gerado em", f"{gerado_em:%d/%m/%Y %H:%M}"),
        ]
    )
    pdf.add_page()
    pdf.secao(
        "Números-chave", "Retorno e risco no período, depois de juntar todos os dias."
    )
    sharpe = ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco)
    pdf.cartoes(
        [
            ("Retorno total", _variacao(total), _cor(total)),
            (
                "Retorno anualizado",
                _variacao(ind.calcular_retorno_anualizado(retorno)),
                _cor(ind.calcular_retorno_anualizado(retorno)),
            ),
            (
                "Volatilidade anual",
                gp.pct_br(ind.calcular_volatilidade_anual(retorno)),
                None,
            ),
            ("Maior queda", gp.pct_br(queda), marca.PAPEL_QUEDA),
            ("Índice de Sharpe", _numero(sharpe), None),
            (
                "Dias de alta",
                gp.pct_br(ind.calcular_percentual_dias_positivos(retorno)),
                None,
            ),
            (f"Melhor dia ({_data(data_melhor)})", _variacao(melhor), _cor(melhor)),
            (f"Pior dia ({_data(data_pior)})", _variacao(pior), _cor(pior)),
        ]
    )
    pdf.imagem(gp.grafico_de_preco(fechamento, f"Preço de fechamento de {ticker}"))
    pdf.secao(
        "Risco: as quedas",
        descrever_pior_drawdown(ind.encontrar_pior_drawdown(fechamento)),
    )
    pdf.imagem(gp.grafico_de_drawdown(fechamento))
    tabela = ind.montar_tabela_retornos(ind.calcular_retorno_mensal(retorno))
    if not tabela.empty:
        pdf.secao(
            "Retorno mês a mês",
            "Verde para meses de alta, vermelho para meses de queda. A última coluna é o ano.",
        )
        pdf.imagem(gp.grafico_de_retorno_mensal(tabela))
    pdf.glossario(
        _o_que_e(
            [
                "Retorno acumulado",
                "Retorno anualizado",
                "Volatilidade",
                "Drawdown",
                "Índice de Sharpe",
                "Dias de alta",
                "Melhor e pior dia",
                "Retorno mensal",
            ]
        )
    )
    return pdf.para_bytes()


# --- 2. comparação --------------------------------------------------------------------------
def relatorio_de_comparacao(
    alinhado: pd.DataFrame,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
) -> bytes:
    """`alinhado`: fechamentos dos ativos nos mesmos dias (de `comparacao.alinhar_fechamentos`)."""
    gerado_em = gerado_em or agora()
    tickers = list(alinhado.columns)
    tabela = montar_tabela_comparativa(alinhado, taxa_livre_de_risco)
    pdf = RelatorioPDF(
        "Comparação de ativos",
        ", ".join(tickers) + (f", período de {periodo}" if periodo else ""),
        gerado_em,
    )
    pdf.capa(
        [
            ("Ativos", ", ".join(tickers)),
            ("Período", _intervalo(alinhado.index)),
            ("Pregões em comum", str(len(alinhado))),
            *_rodape_de_dados(exemplo),
            ("Gerado em", f"{gerado_em:%d/%m/%Y %H:%M}"),
        ]
    )
    pdf.add_page()
    pdf.secao(
        "Lado a lado",
        "Os mesmos números para todos, calculados só nos dias em que todos negociaram.",
    )
    linhas, cores = [], []
    for ticker, linha in tabela.iterrows():
        linhas.append(
            [
                str(ticker),
                _variacao(linha["Retorno total"]),
                _variacao(linha["Retorno anualizado"]),
                gp.pct_br(linha["Volatilidade anual"]),
                gp.pct_br(linha["Maior queda"]),
                _numero(linha["Índice de Sharpe"]),
            ]
        )
        cores.append(
            [None, _cor(linha["Retorno total"]), _cor(linha["Retorno anualizado"]), None,
             marca.PAPEL_QUEDA, None]
        )  # fmt: skip
    pdf.tabela(
        ["Ativo", "Retorno total", "Ao ano", "Volatilidade", "Maior queda", "Sharpe"],
        linhas,
        [34, 30, 26, 28, 28, 28],
        cores,
        tickers=True,
    )
    base_100 = rebasear_para_100(alinhado)
    pdf.imagem(
        gp.grafico_de_linhas(
            {t: base_100[t] for t in tickers},
            "Quanto R$ 100 viraram em cada ativo (base 100)",
            destaque=tickers[0],
        )
    )
    pdf.glossario(
        _o_que_e(
            [
                "Base 100",
                "Retorno anualizado",
                "Volatilidade",
                "Drawdown",
                "Índice de Sharpe",
            ]
        )
    )
    return pdf.para_bytes()


# --- 3. backtest ----------------------------------------------------------------------------
def _descrever_parametros(nome: str, parametros: dict) -> str:
    estrategia = ESTRATEGIAS[nome]
    valores = {**estrategia.parametros_padrao(), **parametros}
    partes = [f"{p.rotulo}: {valores[p.nome]}" for p in estrategia.parametros]
    return "; ".join(partes) if partes else "sem parâmetros"


def relatorio_de_backtest(
    ticker: str,
    dados: pd.DataFrame,
    estrategia: str,
    parametros: dict | None = None,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
) -> bytes:
    gerado_em = gerado_em or agora()
    parametros = parametros or {}
    fechamento = dados["Close"]
    resultado = executar_backtest(
        fechamento, gerar_posicao(estrategia, dados, **parametros), custo_por_operacao
    )
    referencia = executar_backtest(
        fechamento, posicao_comprar_e_segurar(dados), custo_por_operacao
    )
    resumo = resumir_desempenho(
        resultado.retorno, resultado.posicao, resultado.operacoes, taxa_livre_de_risco
    )
    resumo_ref = resumir_desempenho(
        referencia.retorno, taxa_livre_de_risco=taxa_livre_de_risco
    )

    pdf = RelatorioPDF(
        f"Backtest: {estrategia} em {ticker}",
        "E se eu tivesse seguido esta regra de compra e venda?",
        gerado_em,
    )
    pdf.capa(
        [
            ("Ativo", ticker),
            ("Estratégia", estrategia),
            ("Parâmetros", _descrever_parametros(estrategia, parametros)),
            ("Custo por operação", gp.pct_br(custo_por_operacao, 2)),
            ("Período", _intervalo(fechamento.index)),
            *_rodape_de_dados(exemplo),
        ]
    )
    pdf.add_page()
    pdf.secao(
        "Resultado",
        "A decisão de cada dia só vale no dia seguinte (sem olhar o futuro), e cada compra e "
        "venda paga o custo acima.",
    )
    total = resumo["Retorno total"]
    pdf.cartoes(
        [
            ("Retorno total da estratégia", _variacao(total), _cor(total)),
            ("Comprar e segurar", _variacao(resumo_ref["Retorno total"]),
             _cor(resumo_ref["Retorno total"])),
            ("Maior queda", gp.pct_br(resumo["Maior queda"]), marca.PAPEL_QUEDA),
            ("Índice de Sharpe", _numero(resumo["Índice de Sharpe"]), None),
            ("Tempo comprado", gp.pct_br(resumo.get("Exposição média", float("nan"))), None),
            ("Operações", str(int(resumo.get("Operações", len(resultado.operacoes)))), None),
        ]
    )  # fmt: skip
    pdf.imagem(
        gp.grafico_de_linhas(
            {
                estrategia: resultado.curva_de_capital,
                "Comprar e segurar": referencia.curva_de_capital,
            },
            "Quanto R$ 1 virou",
            destaque=estrategia,
        )
    )
    pdf.secao("Estratégia contra comprar e segurar", reservar=8 * 8 + 15)
    metricas = [
        ("Retorno total", True, True),
        ("Retorno anualizado", True, True),
        ("Volatilidade anual", True, False),
        ("Maior queda", True, False),
        ("Índice de Sharpe", False, False),
        ("Índice de Sortino", False, False),
        ("Índice de Calmar", False, False),
    ]
    linhas, cores = [], []
    for nome, em_pct, com_seta in metricas:
        a, b = resumo.get(nome, float("nan")), resumo_ref.get(nome, float("nan"))

        def formatar(v: float, em_pct: bool = em_pct, com_seta: bool = com_seta) -> str:
            if com_seta:
                return _variacao(v)
            return gp.pct_br(v) if em_pct else _numero(v)

        linhas.append([nome, formatar(a), formatar(b)])
        cores.append(
            [None, _cor(a) if com_seta else None, _cor(b) if com_seta else None]
        )
    pdf.tabela(
        ["Métrica", estrategia[:28], "Comprar e segurar"], linhas, [70, 52, 52], cores
    )
    pdf.aviso_destacado(AVISO_DO_BACKTEST)
    pdf.glossario(
        _o_que_e(
            [
                "Backtest",
                "Comprar e segurar (buy and hold)",
                "Custo de operação",
                "Look-ahead bias",
                "Overfitting (sobreajuste)",
                "Drawdown",
                "Índice de Sharpe",
            ]
        )
    )
    return pdf.para_bytes()


# --- 4. carteira ----------------------------------------------------------------------------
def relatorio_de_carteira(
    fechamentos: pd.DataFrame,
    estrategia: str,
    parametros: dict | None = None,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
) -> bytes:
    """`fechamentos`: um ativo por coluna, nos mesmos dias."""
    gerado_em = gerado_em or agora()
    parametros = parametros or {}
    tickers = list(fechamentos.columns)
    resultado = simular_carteira(
        estrategia, fechamentos, custo_por_operacao, **parametros
    )
    referencia_nome = next(iter(ESTRATEGIAS_DE_CARTEIRA))  # pesos iguais
    referencia = simular_carteira(referencia_nome, fechamentos, custo_por_operacao)
    resumo = resumir_desempenho(
        resultado.retorno, taxa_livre_de_risco=taxa_livre_de_risco
    )

    pdf = RelatorioPDF(
        f"Carteira: {estrategia}",
        f"{len(tickers)} ativos: " + ", ".join(tickers),
        gerado_em,
    )
    pdf.capa(
        [
            ("Ativos", ", ".join(tickers)),
            ("Estratégia", estrategia),
            ("Custo por operação", gp.pct_br(custo_por_operacao, 2)),
            ("Período", _intervalo(fechamentos.index)),
            *_rodape_de_dados(exemplo),
        ]
    )
    pdf.add_page()
    pdf.secao(
        "Resultado da carteira",
        "Os pesos são decididos com o que se sabia até o dia da decisão e rebalanceados com "
        "custo.",
    )
    total = resumo["Retorno total"]
    pdf.cartoes(
        [
            ("Retorno total da carteira", _variacao(total), _cor(total)),
            ("Retorno anualizado", _variacao(resumo["Retorno anualizado"]),
             _cor(resumo["Retorno anualizado"])),
            ("Volatilidade anual", gp.pct_br(resumo["Volatilidade anual"]), None),
            ("Maior queda", gp.pct_br(resumo["Maior queda"]), marca.PAPEL_QUEDA),
            ("Índice de Sharpe", _numero(resumo["Índice de Sharpe"]), None),
            ("Giro (compras + vendas)", f"{gp.numero_br(resultado.giro, 1)}× o capital", None),
        ]
    )  # fmt: skip
    curvas = {estrategia: resultado.curva_de_capital}
    if estrategia != referencia_nome:
        curvas["Pesos iguais"] = referencia.curva_de_capital
    pdf.imagem(gp.grafico_de_linhas(curvas, "Quanto R$ 1 virou", destaque=estrategia))
    pdf.imagem(gp.grafico_de_pesos(resultado.pesos))
    pdf.secao(
        "Cada ativo sozinho",
        "Para comparar: os ativos da carteira, cada um por conta.",
        reservar=8 * (len(tickers) + 1) + 15,
    )
    tabela = montar_tabela_comparativa(fechamentos.dropna(), taxa_livre_de_risco)
    linhas = [
        [str(t), _variacao(l["Retorno total"]), gp.pct_br(l["Volatilidade anual"]),
         gp.pct_br(l["Maior queda"]), _numero(l["Índice de Sharpe"])]
        for t, l in tabela.iterrows()
    ]  # fmt: skip
    cores = [[None, _cor(l["Retorno total"]), None, marca.PAPEL_QUEDA, None]
             for _, l in tabela.iterrows()]  # fmt: skip
    pdf.tabela(
        ["Ativo", "Retorno total", "Volatilidade", "Maior queda", "Sharpe"],
        linhas,
        [38, 36, 34, 32, 34],
        cores,
        tickers=True,
    )
    pdf.glossario(
        _o_que_e(["Diversificação", "Rebalanceamento", "Custo de operação", "Drawdown",
                  "Índice de Sharpe"])
    )  # fmt: skip
    return pdf.para_bytes()


# --- 5. minha carteira (arquivo da Área do Investidor da B3) ---------------------------------
def relatorio_da_minha_carteira(
    carteira: CarteiraB3,
    fechamentos: pd.DataFrame,
    referencia: pd.Series | None = None,
    taxa_livre_de_risco: float = 0.0,
    periodo: str = "",
    gerado_em: datetime | None = None,
    exemplo: bool = False,
) -> bytes:
    """`fechamentos`: um ativo da carteira por coluna (tickers com .SA); `referencia`: o Ibovespa."""
    gerado_em = gerado_em or agora()
    pesos = carteira.pesos()
    total = carteira.valor_total
    efetivo = numero_efetivo_de_ativos(pesos)
    pdf = RelatorioPDF(
        "Minha carteira",
        "A sua posição na B3: composição, concentração, risco e como ela se comportou",
        gerado_em,
    )
    pdf.capa(
        [
            ("Ativos com cotação", str(len(carteira.posicoes))),
            ("Tesouro e renda fixa", str(len(carteira.sem_cotacao))),
            ("Valor total (posição)", f"R$ {gp.numero_br(total)}"),
            ("Período analisado", _intervalo(fechamentos.dropna(how="all").index)),
            ("Fonte da posição", "arquivo da Área do Investidor da B3"),
            ("Gerado em", f"{gerado_em:%d/%m/%Y %H:%M}"),
        ]
    )
    pdf.add_page()
    pdf.secao(
        "Composição e concentração",
        "Pelo valor de hoje de cada posição (ativos com cotação na bolsa).",
    )
    maior = pesos.max() if len(pesos) else float("nan")
    tres = pesos.nlargest(3).sum() if len(pesos) else float("nan")
    pdf.cartoes(
        [
            ("Maior posição", f"{pesos.idxmax().removesuffix('.SA')}: {gp.pct_br(maior)}"
             if len(pesos) else "—", None),
            ("3 maiores juntas", gp.pct_br(tres), None),
            ("Número efetivo de ativos", gp.numero_br(efetivo, 1), None),
            ("Tesouro e renda fixa", gp.pct_br(carteira.sem_cotacao["valor"].sum() / total)
             if total else "—", None),
        ]
    )  # fmt: skip
    if len(pesos):
        pdf.imagem(
            gp.grafico_de_composicao(pesos.rename(lambda t: t.removesuffix(".SA")))
        )
    pdf.paragrafo(
        f"O número efetivo de ativos ({gp.numero_br(efetivo, 1)}) diz quantos ativos de mesmo "
        f"peso dariam a mesma concentração. Com {len(pesos)} ativos, quanto mais perto de "
        f"{len(pesos)}, mais dividido está o dinheiro.",
        apagado=True,
    )
    retorno = retorno_com_os_pesos_de_hoje(fechamentos, pesos)
    resumo = resumir_desempenho(retorno, taxa_livre_de_risco=taxa_livre_de_risco)
    pdf.secao("Como esta carteira se comportou", reservar=40)
    pdf.aviso_destacado(AVISO_DA_MINHA_CARTEIRA)
    ret = resumo["Retorno total"]
    pdf.cartoes(
        [
            ("Retorno no período", _variacao(ret), _cor(ret)),
            ("Ao ano", _variacao(resumo["Retorno anualizado"]),
             _cor(resumo["Retorno anualizado"])),
            ("Volatilidade anual", gp.pct_br(resumo["Volatilidade anual"]), None),
            ("Maior queda", gp.pct_br(resumo["Maior queda"]), marca.PAPEL_QUEDA),
            ("Índice de Sharpe", _numero(resumo["Índice de Sharpe"]), None),
        ]
    )  # fmt: skip
    curvas = {"Minha carteira": (1 + retorno).cumprod() * 100}
    if referencia is not None and not referencia.dropna().empty:
        ref = referencia.reindex(retorno.index).ffill().dropna()
        if len(ref) > 1:
            curvas["Ibovespa"] = ref / ref.iloc[0] * 100
    pdf.imagem(gp.grafico_de_linhas(curvas, "Base 100: a carteira de hoje no passado",
                                    destaque="Minha carteira"))  # fmt: skip
    pdf.secao(
        "Cada ativo",
        "O valor e o peso de hoje, e como cada um se comportou no período.",
        reservar=8 * (len(pesos) + 1) + 15,
    )
    tabela = montar_tabela_comparativa(fechamentos.dropna(), taxa_livre_de_risco)
    linhas, cores = [], []
    for _, p in carteira.posicoes.iterrows():
        dados = tabela.loc[p["ticker"]] if p["ticker"] in tabela.index else None
        r = dados["Retorno total"] if dados is not None else float("nan")
        linhas.append(
            [
                p["codigo"],
                p["tipo"][:14],
                f"R$ {gp.numero_br(p['valor'])}",
                gp.pct_br(pesos.get(p["ticker"], float("nan"))),
                _variacao(r),
                gp.pct_br(dados["Maior queda"]) if dados is not None else "—",
            ]
        )
        cores.append([None, None, None, None, _cor(r), marca.PAPEL_QUEDA])
    pdf.tabela(
        ["Ativo", "Tipo", "Valor", "Peso", "Retorno", "Maior queda"],
        linhas,
        [24, 34, 34, 22, 30, 30],
        cores,
        tickers=True,
    )
    if carteira.avisos:
        pdf.paragrafo(
            "Avisos da leitura do arquivo: " + " ".join(carteira.avisos), apagado=True
        )
    pdf.glossario(
        _o_que_e(["Diversificação", "Retorno anualizado", "Volatilidade", "Drawdown",
                  "Índice de Sharpe", "Base 100"])
    )  # fmt: skip
    return pdf.para_bytes()
