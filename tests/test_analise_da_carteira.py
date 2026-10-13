"""Testes de src/analise_da_carteira.py: concentração, comportamento, Raio-X e Rebalanceamento."""

from pathlib import Path

import pandas as pd
import pytest

from src import analise_da_carteira as ac
from src.carteira_b3 import CarteiraB3, ler_carteira, retorno_com_os_pesos_de_hoje
from src.metricas import resumir_desempenho

EXEMPLO = Path("conteudo/carteira_de_exemplo.xlsx")


def _carteira(valores, renda_fixa=0.0, tipos=None):
    codigos = list(valores)
    posicoes = pd.DataFrame(
        {
            "codigo": codigos,
            "ticker": [f"{c}.SA" for c in codigos],
            "tipo": tipos or ["Ações"] * len(codigos),
            "quantidade": [1.0] * len(codigos),
            "valor": list(valores.values()),
        }
    )
    sem_cotacao = pd.DataFrame(
        {
            "tipo": ["Tesouro Direto"],
            "produto": ["Tesouro Selic"],
            "valor": [renda_fixa],
        }
        if renda_fixa
        else {"tipo": [], "produto": [], "valor": []}
    )
    return CarteiraB3(posicoes, sem_cotacao)


def _exemplo():
    carteira = ler_carteira(EXEMPLO.read_bytes(), EXEMPLO.name)
    fechamentos = pd.DataFrame(
        {
            t: pd.read_csv(f"dados_de_exemplo/{t}.csv", index_col=0, parse_dates=True)[
                "Close"
            ]
            for t in carteira.posicoes["ticker"]
        }
    )
    ibov = pd.read_csv("dados_de_exemplo/_BVSP.csv", index_col=0, parse_dates=True)[
        "Close"
    ]
    return carteira, fechamentos, ibov


# --- concentração --------------------------------------------------------------------------


def test_pesos_iguais_dao_numero_efetivo_igual_a_quantidade():
    c = ac.concentracao(
        _carteira({"PETR4": 100, "VALE3": 100, "ITUB4": 100, "WEGE3": 100})
    )
    assert c.numero_efetivo == pytest.approx(4.0)
    assert c.maior == ("PETR4", 0.25)
    assert c.tres_maiores == pytest.approx(0.75)
    assert c.quantidade == 4


def test_uma_posicao_dominante_concentra():
    c = ac.concentracao(_carteira({"PETR4": 900, "VALE3": 50, "ITUB4": 50}))
    assert c.maior == ("PETR4", 0.9)
    assert c.numero_efetivo == pytest.approx(1 / (0.81 + 0.0025 + 0.0025))


def test_renda_fixa_entra_na_fracao_do_total():
    c = ac.concentracao(_carteira({"PETR4": 300}, renda_fixa=100))
    assert c.fracao_renda_fixa == pytest.approx(0.25)


def test_pesos_saem_do_maior_para_o_menor_e_sem_sa():
    c = ac.concentracao(_carteira({"VALE3": 100, "PETR4": 300}))
    assert c.pesos == (("PETR4", 0.75), ("VALE3", 0.25))


# --- comportamento -------------------------------------------------------------------------


def test_comportamento_bate_com_as_contas_do_pdf():
    carteira, fechamentos, ibov = _exemplo()
    c = ac.comportamento(carteira, fechamentos, ibov, 0.0)
    retorno = retorno_com_os_pesos_de_hoje(fechamentos, carteira.pesos())
    resumo = resumir_desempenho(retorno)
    assert c.retorno_total == pytest.approx(resumo["Retorno total"])
    assert c.maior_queda == pytest.approx(resumo["Maior queda"])
    assert c.sharpe == pytest.approx(resumo["Índice de Sharpe"], nan_ok=True)


def test_curva_da_carteira_e_a_do_pdf_e_a_do_ibovespa_comeca_em_100():
    carteira, fechamentos, ibov = _exemplo()
    c = ac.comportamento(carteira, fechamentos, ibov, 0.0)
    retorno = retorno_com_os_pesos_de_hoje(fechamentos, carteira.pesos())
    esperada = (1 + retorno).cumprod() * 100  # a mesma curva do PDF
    assert [p.valor for p in c.curva] == pytest.approx(list(esperada))
    assert c.curva_ibovespa[0].valor == pytest.approx(100.0)
    assert c.retorno_ibovespa == pytest.approx(c.curva_ibovespa[-1].valor / 100 - 1)


def test_sem_ibovespa_a_comparacao_fica_vazia():
    carteira, fechamentos, _ = _exemplo()
    c = ac.comportamento(carteira, fechamentos, None, 0.0)
    assert c.curva_ibovespa is None and c.retorno_ibovespa is None


def test_pdf_da_minha_carteira_mostra_os_numeros_desta_analise():
    from io import BytesIO

    from pypdf import PdfReader

    from src import graficos_pdf as gp
    from src import relatorios

    carteira, fechamentos, ibov = _exemplo()
    pdf = relatorios.relatorio_da_minha_carteira(carteira, fechamentos, ibov)
    texto = " ".join(
        " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages).split()
    )
    conc = ac.concentracao(carteira)
    assert gp.numero_br(conc.numero_efetivo, 1) in texto
    assert f"{conc.maior[0]}: {gp.pct_br(conc.maior[1])}" in texto
    assert (
        gp.pct_br(ac.comportamento(carteira, fechamentos, ibov, 0.0).maior_queda)
        in texto
    )
