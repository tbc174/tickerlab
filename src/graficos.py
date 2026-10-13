"""Gráficos do app (Plotly). Só monta as figuras; quem mostra na tela é o app.py."""

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

if TYPE_CHECKING:  # só para os tipos: o módulo de gráficos não depende do acervo
    from src.juros_e_inflacao import PontoMensal
    from src.linha_do_tempo import LinhaDoTempo

from src import marca
from src.indicadores import (
    NOMES_DOS_MESES,
    PiorDrawdown,
    calcular_media_movel,
    calcular_media_por_mes,
)

# Cores da identidade TickerLab (src/marca.py). A série principal usa o azul claro da marca, que
# lê melhor sobre o fundo escuro; o azul forte fica para botões e seleção.
COR_AZUL = marca.SERIES[0]  # série principal
COR_AZUL_CLARO = marca.AZUL_TEXTO
COR_BOTAO = marca.AZUL  # botão ativo do seletor de período
COR_ALTA = marca.ALTA  # verde só para alta
COR_QUEDA = marca.QUEDA  # vermelho só para queda
COR_INDICE = marca.TEXTO_APAGADO  # índices em cinza
CORES_OUTROS_ATIVOS = list(marca.SERIES[1:5])  # âmbar, verde-água, rosa, amarelo
CORES_MEDIAS = [
    marca.SERIES[5],
    marca.SERIES[3],
    marca.SERIES[2],
]  # violeta, rosa, verde-água
PREENCHIMENTO_AZUL = "rgba(110, 149, 255, 0.22)"
PREENCHIMENTO_QUEDA = "rgba(240, 82, 91, 0.22)"
# mapa de calor: queda (vermelho) → zero (superfície) → alta (verde)
ESCALA_QUEDA_ALTA = [[0, "#b8323b"], [0.5, marca.SUPERFICIE], [1, "#1d9567"]]
LINHA_DE_REFERENCIA = "rgba(232, 236, 244, 0.30)"

# Tema Plotly "tickerlab": fonte e cores da marca em todos os gráficos de uma vez
TEMA = "tickerlab"
pio.templates[TEMA] = go.layout.Template(pio.templates["plotly_dark"])
_LAYOUT_DO_TEMA = pio.templates[TEMA].layout
# o plotly declara a propriedade como opcional, mas num Template ela sempre existe
assert _LAYOUT_DO_TEMA is not None
_LAYOUT_DO_TEMA.update(
    font={"family": f"{marca.FONTE}, sans-serif", "color": marca.TEXTO, "size": 13},
    colorway=list(marca.SERIES),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hoverlabel={
        "bgcolor": marca.DESTAQUE,
        "bordercolor": marca.LINHA_FORTE,
        "font": {"family": f"{marca.FONTE}, sans-serif", "color": marca.TEXTO},
    },
    legend={"font": {"color": marca.TEXTO_APAGADO}},
)
_LAYOUT_DO_TEMA.xaxis.update(
    gridcolor="rgba(148, 163, 190, 0.06)",
    linecolor=marca.LINHA,
    zerolinecolor=marca.LINHA,
    tickfont={"color": marca.TEXTO_APAGADO},
)
_LAYOUT_DO_TEMA.yaxis.update(
    gridcolor="rgba(148, 163, 190, 0.10)",
    linecolor=marca.LINHA,
    zerolinecolor=marca.LINHA,
    tickfont={"color": marca.TEXTO_APAGADO},
)

