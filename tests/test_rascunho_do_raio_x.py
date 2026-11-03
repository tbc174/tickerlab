"""O rascunho do Raio-X em dia de evento (plano `2026-10-28-raio-x-todo-dia`, PR 6b, Tarefa 11).

O rascunho não é publicado: fica no acervo esperando o "pode" do Tiago. Mesmo assim sai sempre com
"Limites e cuidados" e as fontes, como todo relatório do TickerLab.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src import raio_x
from src import rascunho_do_raio_x as rr
from tests.test_raio_x import EMPRESAS_DE_26_10, IBOVESPA_DE_26_10

DIA, VESPERA = date(2026, 10, 26), date(2026, 10, 23)


@pytest.fixture(scope="module")
def raio_x_de_26_10() -> dict:
    empresas = pd.read_csv(EMPRESAS_DE_26_10)
    balancos = pd.DataFrame(
        [
            {
                "cnpj": cnpj,
                "divida_liquida": 3.0 * i - 20,
                "ebitda": 5.0,
                "divulgado_em": "2026-08-07",
            }
            for i, cnpj in enumerate(empresas["cnpj"].dropna().unique())
        ]
    )
    return raio_x.raio_x_do_pregao(DIA, VESPERA, empresas, IBOVESPA_DE_26_10, balancos)


def test_secoes_do_rascunho(raio_x_de_26_10):
    secoes = rr.secoes(raio_x_de_26_10)
    titulos = [s.titulo for s in secoes]
    assert titulos[0] == "O pregão"
    assert titulos[-2:] == ["Fontes", rr.TITULO_DOS_LIMITES]
    abertura = secoes[0].paragrafos[0]
    assert "26/10/2026" in abertura
    assert "−10,0%" in abertura  # o Ibovespa de 26/10
    assert "120 empresas" in abertura
    assert "35 caíram 30% ou mais" in abertura
    quedas = next(s for s in secoes if s.titulo == "Maiores quedas")
    assert len(quedas.tabela.linhas) == raio_x.MAIORES_QUEDAS


def test_limites_e_fontes_sempre(raio_x_de_26_10):
    sem_balanco = {**raio_x_de_26_10, "alavancagem": None, "choques_anteriores": []}
    for saida in (raio_x_de_26_10, sem_balanco):
        secoes = {s.titulo: s for s in rr.secoes(saida)}
        assert secoes[rr.TITULO_DOS_LIMITES].paragrafos == list(rr.LIMITES)
        assert any("recomendação" in limite for limite in rr.LIMITES)
        assert secoes["Fontes"].paragrafos
    divida = {s.titulo: s for s in rr.secoes(sem_balanco)}["Queda e dívida"]
    assert divida.tabela is None
    assert "balanço" in divida.paragrafos[0]


def test_rascunho_em_html_escapa_o_texto(raio_x_de_26_10):
    com_tag = {
        **raio_x_de_26_10,
        "maiores": {
            "quedas": [
                {
                    "simbolo": "ABCD3",
                    "empresa": "<script>alert(1)</script>",
                    "setor": "Varejo",
                    "variacao": -0.4,
                    "fechamento": 1.0,
                }
            ],
            "altas": [],
        },
    }
    pagina = rr.em_html(com_tag)
    assert "<script>alert" not in pagina
    assert "&lt;script&gt;" in pagina
    assert "RASCUNHO" in pagina
    assert rr.TITULO_DOS_LIMITES in pagina


def test_rascunho_em_pdf(raio_x_de_26_10):
    pdf = rr.em_pdf(
        raio_x_de_26_10,
        datetime(2026, 10, 27, 6, 45, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )
    assert pdf.startswith(b"%PDF")
