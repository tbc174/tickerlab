"""A seção Aprendizado de máquina (Avançado), sem internet: abas, avisos e erros em texto simples.

A seção recebe os dados por argumento, então o teste monta uma série sintética e roda só ela.
"""

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest


def _dados(dias: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    indice = pd.bdate_range("2018-01-02", periods=dias)
    fechamento = pd.Series(
        100.0 * np.cumprod(1 + rng.normal(0.0004, 0.012, dias)), index=indice
    )
    return pd.DataFrame(
        {
            "Close": fechamento,
            "High": fechamento * 1.01,
            "Low": fechamento * 0.99,
            "Volume": rng.integers(1_000, 5_000, dias).astype(float),
        }
    )


def _secao_longa() -> None:
    from telas.estrategias.aprendizado import secao_aprendizado
    from tests.test_aprendizado_na_tela import _dados

    secao_aprendizado(_dados(1500), 0.0)


def _secao_curta() -> None:
    from telas.estrategias.aprendizado import secao_aprendizado
    from tests.test_aprendizado_na_tela import _dados

    secao_aprendizado(_dados(60), 0.0)


def _textos(elementos) -> str:
    return " ".join(e.value for e in elementos)


def test_secao_mostra_o_aviso_de_overfitting_e_as_tres_abas():
    app = AppTest.from_function(_secao_longa, default_timeout=180).run()
    assert not app.exception
    assert "overfitting" in _textos(app.warning)
    assert [aba.label for aba in app.tabs] == [
        "Sinal do dia",
        "Barreira tripla e meta-rotulagem",
        "Volatilidade",
    ]


def test_aba_do_sinal_compara_o_modelo_com_a_previsao_ingenua():
    app = AppTest.from_function(_secao_longa, default_timeout=180).run()
    assert not app.exception
    legendas = _textos(app.caption)
    assert "previsões fora da amostra" in legendas
    assert "previsão ingênua" in legendas
    assert app.dataframe


def test_aba_da_volatilidade_mostra_os_tres_cartoes():
    app = AppTest.from_function(_secao_longa, default_timeout=180).run()
    assert not app.exception
    rotulos = [m.label for m in app.metric]
    assert "Erro do modelo (log)" in rotulos
    assert "Melhora sobre a ingênua" in rotulos
    assert "Correlação com o que veio" in rotulos


def test_poucos_dados_viram_aviso_e_nao_erro():
    app = AppTest.from_function(_secao_curta, default_timeout=180).run()
    assert not app.exception
    assert len(app.info) >= 1
    assert not app.dataframe
