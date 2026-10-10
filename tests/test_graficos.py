"""Testes de src/graficos.py: conferem o que vai dentro da figura, sem abrir navegador."""

import numpy as np
import pandas as pd
import pytest

from src.graficos import (
    CONFIG_PLOTLY,
    _numero_br,
    criar_grafico_drawdown,
    criar_grafico_preco,
    criar_grafico_volatilidade,
)
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


# --- Gráfico de preço interativo ------------------------------------------------


def _ohlcv(dias=10, fim_de_semana=False):
    datas = pd.date_range(
        "2026-01-01", periods=dias, freq="D" if fim_de_semana else "B"
    )
    base = np.linspace(10, 12, dias)
    return pd.DataFrame(
        {
            "Open": base,
            "High": base + 0.5,
            "Low": base - 0.5,
            "Close": base + 0.1,
            "Volume": np.arange(dias) * 1000 + 1000,
        },
        index=datas,
    )


def test_grafico_de_preco_em_linha():
    figura = criar_grafico_preco(_ohlcv(), tipo="linha")
    tipos = [type(tr).__name__ for tr in figura.data]
    assert tipos == ["Scatter", "Bar"]  # linha do preço e volume embaixo


def test_grafico_de_preco_em_velas():
    figura = criar_grafico_preco(_ohlcv(), tipo="velas")
    tipos = [type(tr).__name__ for tr in figura.data]
    assert tipos == ["Candlestick", "Bar"]


def test_medias_moveis_viram_linhas_extras_e_ligam_a_legenda():
    figura = criar_grafico_preco(_ohlcv(30), janelas_medias=(5, 10))
    nomes = [tr.name for tr in figura.data]
    assert "MM 5" in nomes and "MM 10" in nomes
    assert figura.layout.showlegend is True


def test_sem_medias_nao_mostra_legenda():
    assert criar_grafico_preco(_ohlcv()).layout.showlegend is False


def test_grafico_de_preco_tem_botoes_de_periodo():
    figura = criar_grafico_preco(_ohlcv())
    rotulos = [b.label for b in figura.layout.xaxis.rangeselector.buttons]
    assert rotulos == ["1M", "3M", "6M", "1A", "YTD", "Tudo"]


def test_zoom_do_preco_e_do_volume_andam_juntos():
    figura = criar_grafico_preco(_ohlcv())
    # os dois eixos horizontais estão ligados: dar zoom em um muda o outro
    assert figura.layout.xaxis.matches == "x2"


def test_etiqueta_com_o_ultimo_preco():
    dados = _ohlcv()
    figura = criar_grafico_preco(dados)
    textos = [a.text for a in figura.layout.annotations]
    assert _numero_br(dados["Close"].iloc[-1]) in textos  # formato brasileiro


def test_dia_util_esconde_o_fim_de_semana_mas_cripto_nao():
    acao = criar_grafico_preco(_ohlcv(10, fim_de_semana=False))
    cripto = criar_grafico_preco(_ohlcv(10, fim_de_semana=True))
    assert len(acao.layout.xaxis.rangebreaks) == 1
    assert not cripto.layout.xaxis.rangebreaks


def test_tipo_de_grafico_invalido():
    with pytest.raises(ValueError, match="Tipo de gráfico"):
        criar_grafico_preco(_ohlcv(), tipo="barras")


def test_dados_sem_colunas_de_preco():
    with pytest.raises(ValueError, match="Faltam colunas"):
        criar_grafico_preco(_ohlcv().drop(columns=["Volume"]))


def test_config_permite_zoom_com_a_roda_do_mouse():
    assert CONFIG_PLOTLY["scrollZoom"] is True
    assert CONFIG_PLOTLY["displaylogo"] is False


def test_graficos_de_risco_tem_botoes_de_periodo_e_linha_guia():
    fechamento = _fechamento()
    figura = criar_grafico_drawdown(calcular_drawdown(fechamento))
    assert len(figura.layout.xaxis.rangeselector.buttons) == 6
    assert figura.layout.xaxis.showspikes is True


# --- Velas: recorte, dica do mouse e formato brasileiro -----------------------------


def test_numero_no_formato_brasileiro():
    assert _numero_br(12345.6) == "12.345,60"
    assert _numero_br(0.5) == "0,50"
    assert _numero_br(1234567.891) == "1.234.567,89"


def test_dias_visiveis_mostra_so_os_ultimos_dias():
    dados = _ohlcv(30)
    figura = criar_grafico_preco(dados, tipo="velas", dias_visiveis=10)
    assert len(figura.data[0].x) == 10
    assert list(figura.data[0].x) == list(dados.index[-10:])
    assert len(figura.data[-1].x) == 10  # o volume acompanha o recorte


def test_media_movel_usa_o_historico_inteiro_mesmo_com_recorte():
    # Com 30 dias e janela 20, só os 10 últimos dias têm média. O recorte de 10 dias
    # não pode zerar a média: ela deve ser calculada antes do recorte.
    dados = _ohlcv(30)
    figura = criar_grafico_preco(dados, janelas_medias=(20,), dias_visiveis=10)
    media = next(tr for tr in figura.data if tr.name == "MM 20")
    assert not pd.isna(np.array(media.y, dtype=float)).any()


def test_dias_visiveis_invalido():
    with pytest.raises(ValueError, match="dias_visiveis"):
        criar_grafico_preco(_ohlcv(), dias_visiveis=0)


def test_dica_do_mouse_das_velas_em_portugues():
    dados = _ohlcv(5)
    vela = criar_grafico_preco(dados, tipo="velas").data[0]
    texto = vela.hovertext[1]
    for palavra in ("Abertura", "Máxima", "Mínima", "Fechamento", "Variação no dia"):
        assert palavra in texto
    assert vela.hoverinfo == "text"


def test_variacao_do_dia_usa_o_fechamento_anterior():
    datas = pd.date_range("2026-01-05", periods=2)
    dados = pd.DataFrame(
        {
            "Open": [10.0, 10.0],
            "High": [11.0, 12.0],
            "Low": [9.0, 9.0],
            "Close": [10.0, 11.0],
            "Volume": [1, 1],
        },
        index=datas,
    )
    vela = criar_grafico_preco(dados, tipo="velas").data[0]
    assert "—" in vela.hovertext[0]  # primeiro dia: sem dia anterior
    assert "+10,00%" in vela.hovertext[1]  # 11 contra o fechamento anterior de 10
