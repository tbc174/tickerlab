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
        self.status = self.status_code = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}", response=self)  # type: ignore[arg-type]

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
    respostas = [RespostaFalsa([{"data": "02/01/2006", "valor": "0.06"}])] + [
        RespostaFalsa([{"data": "02/01/2020", "valor": "0.02"}]) for _ in range(4)
    ]
    serie = bcb.baixar_serie_sgs(
        "selic_diaria",
        date(2006, 1, 1),
        date(2020, 6, 30),
        HOJE,
        _buscar(respostas, pedidos),
    )
    assert len(pedidos) == 5  # 14,5 anos em consultas de até 3
    assert pedidos[0][0].endswith("bcdata.sgs.11/dados")
    assert pedidos[0][1]["dataInicial"] == "01/01/2006"
    assert len(serie) == 2


def test_sgs_nunca_pede_janela_que_o_bc_nao_responde():
    """Regressão (13/10/2026): sem cache, o SGS levou 30 s numa janela de 8 anos da série 432 e
    devolveu uma página HTML "Requisição inválida!" com status 200; em janelas de 3 anos, de 2 a 5 s."""
    pedidos: list = []

    def buscar(url, params=None, timeout=None):
        pedidos.append(params)
        return RespostaFalsa([{"data": "01/09/2026", "valor": "0.48"}])

    bcb.baixar_serie_sgs("selic_meta", date(2010, 1, 1), HOJE, HOJE, buscar)
    for params in pedidos:
        inicio = pd.to_datetime(params["dataInicial"], format="%d/%m/%Y")
        fim = pd.to_datetime(params["dataFinal"], format="%d/%m/%Y")
        assert fim - inicio <= pd.Timedelta(days=3 * 366)


