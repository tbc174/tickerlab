"""Ficha P0-1b: BTCBRL e ETHBRL do Binance Vision, em reais, sem dólar, sem internet nos testes."""

import io
import json
import zipfile

import numpy as np
import pandas as pd

from trader.criterio_quant import FIM_DO_DESENVOLVIMENTO
from trader.estrategias import dados_cripto_brl as dados


def _zip_de_klines(linhas: list[list[float]], nome: str) -> bytes:
    conteudo = "\n".join(",".join(str(v) for v in linha) for linha in linhas)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, conteudo)
    return saida.getvalue()


def _kline(dia: str, fechamento: float, volume_em_reais: float) -> list[float]:
    abertura = int(pd.Timestamp(dia, tz="UTC").timestamp() * 1000)
    return [
        abertura,
        1,
        2,
        0.5,
        fechamento,
        10,
        abertura + 86_399_999,
        volume_em_reais,
        5,
        1,
        1,
        0,
    ]


def _tabela(dias: list[str], fechamentos: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"fechamento": fechamentos, "volume": [1e6] * len(dias)},
        index=pd.DatetimeIndex(dias),
    )


def test_pares_em_reais_e_meses_so_do_desenvolvimento():
    assert dados.PARES == {"BTC": "BTCBRL", "ETH": "ETHBRL"}
    meses = dados.meses_do_desenvolvimento()
    assert str(meses[0]) == "2020-10"
    assert str(meses[-1]) == FIM_DO_DESENVOLVIMENTO.strftime("%Y-%m") == "2023-09"
    assert dados.PASTA_DA_BINANCE_BRL.name == "binance_brl"
    assert dados.PASTA_DA_BINANCE_BRL != dados.dados_p0_1.PASTA_DA_BINANCE


def test_baixar_pares_grava_os_zips_e_o_sha256_numa_pasta_propria(tmp_path):
    pedidos: list[str] = []

    def baixar(url: str) -> bytes:
        pedidos.append(url)
        par, mes = url.rsplit("/", 1)[1].removesuffix(".zip").split("-1d-")
        return _zip_de_klines([_kline(f"{mes}-01", 100.0, 5e6)], f"{par}-1d-{mes}.csv")

    gravados = dados.baixar_pares(tmp_path, baixar)
    total = len(dados.meses_do_desenvolvimento())
    assert gravados == {"BTCBRL": total, "ETHBRL": total}
    assert all("data.binance.vision" in u and "BRL-1d-" in u for u in pedidos)
    hashes = json.loads((tmp_path / "sha256.json").read_text("utf-8"))
    assert len(hashes) == 2 * total
    assert dados.baixar_pares(tmp_path, baixar) == {
        "BTCBRL": 0,
        "ETHBRL": 0,
    }  # já baixados
    tabelas = dados.carregar_pares(tmp_path)
    assert set(tabelas) == {"BTC", "ETH"}
    assert dados.primeiro_candle(tabelas) == {"BTC": "2020-10-01", "ETH": "2020-10-01"}


def test_montar_precos_vazio_antes_do_primeiro_candle_e_repete_depois():
    tabelas = {
        "BTC": _tabela(["2020-10-13", "2020-10-14", "2020-10-16"], [10.0, 11.0, 12.0]),
        "ETH": _tabela(["2020-10-15", "2020-10-16"], [1.0, 2.0]),
    }
    precos, volumes = dados.montar_precos(tabelas)
    assert list(precos.columns) == ["BTC", "ETH"]
    assert precos.index[0] == pd.Timestamp("2020-10-13")
    assert len(precos) == 4  # dias corridos
    assert np.isnan(precos.loc["2020-10-14", "ETH"])  # o ETHBRL ainda não existia
    assert precos.loc["2020-10-15", "BTC"] == 11.0  # sem candle: repete
    assert volumes.loc["2020-10-15", "BTC"] == 0.0  # e não negocia
    assert precos.loc["2020-10-16"].tolist() == [12.0, 2.0]  # já em reais, sem dólar
