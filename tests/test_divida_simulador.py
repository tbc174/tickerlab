"""Simulador de instrumento (B-23 do dossiê da plataforma, protótipo B, parte 3).

O gabarito "da planilha" foi feito por outro caminho (fórmulas fechadas em `Decimal`, como numa
planilha: PGTO para a Price, saldo fechado P × (1 + i)^k − PMT × ((1 + i)^k − 1) ÷ i, e a
flat-forward escrita à mão), não pelo laço do simulador; o fluxo tem de bater ao centavo. As regras
que valem para qualquer instrumento vão por propriedade (Hypothesis)."""

import json
import math
from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.porta import Porta
from src.divida import curva_do_dia as cd
from src.divida import simulador as si

DIA = date(2026, 9, 30)
NOMINAL = ((0.5, 0.11), (1.0, 0.115), (2.0, 0.12))
IMPLICITA = ((0.5, 0.045), (1.0, 0.047))


def _curva(
    nominal: tuple[tuple[float, float], ...] = NOMINAL,
    implicita: tuple[tuple[float, float], ...] = IMPLICITA,
) -> cd.CurvaDoDia:
    return cd.CurvaDoDia(
        date(2026, 9, 29),
        DIA,
        nominal,
        implicita,
        cd.rastro_da_curva(date(2026, 9, 29), DIA),
    )


def _centavos(simulacao: si.Simulacao, *colunas: str) -> list[tuple[float, ...]]:
    return [
        tuple(round(getattr(p, c), 2) + 0.0 for c in colunas)  # + 0.0: −0,0 vira 0,0
        for p in simulacao.periodos
    ]


# --- o gabarito da planilha, ao centavo ------------------------------------------------------------
def test_sac_pre_bate_com_a_planilha():
    instrumento = si.Instrumento(1_200_000, si.PRE, 0.12, 12, si.SAC)
    simulacao = si.simular(instrumento, None, DIA)
    assert _centavos(simulacao, "juros", "amortizacao", "parcela", "saldo_final") == [
        (11386.55, 100000.0, 111386.55, 1100000.0),
        (10437.67, 100000.0, 110437.67, 1000000.0),
        (9488.79, 100000.0, 109488.79, 900000.0),
        (8539.91, 100000.0, 108539.91, 800000.0),
        (7591.03, 100000.0, 107591.03, 700000.0),
        (6642.16, 100000.0, 106642.16, 600000.0),
        (5693.28, 100000.0, 105693.28, 500000.0),
        (4744.4, 100000.0, 104744.4, 400000.0),
        (3795.52, 100000.0, 103795.52, 300000.0),
        (2846.64, 100000.0, 102846.64, 200000.0),
        (1897.76, 100000.0, 101897.76, 100000.0),
        (948.88, 100000.0, 100948.88, 0.0),
    ]


def test_price_pre_bate_com_a_planilha():
    """Planilha: =PGTO((1,12)^(1/12)−1; 12; −1200000) = 106.274,48."""
    instrumento = si.Instrumento(1_200_000, si.PRE, 0.12, 12, si.PRICE)
    simulacao = si.simular(instrumento, None, DIA)
    assert _centavos(simulacao, "juros", "amortizacao", "parcela", "saldo_final") == [
        (11386.55, 94887.93, 106274.48, 1105112.07),
        (10486.18, 95788.3, 106274.48, 1009323.77),
        (9577.26, 96697.22, 106274.48, 912626.55),
        (8659.72, 97614.76, 106274.48, 815011.8),
        (7733.48, 98541.0, 106274.48, 716470.79),
        (6798.44, 99476.04, 106274.48, 616994.76),
        (5854.54, 100419.95, 106274.48, 516574.81),
        (4901.67, 101372.81, 106274.48, 415202.0),
        (3939.77, 102334.72, 106274.48, 312867.29),
        (2968.73, 103305.75, 106274.48, 209561.54),
        (1988.49, 104285.99, 106274.48, 105275.54),
        (998.94, 105275.54, 106274.48, 0.0),
    ]


def test_bullet_semestral_paga_juros_e_o_principal_no_fim():
    instrumento = si.Instrumento(
        500_000, si.PRE, 0.10, 36, si.BULLET, meses_por_periodo=6
    )
    simulacao = si.simular(instrumento, None, DIA)
    assert _centavos(simulacao, "juros", "amortizacao", "saldo_final") == [
        *[(24404.42, 0.0, 500000.0)] * 5,
        (24404.42, 500000.0, 0.0),
    ]
    assert [p.mes for p in simulacao.periodos] == [6, 12, 18, 24, 30, 36]


