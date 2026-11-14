"""A seção de pares (Avançado): os avisos de lista errada e de ativo sem dados, sem internet.

`carregar_dados` é trocado onde a tela o usa: um ticker específico falta, os outros vêm sintéticos.
"""

import pytest
from streamlit.testing.v1 import AppTest


def _secao() -> None:
    from telas.estrategias.pares import secao_pares

    secao_pares("5y", 0.0)


@pytest.fixture(autouse=True)
def _dados_sinteticos(monkeypatch):
    import numpy as np
    import pandas as pd

    from src.dados import DadosIndisponiveisError

    def _carregar(ticker, *_args, **_kwargs):
        if ticker == "SEMDADOS":
            raise DadosIndisponiveisError(ticker)
        indice = pd.bdate_range("2022-01-03", periods=300)
        fechamento = pd.Series(
            100.0 * np.cumprod(1 + 0.0003 + 0.01 * np.sin(np.arange(300))),
            index=indice,
        )
        return pd.DataFrame({"Close": fechamento})

    monkeypatch.setattr("telas.estrategias.pares.carregar_dados", _carregar)


def _com_lista(texto: str) -> AppTest:
    app = AppTest.from_function(_secao).run()
    app.text_input(key="pares_ativos").set_value(texto).run()
    return app


def _textos(elementos) -> str:
    return " ".join(e.value for e in elementos)


def test_um_ativo_so_pede_de_2_a_8():
    app = _com_lista("PETR4.SA")
    assert not app.exception
    assert "Escolha de 2 a 8 ativos (agora são 1)." in _textos(app.info)
    assert not app.dataframe


def test_ativos_demais_pedem_de_2_a_8():
    app = _com_lista("A1,A2,A3,A4,A5,A6,A7,A8,A9")
    assert not app.exception
    assert "Escolha de 2 a 8 ativos (agora são 9)." in _textos(app.info)
    assert not app.dataframe


def test_ativo_sem_dados_fica_de_fora_com_aviso():
    app = _com_lista("SEMDADOS, PETR4.SA")
    assert not app.exception
    assert "Não encontrei dados para: SEMDADOS. Eles ficaram de fora." in _textos(
        app.warning
    )
    assert "Não há ativos suficientes com dados." in _textos(app.info)
    assert not app.dataframe
