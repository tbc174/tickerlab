"""Dados sintéticos da ficha P0-4: dois pares cointegrados, um par ON/PN, ruído e uma deslistada.

- AAA3 e BBB3 (Energia) e CCC3 e DDD3 (setores diferentes) andam juntos: log y = 0,2 + log x +
  resíduo AR(1) com φ = 0,9 (meia-vida perto de 6,6 pregões).
- AAA4 é a PN da mesma empresa de AAA3 (menos líquida), também cointegrada com ela.
- EEE3, FFF3 e GGG3 são passeios aleatórios; HHH3 anda com GGG3 e é deslistada em 14/09/2018.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from tests.ajudantes_f_b3 import acoes, fundamentos
from trader.estrategias import pares

DATAS = pd.bdate_range("2015-01-02", "2019-06-28")
TICKERS = ["AAA3", "AAA4", "BBB3", "CCC3", "DDD3", "EEE3", "FFF3", "GGG3", "HHH3"]
EMPRESA = {t: t[:3] for t in TICKERS}
CNPJS = {
    empresa: f"{i:02d}.000.000/0001-00"
    for i, empresa in enumerate(sorted(set(EMPRESA.values())))
}
SETORES = {
    "AAA": "Energia",
    "BBB": "Energia",
    "CCC": "Bancos",
    "DDD": "Varejo",
    "EEE": "Bancos",
    "FFF": "Varejo",
    "GGG": "Energia",
    "HHH": "Energia",
}
LIQUIDO = 2e7
DESLISTADA = "HHH3"
DIA_DA_DESLISTAGEM = pd.Timestamp("2018-09-14")
PHI = 0.9


def _passeio(gerador, n, desvio=0.015):
    return np.cumsum(gerador.normal(0.0002, desvio, n))


def _residuo(gerador, n, desvio=0.01, phi=PHI):
    e = gerador.normal(0.0, desvio, n)
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = phi * s[t - 1] + e[t]
    return s


def precos(semente=0, datas=DATAS):
    g = np.random.default_rng(semente)
    n = len(datas)
    log = {}
    log["BBB3"] = np.log(30) + _passeio(g, n)
    log["AAA3"] = 0.2 + log["BBB3"] + _residuo(g, n)
    log["AAA4"] = -0.1 + log["AAA3"] + _residuo(g, n, 0.006)
    log["DDD3"] = np.log(20) + _passeio(g, n)
    log["CCC3"] = 0.2 + log["DDD3"] + _residuo(g, n)
    for t in ("EEE3", "FFF3", "GGG3"):
        log[t] = np.log(40) + _passeio(g, n)
    log["HHH3"] = 0.1 + log["GGG3"] + _residuo(g, n)
    return pd.DataFrame({t: np.exp(log[t]) for t in TICKERS}, index=datas)


def dados_sinteticos(semente=0, com_deslistada=True, cdi_diario=0.0003, datas=DATAS):
    fechamento = precos(semente, datas)
    cadastro = pd.DataFrame(
        {
            "cnpj": [CNPJS[EMPRESA[t]] for t in TICKERS],
            "classe": [("PN" if t.endswith("4") else "ON") for t in TICKERS],
            "inicio_negociacao": pd.Timestamp("2010-01-04"),
            "fim_negociacao": pd.NaT,
        },
        index=pd.Index(TICKERS, name="ticker"),
    )
    if com_deslistada:
        fechamento.loc[fechamento.index > DIA_DA_DESLISTAGEM, DESLISTADA] = np.nan
        cadastro.loc[DESLISTADA, "fim_negociacao"] = DIA_DA_DESLISTAGEM
    volume = pd.DataFrame(LIQUIDO, index=datas, columns=TICKERS).where(
        fechamento.notna()
    )
    volume["AAA4"] = volume["AAA4"] / 2  # a ON é a mais líquida
    return pares.Dados(
        fechamento=fechamento,
        abertura=fechamento.copy(),
        volume=volume,
        cadastro=cadastro,
        fundamentos=fundamentos(cnpjs=list(CNPJS.values())),
        acoes=acoes(cnpjs=list(CNPJS.values())),
        cdi=pd.Series(cdi_diario, index=datas),
        setores=pd.DataFrame(
            {
                "cnpj": [CNPJS[e] for e in SETORES],
                "setor": list(SETORES.values()),
                "conhecido_em": pd.Timestamp("2014-06-30"),
            }
        ),
    )


def deslistar(dados, ticker, dia):
    """Os mesmos dados com `ticker` deslistado depois de `dia` (sem preço nem volume)."""
    fechamento = dados.fechamento.copy()
    volume = dados.volume.copy()
    cadastro = dados.cadastro.copy()
    fechamento.loc[fechamento.index > dia, ticker] = np.nan
    volume.loc[volume.index > dia, ticker] = np.nan
    cadastro.loc[ticker, "fim_negociacao"] = dia
    return replace(
        dados,
        fechamento=fechamento,
        abertura=fechamento.copy(),
        volume=volume,
        cadastro=cadastro,
    )