# --- tema claro do app (13/10/2026) -------------------------------------------------------------
# Os gráficos são montados com as cores do tema escuro; quem está no claro recebe uma cópia com cada
# cor trocada pela do mesmo papel na paleta clara (`no_tema`). É uma função pura: nada fica guardado
# no módulo, então uma sessão nunca muda o gráfico de outra.
TEMA_CLARO = "tickerlab_claro"
pio.templates[TEMA_CLARO] = go.layout.Template(pio.templates["plotly_white"])
_LAYOUT_CLARO = pio.templates[TEMA_CLARO].layout
assert _LAYOUT_CLARO is not None
_CLARA = marca.PALETA_CLARA
_LAYOUT_CLARO.update(
    font={"family": f"{marca.FONTE}, sans-serif", "color": _CLARA.texto, "size": 13},
    colorway=list(_CLARA.series),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hoverlabel={
        "bgcolor": _CLARA.superficie,
        "bordercolor": _CLARA.linha_forte,
        "font": {"family": f"{marca.FONTE}, sans-serif", "color": _CLARA.texto},
    },
    legend={"font": {"color": _CLARA.apagado}},
)
for _eixo, _grade in ((_LAYOUT_CLARO.xaxis, 0.06), (_LAYOUT_CLARO.yaxis, 0.10)):
    _eixo.update(
        gridcolor=f"rgba(10, 31, 68, {_grade})",
        linecolor=_CLARA.linha,
        zerolinecolor=_CLARA.linha,
        tickfont={"color": _CLARA.apagado},
    )


def _cores_do_escuro_para_o_claro() -> dict[str, str]:
    """Cada cor do tema escuro usada nos gráficos e a do mesmo papel no claro."""
    escura, clara = marca.PALETA_ESCURA, marca.PALETA_CLARA
    papeis = (
        "fundo",
        "superficie",
        "destaque",
        "linha",
        "linha_forte",
        "texto",
        "apagado",
    )
    trocas = {getattr(escura, p): getattr(clara, p) for p in papeis}
    trocas |= {
        escura.alta: clara.alta,
        escura.queda: clara.queda,
        escura.azul_texto: clara.azul_texto,
    }
    # as séries por último: a primeira (azul) vale mais que o azul de texto, que é a mesma cor
    trocas |= dict(zip(escura.series, clara.series, strict=True))
    trocas |= {
        PREENCHIMENTO_AZUL: "rgba(41, 98, 255, 0.14)",
        PREENCHIMENTO_QUEDA: "rgba(194, 47, 58, 0.16)",
        LINHA_DE_REFERENCIA: "rgba(10, 31, 68, 0.30)",
        # o botão ativo do seletor de período: no claro o texto é marinho, então o fundo vira um
        # azul claro (no escuro, o texto claro se lê sobre o azul elétrico)
        COR_BOTAO: "#c7d6ff",
    }
    return {antes.lower(): depois for antes, depois in trocas.items()}


_DO_ESCURO_PARA_O_CLARO = _cores_do_escuro_para_o_claro()


def _trocar_cores(valor: object, trocas: dict[str, str]) -> object:
    """Troca as cores de uma estrutura do Plotly (dicionários e listas), sem mudar o resto."""
    if isinstance(valor, str):
        return trocas.get(valor.lower(), valor)
    if isinstance(valor, dict):
        return {chave: _trocar_cores(v, trocas) for chave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_trocar_cores(v, trocas) for v in valor]
    return valor


def no_tema(figura: go.Figure, paleta: marca.Paleta) -> go.Figure:
    """O gráfico nas cores do tema da pessoa. No escuro, a própria figura; no claro, uma cópia
    com cada cor trocada pela do mesmo papel (a figura original não muda)."""
    if paleta.tipo == "escuro":
        return figura
    dados = figura.to_dict()
    dados["layout"].pop("template", None)
    clara = go.Figure(_trocar_cores(dados, _DO_ESCURO_PARA_O_CLARO))
    clara.update_layout(template=TEMA_CLARO)
    return clara


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
        template=TEMA,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=altura,
        margin={"l": 10, "r": 10, "t": 50 if titulo else 40, "b": 10},
        hovermode="x unified",
        dragmode="zoom",
        showlegend=False,
    )
    figura.update_xaxes(
        showspikes=True,  # linha vertical que acompanha o cursor
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor=LINHA_DE_REFERENCIA,
    )


