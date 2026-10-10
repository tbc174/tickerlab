"""Gráficos do app (Plotly). Só monta as figuras; quem mostra na tela é o app.py."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.indicadores import (
    NOMES_DOS_MESES,
    PiorDrawdown,
    calcular_media_movel,
    calcular_media_por_mes,
)

COR_AZUL = "#2962ff"  # cor principal do TickerLab
COR_AZUL_CLARO = "#7aa2ff"
COR_ALTA = "#26a69a"  # verde só para alta
COR_QUEDA = "#ef5350"  # vermelho só para queda
COR_INDICE = "#9aa0a6"  # índices em cinza
CORES_OUTROS_ATIVOS = [
    "#a78bfa",
    "#2dd4bf",
    "#f472b6",
    "#94a3b8",
]  # violeta, verde-água, rosa, azul-cinza
CORES_MEDIAS = ["#a78bfa", "#f472b6", "#94a3b8"]  # violeta, rosa e cinza (sem laranja)
ALTURA_PADRAO = 320
ALTURA_PRECO = 520
TIPOS_DE_GRAFICO = ("linha", "velas")
COLUNAS_DE_PRECO = ("Open", "High", "Low", "Close", "Volume")

# Com a roda do mouse ligada, rolar a página por cima de um gráfico dá zoom nele em vez de
# rolar a página (os gráficos são grandes e prendem a rolagem). Mude para True se preferir.
ZOOM_COM_A_RODA_DO_MOUSE = False

# Opções da barra de ferramentas do Plotly: use em st.plotly_chart(..., config=CONFIG_PLOTLY)
CONFIG_PLOTLY = {
    "scrollZoom": ZOOM_COM_A_RODA_DO_MOUSE,
    "displaylogo": False,
    "doubleClick": "reset+autosize",  # duplo clique volta ao zoom inicial
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "toImageButtonOptions": {"format": "png", "filename": "tickerlab", "scale": 2},
}

_BOTOES_DE_PERIODO = [
    {"count": 1, "label": "1M", "step": "month", "stepmode": "backward"},
    {"count": 3, "label": "3M", "step": "month", "stepmode": "backward"},
    {"count": 6, "label": "6M", "step": "month", "stepmode": "backward"},
    {"count": 1, "label": "1A", "step": "year", "stepmode": "backward"},
    {"step": "year", "stepmode": "todate", "label": "YTD"},
    {"step": "all", "label": "Tudo"},
]


def _estilo_base(figura: go.Figure, titulo: str | None, altura: int) -> None:
    """Visual escuro e minimalista do app, com a interação padrão (zoom e linha-guia)."""
    figura.update_layout(
        title={"text": titulo, "font": {"size": 15}} if titulo else None,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=altura,
        margin={"l": 10, "r": 10, "t": 50 if titulo else 40, "b": 10},
        hovermode="x unified",
        dragmode="zoom",
        showlegend=False,
    )
    figura.update_xaxes(
        gridcolor="rgba(255,255,255,0.04)",
        showspikes=True,  # linha vertical que acompanha o cursor
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor="rgba(255,255,255,0.35)",
    )
    figura.update_yaxes(gridcolor="rgba(255,255,255,0.08)")


def _seletor_de_periodo(a_direita: bool = False) -> dict:
    """Botões 1M a Tudo. `a_direita` os põe no canto, ao lado do título, sem cobri-lo."""
    posicao = (
        {"x": 1, "xanchor": "right", "y": 1.0, "yanchor": "bottom"} if a_direita else {}
    )
    return {
        **posicao,
        "buttons": _BOTOES_DE_PERIODO,
        "bgcolor": "rgba(255,255,255,0.06)",
        "activecolor": COR_AZUL,
        "font": {"size": 12},
    }


def _figura_base(titulo: str) -> go.Figure:
    """Figura de um painel só (drawdown, volatilidade), com botões de período."""
    figura = go.Figure()
    _estilo_base(figura, titulo, ALTURA_PADRAO)
    figura.update_xaxes(rangeselector=_seletor_de_periodo(a_direita=True))
    figura.update_yaxes(tickformat=".0%")
    return figura


def _numero_br(valor: float, casas: int = 2) -> str:
    """Formato brasileiro: 12345.6 vira "12.345,60"."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "#").replace(".", ",").replace("#", ".")