def test_cdi_trimestral_com_carencia_bate_com_a_planilha():
    """CDI + 1,5% a.a., SAC trimestral em 2 anos, 6 meses de carência com juros pagos; o CDI de
    cada trimestre é a taxa a termo da curva nominal (flat-forward)."""
    instrumento = si.Instrumento(
        1_000_000, si.CDI, 0.015, 24, si.SAC, carencia_meses=6, meses_por_periodo=3
    )
    simulacao = si.simular(instrumento, _curva(), DIA)
    assert _centavos(simulacao, "juros", "amortizacao", "parcela", "saldo_final") == [
        (30260.99, 0.0, 30260.99, 1000000.0),
        (30260.99, 0.0, 30260.99, 1000000.0),
        (32578.79, 166666.67, 199245.46, 833333.33),
        (27148.99, 166666.67, 193815.66, 666666.67),
        (22486.17, 166666.67, 189152.83, 500000.0),
        (16864.62, 166666.67, 183531.29, 333333.33),
        (11243.08, 166666.67, 177909.75, 166666.67),
        (5621.54, 166666.67, 172288.21, 0.0),
    ]
    cdi = [p.indexador_do_periodo for p in simulacao.periodos]
    assert cdi[0] == pytest.approx(0.026433327247938634, abs=1e-12)
    assert cdi[2] == pytest.approx(0.028742516504512115, abs=1e-12)
    assert cdi[4] == pytest.approx(0.029888703372965238, abs=1e-12)


def test_ipca_com_carencia_capitalizada_bate_com_a_planilha():
    """IPCA + 6% a.a., SAC trimestral em 1 ano, 3 meses de carência com juros capitalizados; o
    saldo é corrigido pela inflação implícita a termo antes dos juros e da amortização."""
    instrumento = si.Instrumento(
        800_000,
        si.IPCA,
        0.06,
        12,
        si.SAC,
        carencia_meses=3,
        meses_por_periodo=3,
        juros_na_carencia=si.CAPITALIZADOS,
    )
    simulacao = si.simular(instrumento, _curva(), DIA)
    colunas = (
        "correcao_monetaria",
        "juros",
        "juros_pagos",
        "amortizacao",
        "parcela",
        "saldo_final",
    )
    assert _centavos(simulacao, *colunas) == [
        (8851.99, 11868.97, 0.0, 0.0, 0.0, 820720.96),
        (9081.27, 12176.39, 12176.39, 276600.74, 288777.13, 553201.49),
        (6656.15, 8215.26, 8215.26, 279928.82, 288144.08, 279928.82),
        (3368.12, 4157.06, 4157.06, 283296.94, 287453.99, 0.0),
    ]


# --- a curva, sem extrapolar ---------------------------------------------------------------------
def test_fator_nos_vertices_e_antes_do_primeiro():
    curva = _curva()
    assert curva.fator(cd.NOMINAL, 0) == 1.0
    assert curva.fator(cd.NOMINAL, 1.0) == pytest.approx(1.115)
    assert curva.fator(cd.NOMINAL, 2.0) == pytest.approx(1.12**2)
    # até o primeiro vértice, a taxa a termo é a dele (flat-forward a partir do fator 1 de hoje)
    assert curva.fator(cd.NOMINAL, 0.25) == pytest.approx(1.11**0.25)


def test_prazo_depois_do_ultimo_vertice_da_erro_explicito():
    with pytest.raises(cd.ForaDaCurva, match="não extrapola"):
        _curva().fator(cd.NOMINAL, 2.01)


@pytest.mark.parametrize(("indexador", "prazo_meses"), [(si.CDI, 27), (si.IPCA, 15)])
def test_instrumento_mais_longo_que_a_curva_nao_e_simulado(indexador, prazo_meses):
    instrumento = si.Instrumento(
        1_000_000, indexador, 0.01, prazo_meses, si.SAC, meses_por_periodo=3
    )
    with pytest.raises(cd.ForaDaCurva):
        si.simular(instrumento, _curva(), DIA)


def test_curva_sem_vertices_da_erro_explicito():
    curva = _curva(implicita=())
    instrumento = si.Instrumento(1_000_000, si.IPCA, 0.06, 12, si.SAC)
    with pytest.raises(cd.ForaDaCurva, match="não tem vértices"):
        si.simular(instrumento, curva, DIA)


def test_cdi_e_ipca_pedem_a_curva_e_o_pre_nao():
    with pytest.raises(ValueError, match="precisa da curva"):
        si.simular(si.Instrumento(1_000, si.CDI, 0.01, 12, si.SAC), None, DIA)
    pre = si.simular(si.Instrumento(1_000, si.PRE, 0.10, 12, si.SAC), _curva(), DIA)
    assert pre.curva_de is None


