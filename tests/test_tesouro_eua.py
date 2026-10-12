"""Leitor da curva de juros do Tesouro dos EUA, sem internet: CSV no formato real."""

import pandas as pd
import pytest
import requests

from src import tesouro_eua

CSV = (
    'Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr",'
    '"10 Yr","20 Yr","30 Yr"\n'
    "10/09/2026,4.13,4.13,4.13,4.25,4.29,4.32,4.47,4.80,4.89,5.02,5.13,5.24,5.65,5.60\n"
    "10/08/2026,4.14,4.14,4.13,4.23,4.29,4.30,4.44,4.75,4.85,4.99,5.11,5.22,5.64,5.60\n"
)


class RespostaFalsa:
    def __init__(self, texto: str, status: int = 200) -> None:
        self.text = texto
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}")


@pytest.mark.parametrize(
    ("coluna", "anos"),
    [
        ("1 Mo", 1 / 12),
        ("1.5 Month", 0.125),
        ("6 Mo", 0.5),
        ("10 Yr", 10.0),
        ("Date", None),
    ],
)
def test_prazo_de_cada_coluna_em_anos(coluna, anos):
    assert tesouro_eua.prazo_em_anos(coluna) == (pytest.approx(anos) if anos else None)


def test_curva_por_dia_em_fracao_e_em_ordem():
    curva = tesouro_eua.montar_curva(CSV)
    assert list(curva.index) == [pd.Timestamp("2026-10-08"), pd.Timestamp("2026-10-09")]
    assert curva.columns[0] == pytest.approx(1 / 12)
    assert curva.columns[-1] == pytest.approx(30.0)
    assert curva.loc["2026-10-09", 10.0] == pytest.approx(0.0524)


def test_csv_estranho_da_erro_claro():
    with pytest.raises(tesouro_eua.TesouroIndisponivelError):
        tesouro_eua.montar_curva("sem,data\n1,2\n")
    with pytest.raises(tesouro_eua.TesouroIndisponivelError, match="prazos"):
        tesouro_eua.montar_curva("Date,nada\n10/09/2026,1\n")


def test_baixa_o_ano_pedido_e_avisa_quando_o_site_falha():
    pedidos = []

    def buscar(url, params=None, timeout=None, headers=None):
        pedidos.append((url, params))
        return RespostaFalsa(CSV)

    tesouro_eua.baixar_curva(2026, buscar)
    assert "/2026/all" in pedidos[0][0]
    assert pedidos[0][1]["field_tdr_date_value"] == "2026"

    def fora_do_ar(url, params=None, timeout=None, headers=None):
        return RespostaFalsa("", status=503)

    with pytest.raises(tesouro_eua.TesouroIndisponivelError):
        tesouro_eua.baixar_curva(2026, fora_do_ar)
