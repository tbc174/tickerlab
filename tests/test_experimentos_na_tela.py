"""A tela dos experimentos (aporte, rebalanceamento, noite e dia, virada do mês) com dados sintéticos.

Sem internet: o segundo ativo do rebalanceamento vem de um dublê de `carregar_dados`.
"""

from streamlit.testing.v1 import AppTest


def _dados(dias: int = 600):
    import numpy as np
    import pandas as pd

    indice = pd.bdate_range("2022-01-03", periods=dias)
    fechamento = pd.Series(
        100.0 * np.cumprod(1 + 0.0004 + 0.01 * np.sin(np.arange(dias))), index=indice
    )
    return pd.DataFrame(
        {
            "Open": fechamento.shift(1).fillna(fechamento.iloc[0]),
            "High": fechamento * 1.01,
            "Low": fechamento * 0.99,
            "Close": fechamento,
            "Volume": 1_000.0,
        }
    )


def _secao() -> None:
    from telas.estrategias.experimentos import secao_experimentos
    from tests.test_experimentos_na_tela import _dados

    secao_experimentos(_dados(), "5y", 0.0)


def _secao_curta() -> None:
    from telas.estrategias.experimentos import secao_experimentos
    from tests.test_experimentos_na_tela import _dados

    secao_experimentos(_dados(30), "5y", 0.0)


def _secao_sem_segundo_ativo() -> None:
    import telas.estrategias.experimentos as tela
    from src.dados import DadosIndisponiveisError
    from tests.test_experimentos_na_tela import _dados

    def _falhar(*_args, **_kwargs):
        raise DadosIndisponiveisError("Sem dados para o segundo ativo.")

    tela.carregar_dados = _falhar
    tela.secao_experimentos(_dados(), "5y", 0.0)


def test_as_quatro_abas_aparecem_na_ordem():
    app = AppTest.from_function(_secao).run()
    assert not app.exception
    assert [a.label for a in app.tabs] == [
        "Aporte único × parcelado",
        "Rebalanceamento",
        "Noite × dia",
        "Virada do mês",
    ]


def test_aporte_mostra_os_quatro_cartoes_e_a_nota_das_janelas():
    app = AppTest.from_function(_secao).run()
    rotulos = [m.label for m in app.metric]
    assert "Aporte único vence em" in rotulos
    assert "Pior caso (único | parcelado)" in rotulos
    assert any("As janelas se sobrepõem" in c.value for c in app.caption)


def test_aporte_com_horizonte_maior_que_os_dados_explica_em_vez_de_quebrar():
    app = AppTest.from_function(_secao_curta).run()
    assert not app.exception
    assert any("Tente menos parcelas" in i.value for i in app.info)


def test_segundo_ativo_vazio_pede_o_ticker():
    app = AppTest.from_function(_secao).run()
    app.text_input(key="exp_segundo").set_value("   ").run()
    assert not app.exception
    assert any("Digite o segundo ativo." in i.value for i in app.info)


def test_segundo_ativo_indisponivel_vira_aviso():
    app = AppTest.from_function(_secao_sem_segundo_ativo).run()
    assert not app.exception
    assert any("Sem dados para o segundo ativo." in w.value for w in app.warning)


def test_noite_e_dia_mostra_a_tabela_e_a_nota_do_custo():
    app = AppTest.from_function(_secao).run()
    assert not app.exception
    assert any("A curva com custos" in c.value for c in app.caption)


def test_virada_do_mes_mostra_a_comparacao_dentro_e_fora():
    app = AppTest.from_function(_secao).run()
    legendas = [c.value for c in app.caption]
    assert any("Média por dia dentro da virada" in c for c in legendas)
    assert "Retorno total" in [m.label for m in app.metric]
