"""Testes de src/graficos.py: conferem o que vai dentro da figura, sem abrir navegador."""

import numpy as np
import pandas as pd

from src.graficos import criar_grafico_drawdown, criar_grafico_volatilidade
from src.indicadores import calcular_drawdown, encontrar_pior_drawdown


def _fechamento():
    datas = pd.date_range("2026-01-01", periods=6)
    return pd.Series([100.0, 120.0, 90.0, 120.0, 60.0, 100.0], index=datas)


def test_grafico_de_drawdown_tem_a_curva_e_o_marcador_do_fundo():
    fechamento = _fechamento()
    drawdown = calcular_drawdown(fechamento)
    figura = criar_grafico_drawdown(drawdown, encontrar_pior_drawdown(fechamento))

    assert len(figura.data) == 2  # a área do drawdown e o ponto da pior queda
    assert list(figura.data[0].y) == list(drawdown)
    assert figura.data[1].y[0] == -0.5
    assert pd.Timestamp(figura.data[1].x[0]) == pd.Timestamp("2026-01-05")


def test_grafico_de_drawdown_sem_pior_queda_nao_tem_marcador():
    drawdown = calcular_drawdown(_fechamento())
    assert len(criar_grafico_drawdown(drawdown).data) == 1


def test_grafico_de_drawdown_de_preco_sempre_subindo_nao_tem_marcador():
    fechamento = pd.Series(
        [1.0, 2.0, 3.0], index=pd.date_range("2026-01-01", periods=3)
    )
    figura = criar_grafico_drawdown(
        calcular_drawdown(fechamento), encontrar_pior_drawdown(fechamento)
    )
    assert len(figura.data) == 1


def test_grafico_de_volatilidade_mostra_a_janela_no_titulo():
    vol = pd.Series([np.nan, 0.2, 0.3], index=pd.date_range("2026-01-01", periods=3))
    figura = criar_grafico_volatilidade(vol, janela=60)
    assert "60 dias" in figura.layout.title.text
    assert len(figura.data) == 1


def test_eixo_vertical_e_em_porcentagem():
    drawdown = calcular_drawdown(_fechamento())
    figura = criar_grafico_drawdown(drawdown)
    assert figura.layout.yaxis.tickformat == ".0%"
