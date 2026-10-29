"""Vida média (WAL), CDR de equilíbrio e as regras da 0.2.0 ligadas nos cenários da cascata.

WAL em `src/securitizacao/cascata.py`; CDR de equilíbrio (bissecção, sem preço nem taxa) e as regras de
referência em `src/securitizacao/cenarios.py`. Toda carteira aqui é sintética (nenhuma operação real).
"""

import dataclasses
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.securitizacao.cascata import (
    PRO_RATA,
    Classe,
    Operacao,
    Periodo,
    Regras,
    rodar,
    vida_media_em_anos,
)
from src.securitizacao.cenarios import (
    CENARIO_BASE,
    CENARIO_PRE_PAGAMENTO,
    CENARIOS_PADRAO,
    REGRAS_DA_0_2_0_LIGADAS,
    TOLERANCIA_DO_EQUILIBRIO,
    Cenario,
    carteira_sintetica,
    cdr_de_equilibrio,
    cdrs_de_equilibrio,
    rodar_cenario,
    rodar_cenarios,
)

GABARITO = Path(__file__).parent / "gabaritos" / "securitizacao_equilibrio.json"
R = 100  # centavos por real


def _so_principal(valor: int) -> Periodo:
    return Periodo(
        principal_recebido=valor, juros_recebidos=0, recuperacoes=0, perda=0, despesas=0
    )


# Vida média ponderada (WAL)


def _wal(resultado, nome: str) -> float:
    vida_media = resultado.vida_media_em_anos[nome]
    assert vida_media is not None, nome
    return vida_media


def test_wal_pondera_o_principal_pelo_mes_em_que_entrou_em_anos():
    op = Operacao(
        classes=[Classe("unica", 1, 300 * R, 0.0)],
        saldo_do_pool=300 * R,
        reserva_minima=0,
    )
    resultados = rodar(op, [_so_principal(100 * R)] * 3)
    # (1 × 100 + 2 × 100 + 3 × 100) / 300 = 2 meses = 2/12 de ano
    assert vida_media_em_anos(resultados, "unica") == pytest.approx(2 / 12)


def test_wal_de_classe_que_nao_recebeu_principal_e_none():
    op = Operacao(
        classes=[Classe("senior", 1, 100 * R, 0.0), Classe("sub", 2, 100 * R, 0.0)],
        saldo_do_pool=200 * R,
        reserva_minima=0,
    )
    resultados = rodar(op, [_so_principal(50 * R)])
    assert vida_media_em_anos(resultados, "sub") is None
    assert vida_media_em_anos(resultados, "senior") == pytest.approx(1 / 12)


def test_wal_conta_o_turbo_como_principal():
    carteira, estrutura = carteira_sintetica()
    com_turbo = dataclasses.replace(
        estrutura, regras=Regras(meta_de_sobrecolateralizacao=0.10)
    )
    sem = rodar_cenario(carteira, estrutura, CENARIO_BASE)
    com = rodar_cenario(carteira, com_turbo, CENARIO_BASE)
    assert sum(sum(r.turbo_pago.values()) for r in com.meses) > 0
    # o turbo antecipa a sênior: a vida média dela encurta
    assert _wal(com, "senior") < _wal(sem, "senior")


def test_cenario_traz_a_wal_de_cada_classe_e_o_pre_pagamento_encurta_a_senior():
    carteira, estrutura = carteira_sintetica()
    base = rodar_cenario(carteira, estrutura, CENARIO_BASE)
    pre = rodar_cenario(carteira, estrutura, CENARIO_PRE_PAGAMENTO)
    assert set(base.vida_media_em_anos) == {c.nome for c in estrutura.classes}
    assert 0 < _wal(base, "senior") < carteira.prazo_meses / 12
    assert _wal(pre, "senior") < _wal(base, "senior")


# CDR de equilíbrio (bissecção)


def _perde(carteira, estrutura, classe, cenario, cdr) -> bool:
    resultado = rodar_cenario(
        carteira, estrutura, dataclasses.replace(cenario, cdr_anual=cdr)
    )
    return resultado.totais_por_classe[classe]["perda"] > 0


@pytest.mark.parametrize("classe", ["senior", "mezanino", "subordinada"])
def test_cdr_de_equilibrio_e_a_virada_da_perda_dentro_da_tolerancia(classe):
    carteira, estrutura = carteira_sintetica()
    cdr = cdr_de_equilibrio(carteira, estrutura, classe)
    assert cdr is not None and 0.0 <= cdr < 1.0
    assert not _perde(carteira, estrutura, classe, CENARIO_BASE, cdr)
    assert _perde(
        carteira, estrutura, classe, CENARIO_BASE, cdr + TOLERANCIA_DO_EQUILIBRIO
    )


def test_quanto_mais_senior_mais_inadimplencia_aguenta():
    carteira, estrutura = carteira_sintetica()
    cdrs = cdrs_de_equilibrio(carteira, estrutura)
    assert cdrs["senior"] > cdrs["mezanino"] > cdrs["subordinada"]


