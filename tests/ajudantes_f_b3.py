"""Dados sintéticos da ficha F-B3 para os testes: 12 ações, uma deslistada em 15/06/2018."""

import numpy as np
import pandas as pd

from trader.estrategias import fatores_b3 as fb

DATAS = pd.bdate_range("2015-01-02", "2020-12-30")
TICKERS = [f"{letra}{letra}{letra}3" for letra in "ABCDEFGHIJKL"]
CNPJS = {t: f"{i:02d}.000.000/0001-00" for i, t in enumerate(TICKERS)}
LIQUIDO = 2e7  # bem acima do piso de R$ 5 milhões
DESLISTADA = "LLL3"
DIA_DA_DESLISTAGEM = pd.Timestamp("2018-06-15")


def precos(semente=0, datas=DATAS, tickers=TICKERS):
    gerador = np.random.default_rng(semente)
    retornos = gerador.normal(0.0003, 0.015, size=(len(datas), len(tickers)))
    return pd.DataFrame(
        50 * np.cumprod(1 + retornos, axis=0), index=datas, columns=tickers
    )


def fundamentos(cnpjs=None, ebit=1e8, lucro=6e7, patrimonio=5e8, divida=1e8, caixa=2e7):
    """DFP de cada ano (12 meses), divulgado em 31/03 do ano seguinte; sem ITR."""
    linhas = []
    for cnpj in cnpjs or CNPJS.values():
        for ano in range(2013, 2021):
            fim = pd.Timestamp(f"{ano}-12-31")
            divulgado = pd.Timestamp(f"{ano + 1}-03-31")
            contas = {
                ("DRE", "3.05"): ebit,
                ("DRE", "3.11"): lucro,
                ("BPP", "2.03"): patrimonio,
                ("BPP", "2.01.04"): divida / 2,
                ("BPP", "2.02.01"): divida / 2,
                ("BPA", "1.01.01"): caixa,
            }
            for (demonstracao, conta), valor in contas.items():
                inicio = (
                    pd.Timestamp(f"{ano}-01-01") if demonstracao == "DRE" else pd.NaT
                )
                linhas.append(
                    (cnpj, demonstracao, conta, inicio, fim, valor, divulgado, pd.NaT)
                )
    return pd.DataFrame(linhas, columns=list(fb.COLUNAS_DOS_FUNDAMENTOS))


def acoes(cnpjs=None, quantidade=1e7):
    return pd.DataFrame(
        [
            (cnpj, quantidade, pd.Timestamp("2012-12-31"))
            for cnpj in cnpjs or CNPJS.values()
        ],
        columns=list(fb.COLUNAS_DAS_ACOES),
    )


def cadastro(tickers=TICKERS):
    return pd.DataFrame(
        {
            "cnpj": [CNPJS[t] for t in tickers],
            "classe": "ON",
            "inicio_negociacao": pd.Timestamp("2010-01-04"),
            "fim_negociacao": pd.NaT,
        },
        index=pd.Index(tickers, name="ticker"),
    )


def dados_sinteticos(semente=0, com_deslistada=True, cdi_diario=0.0003, datas=DATAS):
    fechamento = precos(semente, datas)
    cad = cadastro()
    if com_deslistada:
        fechamento.loc[fechamento.index > DIA_DA_DESLISTAGEM, DESLISTADA] = np.nan
        cad.loc[DESLISTADA, "fim_negociacao"] = DIA_DA_DESLISTAGEM
    abertura = fechamento.shift(1).bfill() * 1.001
    volume = pd.DataFrame(LIQUIDO, index=datas, columns=TICKERS).where(
        fechamento.notna()
    )
    return fb.Dados(
        fechamento=fechamento,
        abertura=abertura,
        volume=volume,
        cadastro=cad,
        fundamentos=fundamentos(),
        acoes=acoes(),
        cdi=pd.Series(cdi_diario, index=datas),
    )


def variar_balancos_por_ano(dados, semente=1):
    """Contas de resultado diferentes a cada ano, para a data do balanço importar."""
    gerador = np.random.default_rng(semente)
    e_resultado = dados.fundamentos["demonstracao"] == "DRE"
    fatores = gerador.uniform(0.5, 1.5, size=int(e_resultado.sum()))
    dados.fundamentos.loc[e_resultado, "valor"] *= fatores
    return dados
