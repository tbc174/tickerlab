"""Testes de src/tentativas.py: a impressão de uma configuração do backtest (ADR 0037, D2)."""

from src.protecoes import Protecoes
from src.tentativas import impressao

BASE = {
    "ticker": "PETR4.SA",
    "estrategia": "Cruzamento de médias",
    "parametros": {"curta": 20, "longa": 50, "tipo": "Simples"},
    "protecoes": None,
    "custo_por_operacao": 0.0005,
    "periodo": "5y",
}


def _com(**mudancas):
    return impressao(**{**BASE, **mudancas})


def test_mesma_configuracao_mesma_impressao():
    assert _com() == _com()
    assert len(_com()) == 64  # SHA-256 em hexadecimal


def test_ordem_dos_parametros_nao_importa():
    assert _com(parametros={"tipo": "Simples", "longa": 50, "curta": 20}) == _com()


def test_protecoes_desligadas_valem_como_sem_protecoes():
    assert _com(protecoes=Protecoes()) == _com()


def test_cada_mudanca_que_muda_o_resultado_muda_a_impressao():
    base = _com()
    assert _com(parametros={"curta": 21, "longa": 50, "tipo": "Simples"}) != base
    assert _com(estrategia="Filtro de tendência") != base
    assert _com(protecoes=Protecoes(stop_loss=0.08)) != base
    assert _com(custo_por_operacao=0.001) != base
    assert _com(periodo="10y") != base
    assert _com(ticker="VALE3.SA") != base


def test_ticker_sem_diferenca_de_caixa():
    assert _com(ticker="petr4.sa") == _com()
