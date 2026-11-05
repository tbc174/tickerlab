"""Dados sintéticos da ficha P0-5: 40 empresas líquidas, lucro sazonal com ruído e o IPE.

O press-release de cada trimestre chega na véspera do ITR (40 dias depois do fim) ou da DFP (75);
um fato relevante sai 10 dias depois do fim. Os preços seguem o mercado (β = 1,1) com ruído, sem
nenhum efeito dos anúncios.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from trader.estrategias import fatores_b3 as fb
from trader.estrategias import pead

DATAS = pd.bdate_range("2012-01-02", "2016-12-30")
EMPRESAS = 40
TICKERS = [f"E{i:02d}3" for i in range(EMPRESAS)]
CNPJS = {t: f"{i:02d}.000.000/0001-00" for i, t in enumerate(TICKERS)}
LIQUIDO = 2e7
DIAS_ATE_O_BALANCO = 40
DIAS_DO_IPE_ANTES_DO_BALANCO = 1  # o press-release sai na véspera do ITR ou da DFP
DIAS_ATE_A_DFP = 75


def _trimestres():
    return pd.period_range("2009Q1", "2016Q3", freq="Q")


def _lucros(gerador):
    """Lucro só do trimestre de cada empresa: nível, sazonalidade e ruído."""
    trimestres = _trimestres()
    sazonal = np.array([1.0, 1.2, 0.9, 1.4])
    return {
        cnpj: pd.Series(
            100 * sazonal[trimestres.quarter - 1]
            + gerador.normal(0, 15, len(trimestres)),
            index=trimestres,
        )
        for cnpj in CNPJS.values()
    }


def _divulgacao(trimestre: pd.Period) -> pd.Timestamp:
    fim = trimestre.end_time.normalize()
    return fim + pd.Timedelta(
        days=DIAS_ATE_A_DFP if trimestre.quarter == 4 else DIAS_ATE_O_BALANCO
    )


def fundamentos_do_lucro(lucros):
    """As linhas do acumulado no ano (3.11), como o ITR e a DFP trazem."""
    linhas = []
    for cnpj, serie in lucros.items():
        for trimestre in serie.index:
            ano = serie[
                (serie.index.year == trimestre.year) & (serie.index <= trimestre)
            ]
            linhas.append(
                {
                    "cnpj": cnpj,
                    "demonstracao": "DRE",
                    "conta": "3.11",
                    "inicio": pd.Timestamp(year=trimestre.year, month=1, day=1),
                    "fim": trimestre.end_time.normalize(),
                    "valor": float(ano.sum()),
                    "divulgado_em": _divulgacao(trimestre),
                    "ate": pd.NaT,
                }
            )
    return pd.DataFrame(linhas)


def documentos(lucros):
    linhas = []
    for cnpj, serie in lucros.items():
        for trimestre in serie.index:
            fim = trimestre.end_time.normalize()
            linhas.append(
                {
                    "cnpj": cnpj,
                    "categoria": "Dados Econômico-Financeiros",
                    "tipo": "Press-release",
                    "tema": "resultados",
                    "referencia": fim,
                    "publicado_em": _divulgacao(trimestre)
                    - pd.Timedelta(days=DIAS_DO_IPE_ANTES_DO_BALANCO),
                }
            )
            linhas.append(
                {
                    "cnpj": cnpj,
                    "categoria": "Fato Relevante",
                    "tipo": "",
                    "tema": "outros",
                    "referencia": fim,
                    "publicado_em": fim + pd.Timedelta(days=10),
                }
            )
    return pd.DataFrame(linhas)


def dados_sinteticos(semente=0):
    g = np.random.default_rng(semente)
    n = len(DATAS)
    mercado = g.normal(0.0003, 0.01, n)
    retornos = {t: 0.0002 + 1.1 * mercado + g.normal(0, 0.012, n) for t in TICKERS}
    fechamento = pd.DataFrame(
        {t: 20 * np.exp(np.cumsum(r)) for t, r in retornos.items()}, index=DATAS
    )
    fechamento.iloc[0] = 20.0
    abertura = fechamento.shift(1).bfill() * (1 + g.normal(0, 0.002, (n, EMPRESAS)))
    lucros = _lucros(g)
    return pead.Dados(
        fechamento=fechamento,
        abertura=abertura,
        volume=pd.DataFrame(LIQUIDO, index=DATAS, columns=TICKERS),
        cadastro=pd.DataFrame(
            {
                "cnpj": [CNPJS[t] for t in TICKERS],
                "classe": "ON",
                "inicio_negociacao": pd.Timestamp("2010-01-04"),
                "fim_negociacao": pd.NaT,
            },
            index=pd.Index(TICKERS, name="ticker"),
        ),
        fundamentos=fundamentos_do_lucro(lucros),
        acoes=pd.DataFrame(columns=list(fb.COLUNAS_DAS_ACOES)),
        cdi=pd.Series(0.0004, index=DATAS),
        ibovespa=pd.Series(mercado, index=DATAS),
        documentos=documentos(lucros),
    )


def deslistar(dados, ticker, dia):
    fechamento = dados.fechamento.copy()
    fechamento.loc[fechamento.index > dia, ticker] = np.nan
    cadastro = dados.cadastro.copy()
    cadastro.loc[ticker, "fim_negociacao"] = dia
    volume = dados.volume.where(fechamento.notna())
    return replace(dados, fechamento=fechamento, volume=volume, cadastro=cadastro)
