"""Universo de ativos e baixador do histórico (com MT5 e yfinance falsos)."""

import pandas as pd
import pytest

from tests.test_trader_dados import _candles
from tests.test_trader_mt5 import CANDLES, MT5Falso, _rates
from trader import baixar_historico as baixador
from trader.dados import PADRAO_DO_SIMBOLO, carregar
from trader.mt5 import ConexaoMT5
from trader.universo import UNIVERSO, Ativo


def test_universo_nao_repete_simbolo_nem_arquivo():
    simbolos = [a.simbolo for a in UNIVERSO]
    arquivos = [a.arquivo for a in UNIVERSO]
    assert len(set(simbolos)) == len(simbolos)
    assert len(set(arquivos)) == len(arquivos)


def test_nome_do_arquivo_e_aceito_pelo_armazenamento():
    for ativo in UNIVERSO:
        assert PADRAO_DO_SIMBOLO.fullmatch(ativo.arquivo), ativo.simbolo


def test_universo_so_tem_fontes_e_papeis_conhecidos():
    assert {a.fonte for a in UNIVERSO} == {"mt5", "yfinance"}
    assert {a.papel for a in UNIVERSO} == {"operar", "atributo"}
    assert all(a.fonte == "yfinance" for a in UNIVERSO if a.papel == "atributo")


def test_arquivo_troca_os_caracteres_de_ticker():
    assert Ativo("^BVSP", "yfinance", "indices").arquivo == "IDX_BVSP"
    assert Ativo("KC=F", "yfinance", "agro").arquivo == "KC_F"
    assert Ativo("BTC-USD", "yfinance", "cripto").arquivo == "BTC_USD"


def _mt5_com_candles():
    return lambda: ConexaoMT5(MT5Falso(rates=_rates(CANDLES)))


def test_baixa_das_duas_fontes_grava_e_relata(tmp_path):
    ativos = [
        Ativo("EURUSD", "mt5", "forex"),
        Ativo("KC=F", "yfinance", "agro"),
        Ativo("^VIX", "yfinance", "macro", "atributo"),
    ]
    relatorio = baixador.baixar_tudo(
        ("yfinance", "mt5"),
        pasta=tmp_path,
        ativos=ativos,
        abrir_mt5=_mt5_com_candles(),
        baixar_yf=lambda simbolo: _candles(40),
    )
    assert list(relatorio["situacao"]) == ["ok", "ok", "ok"]
    assert carregar("KC_F", "D1", tmp_path) is not None
    assert carregar("IDX_VIX", "D1", tmp_path) is not None
    assert carregar("EURUSD", "D1", tmp_path) is not None
    lido = pd.read_csv(tmp_path / "relatorio_de_qualidade.csv")
    assert set(lido["fonte"]) == {"mt5", "yfinance"}


def test_uma_serie_ruim_nao_derruba_as_outras(tmp_path):
    def yf_que_falha(simbolo):
        if simbolo == "RUIM":
            raise ValueError("sem dados")
        return _candles(40)

    relatorio = baixador.baixar_tudo(
        ("yfinance",),
        pasta=tmp_path,
        ativos=[Ativo("RUIM", "yfinance", "agro"), Ativo("BOM", "yfinance", "agro")],
        baixar_yf=yf_que_falha,
    )
    situacoes = dict(zip(relatorio["simbolo"], relatorio["situacao"], strict=True))
    assert situacoes["BOM"] == "ok"
    assert situacoes["RUIM"].startswith("falhou")


def test_mt5_tenta_de_novo_quando_o_terminal_falha_na_primeira(tmp_path):
    class MT5Instavel(MT5Falso):
        chamadas = 0

        def copy_rates_range(self, simbolo, timeframe, inicio, fim):
            MT5Instavel.chamadas += 1
            if MT5Instavel.chamadas == 1:
                return None  # "Terminal: Call failed"
            return super().copy_rates_range(simbolo, timeframe, inicio, fim)

    relatorio = baixador.baixar_tudo(
        ("mt5",),
        pasta=tmp_path,
        ativos=[Ativo("EURUSD", "mt5", "forex")],
        abrir_mt5=lambda: ConexaoMT5(MT5Instavel(rates=_rates(CANDLES))),
    )
    assert relatorio.loc[0, "situacao"] == "ok"
    assert MT5Instavel.chamadas == 2


