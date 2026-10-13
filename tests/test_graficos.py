"""Testes de src/graficos.py: conferem o que vai dentro da figura, sem abrir navegador."""

import json

import numpy as np
import pandas as pd
import pytest

from src import graficos, marca
from src.graficos import (
    CONFIG_PLOTLY,
    ZOOM_COM_A_RODA_DO_MOUSE,
    _numero_br,
    criar_grafico_beta_movel,
    criar_grafico_comparacao,
    criar_grafico_cone_monte_carlo,
    criar_grafico_curvas_de_capital,
    criar_grafico_diferenca_das_janelas,
    criar_grafico_disjuntor,
    criar_grafico_dispersao_do_beta,
    criar_grafico_drawdown,
    criar_grafico_momentum,
    criar_grafico_operacoes_no_preco,
    criar_grafico_pesos,
    criar_grafico_preco,
    criar_grafico_quedas_comparadas,
    criar_grafico_regimes,
    criar_grafico_risco_retorno,
    criar_grafico_volatilidade,
    criar_grafico_volatilidade_prevista,
    criar_grafico_z_do_par,
    criar_histograma_do_acaso,
    criar_mapa_de_calor_de_correlacao,
    criar_mapa_de_calor_de_parametros,
    criar_mapa_de_calor_mensal,
)
from src.indicadores import (
    NOMES_DOS_MESES,
    calcular_drawdown,
    encontrar_pior_drawdown,
    montar_tabela_retornos,
)


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


def test_config_acompanha_a_opcao_de_zoom_com_a_roda_do_mouse():
    assert CONFIG_PLOTLY["scrollZoom"] is ZOOM_COM_A_RODA_DO_MOUSE
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


# --- Mapa de calor do retorno mensal ---------------------------------------------


def _tabela_de_exemplo():
    meses = pd.PeriodIndex(["2025-12", "2026-01", "2026-02"], freq="M")
    return montar_tabela_retornos(pd.Series([0.05, 0.10, -0.01], index=meses))