def test_classe_que_perde_ate_sem_inadimplencia_nao_tem_equilibrio():
    carteira, estrutura = carteira_sintetica()
    menor = dataclasses.replace(carteira, saldo=carteira.saldo - 100_000 * R)
    assert cdr_de_equilibrio(menor, estrutura, "subordinada") is None


def test_classe_que_nao_perde_nem_com_tudo_inadimplente_fica_em_100_por_cento():
    carteira, estrutura = carteira_sintetica()
    com_zerada = dataclasses.replace(
        estrutura, classes=(*estrutura.classes, Classe("zerada", 4, 0, 0.0))
    )
    assert cdr_de_equilibrio(carteira, com_zerada, "zerada") == 1.0


def test_classe_desconhecida_e_recusada():
    carteira, estrutura = carteira_sintetica()
    with pytest.raises(ValueError):
        cdr_de_equilibrio(carteira, estrutura, "nao-existe")


def test_cdr_de_equilibrio_usa_o_resto_do_cenario_dado():
    carteira, estrutura = carteira_sintetica()
    com_recuperacao = Cenario(
        "recuperação", 0.0, taxa_de_recuperacao=0.4, defasagem_da_recuperacao=6
    )
    sem = cdr_de_equilibrio(carteira, estrutura, "senior")
    com = cdr_de_equilibrio(carteira, estrutura, "senior", com_recuperacao)
    assert sem is not None and com is not None
    assert com > sem  # a recuperação volta como principal da sênior


@settings(max_examples=15, deadline=None)
@given(
    cpr=st.floats(min_value=0.0, max_value=0.5),
    recuperacao=st.floats(min_value=0.0, max_value=0.8),
    defasagem=st.integers(min_value=0, max_value=6),
)
def test_propriedade_a_bisseccao_sempre_separa_quem_perde_de_quem_nao_perde(
    cpr, recuperacao, defasagem
):
    carteira, estrutura = carteira_sintetica()
    cenario = Cenario("x", 0.0, cpr, recuperacao, defasagem)
    cdr = cdr_de_equilibrio(carteira, estrutura, "mezanino", cenario)
    if cdr is None:
        assert _perde(carteira, estrutura, "mezanino", cenario, 0.0)
    elif cdr < 1.0:
        assert not _perde(carteira, estrutura, "mezanino", cenario, cdr)
        assert _perde(
            carteira, estrutura, "mezanino", cenario, cdr + TOLERANCIA_DO_EQUILIBRIO
        )


# Regras da 0.2.0 ligadas


def test_regras_da_0_2_0_ligadas_ligam_as_quatro():
    regras = REGRAS_DA_0_2_0_LIGADAS
    assert regras.juros_acumulam
    assert regras.principal == PRO_RATA
    assert regras.gatilho_de_perda is not None
    assert regras.meta_de_sobrecolateralizacao is not None


def test_com_as_regras_ligadas_o_caixa_conserva_e_o_resultado_muda():
    carteira, estrutura = carteira_sintetica()
    ligadas = dataclasses.replace(estrutura, regras=REGRAS_DA_0_2_0_LIGADAS)
    antes = rodar_cenarios(carteira, estrutura)
    depois = rodar_cenarios(carteira, ligadas)
    for a, d in zip(antes, depois, strict=True):
        assert d.reconciliacao["diferenca"] == 0
        assert d.totais_por_classe != a.totais_por_classe, d.cenario.nome
    # com o dobro da inadimplência o gatilho de perda dispara e o principal volta a sequencial
    dobro = depois[1]
    assert any(m.gatilho_disparado for m in dobro.meses)
    assert not any(m.gatilho_disparado for m in depois[0].meses)


# Gabarito gravado (muda só com decisão escrita)


def test_wal_e_equilibrio_batem_com_o_gabarito():
    carteira, estrutura = carteira_sintetica()
    ligadas = dataclasses.replace(estrutura, regras=REGRAS_DA_0_2_0_LIGADAS)
    esperado = json.loads(GABARITO.read_text(encoding="utf-8"))
    obtido = {
        "vida_media_em_anos": {
            r.cenario.nome: r.vida_media_em_anos
            for r in rodar_cenarios(carteira, estrutura, CENARIOS_PADRAO)
        },
        "cdr_de_equilibrio": cdrs_de_equilibrio(carteira, estrutura),
        "cdr_de_equilibrio_com_as_regras_ligadas": cdrs_de_equilibrio(
            carteira, ligadas
        ),
    }
    assert _arredondar(obtido) == _arredondar(esperado)


def _arredondar(valor):
    """Arredonda os floats a 10 casas para comparar o gabarito sem depender do último bit."""
    if isinstance(valor, dict):
        return {k: _arredondar(v) for k, v in valor.items()}
    if isinstance(valor, float):
        return round(valor, 10)
    return valor
