"""A seção Carteira (Estratégias): os avisos de lista errada, de ativo sem dados e de poucos dias em
comum, sem internet.

`carregar_dados` é trocado onde a tela o usa: um ticker específico falta, os outros vêm sintéticos.
"""

import pytest
from streamlit.testing.v1 import AppTest


def _secao() -> None:
    from telas.estrategias.carteira import secao_carteira

    secao_carteira("5y", 0.0, None)


@pytest.fixture(autouse=True)
def _dados_sinteticos(monkeypatch):
    import numpy as np
    import pandas as pd

    from src.dados import DadosIndisponiveisError

    def _carregar(ticker, *_args, **_kwargs):
        if ticker == "SEMDADOS":
            raise DadosIndisponiveisError(ticker)
        dias = 30 if ticker == "CURTO" else 300
        indice = pd.bdate_range("2022-01-03", periods=dias)
        fechamento = pd.Series(
            100.0 * np.cumprod(1 + 0.0003 + 0.01 * np.sin(np.arange(dias))),
            index=indice,
        )
        return pd.DataFrame({"Close": fechamento})

    monkeypatch.setattr("telas.estrategias.carteira.carregar_dados", _carregar)


def _com_lista(texto: str) -> AppTest:
    app = AppTest.from_function(_secao).run()
    app.text_input(key="carteira_ativos").set_value(texto).run()
    return app


def _textos(elementos) -> str:
    return " ".join(e.value for e in elementos)


def test_um_ativo_so_pede_mais_e_nao_simula():
    app = _com_lista("PETR4.SA")
    assert not app.exception
    assert "Escolha de 2 a 8 ativos (agora são 1)." in _textos(app.info)
    assert not app.metric


def test_ativos_demais_pedem_o_limite():
    app = _com_lista("A1,A2,A3,A4,A5,A6,A7,A8,A9")
    assert not app.exception
    assert "Escolha de 2 a 8 ativos (agora são 9)." in _textos(app.info)
    assert not app.metric


def test_ativo_sem_dados_fica_de_fora_com_aviso():
    app = _com_lista("AAA,BBB,SEMDADOS")
    assert not app.exception
    assert "Não encontrei dados para: SEMDADOS" in _textos(app.warning)
    assert len(app.metric) == 4  # os outros dois seguiram e simularam


def test_so_um_ativo_com_dados_nao_simula():
    app = _com_lista("AAA,SEMDADOS")
    assert not app.exception
    assert "Não há ativos suficientes com dados." in _textos(app.info)
    assert not app.metric


def test_poucos_dias_em_comum_pedem_periodo_maior():
    app = _com_lista("AAA,CURTO")
    assert not app.exception
    assert "Só há 30 dias em comum" in _textos(app.warning)
    assert not app.metric