def _seletor_de_periodo(a_direita: bool = False) -> dict:
    """Botões 1M a Tudo. `a_direita` os põe no canto, ao lado do título, sem cobri-lo."""
    posicao = (
        {"x": 1, "xanchor": "right", "y": 1.0, "yanchor": "bottom"} if a_direita else {}
    )
    return {
        **posicao,
        "buttons": _BOTOES_DE_PERIODO,
        "bgcolor": marca.DESTAQUE,
        "activecolor": COR_BOTAO,
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
    for (_, linha), var in zip(dados.iterrows(), variacao, strict=True):
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
        bgcolor=COR_BOTAO,  # texto branco: o azul forte dá mais contraste
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
            fillcolor=PREENCHIMENTO_QUEDA,
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
            colorscale=ESCALA_QUEDA_ALTA,
            xgap=2,
            ygap=2,
            showscale=False,
            hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>",
        )
    )
    figura.update_layout(
        template=TEMA,
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
    figura.add_hline(y=100, line_dash="dot", line_color=LINHA_DE_REFERENCIA)

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
            colorscale=ESCALA_QUEDA_ALTA,
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
        template=TEMA,
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
        ("p5", "p95", "5% a 95%", "rgba(147, 160, 184, 0.18)"),
        ("p25", "p75", "25% a 75%", "rgba(147, 160, 184, 0.32)"),
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
                    pontos["Volatilidade anual"],
                    pontos["Retorno anualizado"],
                    strict=True,
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
    cores = [*marca.SERIES, COR_INDICE, COR_AZUL_CLARO]
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


def criar_grafico_diferenca_das_janelas(diferenca: pd.Series) -> go.Figure:
    """Aporte único menos parcelado, por data de início: acima de zero o aporte único venceu."""
    if diferenca.empty:
        raise ValueError("Não há janelas para mostrar.")
    figura = _figura_base("Aporte único menos aportes parcelados (por data de início)")
    figura.update_yaxes(tickformat="+.0%")
    figura.add_hline(y=0, line_color=LINHA_DE_REFERENCIA)
    figura.add_trace(
        go.Scatter(
            x=diferenca.index,
            y=diferenca,
            mode="lines",
            fill="tozeroy",
            line={"color": COR_AZUL, "width": 1.5},
            fillcolor=PREENCHIMENTO_AZUL,
            hovertemplate="%{y:+.1%}",
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
    figura.add_hline(y=capital_inicial, line_dash="dot", line_color=LINHA_DE_REFERENCIA)
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


def criar_grafico_regimes(
    fechamento: pd.Series, regimes: pd.Series, cores: dict[str, str]
) -> go.Figure:
    """O preço com cada dia pintado pela cor do seu regime (dias sem regime ficam de fora)."""
    if fechamento.empty or not fechamento.index.equals(regimes.index):
        raise ValueError("Preços e regimes precisam ter as mesmas datas.")
    figura = _figura_base("Preço por regime de mercado")
    figura.update_yaxes(tickformat=",.2f")
    for nome, cor in cores.items():
        pontos = fechamento.where(regimes == nome)
        if pontos.notna().any():
            figura.add_trace(
                go.Scatter(
                    x=pontos.index,
                    y=pontos,
                    mode="markers",
                    marker={"color": cor, "size": 4},
                    name=nome,
                    hovertemplate=f"{nome}: %{{y:,.2f}}",
                )
            )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura


def criar_grafico_disjuntor(
    curvas: dict[str, pd.Series],
    capital_inicial: float,
    destaque: str,
    acionamentos: pd.DatetimeIndex,
) -> go.Figure:
    """As curvas de capital, com um marcador onde o disjuntor disparou na curva em destaque."""
    figura = criar_grafico_curvas_de_capital(curvas, capital_inicial, destaque)
    if len(acionamentos):
        pontos = curvas[destaque].reindex(acionamentos) * capital_inicial
        figura.add_trace(
            go.Scatter(
                x=pontos.index,
                y=pontos,
                mode="markers",
                marker={"color": COR_QUEDA, "size": 9, "symbol": "x"},
                name="Disjuntor disparou",
                hovertemplate="Disparou: R$ %{y:,.2f}",
            )
        )
    return figura


def criar_grafico_volatilidade_prevista(
    prevista: pd.Series, ingenua: pd.Series, realizada: pd.Series
) -> go.Figure:
    """Volatilidade anual que veio (cinza), a prevista pelo modelo (azul) e a ingênua (rosa)."""
    if prevista.empty:
        raise ValueError("Não há previsões para mostrar.")
    figura = _figura_base("Volatilidade anual: prevista × que veio de fato")
    figura.update_yaxes(tickformat=".0%")
    for nome, serie, cor, largura in (
        ("Que veio de fato", realizada, COR_INDICE, 1.5),
        ("Ingênua (últimos 20 dias)", ingenua, CORES_MEDIAS[1], 1.2),
        ("Prevista pelo modelo", prevista, COR_AZUL, 2.0),
    ):
        figura.add_trace(
            go.Scatter(
                x=serie.index,
                y=serie,
                mode="lines",
                line={"color": cor, "width": largura},
                name=nome,
                hovertemplate="%{y:.1%}",
            )
        )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura


def criar_grafico_z_do_par(
    z: pd.Series,
    lado: pd.Series,
    entrada: float,
    stop: float,
    inicio_do_teste: pd.Timestamp,
) -> go.Figure:
    """O z-score do spread com as faixas de entrada e de stop; os dias posicionados ficam em cores."""
    if z.dropna().empty:
        raise ValueError("Não há z-score para mostrar.")
    figura = _figura_base("Distância do par em relação ao normal (z-score)")
    figura.add_hline(y=0, line_color=LINHA_DE_REFERENCIA)
    for nivel in (entrada, -entrada):
        figura.add_hline(y=nivel, line_dash="dot", line_color=LINHA_DE_REFERENCIA)
    for nivel in (stop, -stop):
        figura.add_hline(y=nivel, line_dash="dash", line_color=COR_QUEDA)
    figura.add_trace(
        go.Scatter(
            x=z.index,
            y=z,
            mode="lines",
            line={"color": COR_INDICE, "width": 1.2},
            name="z-score",
            hovertemplate="%{y:.2f}",
        )
    )
    for valor, nome, cor in (
        (1.0, "Comprado em A, vendido em B", COR_ALTA),
        (-1.0, "Vendido em A, comprado em B", COR_QUEDA),
    ):
        pontos = z.where(lado == valor)
        if pontos.notna().any():
            figura.add_trace(
                go.Scatter(
                    x=pontos.index,
                    y=pontos,
                    mode="markers",
                    marker={"color": cor, "size": 4},
                    name=nome,
                    hovertemplate="%{y:.2f}",
                )
            )
    figura.add_vline(x=inicio_do_teste, line_dash="dot", line_color=COR_AZUL)
    figura.add_annotation(
        x=inicio_do_teste,
        y=1,
        yref="paper",
        text="início do teste",
        showarrow=False,
        xanchor="left",
        font={"color": COR_AZUL, "size": 11},
    )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura


def criar_mapa_de_calor_de_correlacao(matriz: pd.DataFrame) -> go.Figure:
    """Quadro de correlações: verde = andam juntos, vermelho = opostos, escuro = sem relação."""
    if matriz.shape[0] < 2 or matriz.shape[0] != matriz.shape[1]:
        raise ValueError(
            "A matriz de correlação precisa ser quadrada, com 2 ou mais ativos."
        )
    nomes = [str(c) for c in matriz.columns]
    valores = matriz.to_numpy(dtype=float)
    textos = [[f"{v:.2f}".replace(".", ",") for v in linha] for linha in valores]
    figura = go.Figure(
        go.Heatmap(
            z=valores,
            x=nomes,
            y=nomes,
            text=textos,
            texttemplate="%{text}",
            textfont={"size": 12},
            zmin=-1,
            zmax=1,
            colorscale=ESCALA_QUEDA_ALTA,
            xgap=2,
            ygap=2,
            showscale=False,
            hovertemplate="%{y} × %{x}: %{text}<extra></extra>",
        )
    )
    figura.update_layout(
        template=TEMA,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=140 + 55 * len(nomes),
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis={"side": "top", "fixedrange": True},
        yaxis={"autorange": "reversed", "fixedrange": True},
        dragmode=False,
    )
    return figura


def criar_grafico_beta_movel(beta: pd.Series, janela: int) -> go.Figure:
    """Como o beta do ativo mudou ao longo do tempo (calculado nos últimos `janela` dias)."""
    if beta.empty:
        raise ValueError("Não há beta para mostrar.")
    figura = _figura_base(f"Beta móvel ({janela} dias)")
    figura.update_yaxes(tickformat=".2f")
    figura.add_hline(y=1, line_dash="dot", line_color=LINHA_DE_REFERENCIA)
    figura.add_trace(
        go.Scatter(
            x=beta.index,
            y=beta,
            mode="lines",
            line={"color": COR_AZUL, "width": 2},
            hovertemplate="beta %{y:.2f}",
        )
    )
    return figura


def criar_grafico_dispersao_do_beta(
    retorno_do_ativo: pd.Series,
    retorno_do_indice: pd.Series,
    beta: float,
    alfa_diario: float,
) -> go.Figure:
    """Cada ponto é um dia (índice no eixo x, ativo no y); a reta tem a inclinação do beta."""
    tabela = pd.concat(
        [retorno_do_indice, retorno_do_ativo], axis=1, join="inner"
    ).dropna()
    if tabela.empty:
        raise ValueError("Não há dias em comum para mostrar.")
    x, y = tabela.iloc[:, 0], tabela.iloc[:, 1]
    figura = _figura_base("Cada dia: índice × ativo")
    figura.update_xaxes(tickformat=".1%", title_text="Retorno do índice no dia")
    figura.update_yaxes(tickformat=".1%", title_text="Retorno do ativo no dia")
    figura.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            marker={"color": COR_AZUL_CLARO, "size": 4, "opacity": 0.55},
            hovertemplate="índice %{x:.2%}<br>ativo %{y:.2%}<extra></extra>",
            name="dias",
        )
    )
    extremos = pd.Series([x.min(), x.max()])
    figura.add_trace(
        go.Scatter(
            x=extremos,
            y=alfa_diario + beta * extremos,
            mode="lines",
            line={"color": COR_QUEDA, "width": 2},
            name=f"reta (beta {beta:.2f})".replace(".", ","),
            hoverinfo="skip",
        )
    )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.2})
    return figura


