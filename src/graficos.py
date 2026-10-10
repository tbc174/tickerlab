"""Gráficos do app (Plotly). Só monta as figuras; quem mostra na tela é o app.py."""

import pandas as pd
import plotly.graph_objects as go

from src.indicadores import PiorDrawdown

COR_AZUL = "#2962ff"  # cor principal do TickerLab
COR_AZUL_CLARO = "#7aa2ff"
COR_QUEDA = "#ef5350"  # vermelho só para queda
ALTURA_PADRAO = 320


def _figura_base(titulo: str) -> go.Figure:
    """Figura vazia com o visual escuro e minimalista do app."""
    figura = go.Figure()
    figura.update_layout(
        title={"text": titulo, "font": {"size": 15}},
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=ALTURA_PADRAO,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        hovermode="x unified",
        showlegend=False,
        yaxis={"tickformat": ".0%", "gridcolor": "rgba(255,255,255,0.08)"},
        xaxis={"gridcolor": "rgba(255,255,255,0.04)"},
    )
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
