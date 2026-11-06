"""A página Preços de referência dentro do app (modo local, banco de teste semeado)."""

from datetime import date

import pandas as pd
from streamlit.testing.v1 import AppTest

from src import precos_de_referencia as precos
from src.banco import series as acervo
from src.commodities import painel_de_precos as painel
from tests.ajudantes_da_conta import ir_para

MESES = pd.date_range("2025-08-01", "2026-09-01", freq="MS")


def _semear(banco):
    valores = pd.Series([float(v) for v in range(1, len(MESES) + 1)], index=MESES)
    codigos = [f"bm-pink-{c}" for c in painel.CHAVES_DO_PAINEL]
    codigos += [f"fmi-{c}" for c in precos.COMPARAVEIS]
    with banco.begin() as conexao:
        for codigo in codigos:
            acervo.garantir_serie(conexao, precos.serie_do_acervo(codigo))
            acervo.gravar(conexao, codigo, valores, date(2026, 10, 5))


def _abrir_local():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "precos_de_referencia")


def _textos(app) -> str:
    return " ".join(
        [m.value for m in app.markdown]
        + [c.value for c in app.caption]
        + [w.value for w in app.warning]
    )


def test_mostra_os_precos_com_atribuicao_e_aviso_do_diario(banco):
    _semear(banco)
    app = _abrir_local()
    assert not app.exception
    assert {m.label for m in app.metric} >= {
        "Café arábica (indicador ICO, outros suaves) (US$/kg)",
        "Ureia (US$/t)",
    }
    assert [w.value for w in app.warning] == [painel.AVISO_DIARIO]
    assert painel.ATRIBUICAO in _textos(app)
    assert "Spread arábica menos robusta" in _textos(app)


def test_fertilizante_leva_a_nota_de_que_os_indicadores_diferem(banco):
    _semear(banco)
    assert painel.NOTA_FONTES_DIFEREM in _textos(_abrir_local())


def test_sem_series_coletadas_explica_e_nao_quebra(banco):
    app = _abrir_local()
    assert not app.exception
    assert "ainda não foram coletados" in " ".join(i.value for i in app.info)
