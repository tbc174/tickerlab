"""Gera as imagens do README a partir dos dados de exemplo (sem internet e sem abrir o app).

Usa os mesmos gráficos do app (`src/graficos.py`). Precisa do pacote `kaleido` (só para gerar as
imagens; não faz parte do app):

    python -m pip install kaleido
    python scripts/gerar_imagens_do_readme.py

As imagens vão para `docs/imagens/`.
"""

from pathlib import Path

import plotly.graph_objects as go

from src import graficos
from src import indicadores as ind
from src.backtest import executar_backtest
from src.comparacao import alinhar_fechamentos, rebasear_para_100
from src.estrategias import gerar_posicao
from src.exemplos import carregar_exemplo

PASTA = Path(__file__).resolve().parent.parent / "docs" / "imagens"
LARGURA, ALTURA, ESCALA = 1200, 520, 2
TICKER = "PETR4.SA"


def _salvar(figura: go.Figure, nome: str, altura: int = ALTURA) -> None:
    figura.update_layout(width=LARGURA, height=altura)
    caminho = PASTA / nome
    figura.write_image(caminho, scale=ESCALA)
    print("gerada:", caminho.relative_to(PASTA.parent.parent))


def main() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    dados = carregar_exemplo(TICKER, "2y")
    fechamento = dados["Close"]
    retorno = ind.calcular_retorno_diario(fechamento)

    _salvar(graficos.criar_grafico_preco(dados, "linha", (50, 200)), "preco.png", 620)

    drawdown = ind.calcular_drawdown(fechamento)
    pior = ind.encontrar_pior_drawdown(fechamento)
    _salvar(graficos.criar_grafico_drawdown(drawdown, pior), "drawdown.png", 420)

    tabela = ind.montar_tabela_retornos(ind.calcular_retorno_mensal(retorno))
    _salvar(graficos.criar_mapa_de_calor_mensal(tabela), "retorno-mensal.png", 440)

    curvas = {
        "MACD": executar_backtest(
            fechamento, gerar_posicao("MACD", dados)
        ).curva_de_capital,
        "Comprar e segurar": executar_backtest(
            fechamento, gerar_posicao("Comprar e segurar", dados)
        ).curva_de_capital,
    }
    _salvar(
        graficos.criar_grafico_curvas_de_capital(curvas, 10_000.0, "MACD"),
        "backtest.png",
    )

    fechamentos = {
        t: carregar_exemplo(t, "2y")["Close"] for t in (TICKER, "^BVSP", "^GSPC")
    }
    alinhado, _ = alinhar_fechamentos(fechamentos)
    _salvar(
        graficos.criar_grafico_comparacao(rebasear_para_100(alinhado), TICKER),
        "comparar.png",
    )


if __name__ == "__main__":
    main()
