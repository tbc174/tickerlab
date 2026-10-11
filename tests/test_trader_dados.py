"""Guardar e conferir o histórico baixado do MetaTrader 5."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from tests.test_trader_mt5 import CANDLES, MT5Falso, _rates
from trader import dados
from trader.mt5 import ConexaoMT5


def _candles(n=30, passo="D"):
    indice = pd.date_range("2024-01-01", periods=n, freq=passo)
    preco = pd.Series(range(100, 100 + n), index=indice, dtype=float)
    return pd.DataFrame(
        {
            "Open": preco,
            "High": preco + 1,
            "Low": preco - 1,
            "Close": preco + 0.5,
            "Volume": 1000.0,
            "Spread": 10,
        },
        index=indice,
    )


def test_serie_limpa_e_aprovada():
    q = dados.verificar_qualidade(_candles())
    assert q.aprovada and q.linhas == 30 and q.maiores_lacunas == []


def test_serie_vazia_nao_e_aprovada():
    q = dados.verificar_qualidade(_candles().iloc[0:0])
    assert not q.aprovada and q.linhas == 0


def test_acha_indice_repetido_e_fora_de_ordem():
    candles = _candles()
    repetido = pd.concat([candles, candles.iloc[[5]]])
    q = dados.verificar_qualidade(repetido)
    assert q.indice_repetido == 1 and q.fora_de_ordem and not q.aprovada


def test_acha_precos_vazios_negativos_e_candles_incoerentes():
    candles = _candles()
    candles.iloc[3, candles.columns.get_loc("Close")] = None
    candles.iloc[4, candles.columns.get_loc("Low")] = -1.0
    candles.iloc[6, candles.columns.get_loc("High")] = (
        1.0  # máxima abaixo da mínima e do fechamento
    )
    q = dados.verificar_qualidade(candles)
    assert (
        q.valores_vazios == 1
        and q.precos_nao_positivos == 1
        and q.candles_incoerentes >= 1
    )
    assert not q.aprovada


def test_lacuna_grande_no_diario_aparece():
    candles = _candles(40)
    buraco = pd.concat([candles.iloc[:10], candles.iloc[25:]])  # 15 dias sem dados
    q = dados.verificar_qualidade(buraco, "D1")
    assert len(q.maiores_lacunas) == 1 and q.maiores_lacunas[0][1] == pd.Timedelta(
        days=16
    )
    assert q.aprovada  # lacuna é aviso, não reprova sozinha


def test_fim_de_semana_nao_e_lacuna():
    candles = _candles(60, "B")  # só dias úteis
    assert dados.verificar_qualidade(candles, "D1").maiores_lacunas == []


def test_salvar_e_carregar_ida_e_volta(tmp_path):
    candles = _candles()
    caminho = dados.salvar(candles, "EURUSD", "D1", tmp_path)
    assert caminho.name == "EURUSD_D1.parquet"
    de_volta = dados.carregar("EURUSD", "D1", tmp_path)
    pd.testing.assert_frame_equal(de_volta, candles, check_freq=False)


def test_carregar_o_que_nao_existe(tmp_path):
    assert dados.carregar("NAOEXISTE", "D1", tmp_path) is None


@pytest.mark.parametrize("nome", ["../fora", "a/b", "..\\x", "", "x" * 40, "A B"])
def test_nome_de_simbolo_nao_escapa_da_pasta(tmp_path, nome):
    with pytest.raises(ValueError):
        dados.salvar(_candles(), nome, "D1", tmp_path)
    with pytest.raises(ValueError):
        dados.carregar(nome, "D1", tmp_path)


def test_baixar_guarda_cada_simbolo_e_um_ruim_nao_derruba_os_outros(tmp_path):
    falso = MT5Falso(rates=_rates(CANDLES), simbolos=("EURUSD", "USDJPY"))
    with ConexaoMT5(falso) as mt5:
        resultado = dados.baixar_para_disco(
            mt5,
            ["EURUSD", "NAOTEM", "USDJPY"],
            "D1",
            anos=1,
            pasta=tmp_path,
            agora=datetime(2023, 12, 1, tzinfo=UTC),
        )
    assert resultado["EURUSD"].aprovada and resultado["USDJPY"].aprovada
    assert isinstance(resultado["NAOTEM"], str) and resultado["NAOTEM"].startswith(
        "falhou"
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "EURUSD_D1.parquet",
        "USDJPY_D1.parquet",
    ]