def criar_grafico_momentum(momentum: pd.Series) -> go.Figure:
    """Barras do momentum de cada ativo, do mais forte (em cima) ao mais fraco."""
    if momentum.empty:
        raise ValueError("Não há momentum para mostrar.")
    ordenado = momentum.sort_values()
    figura = _figura_base("Momentum 12-1 por ativo")
    figura.update_xaxes(tickformat="+.0%")
    figura.add_trace(
        go.Bar(
            x=ordenado,
            y=[str(i) for i in ordenado.index],
            orientation="h",
            marker={"color": [COR_ALTA if v > 0 else COR_QUEDA for v in ordenado]},
            hovertemplate="%{y}: %{x:+.1%}<extra></extra>",
        )
    )
    figura.update_layout(height=max(ALTURA_PADRAO - 80, 60 + 45 * len(ordenado)))
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


def criar_grafico_fundamentos_anuais(
    anual: pd.DataFrame, simbolo: str = "R$"
) -> go.Figure:
    """Receita e lucro de cada exercício, em bilhões da moeda do balanço, lado a lado."""
    if anual.empty:
        raise ValueError("Não há demonstrações anuais para mostrar.")
    figura = _figura_base(f"Receita e lucro por ano ({simbolo} bilhões)")
    figura.update_yaxes(tickformat=",.0f")  # bilhões, não porcentagem
    anos = [str(a) for a in anual.index]
    for nome, coluna, cor in (
        ("Receita", "receita", marca.SERIES[0]),
        ("Lucro dos acionistas", "lucro", marca.SERIES[1]),
    ):
        figura.add_trace(
            go.Bar(
                x=anos,
                y=anual[coluna] / 1e9,
                name=nome,
                marker={"color": cor},
                hovertemplate=f"{nome}: {simbolo} %{{y:,.1f}} bi<extra></extra>",
            )
        )
    figura.update_layout(barmode="group", showlegend=True, hovermode="x unified")
    return figura


