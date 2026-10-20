"""Cenários da cascata (src/securitizacao/cenarios.py): conversões, ordem dos cenários, caixa e gabarito.

Toda carteira aqui é sintética (nenhuma operação real).
"""

import dataclasses
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.securitizacao.cenarios import (
    CENARIO_ATRASO_E_RECUPERACAO,
    CENARIO_BASE,
    CENARIOS_PADRAO,
    Cenario,
    CENARIO_INADIMPLENCIA_x2,
    carteira_sintetica,
    cdr_para_mdr,
    cpr_para_smm,
    hash_da_entrada,
    projetar_fluxos,
    rodar_cenario,
    rodar_cenarios,
)

GABARITO = Path(__file__).parent / "gabaritos" / "securitizacao_cenarios.json"


def test_cdr_de_12_por_cento_ao_ano_vira_mdr_de_1_0596_por_cento_ao_mes():
    assert cdr_para_mdr(0.12) == pytest.approx(0.010597, abs=1e-6)


def test_cpr_usa_a_mesma_forma_de_sobrevivencia():
    assert cpr_para_smm(0.12) == cdr_para_mdr(0.12)
    assert cpr_para_smm(0.0) == 0.0


def test_mensal_composto_devolve_o_anual():
    assert 1 - (1 - cdr_para_mdr(0.30)) ** 12 == pytest.approx(0.30)


@pytest.mark.parametrize("taxa", [-0.01, 1.01])
def test_taxa_anual_fora_de_0_a_1_e_recusada(taxa):
    with pytest.raises(ValueError):
        cdr_para_mdr(taxa)
    with pytest.raises(ValueError):
        cpr_para_smm(taxa)


def test_cenario_invalido_e_recusado():
    with pytest.raises(ValueError):
        Cenario("x", 0.1, taxa_de_recuperacao=1.5)
    with pytest.raises(ValueError):
        Cenario("x", 0.1, defasagem_da_recuperacao=-1)


def test_recuperacao_volta_ao_caixa_depois_da_defasagem():
    carteira, estrutura = carteira_sintetica()
    cenario = Cenario("c", 0.12, taxa_de_recuperacao=0.5, defasagem_da_recuperacao=3)
    periodos = projetar_fluxos(carteira, estrutura, cenario)
    assert len(periodos) == carteira.prazo_meses + 3
    assert all(p.recuperacoes == 0 for p in periodos[:3])
    assert periodos[3].recuperacoes == int(periodos[0].perda * 0.5)


def test_cenarios_padrao_tem_os_quatro_pedidos():
    nomes = [c.nome for c in CENARIOS_PADRAO]
    assert nomes == [
        "base",
        "inadimplência ×2",
        "atraso e recuperação",
        "pré-pagamento",
    ]
    assert CENARIO_INADIMPLENCIA_x2.cdr_anual == 2 * CENARIO_BASE.cdr_anual


def test_pior_cenario_paga_menos_a_subordinada_que_o_base():
    carteira, estrutura = carteira_sintetica()
    base, dobro, atraso, _ = rodar_cenarios(carteira, estrutura)
    assert dobro.pago_a_subordinada < base.pago_a_subordinada
    assert atraso.pago_a_subordinada < base.pago_a_subordinada
    # a recuperação volta como principal da classe de cima: reduz a perda dos investidores, e não
    # devolve ao residual da subordinada o que a inadimplência tirou
    assert atraso.perda_total < dobro.perda_total


def test_caixa_conserva_ao_centavo_em_todo_cenario():
    carteira, estrutura = carteira_sintetica()
    for resultado in rodar_cenarios(carteira, estrutura):
        assert resultado.reconciliacao["diferenca"] == 0


def test_mesma_entrada_mesmo_resultado():
    carteira, estrutura = carteira_sintetica()
    a = rodar_cenarios(carteira, estrutura)
    b = rodar_cenarios(carteira, estrutura)
    assert [dataclasses.asdict(x) for x in a] == [dataclasses.asdict(x) for x in b]


def test_hash_da_entrada_e_estavel_e_muda_com_a_carteira():
    carteira, estrutura = carteira_sintetica()
    assert hash_da_entrada(carteira, estrutura) == hash_da_entrada(carteira, estrutura)
    assert len(hash_da_entrada(carteira, estrutura)) == 64
    outra = dataclasses.replace(carteira, saldo=carteira.saldo - 1)
    assert hash_da_entrada(outra, estrutura) != hash_da_entrada(carteira, estrutura)


def _resumo(resultado) -> dict:
    return {
        "totais_por_classe": resultado.totais_por_classe,
        "residual": resultado.residual,
        "pago_a_subordinada": resultado.pago_a_subordinada,
        "perda_total": resultado.perda_total,
        "reconciliacao": resultado.reconciliacao,
    }


def test_tres_cenarios_fixos_batem_com_o_gabarito():
    carteira, estrutura = carteira_sintetica()
    esperado = json.loads(GABARITO.read_text(encoding="utf-8"))
    for cenario in (
        CENARIO_BASE,
        CENARIO_INADIMPLENCIA_x2,
        CENARIO_ATRASO_E_RECUPERACAO,
    ):
        obtido = _resumo(rodar_cenario(carteira, estrutura, cenario))
        assert obtido == esperado[cenario.nome], cenario.nome


@settings(max_examples=60, deadline=None)
@given(
    cdr=st.floats(min_value=0.0, max_value=0.9),
    acrescimo=st.floats(min_value=0.01, max_value=0.1),
    cpr=st.floats(min_value=0.0, max_value=0.9),
    defasagem=st.integers(min_value=0, max_value=12),
)
def test_propriedade_mais_inadimplencia_nunca_paga_mais_a_subordinada(
    cdr, acrescimo, cpr, defasagem
):
    carteira, estrutura = carteira_sintetica()
    comum = {
        "cpr_anual": cpr,
        "taxa_de_recuperacao": 0.0,  # com recuperação a ordem não vale: ela paga a classe de cima
        "defasagem_da_recuperacao": defasagem,
    }
    melhor = rodar_cenario(carteira, estrutura, Cenario("a", cdr, **comum))
    pior = rodar_cenario(
        carteira, estrutura, Cenario("b", min(1.0, cdr + acrescimo), **comum)
    )
    assert pior.pago_a_subordinada <= melhor.pago_a_subordinada
    assert melhor.reconciliacao["diferenca"] == 0 == pior.reconciliacao["diferenca"]


@settings(max_examples=60, deadline=None)
@given(
    cdr=st.floats(min_value=0.0, max_value=1.0),
    cpr=st.floats(min_value=0.0, max_value=1.0),
    recuperacao=st.floats(min_value=0.0, max_value=1.0),
    defasagem=st.integers(min_value=0, max_value=12),
)
def test_propriedade_caixa_conserva_em_qualquer_cenario(
    cdr, cpr, recuperacao, defasagem
):
    carteira, estrutura = carteira_sintetica()
    cenario = Cenario("x", cdr, cpr, recuperacao, defasagem)
    assert rodar_cenario(carteira, estrutura, cenario).reconciliacao["diferenca"] == 0
