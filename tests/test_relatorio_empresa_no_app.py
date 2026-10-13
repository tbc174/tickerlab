"""A página Relatório da empresa (série 2 da base de ML, PR 7) com as amostras reais da CVM, sem
internet: todas as seções, o aviso das notas, "não se aplica" nos bancos e o link a partir de
Fundamentos."""

from streamlit.testing.v1 import AppTest

from src.relatorio_empresa import SECOES
from tests.ajudantes_da_conta import ir_para
from tests.test_fundamentos_no_app import _coletar


def _abrir(ticker, pagina="relatorio_empresa") -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["ticker"] = ticker
    app.run()
    return ir_para(app, pagina)


def _textos(app):
    return " ".join(
        [m.value for m in app.markdown]
        + [c.value for c in app.caption]
        + [i.value for i in app.info]
    )


def test_pagina_mostra_as_secoes_e_o_aviso(banco):
    _coletar(banco)
    app = _abrir("PETR4.SA")
    assert not app.exception
    titulos = [s.value for s in app.subheader]
    assert titulos == list(SECOES.values())
    assert "não é recomendação" in _textos(app)
    metricas = {m.label: m.value for m in app.metric}
    receita = next(v for k, v in metricas.items() if k.startswith("Receita"))
    assert receita.startswith("R$ ")


def test_banco_mostra_nao_se_aplica(banco):
    _coletar(banco)
    app = _abrir("ITUB4.SA")
    assert not app.exception
    assert "Não se aplica" in _textos(app)


def test_sem_cadastro_explica(banco):
    app = _abrir("BTC-USD")
    assert not app.exception
    assert any("B3" in i.value for i in app.info)
    assert not app.subheader


def test_fundamentos_tem_link_para_o_relatorio(banco):
    _coletar(banco)
    app = _abrir("PETR4.SA", pagina="fundamentos")
    assert not app.exception
    rotulos = [link.proto.label for link in app.get("page_link")]
    assert any("Relatório da empresa" in r for r in rotulos)
