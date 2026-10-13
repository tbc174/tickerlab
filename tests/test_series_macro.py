"""Séries macro com safras (Radar, PR 5), sem internet: revisão não apaga a anterior, repetir o
dia não duplica, "como estava em D" e o Yahoo só para uso interno."""

import json
from datetime import date

import pandas as pd
import pytest
import requests

from scripts import atualizar_series_macro as coletor
from src import bcb
from src.banco import series as acervo_de_series
from src.banco.coletas import buscar_com_registro, ultimas
from src.banco.series import SerieDoAcervo

HOJE = date(2026, 10, 13)
IPCA = SerieDoAcervo("bcb-sgs-433", "IPCA", "% no mês", "mensal")


def _serie(**valores) -> pd.Series:
    return pd.Series({pd.Timestamp(d): v for d, v in valores.items()})


def _gravar(banco, valores: pd.Series, safra: date) -> int:
    with banco.begin() as conexao:
        acervo_de_series.garantir_serie(conexao, IPCA)
        return acervo_de_series.gravar(conexao, IPCA.codigo, valores, safra)


# --- acervo de séries ---------------------------------------------------------------------------
def test_repetir_o_dia_nao_duplica(banco):
    valores = pd.Series(
        [0.44, 0.48], index=pd.to_datetime(["2026-08-01", "2026-09-01"])
    )
    assert _gravar(banco, valores, date(2026, 10, 10)) == 2
    assert _gravar(banco, valores, date(2026, 10, 11)) == 0


def test_revisao_vira_safra_nova_sem_apagar_a_anterior(banco):
    agosto = pd.Timestamp("2026-08-01")
    _gravar(banco, pd.Series([0.44], index=[agosto]), date(2026, 9, 10))
    _gravar(banco, pd.Series([0.47], index=[agosto]), date(2026, 10, 10))
    with banco.connect() as conexao:
        assert acervo_de_series.safras(conexao, IPCA.codigo, agosto.date()) == [
            (date(2026, 9, 10), pytest.approx(0.44)),
            (date(2026, 10, 10), pytest.approx(0.47)),
        ]
        antes = acervo_de_series.como_estava_em(conexao, IPCA.codigo, date(2026, 9, 30))
        depois = acervo_de_series.como_estava_em(conexao, IPCA.codigo, HOJE)
        nada = acervo_de_series.como_estava_em(conexao, IPCA.codigo, date(2026, 9, 1))
    assert antes[agosto] == pytest.approx(0.44)
    assert depois[agosto] == pytest.approx(0.47)
    assert nada.empty


def test_valor_vazio_e_ignorado(banco):
    valores = pd.Series(
        [float("nan"), 0.5], index=pd.to_datetime(["2026-08-01", "2026-09-01"])
    )
    assert _gravar(banco, valores, HOJE) == 1


def test_yahoo_fica_so_para_uso_interno(banco):
    with banco.begin() as conexao:
        acervo_de_series.garantir_serie(conexao, IPCA)
        acervo_de_series.garantir_serie(conexao, coletor.serie_yahoo("bvsp"))
        acervo_de_series.garantir_serie(conexao, IPCA)  # de novo: atualiza, não duplica
        assert acervo_de_series.series_para_exportar(conexao) == ["bcb-sgs-433"]


def test_codigos_e_rotulos_das_series():
    assert coletor.serie_sgs("ipca").codigo == "bcb-sgs-433"
    assert coletor.serie_sgs("ipca").frequencia == "mensal"
    assert coletor.serie_sgs("dolar").frequencia == "diária"
    assert coletor.rotulo_do_prazo(0.5) == "6m"
    assert coletor.rotulo_do_prazo(1.5 / 12) == "1.5m"
    assert coletor.rotulo_do_prazo(10.0) == "10a"
    assert coletor.serie_yahoo("gspc").uso_interno


# --- coleta (BC, Tesouro e Yahoo falsos) --------------------------------------------------------
class _Resposta:
    def __init__(self, url: str, corpo: object, status: int = 200) -> None:
        self.url = url
        self.status_code = status
        self.ok = status < 400
        self.text = corpo if isinstance(corpo, str) else json.dumps(corpo)
        self.content = self.text.encode()
        self._corpo = corpo

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(str(self.status_code))

    def json(self) -> object:
        return self._corpo


def _focus(data: str, mediana_2026: float) -> list[dict]:
    return [
        {"Indicador": "IPCA", "Data": data, "DataReferencia": "2026", "Mediana": mediana_2026,
         "Media": 5.0, "Minimo": 4.0, "Maximo": 6.0, "numeroRespondentes": 100},
        {"Indicador": "IPCA", "Data": data, "DataReferencia": "2027", "Mediana": 4.3,
         "Media": 4.3, "Minimo": 3.0, "Maximo": 6.0, "numeroRespondentes": 90},
    ]  # fmt: skip


CURVA = "Date,1 Mo,6 Mo,10 Yr\n10/09/2026,4.10,3.90,4.05\n10/08/2026,4.11,3.91,4.07\n"


