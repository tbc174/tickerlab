"""Tape de recebíveis (src/securitizacao/tape.py): gerador por semente e validador.

Tudo sintético (nenhum tape real). Cada regra tem teste de caso fixo; a propriedade com Hypothesis
mostra que o tape limpo não dá achado e que cada erro plantado dá exatamente o achado dele.
"""

import json
from copy import deepcopy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_base
from src.securitizacao.tape import (
    AVISO,
    CEDENTE_INVALIDO,
    DATA_NO_FUTURO,
    DUPLICIDADE,
    ERRO,
    ESQUEMA,
    REGRAS,
    SACADO_INVALIDO,
    SALDO_NAO_FECHA,
    SALDO_NEGATIVO,
    VENCIMENTO_ANTES_DA_EMISSAO,
    achado_em_dicionario,
    gerar_tape,
    hash_do_tape,
    plantar_erros,
    validar_tape,
)


def _pares(achados):
    return [(a.regra, a.linha) for a in achados]


# --- gerador -----------------------------------------------------------------------------------


def test_mesma_semente_da_o_mesmo_tape_e_o_mesmo_hash():
    assert gerar_tape(7) == gerar_tape(7)
    assert gerar_tape(7)["hash_do_tape"] == gerar_tape(7)["hash_do_tape"]


def test_semente_diferente_da_outro_hash():
    assert gerar_tape(7)["hash_do_tape"] != gerar_tape(8)["hash_do_tape"]


def test_hash_confere_com_o_conteudo_e_muda_se_o_tape_muda():
    tape = gerar_tape(3)
    assert tape["hash_do_tape"] == hash_do_tape(tape)
    tape["recebiveis"][0]["saldo"] += 1
    assert tape["hash_do_tape"] != hash_do_tape(tape)


def test_tape_e_json_puro():
    tape = gerar_tape(1)
    assert json.loads(json.dumps(tape)) == tape


def test_gerar_tape_recusa_tape_vazio():
    with pytest.raises(ValueError):
        gerar_tape(1, n_recebiveis=0)


def test_gerador_produz_cnpj_alfanumerico_e_todos_conferem():
    tape = gerar_tape(5, n_recebiveis=200)
    cnpjs = [r[c] for r in tape["recebiveis"] for c in ("cedente_cnpj", "sacado_cnpj")]
    assert any(cnpj_base.tem_letra(c) for c in cnpjs)
    assert all(cnpj_base.dv_confere(c) for c in cnpjs)


def test_plantar_erros_nao_muda_o_tape_original():
    tape = gerar_tape(2)
    antes = deepcopy(tape)
    plantar_erros(tape, [(SALDO_NEGATIVO, 1)])
    assert tape == antes


def test_plantar_exige_linhas_diferentes_e_regra_conhecida():
    tape = gerar_tape(2)
    with pytest.raises(ValueError):
        plantar_erros(tape, [(SALDO_NEGATIVO, 1), (SALDO_NAO_FECHA, 1)])
    with pytest.raises(ValueError):
        plantar_erros(tape, [("T99", 1)])
    with pytest.raises(ValueError):
        plantar_erros(tape, [(SALDO_NEGATIVO, 999)])


# --- regra por regra ---------------------------------------------------------------------------


def test_tape_limpo_nao_da_achado():
    assert validar_tape(gerar_tape(11, n_recebiveis=100)) == []


def test_t01_campo_faltando_tipo_errado_data_ilegivel_e_valor_negativo():
    tape = gerar_tape(4, n_recebiveis=5)
    r = tape["recebiveis"]
    del r[0]["sacado_cnpj"]
    r[1]["valor_face"] = "abc"
    r[2]["emissao"] = "31/12/2026"
    r[3]["valor_pago"] = -5
    r[4]["saldo"] = 1.5
    achados = validar_tape(tape)
    assert [(a.regra, a.linha, a.campo) for a in achados] == [
        (ESQUEMA, 1, "sacado_cnpj"),
        (ESQUEMA, 2, "valor_face"),
        (ESQUEMA, 3, "emissao"),
        (ESQUEMA, 4, "valor_pago"),
        (ESQUEMA, 5, "saldo"),
    ]
    assert {a.gravidade for a in achados} == {ERRO}


