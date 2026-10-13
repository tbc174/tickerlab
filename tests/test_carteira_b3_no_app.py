"""A página Carteira da B3 dentro do app (modo local): a planilha lida só na memória."""

import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from src import analise_da_carteira as ac
from src.banco.modelo import metadata
from tests.ajudantes_da_conta import ir_para


def _abrir_com_o_exemplo() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "carteira_b3")
    app.toggle(key="carteira_b3_exemplo").set_value(True).run()
    return app


def _linhas_no_banco(banco) -> int:
    with banco.connect() as conexao:
        return sum(
            conexao.execute(sa.select(sa.func.count()).select_from(t)).scalar_one()
            for t in metadata.sorted_tables
            if sa.inspect(banco).has_table(t.name)
        )


def test_sem_planilha_explica_como_baixar():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "carteira_b3")
    assert not app.exception
    assert "Área do Investidor" in " ".join(m.value for m in app.markdown)


def test_carteira_de_exemplo_mostra_concentracao_raio_x_e_rebalanceamento():
    app = _abrir_com_o_exemplo()
    assert not app.exception and not app.error
    rotulos = {m.label for m in app.metric}
    assert {"Maior posição", "3 maiores juntas", "Número efetivo de ativos"} <= rotulos
    textos = " ".join(c.value for c in app.caption)
    assert ac.NOTA_DA_MOEDA in textos
    assert (
        ac.AVISO_DO_REBALANCEAMENTO in " ".join(w.value for w in app.warning) + textos
    )
    assert app.get("plotly_chart")  # a carteira no passado contra o Ibovespa


def test_pagina_nao_guarda_nada_da_planilha(banco):
    antes = _linhas_no_banco(banco)
    app = _abrir_com_o_exemplo()
    assert not app.exception
    assert _linhas_no_banco(banco) == antes
