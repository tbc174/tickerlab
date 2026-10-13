"""A página Carteira dentro do app (modo local, dados de exemplo): validações, estratégias e o CDI
do dinheiro parado."""

from streamlit.testing.v1 import AppTest

from src.carteiras import ESTRATEGIAS_DE_CARTEIRA
from tests.ajudantes_da_conta import ir_para

REFERENCIA = "Pesos iguais (referência)"


def _app_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "carteira")


def _colunas_da_tabela(app) -> list[str]:
    return list(app.dataframe[-1].value.columns)


def test_com_poucos_ativos_pede_mais_e_nao_simula():
    app = _app_local()
    app.text_input(key="carteira_ativos").input("PETR4.SA").run()
    assert not app.exception
    assert any("Escolha de" in i.value for i in app.info)
    assert not app.metric


def test_outra_estrategia_compara_com_os_pesos_iguais():
    app = _app_local()
    outra = next(n for n in ESTRATEGIAS_DE_CARTEIRA if n != REFERENCIA)
    app.selectbox(key="carteira_estrategia").set_value(outra).run()
    assert not app.exception
    colunas = _colunas_da_tabela(app)
    assert colunas[:2] == [outra, REFERENCIA]
    assert any("em pesos iguais" in str(m.proto.delta) for m in app.metric)


def test_dinheiro_parado_rendendo_o_cdi_simula_sem_erro():
    app = _app_local()
    app.checkbox(key="carteira_caixa_cdi").check().run()
    assert not app.exception and not app.error
    assert len(app.metric) == 4  # simulou e mostrou os quatro cartões
