"""Gráficos estáticos (imagens PNG) para os relatórios em PDF, no estilo TickerLab em fundo claro.

Os gráficos do site são interativos (Plotly); num PDF eles precisam virar imagem. Exportar o
Plotly exigiria um navegador inteiro dentro da imagem Docker (kaleido), então os relatórios usam o
matplotlib, desenhando os mesmos dados com a fonte e as cores da marca (`src/marca.py`).
"""

from io import BytesIO

import matplotlib

matplotlib.use("Agg")  # sem janela: só gera arquivos (servidor)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

from src import marca

LARGURA_POLEGADAS = 7.2
DPI = 200
NOMES_CURTOS_DOS_MESES = (
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez",
)  # fmt: skip

for _arquivo in (marca.FONTE_PDF_TEXTO, marca.FONTE_PDF_MEDIA, marca.FONTE_PDF_TITULO):
    font_manager.fontManager.addfont(str(_arquivo))
plt.rcParams.update(
    {
        "font.family": marca.FONTE,
        "font.size": 8.5,
        "axes.edgecolor": marca.PAPEL_LINHA,
        "axes.labelcolor": marca.PAPEL_APAGADO,
        "axes.titlesize": 9.5,
        "axes.titleweight": 800,
        "axes.titlecolor": marca.PAPEL_TEXTO,
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": marca.PAPEL_LINHA,
        "grid.linewidth": 0.6,
        "xtick.color": marca.PAPEL_APAGADO,
        "ytick.color": marca.PAPEL_APAGADO,
        "legend.frameon": False,
        "figure.facecolor": marca.PAPEL_FUNDO,
        "axes.facecolor": marca.PAPEL_FUNDO,
        "axes.prop_cycle": plt.cycler(color=list(marca.PAPEL_SERIES)),
    }
)


def numero_br(valor: float, casas: int = 2) -> str:
    """12345.6 → "12.345,60"."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "#").replace(".", ",").replace("#", ".")


def pct_br(valor: float, casas: int = 1, sinal: bool = False) -> str:
    """0.1234 → "12,3%" (ou "+12,3%" com `sinal`)."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "—"
    texto = numero_br(valor * 100, casas) + "%"
    return f"+{texto}" if sinal and valor > 0 else texto.replace("-", "−")


_EIXO_PCT = FuncFormatter(lambda v, _: pct_br(v, 0))
_EIXO_NUMERO = FuncFormatter(lambda v, _: numero_br(v, 0 if abs(v) >= 100 else 2))


def _figura(altura: float = 2.6) -> tuple[plt.Figure, plt.Axes]:
    figura, eixo = plt.subplots(figsize=(LARGURA_POLEGADAS, altura), dpi=DPI)
    figura.subplots_adjust(left=0.08, right=0.98, top=0.86, bottom=0.14)
    return figura, eixo


def _png(figura: plt.Figure) -> bytes:
    arquivo = BytesIO()
    figura.savefig(arquivo, format="png", dpi=DPI)
    plt.close(figura)
    return arquivo.getvalue()


def grafico_de_preco(
    fechamento: pd.Series, titulo: str = "Preço de fechamento"
) -> bytes:
    """Linha do preço com área suave embaixo e o último valor destacado."""
    figura, eixo = _figura()
    cor = marca.PAPEL_SERIES[0]
    eixo.plot(fechamento.index, fechamento.values, color=cor, linewidth=1.4)
    base = float(fechamento.min()) * 0.97
    eixo.fill_between(fechamento.index, fechamento.values, base, color=cor, alpha=0.10)
    eixo.set_ylim(bottom=base)
    eixo.scatter(
        [fechamento.index[-1]], [fechamento.iloc[-1]], color=cor, s=14, zorder=3
    )
    eixo.yaxis.set_major_formatter(_EIXO_NUMERO)
    eixo.set_title(titulo)
    return _png(figura)


def grafico_de_drawdown(fechamento: pd.Series) -> bytes:
    """Quanto o ativo estava abaixo do último topo em cada dia (área vermelha)."""
    drawdown = fechamento / fechamento.cummax() - 1
    figura, eixo = _figura(2.0)
    eixo.fill_between(
        drawdown.index, drawdown.values, 0, color=marca.PAPEL_QUEDA, alpha=0.25
    )
    eixo.plot(drawdown.index, drawdown.values, color=marca.PAPEL_QUEDA, linewidth=1.0)
    eixo.yaxis.set_major_formatter(_EIXO_PCT)
    eixo.set_title("Quedas a partir do topo (drawdown)")
    return _png(figura)