def _textos_das_velas(dados: pd.DataFrame, fechamento_anterior: pd.Series) -> list[str]:
    """Texto da dica do mouse em cada vela, em português, com a variação do dia."""
    variacao = dados["Close"] / fechamento_anterior - 1
    textos = []
    for (_, linha), var in zip(dados.iterrows(), variacao):
        texto_var = "—" if pd.isna(var) else f"{var:+.2%}".replace(".", ",")
        textos.append(
            f"Abertura: {_numero_br(linha['Open'])}<br>"
            f"Máxima: {_numero_br(linha['High'])}<br>"
            f"Mínima: {_numero_br(linha['Low'])}<br>"
            f"Fechamento: {_numero_br(linha['Close'])}<br>"
            f"Variação no dia: {texto_var}"
        )
    return textos


def criar_grafico_preco(
    dados: pd.DataFrame,
    tipo: str = "linha",
    janelas_medias: tuple[int, ...] = (),
    dias_visiveis: int | None = None,
) -> go.Figure:
    """Preço em linha ou velas, com volume embaixo, médias móveis opcionais e zoom sincronizado.

    `dias_visiveis` mostra só os últimos N dias (útil nas velas, que ficam finas demais com
    muitos dias). As médias móveis são calculadas com todo o histórico antes do recorte.
    """
    if tipo not in TIPOS_DE_GRAFICO:
        raise ValueError(
            f"Tipo de gráfico inválido: {tipo}. Use um de {TIPOS_DE_GRAFICO}."
        )
    faltando = [c for c in COLUNAS_DE_PRECO if c not in dados.columns]
    if faltando:
        raise ValueError(f"Faltam colunas nos dados: {faltando}.")
    if dias_visiveis is not None and dias_visiveis < 1:
        raise ValueError("dias_visiveis precisa ser pelo menos 1.")

    medias = {j: calcular_media_movel(dados["Close"], j) for j in janelas_medias}
    fechamento_anterior = dados["Close"].shift(1)
    if dias_visiveis is not None:
        dados = dados.tail(dias_visiveis)
        medias = {j: serie.loc[dados.index] for j, serie in medias.items()}
        fechamento_anterior = fechamento_anterior.loc[dados.index]

    figura = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.78, 0.22],
        vertical_spacing=0.03,
    )
    _estilo_base(figura, None, ALTURA_PRECO)

    if tipo == "velas":
        figura.add_trace(
            go.Candlestick(
                x=dados.index,
                open=dados["Open"],
                high=dados["High"],
                low=dados["Low"],
                close=dados["Close"],
                increasing={
                    "line": {"color": COR_ALTA, "width": 1.3},
                    "fillcolor": COR_ALTA,
                },
                decreasing={
                    "line": {"color": COR_QUEDA, "width": 1.3},
                    "fillcolor": COR_QUEDA,
                },
                whiskerwidth=0.5,
                hovertext=_textos_das_velas(dados, fechamento_anterior),
                hoverinfo="text",
                name="Preço",
            ),
            row=1,
            col=1,
        )
    else:
        figura.add_trace(
            go.Scatter(
                x=dados.index,
                y=dados["Close"],
                mode="lines",
                line={"color": COR_AZUL, "width": 2},
                hovertemplate="%{y:,.2f}",
                name="Fechamento",
            ),
            row=1,
            col=1,
        )

    for posicao, (janela, serie) in enumerate(medias.items()):
        figura.add_trace(
            go.Scatter(
                x=dados.index,
                y=serie,
                mode="lines",
                line={"color": CORES_MEDIAS[posicao % len(CORES_MEDIAS)], "width": 1.5},
                hovertemplate="%{y:,.2f}",
                name=f"MM {janela}",
            ),
            row=1,
            col=1,
        )

    # etiqueta com o último preço
    figura.add_annotation(
        x=dados.index[-1],
        y=dados["Close"].iloc[-1],
        text=_numero_br(dados["Close"].iloc[-1]),
        showarrow=False,
        xanchor="left",
        bgcolor=COR_AZUL,
        font={"color": "white", "size": 11},
        row=1,
        col=1,
    )

    # volume: verde nos dias de alta (fechou acima da abertura) e vermelho nos de queda
    cores_volume = np.where(dados["Close"] >= dados["Open"], COR_ALTA, COR_QUEDA)
    figura.add_trace(
        go.Bar(
            x=dados.index,
            y=dados["Volume"],
            marker={"color": cores_volume, "opacity": 0.55},
            hovertemplate="%{y:,.0f}",
            name="Volume",
        ),
        row=2,
        col=1,
    )

    figura.update_xaxes(
        rangeslider_visible=False, rangeselector=_seletor_de_periodo(), row=1, col=1
    )
    figura.update_yaxes(title_text="Volume", row=2, col=1)
    figura.update_layout(
        showlegend=bool(janelas_medias), legend={"orientation": "h", "y": 1.05}
    )
    if not (dados.index.dayofweek >= 5).any():  # ação: some o buraco do fim de semana
        figura.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])
    return figura