def test_t01_booleano_nao_vale_como_inteiro():
    tape = gerar_tape(4, n_recebiveis=1)
    tape["recebiveis"][0]["saldo"] = True
    assert _pares(validar_tape(tape)) == [(ESQUEMA, 1)]


def test_t01_tape_sem_lista_ou_sem_data_de_corte_ou_nao_objeto():
    assert _pares(validar_tape([])) == [(ESQUEMA, 0)]
    assert _pares(validar_tape({"recebiveis": []})) == [(ESQUEMA, 0)]
    assert _pares(validar_tape({"data_de_corte": "2026-09-30", "recebiveis": 3})) == [
        (ESQUEMA, 0)
    ]
    tape = gerar_tape(4, n_recebiveis=2)
    tape["recebiveis"][1] = "texto"
    assert _pares(validar_tape(tape)) == [(ESQUEMA, 2)]


def test_linha_com_esquema_ruim_nao_passa_pelas_outras_regras():
    tape = gerar_tape(4, n_recebiveis=2)
    tape["recebiveis"][0]["vencimento"] = "ontem"
    tape["recebiveis"][0]["saldo"] = -1
    assert _pares(validar_tape(tape)) == [(ESQUEMA, 1)]


def test_t02_duplicidade_fica_na_repeticao_e_nao_na_primeira():
    tape = gerar_tape(6, n_recebiveis=4)
    tape["recebiveis"].append(deepcopy(tape["recebiveis"][1]))
    tape["recebiveis"].append(deepcopy(tape["recebiveis"][1]))
    assert _pares(validar_tape(tape)) == [(DUPLICIDADE, 5), (DUPLICIDADE, 6)]


def test_t03_vencimento_antes_da_emissao():
    tape = gerar_tape(6, n_recebiveis=3)
    r = tape["recebiveis"][1]
    r["vencimento"] = "2000-01-01"
    r["emissao"] = "2000-01-02"
    achados = validar_tape(tape)
    assert _pares(achados) == [(VENCIMENTO_ANTES_DA_EMISSAO, 2)]
    assert (
        achados[0].valor == "2000-01-01" and achados[0].valor_esperado == "2000-01-02"
    )


def test_t03_vencimento_igual_a_emissao_e_aceito():
    tape = gerar_tape(6, n_recebiveis=1)
    r = tape["recebiveis"][0]
    r["vencimento"] = r["emissao"]
    assert validar_tape(tape) == []


def test_t04_emissao_depois_do_corte_mas_vencimento_futuro_e_normal():
    tape = gerar_tape(6, n_recebiveis=2)
    tape["recebiveis"][0]["emissao"] = "2026-09-30"  # no dia do corte: aceito
    tape["recebiveis"][0]["vencimento"] = "2027-12-31"  # vencimento futuro: aceito
    tape["recebiveis"][1]["emissao"] = "2026-10-01"
    tape["recebiveis"][1]["vencimento"] = "2026-11-01"
    assert _pares(validar_tape(tape)) == [(DATA_NO_FUTURO, 2)]


def test_t05_saldo_negativo_e_so_ele():
    tape = gerar_tape(8, n_recebiveis=2)
    r = tape["recebiveis"][0]
    r["valor_pago"] = r["valor_face"] + 10
    r["saldo"] = -10
    achados = validar_tape(tape)
    assert _pares(achados) == [(SALDO_NEGATIVO, 1)]
    assert achados[0].valor == -10 and achados[0].valor_esperado == 0


def test_t06_saldo_que_nao_fecha_mostra_o_esperado():
    tape = gerar_tape(8, n_recebiveis=2)
    r = tape["recebiveis"][1]
    esperado = r["valor_face"] - r["valor_pago"]
    r["saldo"] = esperado + 100
    achados = validar_tape(tape)
    assert _pares(achados) == [(SALDO_NAO_FECHA, 2)]
    assert achados[0].valor_esperado == esperado


