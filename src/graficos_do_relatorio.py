"""Os desenhos dos gráficos que o modelo escolhe para o relatório (plano de 23/10/2026, PR 2).

A IA escolhe, o código desenha: `pontos_do_grafico` lê os números da própria ficha (nada do que o
modelo respondeu chega ao desenho além da forma, da tabela e das colunas), corta o que passa da data
da ficha (sem olhar o futuro) e põe tudo numa só escala. `figura` desenha para a tela e a API
(Plotly) e `png` para o PDF (matplotlib), cada tipo do cardápio com o mesmo conjunto de pontos.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import plotly.graph_objects as go
from matplotlib.figure import Figure

from src import graficos, graficos_pdf
from src.analise_escrita import graficos as gr
from src.estilos_pdf import PADRAO, Estilo

DIVISORES = ((1e9, "bilhões"), (1e6, "milhões"), (1e3, "mil"))
LIMITE_DAS_CASAS = 100  # de 100 para cima, os decimais só poluem o eixo
TIPOS_QUE_PEDEM_TODAS_AS_COLUNAS = frozenset({"dispersao", "cascata", "antes_e_agora"})
MOEDA_DA_CASCATA = "R$"  # as tabelas de cascata da ficha guardam reais sem o símbolo


@dataclass(frozen=True)
class PontosDoGrafico:
    """Tudo o que o desenho precisa, lido da ficha: uma tupla de valores por coluna."""

    tipo: str
    titulo: str
    nome_do_eixo: str
    rotulos: tuple[str, ...]
    colunas: tuple[str, ...]
    valores: tuple[tuple[float | None, ...], ...]
    ids: tuple[
        str, ...
    ]  # as linhas da ficha de onde cada ponto saiu, na ordem dos rótulos
    unidade: str  # "R$", "US$", "%" ou "" (contagem e número cru)


@dataclass(frozen=True)
class Escala:
    divisor: float
    medida: str  # "R$ bilhões", "%", "" ...
    casas: int


def _chave_do_tempo(ponto: gr.Ponto) -> tuple[int, int, int]:
    momento = ponto.momento
    assert momento is not None  # só os tipos de eixo no tempo ordenam
    return momento.ano, momento.mes or 0, momento.dia or 0


def _unidade(grafico: gr.Grafico, linhas: list[gr.LinhaDaTabela]) -> str:
    achadas = (
        gr.unidade_da_celula(linha.celulas.get(coluna))
        for linha in linhas
        for coluna in grafico.colunas
    )
    unidade = next((u for u in achadas if u is not None), "")
    if grafico.tipo == "cascata" and not unidade:
        return MOEDA_DA_CASCATA
    return unidade


def pontos_do_grafico(
    grafico: gr.Grafico, entrada: dict[str, Any], corte: date | None = None
) -> PontosDoGrafico:
    """Os pontos do gráfico, só da ficha. `corte` (padrão: o da própria ficha) tira o que o
    eixo do tempo data depois dele: cortar o futuro não muda o passado."""
    linhas = gr.tabelas_da_entrada(entrada).get(grafico.tabela)
    if linhas is None:
        raise ValueError(f"a ficha não tem a tabela {grafico.tabela}")
    corte = corte or date.fromisoformat(entrada["corte"])
    forma = gr.CARDAPIO[grafico.tipo]
    pares = [
        (ponto, linha)
        for ponto, linha in zip(gr.pontos(grafico, linhas), linhas, strict=True)
        if not (ponto.momento and ponto.momento.depois_de(corte))
    ]
    completo = all if grafico.tipo in TIPOS_QUE_PEDEM_TODAS_AS_COLUNAS else any
    pares = [(p, li) for p, li in pares if completo(v is not None for v in p.valores)]
    if forma.eixo == gr.TEMPO:
        pares.sort(key=lambda par: _chave_do_tempo(par[0]))
    return PontosDoGrafico(
        tipo=grafico.tipo,
        titulo=grafico.titulo,
        nome_do_eixo=grafico.eixo,
        rotulos=tuple(p.rotulo for p, _ in pares),
        colunas=grafico.colunas,
        valores=tuple(
            tuple(p.valores[i] for p, _ in pares) for i in range(len(grafico.colunas))
        ),
        ids=tuple(p.id for p, _ in pares),
        unidade=_unidade(grafico, [li for _, li in pares]),
    )


def escala_para(pontos: PontosDoGrafico) -> Escala:
    """Uma escala para o gráfico inteiro: bilhões, milhões ou mil para dinheiro; % para fração."""
    todos = [v for coluna in pontos.valores for v in coluna if v is not None]
    maior = max((abs(v) for v in todos), default=0.0)
    if pontos.unidade == "%":
        return Escala(0.01, "%", 1)
    if pontos.unidade in ("R$", "US$"):
        for divisor, nome in DIVISORES:
            if maior >= divisor:
                return Escala(divisor, f"{pontos.unidade} {nome}", 1)
        return Escala(1.0, pontos.unidade, 0)
    inteiros = all(float(v).is_integer() for v in todos)
    return Escala(1.0, "", 0 if inteiros or maior >= LIMITE_DAS_CASAS else 2)


def series_na_escala(
    pontos: PontosDoGrafico, escala: Escala
) -> dict[str, list[float | None]]:
    return {
        coluna: [None if v is None else v / escala.divisor for v in valores]
        for coluna, valores in zip(pontos.colunas, pontos.valores, strict=True)
    }


def _plotly_da_linha(pontos: PontosDoGrafico, escala: Escala) -> go.Figure:
    return graficos.criar_grafico_linha_do_relatorio(
        list(pontos.rotulos),
        series_na_escala(pontos, escala),
        pontos.titulo,
        escala.medida,
        escala.casas,
    )


def _pdf_da_linha(pontos: PontosDoGrafico, escala: Escala, estilo: Estilo) -> Figure:
    return graficos_pdf.figura_de_linha_do_relatorio(
        list(pontos.rotulos),
        series_na_escala(pontos, escala),
        pontos.titulo,
        escala.medida,
        escala.casas,
        estilo,
    )


_PLOTLY: dict[str, Callable[[PontosDoGrafico, Escala], go.Figure]] = {
    "linha_no_tempo": _plotly_da_linha,
}
_PDF: dict[str, Callable[[PontosDoGrafico, Escala, Estilo], Figure]] = {
    "linha_no_tempo": _pdf_da_linha,
}


def figura(pontos: PontosDoGrafico) -> go.Figure:
    """A figura Plotly do gráfico (tela e React pela API)."""
    return _PLOTLY[pontos.tipo](pontos, escala_para(pontos))


def figura_do_pdf(pontos: PontosDoGrafico, estilo: Estilo = PADRAO) -> Figure:
    """A figura matplotlib do gráfico, antes de virar PNG (os testes olham os eixos dela)."""
    return _PDF[pontos.tipo](pontos, escala_para(pontos), estilo)


def png(pontos: PontosDoGrafico, estilo: Estilo = PADRAO) -> bytes:
    """O gráfico como imagem PNG, nas cores do estilo do PDF."""
    return graficos_pdf.figura_em_png(figura_do_pdf(pontos, estilo))