def criar_grafico_drawdown(
    drawdown: pd.Series, pior: PiorDrawdown | None = None
) -> go.Figure:
    """Área abaixo de zero com a queda de cada dia; marca o fundo da pior queda."""
    figura = _figura_base("Drawdown: distância do último topo")
    figura.add_trace(
        go.Scatter(
            x=drawdown.index,
            y=drawdown,
            mode="lines",
            fill="tozeroy",
            line={"color": COR_QUEDA, "width": 1.5},
            fillcolor="rgba(239, 83, 80, 0.25)",
            hovertemplate="%{y:.2%}",
            name="Drawdown",
        )
    )
    if pior is not None and pior.data_fundo is not None:
        figura.add_trace(
            go.Scatter(
                x=[pior.data_fundo],
                y=[pior.queda],
                mode="markers+text",
                marker={"color": COR_QUEDA, "size": 9},
                text=[f"{pior.queda:.1%}".replace(".", ",")],
                textposition="bottom center",
                hovertemplate="Pior queda: %{y:.2%}",
                name="Pior queda",
            )
        )
    return figura


def criar_grafico_volatilidade(vol_movel: pd.Series, janela: int) -> go.Figure:
    """Linha da volatilidade anualizada numa janela móvel de `janela` dias."""
    figura = _figura_base(f"Volatilidade móvel ({janela} dias, anualizada)")
    figura.add_trace(
        go.Scatter(
            x=vol_movel.index,
            y=vol_movel,
            mode="lines",
            line={"color": COR_AZUL, "width": 2},
            hovertemplate="%{y:.1%}",
            name="Volatilidade",
        )
    )
    return figura


def _pct_br(valor: float, com_sinal: bool = True) -> str:
    """Porcentagem no estilo brasileiro com 1 casa; vazio vira um traço."""
    if pd.isna(valor):
        return "—"
    texto = f"{valor:+.1%}" if com_sinal else f"{valor:.1%}"
    return texto.replace(".", ",")


def criar_mapa_de_calor_mensal(tabela: pd.DataFrame) -> go.Figure:
    """Grade de retornos: um ano por linha, os 12 meses em colunas e uma linha de médias.

    O total de cada ano aparece no rótulo da linha. As cores vão do vermelho (queda)
    ao verde (alta), com o preto no zero.
    """
    if tabela.empty:
        raise ValueError("Tabela de retornos vazia: não há o que mostrar.")

    meses = list(NOMES_DOS_MESES)
    grade = tabela[meses].copy()
    rotulos = [f"{ano}  ({_pct_br(tabela.loc[ano, 'Ano'])})" for ano in tabela.index]
    grade.index = rotulos
    grade.loc["Média do mês"] = calcular_media_por_mes(tabela)

    valores = grade.to_numpy(dtype=float)
    textos = [[_pct_br(v) for v in linha] for linha in valores]
    # limite das cores: um mês excepcional não pode "apagar" os outros
    limite = max(float(np.nanpercentile(np.abs(valores), 95)), 0.01)

    figura = go.Figure(
        go.Heatmap(
            z=valores,
            x=meses,
            y=list(grade.index),
            text=textos,
            texttemplate="%{text}",
            textfont={"size": 12},
            zmin=-limite,
            zmax=limite,
            colorscale=[[0, "#b71c1c"], [0.5, "#161616"], [1, "#1b8f6a"]],
            xgap=2,
            ygap=2,
            showscale=False,
            hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>",
        )
    )
    figura.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=90 + 38 * len(grade),
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis={"side": "top", "fixedrange": True},
        yaxis={"autorange": "reversed", "fixedrange": True},
        dragmode=False,
    )
    return figura