def test_mapa_de_calor_tem_uma_linha_por_ano_mais_a_media():
    figura = criar_mapa_de_calor_mensal(_tabela_de_exemplo())
    mapa = figura.data[0]
    assert len(mapa.y) == 3  # 2025, 2026 e "Média do mês"
    assert list(mapa.x) == [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    assert np.array(mapa.z).shape == (3, 12)


def test_total_do_ano_aparece_no_rotulo_da_linha():
    mapa = criar_mapa_de_calor_mensal(_tabela_de_exemplo()).data[0]
    assert mapa.y[0] == "2025  (+5,0%)"
    assert mapa.y[1] == "2026  (+8,9%)"  # 1,10 x 0,99 - 1


def test_texto_das_celulas_em_formato_brasileiro_e_traco_para_vazio():
    mapa = criar_mapa_de_calor_mensal(_tabela_de_exemplo()).data[0]
    linha_2026 = mapa.text[1]
    assert linha_2026[0] == "+10,0%"  # janeiro de 2026
    assert linha_2026[1] == "-1,0%"  # fevereiro de 2026
    assert linha_2026[2] == "—"  # março: sem dados


def test_cores_simetricas_em_torno_do_zero():
    mapa = criar_mapa_de_calor_mensal(_tabela_de_exemplo()).data[0]
    assert mapa.zmin == -mapa.zmax


def test_mapa_de_calor_sem_dados_levanta_erro():
    with pytest.raises(ValueError, match="vazia"):
        criar_mapa_de_calor_mensal(montar_tabela_retornos(pd.Series(dtype=float)))


def test_botoes_dos_graficos_de_risco_ficam_a_direita_do_titulo():
    figura = criar_grafico_drawdown(calcular_drawdown(_fechamento()))
    seletor = figura.layout.xaxis.rangeselector
    assert seletor.x == 1 and seletor.xanchor == "right"


# --- Gráfico de comparação (base 100) ----------------------------------------------------


def _base100():
    datas = pd.date_range("2026-01-05", periods=4, freq="B")
    return pd.DataFrame(
        {
            "PETR4.SA": [100.0, 105.0, 103.0, 110.0],
            "^BVSP": [100.0, 101.0, 102.0, 103.0],
            "^GSPC": [100.0, 99.0, 101.0, 104.0],
            "AAPL": [100.0, 102.0, 104.0, 106.0],
            "VALE3.SA": [100.0, 98.0, 99.0, 97.0],
        },
        index=datas,
    )


def test_comparacao_tem_uma_linha_por_ativo_com_a_cor_certa():
    figura = criar_grafico_comparacao(_base100(), principal="PETR4.SA")
    linhas = {tr.name: tr.line for tr in figura.data}
    assert list(linhas) == ["PETR4.SA", "^BVSP", "^GSPC", "AAPL", "VALE3.SA"]
    assert linhas["PETR4.SA"].color == graficos.COR_AZUL  # o principal, em azul
    assert linhas["^BVSP"].color == linhas["^GSPC"].color  # índices em cinza
    assert linhas["^GSPC"].dash == "dash"  # S&P 500 tracejado
    assert linhas["^BVSP"].dash is None
    assert (
        linhas["AAPL"].color != linhas["VALE3.SA"].color
    )  # os demais, cores diferentes


def test_comparacao_usa_nomes_amigaveis_na_legenda():
    figura = criar_grafico_comparacao(
        _base100(), "PETR4.SA", nomes={"^BVSP": "Ibovespa", "^GSPC": "S&P 500"}
    )
    nomes = [tr.name for tr in figura.data]
    assert "Ibovespa" in nomes and "S&P 500" in nomes and "^BVSP" not in nomes
    assert figura.layout.showlegend is True


def test_comparacao_tem_linha_de_referencia_em_100():
    figura = criar_grafico_comparacao(_base100(), "PETR4.SA")
    assert any(forma.y0 == 100 for forma in figura.layout.shapes)


def test_comparacao_sem_dados_levanta_erro():
    with pytest.raises(ValueError, match="em comum"):
        criar_grafico_comparacao(pd.DataFrame(), "PETR4.SA")


# --- Gráficos do backtest ----------------------------------------------------------------


def _curvas():
    datas = pd.date_range("2026-01-05", periods=4, freq="B")
    return {
        "Cruzamento de médias": pd.Series([1.0, 1.05, 1.02, 1.10], index=datas),
        "Comprar e segurar": pd.Series([1.0, 1.10, 0.90, 1.20], index=datas),
    }


def test_curvas_de_capital_multiplicam_pelo_capital_inicial():
    figura = criar_grafico_curvas_de_capital(
        _curvas(), 10_000, destaque="Cruzamento de médias"
    )
    destaque = next(tr for tr in figura.data if tr.name == "Cruzamento de médias")
    assert list(destaque.y) == pytest.approx([10_000, 10_500, 10_200, 11_000])
    assert destaque.line.color == graficos.COR_AZUL  # a estratégia em destaque, em azul
    outra = next(tr for tr in figura.data if tr.name == "Comprar e segurar")
    assert outra.line.color != graficos.COR_AZUL
    assert any(forma.y0 == 10_000 for forma in figura.layout.shapes)


def test_quedas_comparadas_comecam_em_zero_e_nunca_sao_positivas():
    figura = criar_grafico_quedas_comparadas(_curvas(), destaque="Cruzamento de médias")
    assert len(figura.data) == 2
    for tr in figura.data:
        assert max(tr.y) <= 0
    referencia = next(tr for tr in figura.data if tr.name == "Comprar e segurar")
    assert min(referencia.y) == pytest.approx(0.90 / 1.10 - 1)


@pytest.mark.parametrize(
    "funcao",
    [
        lambda: criar_grafico_curvas_de_capital({}, 10_000, "x"),
        lambda: criar_grafico_quedas_comparadas({}, "x"),
    ],
)
def test_graficos_do_backtest_sem_curvas(funcao):
    with pytest.raises(ValueError, match="curvas"):
        funcao()


def test_operacoes_no_preco_marcam_entradas_e_saidas():
    datas = pd.date_range("2026-01-05", periods=6, freq="B")
    fechamento = pd.Series([10, 11, 12, 11, 10, 12], index=datas, dtype=float)
    operacoes = pd.DataFrame(
        {
            "entrada": [datas[1], datas[4]],
            "saida": [datas[2], datas[5]],
            "dias": [2, 2],
            "retorno": [0.1, 0.2],
            "aberta": [False, True],
        }
    )
    figura = criar_grafico_operacoes_no_preco(fechamento, operacoes)
    nomes = [tr.name for tr in figura.data]
    assert nomes == ["Preço", "Entrada", "Saída"]
    entrada = figura.data[1]
    assert list(entrada.y) == [11, 10]
    saida = figura.data[2]
    assert list(saida.y) == [12]  # a operação aberta ainda não tem saída


def test_operacoes_no_preco_sem_operacoes_mostra_so_o_preco():
    datas = pd.date_range("2026-01-05", periods=3, freq="B")
    fechamento = pd.Series([10, 11, 12], index=datas, dtype=float)
    vazio = pd.DataFrame(columns=["entrada", "saida", "dias", "retorno", "aberta"])
    figura = criar_grafico_operacoes_no_preco(fechamento, vazio)
    assert [tr.name for tr in figura.data] == ["Preço"]


# --- Mapa de parâmetros ---------------------------------------------------------------------


def _mapa_de_parametros():
    return pd.DataFrame([[0.5, np.nan], [-0.2, 1.3]], index=[50, 100], columns=[10, 20])


def test_mapa_de_parametros_mostra_cada_celula_e_deixa_a_invalida_vazia():
    figura = criar_mapa_de_calor_de_parametros(_mapa_de_parametros(), "Curta", "Longa")
    heat = figura.data[0]
    assert list(heat.x) == ["10", "20"] and list(heat.y) == ["50", "100"]
    assert heat.text[0][0] == "0,50" and heat.text[0][1] == ""
    assert heat.text[1][0] == "-0,20"


def test_mapa_de_parametros_centra_as_cores_no_zero():
    heat = criar_mapa_de_calor_de_parametros(
        _mapa_de_parametros(), "Curta", "Longa"
    ).data[0]
    assert heat.zmin == -heat.zmax


def test_mapa_de_parametros_marca_a_escolha_atual():
    figura = criar_mapa_de_calor_de_parametros(
        _mapa_de_parametros(), "Curta", "Longa", escolhido=(20, 100)
    )
    assert len(figura.data) == 2
    assert figura.data[1].x == ("20",) and figura.data[1].y == ("100",)


def test_mapa_de_parametros_ignora_escolha_fora_da_grade():
    figura = criar_mapa_de_calor_de_parametros(
        _mapa_de_parametros(), "Curta", "Longa", escolhido=(999, 100)
    )
    assert len(figura.data) == 1


def test_mapa_de_parametros_com_uma_linha_esconde_o_eixo_y():
    mapa = pd.DataFrame([[0.4, 0.9]], index=[""], columns=[100, 200])
    figura = criar_mapa_de_calor_de_parametros(mapa, "Janela", escolhido=(200, ""))
    assert figura.layout.yaxis.showticklabels is False
    assert len(figura.data) == 2


def test_mapa_de_parametros_vazio_da_erro():
    with pytest.raises(ValueError, match="vazio"):
        criar_mapa_de_calor_de_parametros(pd.DataFrame(), "Curta")


# --- Monte Carlo e acaso ----------------------------------------------------------------------


def _percentis():
    return pd.DataFrame(
        {
            "p5": [1, 0.9, 0.8],
            "p25": [1, 1.0, 0.95],
            "p50": [1, 1.05, 1.1],
            "p75": [1, 1.1, 1.25],
            "p95": [1, 1.2, 1.5],
        }
    )


def test_cone_tem_faixas_mediana_e_ordem_real():
    figura = criar_grafico_cone_monte_carlo(_percentis(), np.array([1.0, 1.1, 1.3]))
    nomes = [t.name for t in figura.data]
    assert nomes[-2:] == ["Mediana", "Ordem real"]
    assert "5% a 95%" in nomes and "25% a 75%" in nomes
    assert list(figura.data[-1].y) == [1.0, 1.1, 1.3]


def test_cone_vazio_da_erro():
    with pytest.raises(ValueError, match="simulações"):
        criar_grafico_cone_monte_carlo(pd.DataFrame(), np.array([1.0]))


def test_histograma_do_acaso_marca_o_sharpe_real():
    figura = criar_histograma_do_acaso(np.array([0.1, 0.2, -0.3, 0.5]), 0.9)
    assert figura.layout.shapes[0].x0 == 0.9
    assert len(figura.data[0].x) == 4


def test_histograma_do_acaso_vazio_da_erro():
    with pytest.raises(ValueError, match="sorteios"):
        criar_histograma_do_acaso(np.array([]), 1.0)


# --- Risco e retorno --------------------------------------------------------------------------


def _pontos():
    return pd.DataFrame(
        {
            "Volatilidade anual": [0.2, 0.1, np.nan],
            "Retorno anualizado": [0.15, 0.05, 0.3],
        },
        index=["Comprar e segurar", "Filtro de tendência", "Sem dados"],
    )


def test_risco_retorno_tem_um_ponto_por_estrategia_com_numeros():
    figura = criar_grafico_risco_retorno(_pontos(), destaque="Comprar e segurar")
    assert list(figura.data[0].text) == ["Comprar e segurar", "Filtro de tendência"]
    assert figura.data[0].marker.color[0] == graficos.COR_AZUL
    assert figura.data[0].marker.color[1] != graficos.COR_AZUL


def test_risco_retorno_vazio_da_erro():
    with pytest.raises(ValueError, match="estratégias"):
        criar_grafico_risco_retorno(pd.DataFrame())
    with pytest.raises(ValueError, match="números"):
        criar_grafico_risco_retorno(_pontos().iloc[[2]])


# --- Composição da carteira -------------------------------------------------------------------


def test_grafico_de_pesos_tem_um_traco_por_ativo_mais_o_caixa():
    pesos = pd.DataFrame(
        {"A": [0.5, 0.0, 0.3], "B": [0.25, 0.0, 0.3]},
        index=pd.date_range("2026-01-01", periods=3),
    )
    figura = criar_grafico_pesos(pesos)
    assert [t.name for t in figura.data] == ["A", "B", "Caixa"]
    assert list(figura.data[-1].y) == pytest.approx([0.25, 1.0, 0.4])
    assert all(t.stackgroup == "carteira" for t in figura.data)


def test_grafico_de_pesos_vazio_da_erro():
    with pytest.raises(ValueError, match="pesos"):
        criar_grafico_pesos(pd.DataFrame())


# --- Diferença das janelas --------------------------------------------------------------------


def test_diferenca_das_janelas_desenha_a_serie_com_linha_no_zero():
    serie = pd.Series([0.1, -0.05, 0.02], index=pd.date_range("2026-01-01", periods=3))
    figura = criar_grafico_diferenca_das_janelas(serie)
    assert list(figura.data[0].y) == [0.1, -0.05, 0.02]
    assert figura.layout.shapes[0].y0 == 0


def test_diferenca_das_janelas_vazia_da_erro():
    with pytest.raises(ValueError, match="janelas"):
        criar_grafico_diferenca_das_janelas(pd.Series(dtype=float))


def test_grafico_de_regimes_pinta_cada_dia_com_a_cor_do_seu_regime():
    indice = pd.date_range("2026-01-01", periods=4)
    preco = pd.Series([10.0, 11.0, 12.0, 13.0], index=indice)
    regime = pd.Series(["Calmo", "Agitado", "Calmo", "Sem histórico"], index=indice)
    figura = criar_grafico_regimes(
        preco, regime, {"Calmo": graficos.COR_ALTA, "Agitado": graficos.COR_QUEDA}
    )
    assert [t.name for t in figura.data] == ["Calmo", "Agitado"]
    assert figura.data[0].y[0] == 10.0 and figura.data[0].y[2] == 12.0


def test_grafico_de_regimes_exige_as_mesmas_datas():
    preco = pd.Series([1.0, 2.0], index=pd.date_range("2026-01-01", periods=2))
    with pytest.raises(ValueError, match="mesmas datas"):
        criar_grafico_regimes(preco, preco.iloc[:1].astype(object), {"A": "#000"})


def test_grafico_do_disjuntor_marca_os_disparos():
    indice = pd.date_range("2026-01-01", periods=5)
    curva = pd.Series([1.0, 1.1, 1.0, 0.9, 0.95], index=indice)
    figura = criar_grafico_disjuntor({"Com": curva}, 100.0, "Com", indice[[3]])
    assert figura.data[-1].name == "Disjuntor disparou"
    assert list(figura.data[-1].y) == pytest.approx([90.0])
    sem = criar_grafico_disjuntor({"Com": curva}, 100.0, "Com", indice[:0])
    assert len(sem.data) == 1


def test_grafico_da_volatilidade_prevista_tem_tres_linhas():
    indice = pd.date_range("2026-01-01", periods=5)
    serie = pd.Series([0.2, 0.25, 0.3, 0.2, 0.22], index=indice)
    figura = criar_grafico_volatilidade_prevista(serie, serie * 1.1, serie * 0.9)
    assert [t.name for t in figura.data][-1] == "Prevista pelo modelo"
    assert len(figura.data) == 3
    with pytest.raises(ValueError, match="previsões"):
        criar_grafico_volatilidade_prevista(serie.iloc[:0], serie, serie)


def test_grafico_do_z_do_par_marca_posicoes_e_inicio_do_teste():
    indice = pd.date_range("2026-01-01", periods=6)
    z = pd.Series([0.0, -2.5, -2.0, 0.1, 2.6, 0.0], index=indice)
    lado = pd.Series([0.0, 1.0, 1.0, 0.0, -1.0, 0.0], index=indice)
    figura = criar_grafico_z_do_par(z, lado, 2.0, 4.0, indice[2])
    nomes = [t.name for t in figura.data]
    assert nomes == [
        "z-score",
        "Comprado em A, vendido em B",
        "Vendido em A, comprado em B",
    ]
    assert (
        len(figura.layout.shapes) == 6
    )  # zero, duas entradas, dois stops e o início do teste
    with pytest.raises(ValueError, match="z-score"):
        criar_grafico_z_do_par(z * float("nan"), lado, 2.0, 4.0, indice[2])


def test_mapa_de_correlacao_mostra_a_matriz_em_formato_brasileiro():
    matriz = pd.DataFrame(
        [[1.0, 0.5], [0.5, 1.0]], index=["A", "B"], columns=["A", "B"]
    )
    figura = criar_mapa_de_calor_de_correlacao(matriz)
    assert figura.data[0].text[0][1] == "0,50"
    assert figura.data[0].zmin == -1 and figura.data[0].zmax == 1
    with pytest.raises(ValueError, match="quadrada"):
        criar_mapa_de_calor_de_correlacao(matriz.iloc[:1])


def test_grafico_do_beta_movel_tem_linha_em_um():
    beta = pd.Series([0.9, 1.1, 1.3], index=pd.date_range("2026-01-01", periods=3))
    figura = criar_grafico_beta_movel(beta, 126)
    assert list(figura.data[0].y) == [0.9, 1.1, 1.3]
    assert figura.layout.shapes[0].y0 == 1
    with pytest.raises(ValueError, match="beta"):
        criar_grafico_beta_movel(beta.iloc[:0], 126)


def test_dispersao_do_beta_tem_pontos_e_reta_com_a_inclinacao_certa():
    indice = pd.date_range("2026-01-01", periods=4)
    x = pd.Series([-0.02, -0.01, 0.01, 0.02], index=indice)
    figura = criar_grafico_dispersao_do_beta(2 * x, x, 2.0, 0.0)
    assert len(figura.data[0].x) == 4
    reta = figura.data[1]
    assert list(reta.y) == pytest.approx([-0.04, 0.04])
    with pytest.raises(ValueError, match="em comum"):
        criar_grafico_dispersao_do_beta(x.iloc[:0], x.iloc[:0], 1.0, 0.0)


def test_grafico_do_momentum_pinta_positivos_de_verde_e_negativos_de_vermelho():
    momentum = pd.Series({"A": 0.3, "B": -0.1, "C": 0.05})
    figura = criar_grafico_momentum(momentum)
    barra = figura.data[0]
    assert list(barra.y) == ["B", "C", "A"]  # do mais fraco ao mais forte
    assert list(barra.marker.color) == [
        graficos.COR_QUEDA,
        graficos.COR_ALTA,
        graficos.COR_ALTA,
    ]
    with pytest.raises(ValueError, match="momentum"):
        criar_grafico_momentum(momentum.iloc[:0])


def test_eixos_dos_graficos_em_dinheiro_nao_viram_porcentagem():
    """A base dos gráficos formata o eixo como porcentagem; os de dinheiro e de fatia trocam."""
    anual = pd.DataFrame(
        {"receita": [1e11, 2e11], "lucro": [1e10, 2e10]}, index=[2024, 2025]
    )
    assert (
        graficos.criar_grafico_fundamentos_anuais(anual).layout.yaxis.tickformat
        != ".0%"
    )
    resumo = pd.DataFrame(
        {"mes": pd.to_datetime(["2026-08-01"]), "compras": [2e6], "vendas": [-1e6]}
    )
    assert (
        graficos.criar_grafico_negociacoes(resumo, "BRL").layout.yaxis.tickformat
        != ".0%"
    )
    historico = pd.DataFrame(
        {"competencia": pd.to_datetime(["2026-07-31", "2026-08-31"]), "fatia": [0.1, 0.12],
         "fatia_vendidos": [0.01, 0.02], "vendidos": [3, 4]}
    )  # fmt: skip
    assert max(graficos.criar_grafico_detentores(historico, "fundos").data[0].y) <= 1


# --- tema claro (13/10/2026): o mesmo gráfico, com as cores da paleta clara -------------------
_SO_DO_ESCURO = (
    marca.FUNDO,
    marca.SUPERFICIE,
    marca.DESTAQUE,
    marca.TEXTO,
    marca.TEXTO_APAGADO,
    *marca.SERIES,
)


def _cores_da_figura(figura) -> str:
    dados = json.loads(
        figura.to_json()
    )  # o JSON do Plotly sabe gravar os arrays do NumPy
    dados["layout"].pop("template", None)  # o tema do Plotly é conferido à parte
    return json.dumps(dados).lower()


@pytest.mark.parametrize("tipo", ["linha", "velas"])
def test_grafico_no_tema_claro_nao_leva_cor_do_escuro(tipo):
    figura = criar_grafico_preco(_ohlcv(), tipo=tipo)
    clara = graficos.no_tema(figura, marca.PALETA_CLARA)
    cores = _cores_da_figura(clara)
    for cor in _SO_DO_ESCURO:
        assert cor.lower() not in cores, cor
    assert clara.layout.template.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert clara.layout.template.layout.font.color == marca.PALETA_CLARA.texto


def test_no_tema_nao_muda_a_figura_original_nem_vaza_para_outra_sessao():
    """Função pura: uma pessoa no claro não muda o gráfico de quem está no escuro."""
    figura = criar_grafico_preco(_ohlcv(), tipo="linha")
    antes = figura.to_json()
    graficos.no_tema(figura, marca.PALETA_CLARA)
    assert figura.to_json() == antes
    escura = graficos.no_tema(
        criar_grafico_preco(_ohlcv(), tipo="linha"), marca.PALETA_ESCURA
    )
    assert escura.to_json() == antes  # no escuro, nada muda


def test_mapa_de_calor_no_tema_claro_usa_a_superficie_clara_no_zero():
    tabela = pd.DataFrame(
        [[0.01] * 12 + [0.12]], index=[2025], columns=[*NOMES_DOS_MESES, "Ano"]
    )
    clara = graficos.no_tema(
        graficos.criar_mapa_de_calor_mensal(tabela), marca.PALETA_CLARA
    )
    meio = next(c for posicao, c in clara.data[0].colorscale if posicao == 0.5)
    assert meio == marca.PALETA_CLARA.superficie


def test_botao_ativo_do_periodo_le_bem_no_claro():
    clara = graficos.no_tema(
        criar_grafico_preco(_ohlcv(), tipo="linha"), marca.PALETA_CLARA
    )
    seletor = clara.layout.xaxis.rangeselector
    assert (
        seletor.activecolor == "#c7d6ff"
    )  # texto marinho sobre azul claro (no escuro: elétrico)
