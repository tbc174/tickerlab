"""O Raio-X do choque para qualquer pregão (plano `2026-10-28-raio-x-todo-dia`, PR 6).

O gabarito é o Raio-X publicado de 26/10/2026: `arquivos/raio_x/empresas_2026-10-26.csv` é a tabela de
empresas que o pregão do dia monta do COTAHIST da B3 (23 e 26/10) e do FCA da CVM, refeita no servidor
de casa em 03/11/2026 pela mesma rota do `scripts/gerar_pregao_do_dia.py`.
"""

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import raio_x

EMPRESAS_DE_26_10 = (
    Path(__file__).parent / "arquivos" / "raio_x" / "empresas_2026-10-26.csv"
)
DIA, VESPERA = date(2026, 10, 26), date(2026, 10, 23)
# Ibovespa da B3 em 23 e 26/10/2026 (raiox_ibov.json do estudo publicado)
IBOVESPA_DE_26_10 = pd.Series(
    [146_000.0, 131_400.0], index=pd.to_datetime([VESPERA, DIA])
)


@pytest.fixture(scope="module")
def empresas() -> pd.DataFrame:
    return pd.read_csv(EMPRESAS_DE_26_10)


def _balanco(cnpj: str, divida_liquida: float, ebitda: float, divulgado_em: str):
    return {
        "cnpj": cnpj,
        "divida_liquida": divida_liquida,
        "ebitda": ebitda,
        "divulgado_em": divulgado_em,
    }


# --- o gabarito de 26/10 ---------------------------------------------------------------------------


def test_raio_x_refaz_26_10(empresas):
    """Mesmo recorte, mesma mediana e mesmas quedas fortes da página publicada."""
    queda = raio_x.queda_do_dia(empresas)
    assert queda["empresas"] == 120
    assert queda["mediana"] == pytest.approx(-0.2272, abs=1e-4)
    assert queda["quedas_fortes"] == 35
    assert queda["subiram"] == 8
    assert queda["limite_da_queda_forte"] == raio_x.QUEDA_FORTE


def test_raio_x_de_26_10_setor_que_mais_caiu(empresas):
    setores = raio_x.raio_x_do_pregao(DIA, VESPERA, empresas, IBOVESPA_DE_26_10)[
        "setores"
    ]
    pior = setores[0]
    assert pior["setor"] == "Serviços Transporte e Logística"
    assert pior["empresas"] == 9
    assert pior["mediana"] == pytest.approx(-0.5032, abs=1e-4)
    medianas = [s["mediana"] for s in setores]
    assert medianas == sorted(medianas)


def test_raio_x_do_pregao_e_json_simples(empresas):
    """Tipos simples, sem NaN: vai para o rascunho, para o PDF e um dia para a API."""
    balancos = pd.DataFrame(
        [_balanco("33.000.167/0001-01", 300e9, 200e9, "2026-08-07")]
    )
    saida = raio_x.raio_x_do_pregao(DIA, VESPERA, empresas, IBOVESPA_DE_26_10, balancos)
    json.dumps(saida, allow_nan=False)
    assert saida["pregao"] == "2026-10-26"
    assert saida["vespera"] == "2026-10-23"
    assert saida["ibovespa"]["variacao"] == pytest.approx(-0.10)
    assert len(saida["maiores"]["quedas"]) == raio_x.MAIORES_QUEDAS
    assert all(item["fonte"] for item in saida["fontes"].values())


# --- alavancagem -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("divida_liquida", "ebitda", "faixa"),
    [
        (-10.0, 5.0, "Caixa maior que a dívida"),
        (-10.0, -5.0, "Caixa maior que a dívida"),
        (0.0, 5.0, "Até 1x"),
        (5.0, 5.0, "Até 1x"),
        (7.5, 5.0, "1x a 2x"),
        (10.0, 5.0, "1x a 2x"),
        (12.0, 5.0, "2x a 3x"),
        (18.0, 5.0, "3x a 4x"),
        (25.0, 5.0, "Acima de 4x"),
        (25.0, 0.0, None),
        (25.0, -3.0, None),
        (math.nan, 5.0, None),
    ],
)
def test_faixa_de_alavancagem(divida_liquida, ebitda, faixa):
    assert raio_x.faixa_de_alavancagem(divida_liquida, ebitda) == faixa