def criar_grafico_negociacoes(resumo: pd.DataFrame, moeda: str) -> go.Figure:
    """Compras (para cima) e vendas (para baixo) de pessoas de dentro, por mês de entrega."""
    if resumo.empty:
        raise ValueError("Não há negociações para mostrar.")
    simbolo = {"BRL": "R$", "USD": "US$"}.get(moeda, moeda)
    figura = _figura_base(
        f"Compras e vendas de pessoas de dentro por mês ({simbolo} milhões)"
    )
    figura.update_yaxes(tickformat=",.1f")  # milhões, não porcentagem
    for nome, coluna, cor in (
        ("Compras", "compras", marca.ALTA),
        ("Vendas", "vendas", marca.QUEDA),
    ):
        figura.add_trace(
            go.Bar(
                x=resumo["mes"],
                y=resumo[coluna] / 1e6,
                name=nome,
                marker={"color": cor},
                hovertemplate=f"{nome}: {simbolo} %{{y:,.1f}} mi<extra></extra>",
            )
        )
    figura.update_layout(barmode="relative", showlegend=True, hovermode="x unified")
    figura.update_xaxes(tickformat="%m/%Y")
    return figura


def criar_grafico_detentores(historico: pd.DataFrame, quem: str) -> go.Figure:
    """A fatia dos fundos (ou gestores) que informaram e têm a ação e, na B3, a dos vendidos."""
    if historico.empty:
        raise ValueError("Não há histórico para mostrar.")
    figura = _figura_base(f"% dos {quem} que informaram e têm a ação")
    series = [("fatia", f"{quem.capitalize()} comprados", marca.SERIES[0])]
    if historico["vendidos"].sum() > 0:
        series.append(("fatia_vendidos", f"{quem.capitalize()} vendidos", marca.QUEDA))
    for coluna, nome, cor in series:
        figura.add_trace(
            go.Scatter(
                x=historico["competencia"],
                y=historico[coluna],
                name=nome,
                mode="lines+markers",
                line={"color": cor},
                hovertemplate=f"{nome}: %{{y:.1%}}<extra></extra>",
            )
        )
    figura.update_layout(showlegend=True, hovermode="x unified")
    figura.update_xaxes(tickformat="%m/%Y")
    return figura


