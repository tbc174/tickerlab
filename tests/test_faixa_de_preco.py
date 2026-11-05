"""Linha 412: mínima e máxima de 52 semanas e variação em 12 meses, com o fechamento sem ajuste."""

import pandas as pd
import pytest

from src import dados
from src.faixa_de_preco import calcular_faixa_de_preco


def _serie(valores: list[float], fim: str = "2026-11-03") -> pd.Series:
    indice = pd.bdate_range(end=fim, periods=len(valores))
    return pd.Series(valores, index=indice, name="Close")


def _dois_anos() -> pd.Series:
    """520 dias úteis: sobe de 10 a 20, com um pico de 30 e um vale de 5 no último ano."""
    valores = [10.0 + i * 10 / 519 for i in range(520)]
    valores[400], valores[450] = 30.0, 5.0
    return _serie(valores)


def test_minima_e_maxima_so_olham_as_52_semanas():
    serie = _dois_anos()
    serie.iloc[10] = 100.0  # fora da janela: não pode entrar
    faixa = calcular_faixa_de_preco(serie)
    assert faixa is not None
    assert faixa.maxima == 30.0 and faixa.minima == 5.0
    assert faixa.data_da_maxima == serie.index[400].date()
    assert faixa.data_da_minima == serie.index[450].date()
    assert faixa.ate == serie.index[-1].date()


def test_variacao_em_12_meses_compara_com_o_dia_de_um_ano_antes():
    serie = _serie([10.0] * 400 + [11.0] * 120)
    faixa = calcular_faixa_de_preco(serie)
    assert faixa is not None
    assert faixa.variacao_12_meses == pytest.approx(0.10)
    assert faixa.data_da_base < faixa.ate


def test_sem_historico_de_um_ano_nao_ha_variacao_mas_ha_faixa():
    faixa = calcular_faixa_de_preco(_serie([10.0, 12.0, 8.0] * 30))
    assert faixa is not None
    assert faixa.variacao_12_meses is None
    assert (faixa.minima, faixa.maxima) == (8.0, 12.0)


@pytest.mark.parametrize("vazia", [None, pd.Series([], dtype=float)])
def test_sem_serie_nao_ha_faixa(vazia):
    assert calcular_faixa_de_preco(vazia) is None


def test_cortar_o_futuro_nao_muda_o_passado():
    serie = _dois_anos()
    corte = serie.index[-30]
    inteira = calcular_faixa_de_preco(serie, ate=corte.date())
    cortada = calcular_faixa_de_preco(serie.loc[:corte])
    assert inteira == cortada


def test_o_texto_diz_a_base_a_fonte_e_a_data():
    faixa = calcular_faixa_de_preco(_serie([10.0] * 400 + [11.0] * 120))
    assert faixa is not None
    texto = faixa.texto()
    assert "sem ajuste" in texto and "Yahoo Finance" in texto
    assert "proventos" in texto  # avisa que a variação não conta dividendos
    assert faixa.ate.strftime("%d/%m/%Y") in texto


def test_o_download_pede_o_fechamento_sem_ajuste(monkeypatch):
    pedidos = []
    colunas = pd.MultiIndex.from_tuples(
        [("Close", "PETR4.SA")], names=["Price", "Ticker"]
    )
    tabela = pd.DataFrame(
        [[10.0], [11.0]], index=pd.bdate_range("2026-11-02", periods=2), columns=colunas
    )

    def falso(ticker, **pedido):
        pedidos.append(pedido)
        return tabela

    monkeypatch.setattr("src.dados.yf.download", falso)
    serie = dados.baixar_fechamento_sem_ajuste("petr4")
    assert pedidos[0]["auto_adjust"] is False
    assert list(serie) == [10.0, 11.0]


def test_o_download_falho_devolve_none(monkeypatch):
    monkeypatch.setattr("src.dados.yf.download", lambda *a, **k: pd.DataFrame())
    assert dados.baixar_fechamento_sem_ajuste("XXXX9") is None