def _tabela(linhas: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Empresas líquidas mínimas: (cnpj, setor, variação)."""
    return pd.DataFrame(
        [
            {
                "simbolo": f"PAP{i}3",
                "cnpj": cnpj,
                "empresa": f"Empresa {i}",
                "setor": setor,
                "fechamento_vespera": 10.0,
                "fechamento": 10.0 * (1 + variacao),
                "volume_vespera": 50e6,
                "volume": 80e6,
                "variacao": variacao,
                "a_conferir": False,
            }
            for i, (cnpj, setor, variacao) in enumerate(linhas)
        ]
    )


def test_queda_por_alavancagem_tira_os_bancos():
    tabela = _tabela(
        [
            ("A", "Energia Elétrica", -0.10),
            ("B", "Energia Elétrica", -0.30),
            ("C", "Bancos", -0.20),
        ]
    )
    balancos = pd.DataFrame(
        [
            _balanco("A", -1.0, 1.0, "2026-08-01"),
            _balanco("B", 5.0, 1.0, "2026-08-01"),
            _balanco("C", 50.0, 1.0, "2026-08-01"),
        ]
    )
    alavancagem = raio_x.queda_por_alavancagem(tabela, balancos, VESPERA)
    assert alavancagem["empresas"] == 2
    faixas = {f["faixa"]: f for f in alavancagem["faixas"]}
    assert faixas["Caixa maior que a dívida"]["mediana"] == pytest.approx(-0.10)
    assert faixas["Acima de 4x"]["mediana"] == pytest.approx(-0.30)
    assert [f["faixa"] for f in alavancagem["faixas"]] == [
        "Caixa maior que a dívida",
        "Acima de 4x",
    ]


# --- sem olhar o futuro ----------------------------------------------------------------------------


def test_raio_x_sem_olhar_o_futuro_no_balanco():
    """Balanço divulgado depois da véspera não entra: vale o último que já era público."""
    tabela = _tabela([("A", "Varejo", -0.25)])
    publico = _balanco("A", 1.5, 1.0, "2026-08-07")
    do_futuro = _balanco("A", 9.0, 1.0, "2026-10-26")
    so_o_publico = raio_x.queda_por_alavancagem(
        tabela, pd.DataFrame([publico]), VESPERA
    )
    com_o_futuro = raio_x.queda_por_alavancagem(
        tabela, pd.DataFrame([publico, do_futuro]), VESPERA
    )
    assert com_o_futuro == so_o_publico
    assert so_o_publico["faixas"][0]["faixa"] == "1x a 2x"


def _ibovespa_com_choque(depois_do_dia: int = 0) -> tuple[pd.Series, date]:
    """300 pregões de 100 pontos, um choque de −8% no 10º e o pregão estudado no 200º."""
    dias = pd.bdate_range("2025-01-01", periods=300 + depois_do_dia)
    pontos = np.full(len(dias), 100.0)
    pontos[10:] = 92.0
    pontos[25:] = 95.0
    pontos[200:] = 90.0  # o próprio pregão estudado também cai
    return pd.Series(pontos, index=dias), dias[200].date()


def test_choques_anteriores():
    serie, dia = _ibovespa_com_choque()
    choques = raio_x.choques_anteriores(serie.loc[: pd.Timestamp(dia)], dia)
    assert [c["dia"] for c in choques] == [serie.index[10].date().isoformat()]
    choque = choques[0]
    assert choque["queda"] == pytest.approx(-0.08)
    assert choque["depois"]["1 mês"] == pytest.approx(95 / 92 - 1)
    # 12 meses depois de um choque no 10º pregão é o 262º: ainda não tinha acontecido no 200º
    assert choque["depois"]["12 meses"] is None


def test_raio_x_sem_olhar_o_futuro_nos_choques():
    """Cortar o futuro não muda o passado: o que vem depois do pregão estudado não entra."""
    curta, dia = _ibovespa_com_choque()
    longa, _ = _ibovespa_com_choque(depois_do_dia=400)
    longa.iloc[201:] = 50.0  # um tombo depois do dia estudado
    assert raio_x.choques_anteriores(longa, dia) == raio_x.choques_anteriores(
        curta.loc[: pd.Timestamp(dia)], dia
    )


# --- betas -----------------------------------------------------------------------------------------


def _retornos(pregoes: int, semente: int = 7) -> tuple[pd.Series, pd.Series]:
    dias = pd.bdate_range("2025-10-01", periods=pregoes)
    fator = pd.Series(
        np.random.default_rng(semente).normal(0, 0.01, pregoes), index=dias
    )
    return 1.5 * fator, fator


def test_beta_contra_um_fator():
    papel, fator = _retornos(260)
    assert raio_x.beta(papel, fator, fator.index[-1].date()) == pytest.approx(1.5)


def test_beta_com_poucos_pregoes_fica_vazio():
    papel, fator = _retornos(raio_x.MINIMO_DE_PREGOES)
    assert raio_x.beta(papel, fator, fator.index[-1].date()) is None


def test_raio_x_sem_olhar_o_futuro_no_beta():
    """O beta usa só o ano até a véspera: o pregão do choque e o que vem depois não mexem nele."""
    papel, fator = _retornos(400)
    vespera = fator.index[300].date()
    antes = raio_x.beta(papel.iloc[:301], fator.iloc[:301], vespera)
    papel_com_futuro = papel.copy()
    papel_com_futuro.iloc[301:] = -0.5
    assert raio_x.beta(papel_com_futuro, fator, vespera) == pytest.approx(antes)
