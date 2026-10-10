"""Testes de capturar e restaurar as escolhas da tela."""

import pytest

from src.simulacoes import capturar_estado, restaurar_estado

TELA = {
    "ticker": "PETR4.SA",
    "periodo": "2y",
    "taxa": "Zero",
    "em_reais": True,
    "usar_exemplo": False,
    "favoritos": [
        "AAPL"
    ],  # lista: fica de fora (vai para a conta, não para a simulação)
    "backtest_estrategia": "MACD",
    "parametro_MACD_rapida": 12,
    "custo_taxas": 0.03,
    "carteira_ativos": "A, B",
    "pares_custo": 0.05,
    "exp_total": 5,
}


def test_captura_so_o_topo_e_os_campos_do_tipo():
    retrato = capturar_estado(TELA, "backtest")
    assert set(retrato) == {
        "ticker",
        "periodo",
        "taxa",
        "em_reais",
        "usar_exemplo",
        "backtest_estrategia",
        "parametro_MACD_rapida",
        "custo_taxas",
    }
    assert set(capturar_estado(TELA, "carteira")) - {
        "ticker",
        "periodo",
        "taxa",
        "em_reais",
        "usar_exemplo",
    } == {"carteira_ativos"}


def test_captura_ignora_valores_que_nao_sao_simples():
    estado = {"backtest_a": float("nan"), "backtest_b": [1], "backtest_c": "x" * 301}
    assert capturar_estado(estado, "backtest") == {}


def test_captura_nao_leva_campos_que_dependem_dos_dados():
    estado = {"pares_escolhido": "A × B", "pares_custo": 0.05}
    assert capturar_estado(estado, "pares") == {"pares_custo": 0.05}


def test_tipo_desconhecido():
    with pytest.raises(ValueError):
        capturar_estado(TELA, "outro")
    with pytest.raises(ValueError):
        restaurar_estado({}, "outro")


def test_ida_e_volta():
    retrato = capturar_estado(TELA, "backtest")
    assert restaurar_estado(retrato, "backtest") == retrato


def test_restaurar_ignora_chaves_de_outros_tipos_e_desconhecidas():
    retrato = {
        "carteira_ativos": "A, B",
        "pares_custo": 0.1,
        "backtest_estrategia": "MACD",
        "__class__": "x",
        "ticker": "PETR4.SA",
    }
    assert restaurar_estado(retrato, "backtest") == {
        "backtest_estrategia": "MACD",
        "ticker": "PETR4.SA",
    }


@pytest.mark.parametrize(
    "ruim", [{"ticker": "<script>"}, {"periodo": "10y"}, {"taxa": "Outra"}]
)
def test_topo_invalido_e_ignorado(ruim):
    assert restaurar_estado(ruim, "backtest") == {}


def test_caixas_do_topo_so_aceitam_verdadeiro_ou_falso():
    assert restaurar_estado({"em_reais": "sim"}, "backtest") == {"em_reais": False}
    assert restaurar_estado({"usar_exemplo": True}, "backtest") == {
        "usar_exemplo": True
    }


def test_valores_nao_simples_nao_voltam():
    retrato = {"backtest_a": [1, 2], "backtest_b": {"x": 1}, "backtest_c": 3}
    assert restaurar_estado(retrato, "backtest") == {"backtest_c": 3}


def test_validador_do_app_recusa_o_que_a_tela_nao_aceita_mais():
    retrato = {"backtest_estrategia": "Extinta", "backtest_capital": 5000.0}
    validos = restaurar_estado(
        retrato, "backtest", lambda chave, valor: valor != "Extinta"
    )
    assert validos == {"backtest_capital": 5000.0}


def test_retrato_que_nao_e_dicionario():
    assert restaurar_estado("lixo", "backtest") == {}  # type: ignore[arg-type]


def test_limite_de_campos():
    retrato = {f"backtest_{i}": i for i in range(500)}
    assert len(restaurar_estado(retrato, "backtest")) == 80
