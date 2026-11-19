"""`telas.carteira_b3._setores`: o setor é enfeite do raio-x; falha do banco nunca derruba a tela."""

import logging
from contextlib import contextmanager

import pandas as pd
import pytest

from telas import carteira_b3


class _Carteira:
    posicoes = pd.DataFrame({"ticker": ["PETR4", "VALE3"]})


class _Motor:
    def connect(self):
        @contextmanager
        def conexao():
            yield "conexao"

        return conexao()


@pytest.fixture
def motor(monkeypatch):
    monkeypatch.setattr(carteira_b3, "obter_engine", lambda: _Motor())


def test_devolve_os_setores_dos_tickers_da_carteira(motor, monkeypatch):
    chamadas = []

    def setores(conexao, tickers):
        chamadas.append((conexao, tickers))
        return {"PETR4": "Petróleo"}

    monkeypatch.setattr(carteira_b3, "setores_dos_tickers", setores)

    assert carteira_b3._setores(_Carteira()) == {"PETR4": "Petróleo"}
    assert chamadas == [("conexao", ["PETR4", "VALE3"])]


def test_tabela_inexistente_devolve_vazio_sem_registrar_erro(
    motor, monkeypatch, caplog
):
    def setores(conexao, tickers):
        raise RuntimeError("no such table: empresas")

    monkeypatch.setattr(carteira_b3, "setores_dos_tickers", setores)

    with caplog.at_level(logging.ERROR):
        assert carteira_b3._setores(_Carteira()) == {}
    assert caplog.records == []


def test_outra_falha_devolve_vazio_e_registra_o_erro(motor, monkeypatch, caplog):
    def setores(conexao, tickers):
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(carteira_b3, "setores_dos_tickers", setores)

    with caplog.at_level(logging.ERROR):
        assert carteira_b3._setores(_Carteira()) == {}
    assert any("setores da CVM" in r.getMessage() for r in caplog.records)