def grafico_de_retorno_mensal(tabela: pd.DataFrame) -> bytes:
    """Mapa de calor: um quadrado por mês e ano, verde para alta e vermelho para queda.

    `tabela` vem de `indicadores.montar_tabela_retornos` (anos nas linhas, "Jan" a "Dez" e o
    total "Ano" nas colunas).
    """
    colunas = [c for c in tabela.columns if c in (*NOMES_CURTOS_DOS_MESES, "Ano")]
    valores = tabela[colunas].astype(float)
    limite = (
        float(np.nanmax(np.abs(valores.to_numpy())))
        if valores.notna().any().any()
        else 0.1
    )
    from matplotlib.colors import LinearSegmentedColormap

    escala = LinearSegmentedColormap.from_list(
        "queda_alta", [marca.PAPEL_QUEDA, marca.PAPEL_FUNDO, marca.PAPEL_ALTA]
    )
    altura = 0.9 + 0.32 * len(valores)
    figura, eixo = plt.subplots(figsize=(LARGURA_POLEGADAS, altura), dpi=DPI)
    figura.subplots_adjust(
        left=0.07, right=0.99, top=1 - 0.35 / altura, bottom=0.25 / altura
    )
    eixo.imshow(
        valores.to_numpy(), cmap=escala, vmin=-limite, vmax=limite, aspect="auto"
    )
    eixo.grid(False)
    eixo.set_xticks(range(len(colunas)), colunas)
    if "Ano" in colunas:  # uma linha separa o total do ano dos meses
        eixo.axvline(colunas.index("Ano") - 0.5, color=marca.PAPEL_FUNDO, linewidth=3)
    eixo.set_yticks(range(len(valores)), [str(a) for a in valores.index])
    eixo.tick_params(length=0)
    for spine in eixo.spines.values():
        spine.set_visible(False)
    for i in range(valores.shape[0]):
        for j in range(valores.shape[1]):
            v = valores.iat[i, j]
            if not np.isnan(v):
                eixo.text(
                    j, i, pct_br(v, 1), ha="center", va="center", fontsize=6.5,
                    color=marca.PAPEL_TEXTO,
                )  # fmt: skip
    eixo.set_title("Retorno de cada mês")
    return _png(figura)


def grafico_de_linhas(
    series: dict[str, pd.Series],
    titulo: str,
    eixo_em_pct: bool = False,
    destaque: str | None = None,
) -> bytes:
    """Várias linhas no mesmo gráfico, nas cores da marca, com legenda embaixo."""
    figura, eixo = _figura(2.8)
    for i, (nome, serie) in enumerate(series.items()):
        cor = marca.PAPEL_SERIES[i % len(marca.PAPEL_SERIES)]
        grossura = 1.8 if nome == destaque else 1.1
        eixo.plot(serie.index, serie.values, color=cor, linewidth=grossura, label=nome)
    eixo.yaxis.set_major_formatter(_EIXO_PCT if eixo_em_pct else _EIXO_NUMERO)
    eixo.set_title(titulo)
    eixo.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=min(len(series), 5)
    )
    figura.subplots_adjust(bottom=0.24)
    return _png(figura)


def grafico_de_pesos(pesos: pd.DataFrame) -> bytes:
    """Como o dinheiro da carteira se dividiu entre os ativos ao longo do tempo (áreas)."""
    figura, eixo = _figura(2.6)
    cores = [
        marca.PAPEL_SERIES[i % len(marca.PAPEL_SERIES)] for i in range(pesos.shape[1])
    ]
    eixo.stackplot(pesos.index, pesos.T.to_numpy(), labels=list(pesos.columns), colors=cores,
                   alpha=0.85)  # fmt: skip
    eixo.set_ylim(0, 1)
    eixo.yaxis.set_major_formatter(_EIXO_PCT)
    eixo.set_title("Composição da carteira (o que falta até 100% fica em caixa)")
    eixo.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=min(pesos.shape[1], 5)
    )
    figura.subplots_adjust(bottom=0.24)
    return _png(figura)


def grafico_de_composicao(pesos: pd.Series, maximo: int = 15) -> bytes:
    """Barras horizontais: quanto do dinheiro está em cada ativo (do maior para o menor)."""
    pesos = pesos.sort_values(ascending=True)
    if len(pesos) > maximo:  # os menores viram "Outros"
        outros = pesos.iloc[: len(pesos) - maximo + 1].sum()
        pesos = pd.concat(
            [pd.Series({"Outros": outros}), pesos.iloc[len(pesos) - maximo + 1 :]]
        )
    altura = 0.8 + 0.26 * len(pesos)
    figura, eixo = plt.subplots(figsize=(LARGURA_POLEGADAS, altura), dpi=DPI)
    figura.subplots_adjust(
        left=0.16, right=0.93, top=1 - 0.35 / altura, bottom=0.3 / altura
    )
    eixo.barh(pesos.index, pesos.values, color=marca.PAPEL_SERIES[0], height=0.62)
    for i, v in enumerate(pesos.values):
        eixo.text(v, i, f"  {pct_br(v, 1)}", va="center", fontsize=7.5,
                  color=marca.PAPEL_TEXTO)  # fmt: skip
    eixo.xaxis.set_major_formatter(_EIXO_PCT)
    eixo.set_xlim(0, max(pesos.max() * 1.18, 0.05))
    eixo.grid(axis="y", visible=False)
    eixo.set_title("Quanto do dinheiro está em cada ativo")
    return _png(figura)
