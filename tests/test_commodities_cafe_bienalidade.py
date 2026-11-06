"""Bienalidade do arábica: ano cheio ou vazio e a surpresa de ciclo (em tela e API com a data citada)."""

from datetime import date

import pytest

from src.commodities.cafe.bienalidade import ciclo_quebrado, marcar
from tests.ajudantes_do_cafe import tabela

# 2019 vazio, 2020 cheio, 2021 vazio, 2022 cheio, 2023 CHEIO de novo (ciclo quebrado)
PRODUCOES = {
    2018: {4: 60.0},
    2019: {4: 50.0},
    2020: {4: 60.0},
    2021: {4: 45.0},
    2022: {4: 55.0},
    2023: {4: 58.0},
}


def _rotulos(pontos):
    return {p.safra: p.rotulo for p in pontos}


def test_cheio_e_vazio_por_comparacao_com_a_safra_anterior():
    rotulos = _rotulos(marcar(tabela(PRODUCOES), "arabica"))
    assert rotulos == {
        2019: "vazio",
        2020: "cheio",
        2021: "vazio",
        2022: "cheio",
        2023: "cheio",
    }


def test_a_primeira_safra_nao_tem_marca():
    assert 2018 not in _rotulos(marcar(tabela(PRODUCOES), "arabica"))


def test_ciclo_quebrado_quando_duas_altas_seguidas():
    pontos = {p.safra: p.valor for p in ciclo_quebrado(tabela(PRODUCOES), "arabica")}
    assert pontos[2023] == 1.0
    assert pontos[2022] == 0.0 and pontos[2021] == 0.0


def test_ciclo_quebrado_nao_marca_a_primeira_marca():
    safras = {p.safra for p in ciclo_quebrado(tabela(PRODUCOES), "arabica")}
    assert 2019 not in safras  # precisa de duas variações para comparar


def test_usa_o_levantamento_mais_novo_ate_o_corte():
    t = tabela({2019: {1: 52.0, 4: 50.0}, 2020: {1: 49.0, 3: 53.0}})
    # em 30/06/2020 só havia o 1º e o 2º; a 2020 está abaixo da 2019 (49 < 52): vazio
    assert _rotulos(marcar(t, "arabica", ate=date(2020, 6, 30))) == {2020: "vazio"}
    # depois do 3º levantamento a 2020 passa a 53 > 50: cheio
    assert _rotulos(marcar(t, "arabica", ate=date(2020, 12, 31))) == {2020: "cheio"}


def test_corte_em_d_nao_muda_o_passado():
    inteira = tabela(PRODUCOES)
    antes = _rotulos(marcar(inteira, "arabica", ate=date(2021, 12, 31)))
    depois = _rotulos(marcar(inteira, "arabica", ate=date(2023, 12, 31)))
    assert all(depois[s] == r for s, r in antes.items())


def test_a_marca_cita_o_dia_do_levantamento_que_usou():
    # ADR 0102: fonte e data citadas; aqui a data é a do levantamento mais novo até o corte
    t = tabela({2019: {1: 52.0, 4: 50.0}, 2020: {1: 49.0, 3: 53.0}})
    [pelo_primeiro] = marcar(t, "arabica", ate=date(2020, 6, 30))
    assert pelo_primeiro.divulgado_em == t["divulgado_em"].iloc[2].date().isoformat()
    [pelo_terceiro] = marcar(t, "arabica", ate=date(2020, 12, 31))
    assert pelo_terceiro.divulgado_em == t["divulgado_em"].iloc[3].date().isoformat()
    quebras = {
        p.safra: p.divulgado_em for p in ciclo_quebrado(tabela(PRODUCOES), "arabica")
    }
    assert quebras[2023] == "2023-12-04"


def test_so_o_arabica_tem_bienalidade():
    with pytest.raises(ValueError, match="arabica"):
        marcar(tabela(PRODUCOES, tipo="conilon"), "conilon")
