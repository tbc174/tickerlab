"""Notas por padrões públicos (série 2 da base de ML, PR 4; ADR 0033): ótimo a péssimo pelos quintis
do grupo, na direção do indicador; barato, justo ou caro pelo setor e pelo próprio histórico; toda
nota com o padrão, a fonte e o aviso, e o selo quando o número está em conferência."""

from datetime import date

import pandas as pd
import pytest

from src import notas
from src.setores import MERCADO

PERCENTIS = {"10": 0.01, "20": 0.02, "25": 0.025, "33": 0.033, "40": 0.04, "50": 0.05,
             "60": 0.06, "67": 0.067, "75": 0.075, "80": 0.08, "90": 0.09}  # fmt: skip
CORTE = date(2025, 12, 31)


def _padroes(
    grupo="energia", indicador="margem_liquida", empresas=40, percentis=PERCENTIS
):
    return pd.DataFrame(
        [
            {
                "grupo": grupo,
                "indicador": indicador,
                "empresas": empresas,
                "percentis": percentis,
            }
        ]
    )


@pytest.mark.parametrize(
    ("valor", "maior_e_melhor", "esperada"),
    [
        (0.085, True, "ótimo"),
        (0.065, True, "bom"),
        (0.05, True, "médio"),
        (0.03, True, "ruim"),
        (0.01, True, "péssimo"),
        (0.01, False, "ótimo"),  # dívida: menor é melhor
        (0.085, False, "péssimo"),
    ],
)
def test_faixas_otimo_a_pessimo_pela_direcao_do_indicador(
    valor, maior_e_melhor, esperada
):
    assert notas.qualidade(valor, PERCENTIS, maior_e_melhor) == esperada


def test_nota_da_empresa_traz_o_padrao_a_fonte_e_o_grupo():
    [nota] = notas.notas_da_empresa(
        {"margem_liquida": 0.085}, "energia", _padroes(), CORTE
    )
    assert nota.nota == "ótimo"
    texto = nota.texto
    assert "Margem líquida (lucro consolidado) 8,5%: ótimo" in texto
    assert "Energia elétrica" in texto and "40 empresas" in texto
    assert "31/12/2025" in texto and "CVM" in texto
    assert "2,5%" in texto and "7,5%" in texto  # metade do grupo fica entre p25 e p75


def test_toda_nota_vem_com_o_aviso():
    assert "não é recomendação" in notas.AVISO.lower()
    assert "metodologia" in notas.AVISO.lower()


def test_numero_em_conferencia_mostra_o_selo_ao_lado_da_nota():
    [nota] = notas.notas_da_empresa(
        {"margem_liquida": 0.085}, "energia", _padroes(), CORTE, em_conferencia=True
    )
    assert nota.em_conferencia and "em conferência" in nota.texto.lower()


def test_grupo_pequeno_compara_com_o_mercado_e_avisa():
    padroes = pd.concat(
        [_padroes(grupo="educacao", empresas=5), _padroes(grupo=MERCADO, empresas=600)]
    )
    [nota] = notas.notas_da_empresa(
        {"margem_liquida": 0.085}, "educacao", padroes, CORTE
    )
    assert nota.grupo == MERCADO and "5 empresas" in nota.aviso_do_grupo
    assert "Mercado" in nota.texto


def test_sem_valor_ou_sem_padrao_nao_tem_nota():
    assert (
        notas.notas_da_empresa({"margem_liquida": None}, "energia", _padroes(), CORTE)
        == []
    )
    assert notas.notas_da_empresa({"roe": 0.1}, "energia", _padroes(), CORTE) == []


@pytest.mark.parametrize(
    ("multiplo", "setor", "historico", "esperado"),
    [
        (5.0, {"33": 8.0, "67": 12.0}, {"33": 7.0, "67": 11.0}, "barato"),
        (15.0, {"33": 8.0, "67": 12.0}, {"33": 7.0, "67": 11.0}, "caro"),
        (10.0, {"33": 8.0, "67": 12.0}, {"33": 7.0, "67": 11.0}, "justo"),
        (
            5.0,
            {"33": 8.0, "67": 12.0},
            {"33": 2.0, "67": 4.0},
            "justo",
        ),  # réguas discordam
        (5.0, {"33": 8.0, "67": 12.0}, None, "barato"),  # sem histórico: só o setor
    ],
)
def test_barato_justo_caro_pelo_setor_e_pelo_proprio_historico(
    multiplo, setor, historico, esperado
):
    resultado = notas.preco(multiplo, setor, historico)
    assert resultado.nota == esperado
    assert resultado.pelo_setor in {"barato", "justo", "caro"}
    if historico is None:
        assert resultado.pelo_historico is None


def test_multiplo_negativo_nao_tem_nota_de_preco():
    resultado = notas.preco(-3.0, {"33": 8.0, "67": 12.0}, None)
    assert resultado.nota is None and "prejuízo" in resultado.motivo


# --- faixa fixa (série 3, PR 2; decisão do Tiago em 14/10/2026) -----------------------------------
@pytest.mark.parametrize(
    ("valor", "esperada"),
    [
        (0.7, "atenção"),
        (0.8, "saudável"),  # os limites entram na faixa do meio
        (1.0, "saudável"),
        (1.5, "saudável"),
        (1.6, "conferir o lucro"),  # Petrobras no relatório de fim da série 2
    ],
)
def test_caixa_operacional_sobre_lucro_por_faixa_fixa(valor, esperada):
    nota = notas.nota_por_faixa("conversao_de_caixa", valor)
    assert nota.nota == esperada
    assert "não compara com o setor" in nota.texto
    assert "0,80×" in nota.texto and "1,50×" in nota.texto


def test_caixa_operacional_sobre_lucro_sai_dos_padroes_por_setor():
    """Um número alto costuma ser lucro pequeno, não caixa bom: o percentil do setor enganava."""
    from src.padroes import INDICADORES

    assert "conversao_de_caixa" not in INDICADORES
    nada = notas.notas_da_empresa(
        {"conversao_de_caixa": 1.6},
        "energia",
        _padroes(indicador="conversao_de_caixa"),
        CORTE,
    )
    assert nada == []


def test_indicador_sem_faixa_fixa_nao_tem_nota_por_faixa():
    assert notas.nota_por_faixa("margem_liquida", 0.1) is None