def _fonte_falsa(pedidos: list, tesouro_fora: bool = False):
    def buscar(url, params=None, **_):
        pedidos.append(url)
        if "bcdata.sgs" in url:
            return _Resposta(url, [{"data": "01/09/2026", "valor": "0.48"}])
        if "PTAX" in url:
            cotacao = {"cotacaoCompra": 5.30, "cotacaoVenda": 5.31,
                       "dataHoraCotacao": "2026-10-09 13:00:00.0"}  # fmt: skip
            return _Resposta(url, {"value": [cotacao]})
        if "Expectativas" in url:
            assert "baseCalculo%20eq%200" in url  # só a conta do boletim
            return _Resposta(
                url, {"value": _focus("2026-10-02", 5.01) + _focus("2026-10-09", 5.05)}
            )
        if "treasury" in url:
            return (
                _Resposta(url, "erro", 503) if tesouro_fora else _Resposta(url, CURVA)
            )
        raise AssertionError(url)

    return buscar


def _yahoo(ticker: str, inicio: date) -> pd.Series:
    return _serie(**{"2026-10-08": 130_000.0, "2026-10-09": 131_000.0})


def test_coleta_grava_todas_as_fontes_com_safra(banco):
    pedidos: list = []
    assert coletor.coletar_tudo(banco, HOJE, _fonte_falsa(pedidos), _yahoo)
    with banco.connect() as conexao:
        focus = coletor.serie_focus("ipca").codigo
        # o Focus com duas pesquisas guarda as duas safras do mesmo ano
        assert acervo_de_series.safras(conexao, focus, date(2026, 12, 31)) == [
            (date(2026, 10, 2), pytest.approx(5.01)),
            (date(2026, 10, 9), pytest.approx(5.05)),
        ]
        como_em_5 = acervo_de_series.como_estava_em(conexao, focus, date(2026, 10, 5))
        assert como_em_5[pd.Timestamp("2026-12-31")] == pytest.approx(5.01)
        assert acervo_de_series.como_estava_em(
            conexao, "tesouro-eua-10a", HOJE
        ).tolist() == [
            pytest.approx(0.0407),
            pytest.approx(0.0405),
        ]
        assert (
            acervo_de_series.como_estava_em(conexao, "bcb-ptax-venda", HOJE).iloc[0]
            == 5.31
        )
        assert len(acervo_de_series.como_estava_em(conexao, "yahoo-bvsp", HOJE)) == 2
        registradas = {linha.fonte for linha in ultimas(conexao, quantas=100)}
    assert registradas == {"bcb-sgs", "bcb-ptax", "bcb-focus", "tesouro-eua"}


def test_segunda_coleta_do_dia_nao_grava_nada_e_pede_so_a_janela(banco):
    coletor.coletar_tudo(banco, HOJE, _fonte_falsa([]), _yahoo)
    with banco.connect() as conexao:
        total = conexao.exec_driver_sql("select count(*) from observacoes").scalar()
    pedidos: list = []
    assert coletor.coletar_tudo(banco, HOJE, _fonte_falsa(pedidos), _yahoo)
    with banco.connect() as conexao:
        assert (
            conexao.exec_driver_sql("select count(*) from observacoes").scalar()
            == total
        )
    # já tem dados: o Tesouro pede só os anos da janela de revisão, não desde 2010
    assert sum("treasury" in p for p in pedidos) == 2


def test_uma_fonte_fora_do_ar_nao_impede_as_outras(banco):
    assert not coletor.coletar_tudo(
        banco, HOJE, _fonte_falsa([], tesouro_fora=True), _yahoo
    )
    with banco.connect() as conexao:
        assert not acervo_de_series.tem_dados(conexao, "tesouro-eua-10a")
        assert acervo_de_series.tem_dados(conexao, "yahoo-gspc")
        falhas = [linha for linha in ultimas(conexao) if linha.situacao == "falhou"]
    assert falhas and falhas[0].detalhe == "HTTP 503"


def test_yahoo_vazio_e_falha(banco):
    assert not coletor.coletar_tudo(banco, HOJE, _fonte_falsa([]), lambda *_: None)


def test_registro_do_buscar_404_e_erro(banco):
    def buscar(url, **_):
        if "sumiu" in url:
            return _Resposta(url, "", 404)
        raise requests.ConnectionError("sem rede")

    registrar = buscar_com_registro("bcb-sgs", buscar)
    assert registrar("https://api.bcb.gov.br/sumiu").status_code == 404
    with pytest.raises(requests.ConnectionError):
        registrar("https://api.bcb.gov.br/x")
    with banco.connect() as conexao:
        situacoes = sorted((l.situacao, l.detalhe) for l in ultimas(conexao))
    assert situacoes == [("falhou", "ConnectionError"), ("nao_encontrado", "HTTP 404")]


def test_focus_sem_base_de_calculo_nao_filtra():
    pedidos: list = []

    def buscar(url, params=None, timeout=None):
        pedidos.append(url)
        return _Resposta(url, {"value": []})

    bcb.baixar_focus("IPCA", HOJE, buscar)
    assert "baseCalculo" not in pedidos[0]