def test_mt5_desiste_depois_das_tentativas(tmp_path):
    relatorio = baixador.baixar_tudo(
        ("mt5",),
        pasta=tmp_path,
        ativos=[Ativo("EURUSD", "mt5", "forex")],
        abrir_mt5=lambda: ConexaoMT5(MT5Falso(rates=None)),
    )
    assert relatorio.loc[0, "situacao"].startswith("falhou")


def test_so_baixa_as_fontes_pedidas(tmp_path):
    relatorio = baixador.baixar_tudo(
        ("yfinance",),
        pasta=tmp_path,
        ativos=[Ativo("EURUSD", "mt5", "forex"), Ativo("KC=F", "yfinance", "agro")],
        baixar_yf=lambda simbolo: _candles(40),
    )
    assert list(relatorio["simbolo"]) == ["KC=F"]


def test_conta_real_e_recusada(tmp_path):
    from trader.mt5 import ContaRealRecusadaError

    with pytest.raises(ContaRealRecusadaError):
        baixador.baixar_tudo(
            ("mt5",),
            pasta=tmp_path,
            ativos=[Ativo("EURUSD", "mt5", "forex")],
            abrir_mt5=lambda: ConexaoMT5(MT5Falso(modo=2, rates=_rates(CANDLES))),
        )


def test_serie_com_defeito_de_ohlc_e_gravada_reparada_e_relatada(tmp_path):
    def yf_com_defeito(simbolo):
        candles = _candles(300)
        candles.iloc[10, candles.columns.get_loc("High")] = 0.5  # máxima impossível
        return candles

    relatorio = baixador.baixar_tudo(
        ("yfinance",),
        pasta=tmp_path,
        ativos=[Ativo("KC=F", "yfinance", "agro")],
        baixar_yf=yf_com_defeito,
    )
    linha = relatorio.iloc[0]
    assert linha["situacao"] == "reparada"
    assert linha["incoerentes_no_bruto"] == 1 and linha["reparados"] == 1
    assert linha["candles_incoerentes"] == 0  # o que foi gravado está coerente
    assert carregar("KC_F", "D1", tmp_path) is not None


def test_preco_negativo_conhecido_vira_ok_com_aviso(tmp_path):
    def petroleo(simbolo):
        candles = _candles(300)
        candles.iloc[50, candles.columns.get_loc("Close")] = -37.63
        candles.iloc[50, candles.columns.get_loc("Low")] = -40.0
        return candles

    com_aviso = Ativo("CL=F", "yfinance", "energia", aviso="preço negativo real")
    sem_aviso = Ativo("XX=F", "yfinance", "energia")
    relatorio = baixador.baixar_tudo(
        ("yfinance",),
        pasta=tmp_path,
        ativos=[com_aviso, sem_aviso],
        baixar_yf=petroleo,
    )
    situacoes = dict(zip(relatorio["simbolo"], relatorio["situacao"], strict=True))
    assert situacoes["CL=F"] == "ok com aviso"
    assert (
        situacoes["XX=F"] == "COM PROBLEMAS"
    )  # sem aviso conhecido, continua suspeito


def test_cl_f_tem_aviso_no_universo_e_usdbrl_do_mt5_saiu():
    por_simbolo = {a.simbolo: a for a in UNIVERSO}
    assert "-37,63" in por_simbolo["CL=F"].aviso
    assert "USDBRL" not in por_simbolo  # o demo só tem 259 candles; usamos BRL=X
    assert "BRL=X" in por_simbolo