def criar_grafico_adx(adx: pd.DataFrame, nivel: int) -> go.Figure:
    """ADX (força da tendência) com +DI e -DI (direção) e a linha do nível de tendência."""
    dados = adx.dropna(subset=["adx"])
    if dados.empty:
        raise ValueError("Não há ADX para mostrar.")
    figura = _figura_base("Força da tendência (ADX)")
    figura.update_yaxes(tickformat=".0f", range=[0, 100])
    figura.add_hline(y=nivel, line_dash="dot", line_color=LINHA_DE_REFERENCIA)
    for coluna, nome, cor, largura in (
        ("adx", "ADX", COR_AZUL, 2.5),
        ("mais_di", "+DI (força de alta)", marca.ALTA, 1.2),
        ("menos_di", "-DI (força de queda)", marca.QUEDA, 1.2),
    ):
        figura.add_trace(
            go.Scatter(
                x=dados.index, y=dados[coluna], name=nome, mode="lines",
                line={"color": cor, "width": largura},
                hovertemplate=f"{nome}: %{{y:.1f}}<extra></extra>",
            )
        )  # fmt: skip
    figura.update_layout(showlegend=True, hovermode="x unified")
    return figura


def criar_grafico_obv(obv: pd.Series, volume_relativo: pd.Series) -> go.Figure:
    """OBV (linha, eixo da esquerda) e volume relativo (barras, eixo da direita)."""
    if obv.dropna().empty:
        raise ValueError("Não há volume para mostrar.")
    figura = make_subplots(specs=[[{"secondary_y": True}]])
    _estilo_base(figura, "Saldo de volume (OBV) e volume relativo", ALTURA_PADRAO)
    figura.update_xaxes(rangeselector=_seletor_de_periodo(a_direita=True))
    figura.add_trace(
        go.Bar(
            x=volume_relativo.index, y=volume_relativo, name="Volume relativo",
            marker={"color": LINHA_DE_REFERENCIA}, opacity=0.5,
            hovertemplate="volume relativo %{y:.2f}×<extra></extra>",
        ),
        secondary_y=True,
    )  # fmt: skip
    figura.add_trace(
        go.Scatter(
            x=obv.index, y=obv, name="OBV", mode="lines",
            line={"color": COR_AZUL, "width": 2}, hovertemplate="OBV %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )  # fmt: skip
    figura.update_yaxes(tickformat="~s", secondary_y=False)
    figura.update_yaxes(tickformat=".1f", secondary_y=True, showgrid=False)
    figura.update_layout(showlegend=True, hovermode="x unified")
    return figura


def criar_grafico_juros_e_inflacao(
    historico: "tuple[PontoMensal, ...]",
) -> go.Figure:
    """A meta da Selic e o IPCA em 12 meses, mês a mês (`historico`: pontos de
    `juros_e_inflacao.PontoMensal`)."""
    if not historico:
        raise ValueError("Não há meses para mostrar.")
    meses = pd.to_datetime([p.mes for p in historico])
    figura = _figura_base("Meta da Selic e IPCA em 12 meses (% ao ano)")
    figura.update_yaxes(tickformat=".1f", ticksuffix="%")
    for nome, valores, cor in (
        ("Meta da Selic", [p.selic_meta for p in historico], COR_AZUL),
        ("IPCA em 12 meses", [p.ipca_12_meses for p in historico], COR_INDICE),
    ):
        figura.add_trace(
            go.Scatter(
                x=meses,
                y=valores,
                mode="lines",
                line={"color": cor, "width": 2.2},
                hovertemplate="%{y:.2f}%",
                name=nome,
            )
        )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura


def criar_grafico_linha_do_tempo(linha: "LinhaDoTempo") -> go.Figure:
    """O preço em base 100 e um ponto em cada acontecimento (o texto aparece ao passar o mouse)."""
    if not linha.curva:
        raise ValueError("Não há preço para mostrar.")
    figura = _figura_base("Preço (base 100) e acontecimentos")
    figura.update_yaxes(tickformat=".0f")
    figura.add_trace(
        go.Scatter(
            x=pd.to_datetime([p.dia for p in linha.curva]),
            y=[p.valor for p in linha.curva],
            mode="lines",
            line={"color": COR_INDICE, "width": 1.8},
            hovertemplate="%{y:.1f}",
            name="Preço (base 100)",
        )
    )
    if linha.marcos:
        figura.add_trace(
            go.Scatter(
                x=pd.to_datetime([m.dia_no_grafico for m in linha.marcos]),
                y=[m.valor_no_grafico for m in linha.marcos],
                mode="markers",
                marker={"color": COR_AZUL, "size": 9, "symbol": "diamond"},
                text=[
                    f"{m.data:%d/%m/%Y} · {m.rotulo}: {m.assunto}" for m in linha.marcos
                ],
                hovertemplate="%{text}<extra></extra>",
                name="Acontecimentos",
            )
        )
    figura.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.12})
    return figura
