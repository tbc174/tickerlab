"""As velas da Visão geral com os períodos longos (2 e 5 anos, Tudo) abrem sem erro."""

import pytest
from streamlit.testing.v1 import AppTest

from tests.ajudantes_da_conta import ir_para


@pytest.mark.parametrize("periodo", ["2 anos", "5 anos", "Tudo"])
def test_velas_de_periodo_longo_abrem(periodo):
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "visao_geral")
    tipo = next(r for r in app.radio if r.label == "Tipo de gráfico")
    tipo.set_value("Velas").run()
    velas = next(r for r in app.radio if r.label == "Velas: período mostrado")
    assert periodo in velas.options
    velas.set_value(periodo).run()
    assert not app.exception