# --- a curva como era, pela porta ---------------------------------------------------------------
def _linhas_da_curva(data_base: str, disponivel_em: str, nivel: float) -> list[dict]:
    return [
        {
            "data_base": pd.Timestamp(data_base),
            "curva": curva,
            "prazo_anos": prazo,
            "taxa": nivel + extra,
            "titulos": 5,
            "maior_prazo_anos": 2.2,
            "disponivel_em": pd.Timestamp(disponivel_em),
        }
        for curva, extra in (("nominal", 0.0), ("real", -0.06), ("implicita", -0.07))
        for prazo in (0.5, 1.0, 2.0)
    ]


def _porta(tmp_path, linhas: list[dict]) -> Porta:
    return Porta(
        tmp_path,
        arquivos={},
        conferidas={},
        extras={"curva_juros": pd.DataFrame(linhas)},
    )


def test_curva_como_era_usa_a_mais_nova_ja_publica(tmp_path):
    linhas = [
        *_linhas_da_curva("2026-09-28", "2026-09-29", 0.11),
        *_linhas_da_curva("2026-09-29", "2026-09-30", 0.12),
        *_linhas_da_curva("2026-09-30", "2026-10-01", 0.50),  # só pública depois do dia
    ]
    with _porta(tmp_path, linhas) as porta:
        curva = cd.curva_como_era(porta, DIA)
    assert curva.data_base == date(2026, 9, 29)
    assert curva.disponivel_em == DIA
    assert curva.nominal == ((0.5, 0.12), (1.0, 0.12), (2.0, 0.12))
    assert curva.implicita[0] == (0.5, pytest.approx(0.05))
    assert curva.rastro.publicado_em == DIA
    assert curva.rastro.fonte_id == "tesouro-br-direto"
    assert curva.rastro.o_que_falta() == []


def test_sem_curva_publica_no_dia_da_erro_explicito(tmp_path):
    with (
        _porta(tmp_path, _linhas_da_curva("2026-09-30", "2026-10-01", 0.11)) as porta,
        pytest.raises(cd.ForaDaCurva, match="Não há curva"),
    ):
        cd.curva_como_era(porta, DIA)


def test_curva_que_saiu_depois_do_dia_nao_muda_a_simulacao(tmp_path):
    """Sem olhar o futuro: acrescentar a curva de amanhã não muda a simulação de hoje."""
    hoje = _linhas_da_curva("2026-09-29", "2026-09-30", 0.12)
    amanha = _linhas_da_curva("2026-09-30", "2026-10-01", 0.30)
    instrumento = si.Instrumento(
        1_000_000, si.CDI, 0.01, 24, si.PRICE, meses_por_periodo=3
    )
    with _porta(tmp_path / "a", hoje) as porta:
        so_hoje = si.simular(instrumento, cd.curva_como_era(porta, DIA), DIA)
    with _porta(tmp_path / "b", hoje + amanha) as porta:
        com_amanha = si.simular(instrumento, cd.curva_como_era(porta, DIA), DIA)
    assert so_hoje.periodos == com_amanha.periodos


# --- os termos declarados ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("campos", "mensagem"),
    [
        ({"principal": 0}, "principal"),
        ({"taxa": -1.0}, "taxa"),
        ({"indexador": "selic"}, "indexador"),
        ({"amortizacao": "americano"}, "amortizacao"),
        ({"meses_por_periodo": 2}, "meses_por_periodo"),
        ({"prazo_meses": 13, "meses_por_periodo": 3}, "prazo"),
        ({"carencia_meses": 4, "meses_por_periodo": 3}, "carência"),
        ({"carencia_meses": 12}, "carência"),
        ({"amortizacao": si.BULLET, "carencia_meses": 3}, "bullet"),
        ({"juros_na_carencia": "perdoados"}, "juros_na_carencia"),
    ],
)
def test_termos_invalidos_sao_recusados(campos, mensagem):
    termos = {
        "principal": 1_000.0,
        "indexador": si.PRE,
        "taxa": 0.1,
        "prazo_meses": 12,
        "amortizacao": si.SAC,
    }
    with pytest.raises(ValueError, match=mensagem):
        si.Instrumento(**{**termos, **campos})


def test_instrumento_vai_e_volta_em_json():
    instrumento = si.Instrumento(
        1_000, si.IPCA, 0.06, 24, si.PRICE, 6, 3, si.CAPITALIZADOS
    )
    assert (
        si.Instrumento.de_dict(json.loads(json.dumps(instrumento.como_dict())))
        == instrumento
    )