@pytest.mark.parametrize(
    ("campo", "regra", "gravidade"),
    [("cedente_cnpj", CEDENTE_INVALIDO, ERRO), ("sacado_cnpj", SACADO_INVALIDO, AVISO)],
)
def test_t07_t08_cnpj_com_dv_errado_tamanho_errado_ou_pontuado_valido(
    campo, regra, gravidade
):
    tape = gerar_tape(9, n_recebiveis=3)
    r = tape["recebiveis"]
    r[0][campo] = r[0][campo][:-1] + ("0" if r[0][campo][-1] != "0" else "1")
    r[1][campo] = "123"
    r[2][campo] = cnpj_base.formatar(r[2][campo])  # com pontuação continua válido
    achados = validar_tape(tape)
    assert _pares(achados) == [(regra, 1), (regra, 2)]
    assert {a.gravidade for a in achados} == {gravidade}


def test_cnpj_alfanumerico_valido_passa_e_com_letra_e_dv_errado_falha():
    tape = gerar_tape(9, n_recebiveis=2)
    raiz = "12ABC34501DE"
    bom = raiz + cnpj_base.digitos_verificadores(raiz)
    tape["recebiveis"][0]["cedente_cnpj"] = bom
    tape["recebiveis"][1]["cedente_cnpj"] = (
        raiz + "00" if bom[-2:] != "00" else raiz + "11"
    )
    assert _pares(validar_tape(tape)) == [(CEDENTE_INVALIDO, 2)]


def test_achados_vem_ordenados_por_linha_e_regra_e_viram_json():
    tape = gerar_tape(10, n_recebiveis=3)
    r = tape["recebiveis"]
    r[2]["saldo"] = r[2]["saldo"] + 1
    r[2]["cedente_cnpj"] = "1"
    r[0]["saldo"] = -1
    achados = validar_tape(tape)
    assert _pares(achados) == [
        (SALDO_NEGATIVO, 1),
        (SALDO_NAO_FECHA, 3),
        (CEDENTE_INVALIDO, 3),
    ]
    assert [a.linha for a in achados] == sorted(a.linha for a in achados)
    json.dumps([achado_em_dicionario(a) for a in achados])


def test_validador_nao_altera_o_tape():
    tape = gerar_tape(10, n_recebiveis=5)
    tape["recebiveis"][0]["saldo"] = -1
    antes = deepcopy(tape)
    validar_tape(tape)
    assert tape == antes


# --- propriedades ------------------------------------------------------------------------------


@given(semente=st.integers(0, 10**9), n=st.integers(1, 80))
@settings(max_examples=60, deadline=None)
def test_tape_limpo_de_qualquer_semente_nao_da_achado(semente, n):
    assert validar_tape(gerar_tape(semente, n_recebiveis=n)) == []


@st.composite
def _tape_com_erros(draw):
    semente = draw(st.integers(0, 10**9))
    n = draw(st.integers(len(REGRAS), 60))
    regras = draw(st.lists(st.sampled_from(REGRAS), unique=True, min_size=1))
    linhas = draw(
        st.lists(
            st.integers(1, n), unique=True, min_size=len(regras), max_size=len(regras)
        )
    )
    return semente, n, list(zip(regras, linhas, strict=True))


@given(_tape_com_erros())
@settings(max_examples=150, deadline=None)
def test_cada_erro_plantado_da_exatamente_o_achado_dele(caso):
    semente, n, plantas = caso
    limpo = gerar_tape(semente, n_recebiveis=n)
    sujo = plantar_erros(limpo, plantas)
    # a linha do achado de duplicidade é a da cópia, no fim do tape
    esperado = sorted(
        (regra, n + 1 if regra == DUPLICIDADE else linha) for regra, linha in plantas
    )
    assert sorted(_pares(validar_tape(sujo))) == esperado