def criar_grafico_comparacao(
    base100: pd.DataFrame, principal: str, nomes: dict[str, str] | None = None
) -> go.Figure:
    """Linhas de desempenho de vários ativos, todos começando em 100.

    O ativo principal fica em azul; os índices (começam com "^") em cinza, e o S&P 500 tracejado;
    os demais usam cores fixas, na ordem em que aparecem.
    """
    if base100.empty:
        raise ValueError("Não há dias em comum para comparar.")
    nomes = nomes or {}
    figura = _figura_base("Desempenho (base 100 no primeiro dia em comum)")
    figura.update_yaxes(tickformat=",.0f")
    figura.add_hline(y=100, line_dash="dot", line_color="rgba(255,255,255,0.25)")

    proxima_cor = 0
    for ticker in base100.columns:
        linha = {"width": 2}
        if ticker == principal:
            linha["color"] = COR_AZUL
            linha["width"] = 2.5
        elif ticker.startswith("^"):
            linha["color"] = COR_INDICE
            if ticker == "^GSPC":
                linha["dash"] = "dash"
        else:
            linha["color"] = CORES_OUTROS_ATIVOS[proxima_cor % len(CORES_OUTROS_ATIVOS)]
            proxima_cor += 1
        figura.add_trace(
            go.Scatter(
                x=base100.index,
                y=base100[ticker],
                mode="lines",
                line=linha,
                hovertemplate="%{y:,.1f}",
                name=nomes.get(ticker, ticker),
            )
        )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura


def criar_mapa_de_calor_de_parametros(
    mapa: pd.DataFrame,
    rotulo_x: str,
    rotulo_y: str | None = None,
    escolhido: tuple | None = None,
) -> go.Figure:
    """Sharpe de cada combinação de parâmetros: verde acima de zero, vermelho abaixo.

    `escolhido` é o par (x, y) em uso no momento; ele ganha uma moldura para a pessoa
    ver onde a escolha dela está na paisagem. Combinações sem resultado ficam vazias.
    """
    if mapa.empty:
        raise ValueError("O mapa está vazio: não há o que mostrar.")
    valores = mapa.to_numpy(dtype=float)
    colunas = [str(c) for c in mapa.columns]
    linhas = [str(i) for i in mapa.index]
    textos = [
        ["" if np.isnan(v) else _numero_br(v) for v in linha] for linha in valores
    ]
    limite = (
        max(float(np.nanmax(np.abs(valores))), 0.1)
        if not np.all(np.isnan(valores))
        else 1.0
    )

    figura = go.Figure(
        go.Heatmap(
            z=valores,
            x=colunas,
            y=linhas,
            text=textos,
            texttemplate="%{text}",
            textfont={"size": 12},
            zmin=-limite,
            zmax=limite,
            colorscale=[[0, "#b71c1c"], [0.5, "#161616"], [1, "#1b8f6a"]],
            xgap=2,
            ygap=2,
            showscale=False,
            hovertemplate=(
                f"{rotulo_x}: %{{x}}"
                + (f"<br>{rotulo_y}: %{{y}}" if rotulo_y else "")
                + "<br>Sharpe: %{text}<extra></extra>"
            ),
        )
    )
    if escolhido is not None and str(escolhido[0]) in colunas:
        y = str(escolhido[1]) if rotulo_y else ""
        if y in linhas:
            figura.add_trace(
                go.Scatter(
                    x=[str(escolhido[0])],
                    y=[y],
                    mode="markers",
                    marker={
                        "symbol": "square-open",
                        "size": 34,
                        "color": COR_AZUL_CLARO,
                        "line": {"width": 3},
                    },
                    hoverinfo="skip",
                )
            )
    figura.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(150, 90 + 46 * len(linhas)),
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis={
            "title": rotulo_x,
            "side": "top",
            "fixedrange": True,
            "type": "category",
        },
        yaxis={
            "title": rotulo_y or "",
            "autorange": "reversed",
            "fixedrange": True,
            "type": "category",
            "showticklabels": bool(rotulo_y),
        },
        showlegend=False,
        dragmode=False,
    )
    return figura