def test_sgs_sem_dados_ou_resposta_estranha_da_erro_claro(monkeypatch):
    monkeypatch.setattr(bcb, "esperar", lambda _: None)  # o 503 é tentado 3 vezes
    with pytest.raises(bcb.BcbIndisponivelError, match="não devolveu"):
        bcb.montar_serie_sgs([], "IPCA", HOJE)
    with pytest.raises(bcb.BcbIndisponivelError, match="inesperada"):
        bcb.montar_serie_sgs([{"dia": "x"}], "IPCA", HOJE)
    with pytest.raises(bcb.BcbIndisponivelError):
        bcb.baixar_serie_sgs(
            "ipca", date(2026, 1, 1), date(2026, 2, 1), HOJE,
            _buscar([RespostaFalsa(None, status=503) for _ in range(3)], []),
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


def test_consulta_longa_do_sgs_tem_tempo_para_responder():
    """Regressão (13/10/2026): sem cache, o SGS levou 18 a 26 s numa janela de 9 anos, e o limite
    de 20 s derrubava a primeira carga das séries. Repetida, a mesma consulta volta em 1 s."""
    pedidos: list = []

    def buscar(url, params=None, timeout=None):
        pedidos.append(timeout)
        return RespostaFalsa([{"data": "01/09/2026", "valor": "0.48"}])

    bcb.baixar_serie_sgs("ipca", date(2010, 1, 1), HOJE, HOJE, buscar)
    assert pedidos and min(pedidos) >= 60


def test_erro_passageiro_do_bc_tenta_de_novo(monkeypatch):
    """Regressão (13/10/2026): um 502 isolado do SGS (34 de 35 consultas certas; repetida, a mesma
    respondeu em 2,6 s) derrubava as séries que vinham depois e disparava o alarme do dia."""
    esperas: list = []
    monkeypatch.setattr(bcb, "esperar", esperas.append)
    respostas = [
        RespostaFalsa(None, status=502),
        requests.ReadTimeout("lento"),
        RespostaFalsa([{"data": "01/09/2026", "valor": "0.48"}]),
    ]

    def buscar(url, params=None, timeout=None):
        resposta = respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    serie = bcb.baixar_serie_sgs("ipca", date(2026, 1, 1), HOJE, HOJE, buscar)
    assert len(serie) == 1 and len(esperas) == 2


def test_erro_que_nao_passa_nao_tenta_de_novo(monkeypatch):
    esperas: list = []
    monkeypatch.setattr(bcb, "esperar", esperas.append)
    pedidos: list = []
    with pytest.raises(bcb.BcbIndisponivelError):
        bcb.baixar_serie_sgs(
            "ipca",
            date(2026, 1, 1),
            HOJE,
            HOJE,
            _buscar([RespostaFalsa(None, status=404)], pedidos),
        )
    assert esperas == [] and len(pedidos) == 1


def test_pagina_de_erro_com_status_200_tenta_de_novo(monkeypatch):
    """Regressão (13/10/2026): mesmo numa janela de 3 anos, com o cache frio o servidor do BC
    passou dos ~30 s e devolveu a página HTML "Requisição inválida!" com status 200; repetida, a
    mesma consulta respondeu em 3,8 s. Antes essa página não era tentada de novo."""
    esperas: list = []
    monkeypatch.setattr(bcb, "esperar", esperas.append)
    pedidos: list = []
    respostas = [
        RespostaFalsa(ValueError("Expecting value: line 1 column 1 (char 0)")),
        RespostaFalsa([{"data": "01/09/2026", "valor": "0.48"}]),
    ]
    serie = bcb.baixar_serie_sgs(
        "ipca", date(2026, 1, 1), HOJE, HOJE, _buscar(respostas, pedidos)
    )
    assert len(serie) == 1 and len(esperas) == 1 and len(pedidos) == 2


def test_erro_passageiro_que_insiste_desiste_depois_de_tres_tentativas(monkeypatch):
    monkeypatch.setattr(bcb, "esperar", lambda _: None)
    pedidos: list = []
    with pytest.raises(bcb.BcbIndisponivelError):
        bcb.baixar_serie_sgs(
            "ipca",
            date(2026, 1, 1),
            HOJE,
            HOJE,
            _buscar([RespostaFalsa(None, status=503) for _ in range(3)], pedidos),
        )
    assert len(pedidos) == 3


# --- PTAX de outras moedas (ferramentas do site, PR 3) -----------------------------------------
MOEDAS = {
    "value": [
        {"simbolo": "AUD", "nomeFormatado": "Dólar australiano", "tipoMoeda": "B"},
        {"simbolo": "EUR", "nomeFormatado": "Euro", "tipoMoeda": "B"},
        {
            "simbolo": "USD",
            "nomeFormatado": "Dólar dos Estados Unidos",
            "tipoMoeda": "A",
        },
    ]
}
PTAX_DO_EURO = {
    "value": [
        {"paridadeCompra": 1.1182, "paridadeVenda": 1.1183, "cotacaoCompra": 5.613,
         "cotacaoVenda": 5.6142, "dataHoraCotacao": "2026-10-08 10:03:11.648598",
         "tipoBoletim": "Abertura"},
        {"paridadeCompra": 1.1191, "paridadeVenda": 1.1192, "cotacaoCompra": 5.6081,
         "cotacaoVenda": 5.6093, "dataHoraCotacao": "2026-10-08 13:08:16.814037",
         "tipoBoletim": "Fechamento"},
        {"paridadeCompra": 1.1197, "paridadeVenda": 1.1199, "cotacaoCompra": 5.5998,
         "cotacaoVenda": 5.6015, "dataHoraCotacao": "2026-10-09 10:10:14.047225",
         "tipoBoletim": "Abertura"},
    ]
}  # fmt: skip


def test_lista_de_moedas_da_ptax():
    moedas = bcb.montar_moedas(MOEDAS)
    assert [m.codigo for m in moedas] == ["AUD", "EUR", "USD"]
    assert moedas[1].nome == "Euro"


def test_lista_de_moedas_vazia_da_erro_claro():
    with pytest.raises(bcb.BcbIndisponivelError, match="moedas"):
        bcb.montar_moedas({"value": []})


def test_ptax_de_outra_moeda_fica_so_com_o_boletim_de_fechamento():
    """O dia 09/10 só tem a abertura (o fechamento sai às 13h): não entra."""
    euro = bcb.montar_ptax_da_moeda(PTAX_DO_EURO, HOJE)
    assert list(euro.index) == [pd.Timestamp("2026-10-08")]
    assert euro.loc["2026-10-08", "venda"] == pytest.approx(5.6093)


def test_ptax_de_outra_moeda_pede_a_moeda_e_o_periodo():
    pedidos: list = []
    bcb.baixar_ptax_da_moeda(
        "EUR",
        date(2026, 10, 6),
        date(2026, 10, 9),
        HOJE,
        _buscar([RespostaFalsa(PTAX_DO_EURO)], pedidos),
    )
    assert "CotacaoMoedaPeriodo" in pedidos[0][0]
    assert pedidos[0][1]["@moeda"] == "'EUR'"
    assert pedidos[0][1]["@dataInicial"] == "'10-06-2026'"


def test_ptax_de_moeda_sem_fechamento_no_periodo_da_erro_claro():
    so_abertura = {"value": PTAX_DO_EURO["value"][2:]}
    with pytest.raises(bcb.BcbIndisponivelError, match="PTAX"):
        bcb.montar_ptax_da_moeda(so_abertura, HOJE)


def test_series_do_sgs_sem_codigo_nem_nome_repetido_e_com_unidade():
    codigos = [s.codigo for s in bcb.SERIES.values()]
    assert len(codigos) == len(set(codigos))
    nomes = [s.nome for s in bcb.SERIES.values()]
    assert len(nomes) == len(set(nomes))
    assert all(s.nome and s.unidade for s in bcb.SERIES.values())


def test_series_do_lote_1_estao_na_lista_e_as_encerradas_ficam_de_fora():
    for chave, codigo in {
        "credito_saldo": 20539,
        "inadimplencia": 21082,
        "juros_credito": 20714,
        "transacoes_correntes": 22701,
        "divida_bruta_pib": 13762,
        "ipca_nucleo_aparadas_suavizado": 4466,
        "ibc_br_dessazonalizado": 24364,
        "inadimplencia_publicos": 13667,
    }.items():
        assert bcb.SERIES[chave].codigo == codigo
    # param de ser divulgada (conferido em 23/10/2026): CDB/RDB pós-fixado parou em 2024
    assert 28663 not in {s.codigo for s in bcb.SERIES.values()}


def test_sgs_de_valor_negativo_ou_grande_e_lido_e_o_futuro_continua_cortado():
    """Saldo de transações correntes é negativo e o crédito passa de 7 milhões (R$ milhões)."""
    registros = [
        {"data": "01/07/2026", "valor": "-5054.7"},
        {"data": "01/08/2026", "valor": "7397669"},
        {"data": "01/11/2026", "valor": "1"},  # depois de hoje
    ]
    serie = bcb.montar_serie_sgs(registros, "Saldo", HOJE)
    assert serie.tolist() == [pytest.approx(-5054.7), pytest.approx(7397669.0)]


def test_focus_de_indicador_novo_e_lido_pela_mesma_montagem():
    resposta = {
        "value": [
            {"Indicador": "Dívida líquida do setor público", "IndicadorDetalhe": None,
             "Data": "2026-10-13", "DataReferencia": "2026", "Mediana": 70, "Media": 70.1,
             "Minimo": 66, "Maximo": 75, "numeroRespondentes": 30},
        ]
    }  # fmt: skip
    pedidos: list = []
    focus = bcb.baixar_focus(
        "Dívida líquida do setor público", date(2026, 10, 1),
        _buscar([RespostaFalsa(resposta)], pedidos),
    )  # fmt: skip
    assert focus["mediana"].tolist() == [70]
    assert "D%C3%ADvida%20l%C3%ADquida%20do%20setor%20p%C3%BAblico" in pedidos[0][0]
