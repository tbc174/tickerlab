"""As taxas de hoje do Tesouro Direto (src/tesouro_direto.py), sem internet.

O arquivo do Tesouro Transparente (ODbL) vem com os dias mais novos primeiro; o leitor usa só o
começo dele (pedido com Range) e fica com o dia mais novo.
"""

from datetime import date

import pytest
import requests

from src import tesouro_direto as td

CABECALHO = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
)
LINHAS = [
    "Tesouro Selic;01/03/2031;13/10/2026;0,09;0,10;20001,60;19982,63;19982,63",
    "Tesouro Prefixado;01/01/2032;13/10/2026;13,85;13,97;512,01;508,96;508,96",
    "Tesouro IPCA+;15/05/2035;13/10/2026;7,52;7,64;1980,33;1965,12;1965,12",
    "Tesouro IPCA+ com Juros Semestrais;15/08/2040;13/10/2026;7,40;7,52;4100,00;4000,00;4000,00",
    "Tesouro Prefixado;01/01/2027;13/10/2026;0,00;14,20;0,00;980,00;980,00",  # só resgate
    "Tesouro Prefixado;01/01/2032;10/10/2026;13,70;13,82;514,00;511,00;511,00",  # dia anterior
]


def _csv(linhas: list[str], cortar_no_meio: bool = False) -> bytes:
    texto = CABECALHO + "\n".join(linhas) + "\n"
    if cortar_no_meio:
        texto += "Tesouro Prefixado;01/01/20"  # o Range corta a última linha no meio
    return texto.encode("latin-1")


def test_le_so_o_dia_mais_novo_e_os_titulos_a_venda():
    taxas = td.ler_taxas_do_dia(_csv(LINHAS))
    assert taxas == {
        "data": "2026-10-13",
        "titulos": [
            {"titulo": "Tesouro IPCA+", "vencimento": "2035-05-15", "taxa": pytest.approx(0.0752)},
            {"titulo": "Tesouro Prefixado", "vencimento": "2032-01-01", "taxa": pytest.approx(0.1385)},
            {"titulo": "Tesouro Selic", "vencimento": "2031-03-01", "taxa": pytest.approx(0.0009)},
        ],
    }  # fmt: skip


def test_a_ultima_linha_cortada_pelo_range_e_ignorada():
    assert (
        td.ler_taxas_do_dia(_csv(LINHAS, cortar_no_meio=True))["data"] == "2026-10-13"
    )


def test_sem_titulo_a_venda_e_erro():
    with pytest.raises(td.TesouroIndisponivelError):
        td.ler_taxas_do_dia(_csv([LINHAS[4]]))


class Resposta:
    def __init__(self, conteudo: bytes, status: int) -> None:
        self.content = conteudo
        self.status_code = status


def test_baixa_so_o_comeco_do_arquivo():
    pedidos = []

    def buscar(url, params=None, timeout=None, headers=None):
        pedidos.append(headers)
        return Resposta(_csv(LINHAS, cortar_no_meio=True), 206)

    taxas = td.baixar_taxas_do_dia(date(2026, 10, 14), buscar)
    assert taxas["data"] == "2026-10-13"
    assert pedidos == [{"Range": f"bytes=0-{td.BYTES_DO_COMECO - 1}"}]


def test_dia_mais_novo_velho_demais_e_erro():
    # se o Tesouro mudar a ordem do arquivo (mais velhos primeiro), o começo traria 2002
    def buscar(url, params=None, timeout=None, headers=None):
        return Resposta(_csv(LINHAS), 206)

    with pytest.raises(td.TesouroIndisponivelError, match="velho"):
        td.baixar_taxas_do_dia(date(2026, 12, 1), buscar)


def test_falha_de_rede_vira_erro_do_tesouro():
    def buscar(url, params=None, timeout=None, headers=None):
        raise requests.ConnectionError("fora do ar")

    with pytest.raises(td.TesouroIndisponivelError):
        td.baixar_taxas_do_dia(date(2026, 10, 14), buscar)