def test_simulacao_vira_json_com_o_rastro_de_cada_coluna():
    simulacao = si.simular(
        si.Instrumento(1_000, si.CDI, 0.01, 12, si.SAC), _curva(), DIA
    )
    dados = json.loads(json.dumps(simulacao.como_dict()))
    assert dados["curva_de"] == "2026-09-29"
    assert set(dados["rastros"]) == set(si.FORMULAS)
    for rastro in simulacao.rastros.values():
        assert rastro.o_que_falta() == []
        assert rastro.fonte_id == "tesouro-br-direto"


def test_pre_tem_rastro_dos_termos_declarados():
    simulacao = si.simular(si.Instrumento(1_000, si.PRE, 0.1, 12, si.SAC), None, DIA)
    for rastro in simulacao.rastros.values():
        assert rastro.fonte_id == si.FONTE_DOS_TERMOS
        assert rastro.o_que_falta() == []


# --- propriedades (Hypothesis) -------------------------------------------------------------------
@st.composite
def instrumentos(
    draw, indexadores=si.INDEXADORES, amortizacoes=si.AMORTIZACOES
) -> si.Instrumento:
    meses = draw(st.sampled_from(si.MESES_POR_PERIODO))
    periodos = draw(st.integers(1, 24 // meses))
    amortizacao = draw(st.sampled_from(amortizacoes))
    carencia = 0 if amortizacao == si.BULLET else draw(st.integers(0, periodos - 1))
    return si.Instrumento(
        principal=draw(st.floats(1_000, 1e10)),
        indexador=draw(st.sampled_from(indexadores)),
        taxa=draw(st.floats(-0.02, 0.4)),
        prazo_meses=periodos * meses,
        amortizacao=amortizacao,
        carencia_meses=carencia * meses,
        meses_por_periodo=meses,
        juros_na_carencia=draw(st.sampled_from(si.JUROS_NA_CARENCIA)),
    )


@st.composite
def curvas(draw) -> cd.CurvaDoDia:
    taxas = st.floats(0.0, 0.3)
    nominal = tuple((p, draw(taxas)) for p in (0.5, 1.0, 2.0))
    implicita = tuple((p, draw(st.floats(-0.01, 0.15))) for p in (0.5, 1.0, 2.0))
    return _curva(nominal, implicita)


@settings(max_examples=200, deadline=None)
@given(instrumentos(), curvas())
def test_amortizacoes_somam_o_principal_mais_correcao_e_juros_capitalizados(
    instrumento, curva
):
    simulacao = si.simular(instrumento, curva, DIA)
    capitalizados = simulacao.total("juros") - simulacao.total("juros_pagos")
    devido = (
        instrumento.principal + simulacao.total("correcao_monetaria") + capitalizados
    )
    assert simulacao.total("amortizacao") == pytest.approx(devido, rel=1e-9)
    assert simulacao.periodos[-1].saldo_final == 0.0


@settings(max_examples=200, deadline=None)
@given(instrumentos(indexadores=(si.PRE, si.CDI), amortizacoes=(si.SAC,)), curvas())
def test_sac_tem_amortizacao_constante_depois_da_carencia(instrumento, curva):
    simulacao = si.simular(instrumento, curva, DIA)
    depois = [
        p.amortizacao for p in simulacao.periodos[instrumento.periodos_de_carencia :]
    ]
    assert all(a == pytest.approx(depois[0], rel=1e-9) for a in depois)


@settings(max_examples=200, deadline=None)
@given(instrumentos(indexadores=(si.PRE,), amortizacoes=(si.PRICE,)))
def test_price_pre_tem_parcela_constante_depois_da_carencia(instrumento):
    simulacao = si.simular(instrumento, None, DIA)
    depois = [p.parcela for p in simulacao.periodos[instrumento.periodos_de_carencia :]]
    assert all(a == pytest.approx(depois[0], rel=1e-9) for a in depois)


@settings(max_examples=100, deadline=None)
@given(instrumentos(), curvas())
def test_parcela_e_juros_pagos_mais_amortizacao_e_nada_e_negativo(instrumento, curva):
    for p in si.simular(instrumento, curva, DIA).periodos:
        assert p.parcela == pytest.approx(p.juros_pagos + p.amortizacao)
        assert p.saldo_final >= 0 or math.isclose(p.saldo_final, 0, abs_tol=1e-6)
        if instrumento.taxa >= 0 and p.indexador_do_periodo >= 0:
            assert p.amortizacao >= -1e-6
