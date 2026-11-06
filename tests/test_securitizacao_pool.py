"""Pool, concentração e vintages (src/securitizacao/pool.py).

O gabarito de 3 safras foi feito à mão (contas nos comentários); a data de entrada em inadimplência é
vencimento + 90 dias. Tudo sintético.
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_base
from src.securitizacao.pool import (
    ATRASO_DIAS,
    TAMANHOS_DO_TOPO,
    montar_pool,
)
from src.securitizacao.tape import (
    CEDENTE_INVALIDO,
    DUPLICIDADE,
    SACADO_INVALIDO,
    com_hash,
    gerar_tape,
    plantar_erros,
)


def _cnpj(base12: str) -> str:
    return base12 + cnpj_base.digitos_verificadores(base12)


CEDENTE_X, CEDENTE_Y = _cnpj("111111111112"), _cnpj("222222222223")
SACADO_A, SACADO_B, SACADO_C, SACADO_D, SACADO_E = (
    _cnpj(f"{n}0000000000{n}") for n in (3, 4, 5, 6, 7)
)


def _r(id_, cedente, sacado, emissao, vencimento, face, pago):
    return {
        "recebivel_id": id_,
        "cedente_cnpj": cedente,
        "sacado_cnpj": sacado,
        "emissao": emissao,
        "vencimento": vencimento,
        "valor_face": face,
        "valor_pago": pago,
        "saldo": face - pago,
    }


def _tape_do_gabarito():
    return com_hash(
        {
            "data_de_corte": "2026-12-31",
            "recebiveis": [
                # safra 2026-01, face 100000
                _r("R1", CEDENTE_X, SACADO_A, "2026-01-05", "2026-02-05", 40000, 0),
                _r("R2", CEDENTE_X, SACADO_D, "2026-01-10", "2026-03-10", 60000, 60000),
                # safra 2026-02, face 100000
                _r("R3", CEDENTE_X, SACADO_A, "2026-02-01", "2026-03-01", 50000, 10000),
                _r("R4", CEDENTE_Y, SACADO_C, "2026-02-15", "2026-04-15", 50000, 0),
                # safra 2026-03, face 200000
                _r("R5", CEDENTE_Y, SACADO_B, "2026-03-01", "2026-12-01", 100000, 0),
                _r(
                    "R6",
                    CEDENTE_Y,
                    SACADO_E,
                    "2026-03-03",
                    "2026-03-20",
                    100000,
                    100000,
                ),
            ],
        }
    )


def _vintages_por_safra(pool):
    return {v.safra: v for v in pool.vintages}


# --- gabarito à mão ----------------------------------------------------------------------------


def test_vintage_de_janeiro_confere_com_a_conta_a_mao():
    # R1 vence 05/02; +90 dias = 06/05 (maio). Saldo 40000 / face 100000 = 0,4 de maio em diante.
    # R2 foi paga: nunca entra. Janeiro a dezembro = 12 meses.
    v = _vintages_por_safra(montar_pool(_tape_do_gabarito()))["2026-01"]
    assert v.face == 100000
    assert v.meses[0] == "2026-01" and v.meses[-1] == "2026-12" and len(v.meses) == 12
    assert v.inadimplencia_acumulada == (0, 0, 0, 0) + (0.4,) * 8


def test_vintage_de_fevereiro_confere_com_a_conta_a_mao():
    # R3 vence 01/03; +90 = 30/05 (maio): saldo 40000 / 100000 = 0,4 em maio.
    # R4 vence 15/04; +90 = 14/07 (julho): +50000 -> 0,9 de julho em diante. Fevereiro a dezembro = 11 meses.
    v = _vintages_por_safra(montar_pool(_tape_do_gabarito()))["2026-02"]
    assert v.face == 100000
    assert v.inadimplencia_acumulada == (0, 0, 0, 0.4, 0.4) + (0.9,) * 6


def test_vintage_de_marco_nao_conta_o_que_ainda_nao_passou_de_90_dias():
    # R5 vence 01/12; +90 dias cai depois do corte (31/12): fica de fora. R6 foi paga. Tudo zero.
    v = _vintages_por_safra(montar_pool(_tape_do_gabarito()))["2026-03"]
    assert v.face == 200000
    assert v.inadimplencia_acumulada == (0.0,) * 10


def test_concentracao_confere_com_a_conta_a_mao():
    # Saldo em aberto: R1 40000 (A), R3 40000 (A), R4 50000 (C), R5 100000 (B); total 230000.
    # Sacados: B 100000, A 80000, C 50000. Cedentes: Y 150000, X 80000.
    pool = montar_pool(_tape_do_gabarito())
    c = {k: n.valor for k, n in pool.concentracao.items()}
    assert pool.saldo == 230000 and pool.n_recebiveis == 6
    assert c["sacado_top1"] == pytest.approx(100000 / 230000)
    assert c["sacado_top5"] == 1.0 and c["sacado_top10"] == 1.0
    assert c["cedente_top1"] == pytest.approx(150000 / 230000)
    assert c["cedente_top5"] == 1.0 and c["cedente_top10"] == 1.0


def test_cnpj_igual_com_caixa_diferente_conta_como_uma_contraparte_so():
    tape = _tape_do_gabarito()
    tape["recebiveis"][0]["sacado_cnpj"] = SACADO_A.lower()
    pool = montar_pool(com_hash(tape))
    esperado = montar_pool(_tape_do_gabarito()).concentracao
    assert {k: n.valor for k, n in pool.concentracao.items()} == {
        k: n.valor for k, n in esperado.items()
    }


# --- validação sem consertar em silêncio ------------------------------------------------------


def test_linha_com_erro_fica_de_fora_e_aparece_na_validacao():
    tape = plantar_erros(gerar_tape(1, 20), [(CEDENTE_INVALIDO, 3), (DUPLICIDADE, 5)])
    pool = montar_pool(tape)
    assert pool.linhas_excluidas == (3, 21)
    assert pool.n_recebiveis == len(tape["recebiveis"]) - 2
    assert {(a["regra"], a["linha"]) for a in pool.validacao} == {
        (CEDENTE_INVALIDO, 3),
        (DUPLICIDADE, 21),
    }


def test_linha_so_com_aviso_entra_no_pool():
    tape = plantar_erros(gerar_tape(2, 20), [(SACADO_INVALIDO, 4)])
    pool = montar_pool(tape)
    assert pool.linhas_excluidas == ()
    assert pool.n_recebiveis == 20
    assert [a["regra"] for a in pool.validacao] == [SACADO_INVALIDO]


def test_tape_sem_estrutura_nao_vira_pool():
    with pytest.raises(ValueError, match="sem estrutura"):
        montar_pool({"recebiveis": []})


def test_tape_sem_nenhum_recebivel_aceito_da_pool_vazio():
    tape = com_hash({"data_de_corte": "2026-09-30", "recebiveis": []})
    pool = montar_pool(tape)
    assert pool.saldo == 0 and pool.vintages == ()
    assert all(n.valor == 0.0 for n in pool.concentracao.values())


# --- rastro e JSON ----------------------------------------------------------------------------


def test_todo_numero_tem_rastro_completo():
    pool = montar_pool(_tape_do_gabarito())
    rastros = [n.rastro for n in pool.concentracao.values()]
    rastros += [v.rastro for v in pool.vintages] + [pool.rastro]
    assert len(rastros) == 6 + 3 + 1
    assert all(r.o_que_falta() == [] for r in rastros)
    assert all(pool.hash_do_tape[:16] in r.documentos[0].nome for r in rastros)


def test_pool_vira_json_e_leva_o_hash_do_tape():
    tape = _tape_do_gabarito()
    como_dict = montar_pool(tape).como_dict()
    texto = json.dumps(como_dict)
    assert json.loads(texto)["hash_do_tape"] == tape["hash_do_tape"]
    assert como_dict["data_de_corte"] == "2026-12-31"
    assert como_dict["concentracao"]["sacado_top1"]["rastro"]["versao_do_calculo"]


# --- propriedades -----------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(st.integers(0, 10_000), st.integers(1, 80))
def test_concentracao_fica_entre_0_e_1_e_cresce_do_top1_ao_top10(semente, n):
    c = {
        k: v.valor for k, v in montar_pool(gerar_tape(semente, n)).concentracao.items()
    }
    for sujeito in ("sacado", "cedente"):
        valores = [c[f"{sujeito}_top{t}"] for t in TAMANHOS_DO_TOPO]
        assert all(0.0 <= v <= 1.0 for v in valores)
        assert valores == sorted(valores)


@settings(max_examples=60, deadline=None)
@given(st.integers(0, 10_000), st.integers(1, 80))
def test_inadimplencia_acumulada_nunca_cai_e_fica_entre_0_e_1(semente, n):
    for v in montar_pool(gerar_tape(semente, n)).vintages:
        serie = v.inadimplencia_acumulada
        assert len(serie) == len(v.meses)
        assert all(0.0 <= x <= 1.0 for x in serie)
        assert list(serie) == sorted(serie)


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 10_000), st.integers(1, 60))
def test_mesma_semente_mesmo_pool(semente, n):
    assert montar_pool(gerar_tape(semente, n)) == montar_pool(gerar_tape(semente, n))


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 10_000), st.integers(1, 60))
def test_o_saldo_do_pool_e_a_soma_dos_saldos_do_tape_limpo(semente, n):
    tape = gerar_tape(semente, n)
    assert montar_pool(tape).saldo == sum(r["saldo"] for r in tape["recebiveis"])


def test_o_atraso_e_de_90_dias():
    assert ATRASO_DIAS == 90
