"""Leitores do Banco Central (SGS, PTAX e Focus), sem internet: respostas no formato real."""

from datetime import date

import pandas as pd
import pytest
import requests

from src import bcb

HOJE = date(2026, 10, 12)


class RespostaFalsa:
    def __init__(self, conteudo: object, status: int = 200) -> None:
        self.conteudo = conteudo
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}")

    def json(self) -> object:
        if isinstance(self.conteudo, Exception):
            raise self.conteudo
        return self.conteudo


def _buscar(respostas: list, pedidos: list):
    def buscar(url, params=None, timeout=None):
        pedidos.append((url, params))
        return respostas.pop(0)

    return buscar


def test_sgs_le_data_e_valor_e_corta_o_futuro():
    """A meta da Selic vem repetida até a próxima reunião do Copom: o futuro não entra."""
    registros = [
        {"data": "18/09/2026", "valor": "13.75"},
        {"data": "09/10/2026", "valor": "13.75"},
        {"data": "04/11/2026", "valor": "13.75"},  # depois de hoje
    ]
    serie = bcb.montar_serie_sgs(registros, "Meta da Selic", HOJE)
    assert list(serie.index) == [pd.Timestamp("2026-09-18"), pd.Timestamp("2026-10-09")]
    assert serie.iloc[-1] == pytest.approx(13.75)
    assert serie.name == "Meta da Selic"


def test_sgs_divide_consultas_longas_e_junta_tudo():
    pedidos: list = []
    respostas = [
        RespostaFalsa([{"data": "02/01/2006", "valor": "0.06"}]),
        RespostaFalsa([{"data": "02/01/2020", "valor": "0.02"}]),
    ]
    serie = bcb.baixar_serie_sgs(
        "selic_diaria",
        date(2006, 1, 1),
        date(2020, 6, 30),
        HOJE,
        _buscar(respostas, pedidos),
    )
    assert len(pedidos) == 2  # 14 anos em consultas de até 9
    assert pedidos[0][0].endswith("bcdata.sgs.11/dados")
    assert pedidos[0][1]["dataInicial"] == "01/01/2006"
    assert len(serie) == 2


def test_sgs_sem_dados_ou_resposta_estranha_da_erro_claro():
    with pytest.raises(bcb.BcbIndisponivelError, match="não devolveu"):
        bcb.montar_serie_sgs([], "IPCA", HOJE)
    with pytest.raises(bcb.BcbIndisponivelError, match="inesperada"):
        bcb.montar_serie_sgs([{"dia": "x"}], "IPCA", HOJE)
    with pytest.raises(bcb.BcbIndisponivelError):
        bcb.baixar_serie_sgs(
            "ipca", date(2026, 1, 1), date(2026, 2, 1), HOJE,
            _buscar([RespostaFalsa(None, status=503)], []),
        )  # fmt: skip


def test_sgs_recusa_periodo_invertido_e_serie_desconhecida():
    with pytest.raises(ValueError, match="final"):
        bcb.baixar_serie_sgs("ipca", date(2026, 2, 1), date(2026, 1, 1), HOJE)
    with pytest.raises(KeyError):
        bcb.baixar_serie_sgs("nao_existe", date(2026, 1, 1), date(2026, 2, 1), HOJE)


PTAX = {
    "value": [
        {"cotacaoCompra": 4.9692, "cotacaoVenda": 4.9698, "dataHoraCotacao": "2026-10-06 13:03:21.267"},
        {"cotacaoCompra": 4.9929, "cotacaoVenda": 4.9935, "dataHoraCotacao": "2026-10-07 10:02:00.000"},
        {"cotacaoCompra": 4.9950, "cotacaoVenda": 4.9956, "dataHoraCotacao": "2026-10-07 13:05:23.249"},
    ]
}  # fmt: skip


def test_ptax_fica_com_a_ultima_cotacao_de_cada_dia():
    ptax = bcb.montar_ptax(PTAX, HOJE)
    assert list(ptax.columns) == ["compra", "venda"]
    assert list(ptax.index) == [pd.Timestamp("2026-10-06"), pd.Timestamp("2026-10-07")]
    assert ptax.loc["2026-10-07", "venda"] == pytest.approx(
        4.9956
    )  # a de fechamento (13h)


def test_ptax_pede_o_periodo_no_formato_da_api():
    pedidos: list = []
    bcb.baixar_ptax(
        date(2026, 10, 6),
        date(2026, 10, 9),
        HOJE,
        _buscar([RespostaFalsa(PTAX)], pedidos),
    )
    assert pedidos[0][1]["@dataInicial"] == "'10-06-2026'"
    assert pedidos[0][1]["@dataFinalCotacao"] == "'10-09-2026'"


def test_ptax_vazia_da_erro_claro():
    with pytest.raises(bcb.BcbIndisponivelError, match="PTAX"):
        bcb.montar_ptax({"value": []}, HOJE)


FOCUS = {
    "value": [
        {"Indicador": "IPCA", "IndicadorDetalhe": None, "Data": "2026-10-02",
         "DataReferencia": "2027", "Media": 4.3348, "Mediana": 4.3007, "DesvioPadrao": 0.42,
         "Minimo": 3.17, "Maximo": 6.0, "numeroRespondentes": 144, "baseCalculo": 0},
        {"Indicador": "IPCA", "IndicadorDetalhe": None, "Data": "2026-10-02",
         "DataReferencia": "2026", "Media": 5.0046, "Mediana": 5.0129, "DesvioPadrao": 0.22,
         "Minimo": 4.338, "Maximo": 5.8963, "numeroRespondentes": 144, "baseCalculo": 0},
    ]
}  # fmt: skip


def test_focus_uma_linha_por_pesquisa_e_ano():
    focus = bcb.montar_focus(FOCUS)
    assert list(focus.columns) == list(bcb.COLUNAS_DO_FOCUS.values())
    assert list(focus["ano"]) == [2026, 2027]
    assert focus.iloc[0]["mediana"] == pytest.approx(5.0129)
    assert focus.iloc[0]["respondentes"] == 144


def test_focus_filtra_pelo_indicador_e_pela_data():
    pedidos: list = []
    bcb.baixar_focus(
        "IPCA", date(2026, 10, 1), _buscar([RespostaFalsa(FOCUS)], pedidos)
    )
    url, params = pedidos[0]
    assert params is None  # a consulta vai pronta no endereço
    # espaços como %20 (com "+" a API Olinda responde 400)
    assert "$filter=Indicador%20eq%20'IPCA'%20and%20Data%20ge%20'2026-10-01'" in url
    assert "+" not in url


def test_focus_sem_pesquisas_devolve_tabela_vazia_e_recusa_aspas():
    assert bcb.montar_focus({"value": []}).empty
    with pytest.raises(ValueError, match="Indicador"):
        bcb.baixar_focus("IPCA' or 1 eq 1", date(2026, 1, 1))