def criar_grafico_cone_monte_carlo(
    percentis: pd.DataFrame, observada: np.ndarray
) -> go.Figure:
    """Cone de curvas possíveis (faixas de 5-95% e 25-75%) com a ordem real em azul."""
    if percentis.empty:
        raise ValueError("Não há simulações para mostrar.")
    x = list(percentis.index)
    figura = _figura_base("Capital depois de cada operação (simulações)")
    figura.update_layout(
        hovermode="x unified", showlegend=True, legend={"orientation": "h", "y": -0.18}
    )
    figura.update_xaxes(title="Número da operação")
    for baixo, alto, rotulo, cor in (
        ("p5", "p95", "5% a 95%", "rgba(154,160,166,0.18)"),
        ("p25", "p75", "25% a 75%", "rgba(154,160,166,0.32)"),
    ):
        figura.add_trace(
            go.Scatter(
                x=x,
                y=percentis[alto],
                mode="lines",
                line={"width": 0},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        figura.add_trace(
            go.Scatter(
                x=x,
                y=percentis[baixo],
                mode="lines",
                line={"width": 0},
                fill="tonexty",
                fillcolor=cor,
                name=rotulo,
                hoverinfo="skip",
            )
        )
    figura.add_trace(
        go.Scatter(
            x=x,
            y=percentis["p50"],
            mode="lines",
            name="Mediana",
            line={"color": COR_INDICE, "width": 1.8, "dash": "dot"},
            hovertemplate="%{y:.2f}x",
        )
    )
    figura.add_trace(
        go.Scatter(
            x=list(range(len(observada))),
            y=observada,
            mode="lines",
            name="Ordem real",
            line={"color": COR_AZUL, "width": 2.5},
            hovertemplate="%{y:.2f}x",
        )
    )
    return figura


def criar_histograma_do_acaso(
    sharpes_ao_acaso: np.ndarray, sharpe_real: float
) -> go.Figure:
    """Sharpes das versões ao acaso, com uma linha no Sharpe real da estratégia."""
    if len(sharpes_ao_acaso) == 0:
        raise ValueError("Não há sorteios para mostrar.")
    figura = go.Figure(
        go.Histogram(
            x=sharpes_ao_acaso,
            nbinsx=30,
            marker={"color": COR_INDICE},
            hovertemplate="Sharpe %{x}<br>%{y} sorteios<extra></extra>",
        )
    )
    figura.add_vline(
        x=sharpe_real,
        line_color=COR_AZUL,
        line_width=3,
        annotation_text="Estratégia real",
        annotation_font_color=COR_AZUL_CLARO,
    )
    _estilo_base(figura, "Sharpe de versões ao acaso (mesma exposição)", ALTURA_PADRAO)
    figura.update_layout(hovermode="closest", bargap=0.05)
    figura.update_xaxes(title="Índice de Sharpe", showspikes=False)
    figura.update_yaxes(title="Sorteios")
    return figura


def criar_grafico_risco_retorno(
    pontos: pd.DataFrame, destaque: str | None = None
) -> go.Figure:
    """Cada estratégia como um ponto: risco (volatilidade) no eixo x e retorno anual no y.

    `pontos` tem uma linha por estratégia e as colunas "Volatilidade anual" e "Retorno anualizado".
    Quanto mais para cima e para a esquerda, melhor. A de `destaque` aparece em azul.
    """
    if pontos.empty:
        raise ValueError("Não há estratégias para mostrar.")
    pontos = pontos.dropna(subset=["Volatilidade anual", "Retorno anualizado"])
    if pontos.empty:
        raise ValueError("Não há estratégias com números para mostrar.")
    figura = go.Figure(
        go.Scatter(
            x=pontos["Volatilidade anual"],
            y=pontos["Retorno anualizado"],
            mode="markers+text",
            text=list(pontos.index),
            textposition="top center",
            textfont={"size": 11},
            marker={
                "size": [14 if n == destaque else 10 for n in pontos.index],
                "color": [
                    COR_AZUL if n == destaque else COR_INDICE for n in pontos.index
                ],
            },
            customdata=[
                [_pct_br(v), _pct_br(r)]
                for v, r in zip(
                    pontos["Volatilidade anual"], pontos["Retorno anualizado"]
                )
            ],
            hovertemplate="%{text}<br>Risco: %{customdata[0]}<br>Retorno: %{customdata[1]}<extra></extra>",
        )
    )
    _estilo_base(figura, "Risco e retorno por estratégia (ao ano)", 460)
    figura.update_layout(hovermode="closest")
    figura.update_xaxes(
        title="Volatilidade anual (risco)", tickformat=".0%", showspikes=False
    )
    figura.update_yaxes(title="Retorno anualizado", tickformat=".0%")
    return figura


def criar_grafico_pesos(pesos: pd.DataFrame) -> go.Figure:
    """Áreas empilhadas: quanto da carteira estava em cada ativo (e em caixa) ao longo do tempo."""
    if pesos.empty:
        raise ValueError("Não há pesos para mostrar.")
    caixa = (1 - pesos.sum(axis=1)).clip(lower=0)
    figura = _figura_base("Composição da carteira")
    figura.update_yaxes(tickformat=".0%", range=[0, 1])
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    cores = [
        COR_AZUL,
        "#a78bfa",
        "#f472b6",
        COR_ALTA,
        "#38bdf8",
        "#94a3b8",
        COR_AZUL_CLARO,
        "#facc15",
    ]
    for i, coluna in enumerate(pesos.columns):
        figura.add_trace(
            go.Scatter(
                x=pesos.index,
                y=pesos[coluna],
                name=str(coluna),
                stackgroup="carteira",
                mode="lines",
                line={"width": 0.5, "color": cores[i % len(cores)]},
                hovertemplate="%{y:.1%}",
            )
        )
    figura.add_trace(
        go.Scatter(
            x=pesos.index,
            y=caixa,
            name="Caixa",
            stackgroup="carteira",
            mode="lines",
            line={"width": 0.5, "color": COR_INDICE},
            hovertemplate="%{y:.1%}",
        )
    )
    return figura


def criar_grafico_curvas_de_capital(
    curvas: dict[str, pd.Series], capital_inicial: float, destaque: str
) -> go.Figure:
    """Quanto o capital inicial viraria em cada estratégia. A de `destaque` aparece em azul."""
    if not curvas:
        raise ValueError("Não há curvas para mostrar.")
    figura = _figura_base("Evolução do capital (R$)")
    figura.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    figura.add_hline(
        y=capital_inicial, line_dash="dot", line_color="rgba(255,255,255,0.25)"
    )
    for nome, curva in curvas.items():
        em_destaque = nome == destaque
        figura.add_trace(
            go.Scatter(
                x=curva.index,
                y=curva * capital_inicial,
                mode="lines",
                line={
                    "color": COR_AZUL if em_destaque else COR_INDICE,
                    "width": 2.5 if em_destaque else 1.8,
                },
                hovertemplate="R$ %{y:,.2f}",
                name=nome,
            )
        )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura


def criar_grafico_quedas_comparadas(
    curvas: dict[str, pd.Series], destaque: str
) -> go.Figure:
    """Drawdown de cada estratégia: o quanto estava abaixo do próprio topo em cada dia."""
    from src.indicadores import calcular_drawdown

    if not curvas:
        raise ValueError("Não há curvas para mostrar.")
    figura = _figura_base("Quedas desde o topo (drawdown)")
    for nome, curva in curvas.items():
        em_destaque = nome == destaque
        queda = calcular_drawdown(curva)
        figura.add_trace(
            go.Scatter(
                x=queda.index,
                y=queda,
                mode="lines",
                fill="tozeroy" if em_destaque else None,
                fillcolor="rgba(41, 98, 255, 0.18)" if em_destaque else None,
                line={
                    "color": COR_AZUL if em_destaque else COR_INDICE,
                    "width": 1.8 if em_destaque else 1.3,
                },
                hovertemplate="%{y:.2%}",
                name=nome,
            )
        )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura


def criar_grafico_operacoes_no_preco(
    fechamento: pd.Series, operacoes: pd.DataFrame
) -> go.Figure:
    """Preço de fechamento com setas nos dias de entrada e de saída de cada operação."""
    figura = _figura_base("Preço e operações")
    figura.update_yaxes(tickformat=",.2f")
    figura.add_trace(
        go.Scatter(
            x=fechamento.index,
            y=fechamento,
            mode="lines",
            line={"color": COR_INDICE, "width": 1.5},
            hovertemplate="%{y:,.2f}",
            name="Preço",
        )
    )
    if not operacoes.empty:
        entradas = pd.to_datetime(operacoes["entrada"])
        figura.add_trace(
            go.Scatter(
                x=entradas,
                y=fechamento.loc[entradas],
                mode="markers",
                marker={"symbol": "triangle-up", "color": COR_ALTA, "size": 10},
                hovertemplate="Primeiro dia comprado: %{y:,.2f}",
                name="Entrada",
            )
        )
        fechadas = operacoes[~operacoes["aberta"]]
        saidas = pd.to_datetime(fechadas["saida"])
        figura.add_trace(
            go.Scatter(
                x=saidas,
                y=fechamento.loc[saidas],
                mode="markers",
                marker={"symbol": "triangle-down", "color": COR_QUEDA, "size": 10},
                hovertemplate="Último dia comprado: %{y:,.2f}",
                name="Saída",
            )
        )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura
