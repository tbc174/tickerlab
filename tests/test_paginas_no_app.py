"""Todas as páginas do menu abrem sem erro, e cada uma mostra o seu título e a sua frase."""

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.paginas import PAGINA_INICIAL, PAGINAS
from tests.ajudantes_da_conta import ir_para


def _app_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    return app.run()


def test_o_menu_registra_todas_as_paginas_do_mapa():
    app = _app_local()
    assert not app.exception
    enderecos = {i["url_pathname"] for i in app._registered_pages.values()}
    # a página de administração só existe no menu de administradores
    esperados = {
        "" if p.chave == PAGINA_INICIAL else p.url
        for p in PAGINAS
        if not p.somente_admin
    }
    assert enderecos == esperados


def test_todas_as_paginas_abrem_sem_erro_no_modo_local():
    app = _app_local()
    for p in PAGINAS:
        if p.somente_admin:  # testada em test_admin_no_app.py
            continue
        ir_para(app, p.chave)
        assert not app.exception, f"{p.chave}: {[e.value for e in app.exception]}"
        assert not app.error, f"{p.chave}: {[e.value for e in app.error]}"
        if p.chave == PAGINA_INICIAL:  # a chamada principal faz o papel de título
            continue
        titulos = " ".join(m.value for m in app.markdown)
        assert p.titulo in titulos, f"{p.chave}: sem título"
        legendas = " ".join(c.value for c in app.caption)
        assert p.descricao in legendas, f"{p.chave}: sem a frase de apoio"


def test_a_pagina_inicial_explica_e_leva_aos_proximos_passos():
    app = _app_local()
    texto = " ".join(m.value for m in app.markdown if not m.value.startswith("<style>"))
    assert "Entenda uma ação antes de investir" in texto
    for principio in ("Sem olhar o futuro", "Com custos", "Honesto", "Explicado"):
        assert principio in texto
    for atalho in (
        "Analisar ativo",
        "Testar estratégia",
        "Gerar relatório",
        "Minha carteira (B3)",
    ):
        assert atalho in texto  # os quatro cartões de atalho
    assert (
        "TickerLab Trade" not in texto
    )  # experimental: fica no menu "Mais", não no destaque
    rotulos = [b.label for b in app.button]
    assert rotulos[0] == "Analisar ativo" and "Abrir" in rotulos
    assert rotulos.count("Começar") == 3  # as três portas do tutorial (primeira visita)
    assert [s.key for s in app.selectbox] == ["ativo_do_inicio"]  # a busca do início


def test_analisar_no_inicio_abre_a_visao_geral_com_o_ativo_digitado():
    app = _app_local()
    app.selectbox(key="ativo_do_inicio").set_value("VALE3.SA")  # escolhido na lista
    app.button(key="comecar").click().run()
    assert not app.exception
    assert app.session_state["ticker"] == "VALE3.SA"
    assert app.selectbox(key="ticker").value == "VALE3.SA"  # já na Visão geral


def test_termos_e_privacidade_ficam_fora_do_menu_mas_abrem():
    app = _app_local()
    paginas = {i["url_pathname"]: i for i in app._registered_pages.values()}
    assert "termos" in paginas and "privacidade" in paginas
    ir_para(app, "termos")
    assert not app.exception


def test_paginas_de_analise_mostram_o_ativo_e_as_outras_nao():
    app = _app_local()
    # Início tem o seu próprio campo (que leva à Visão geral), mas não o do topo das análises
    assert not [s for s in app.selectbox if s.key == "ticker"]
    ir_para(app, "visao_geral")
    assert [s.key for s in app.selectbox if s.key == "ticker"] == ["ticker"]
    ir_para(app, "guia")
    assert not [s for s in app.selectbox if s.key == "ticker"]


def test_exemplos_do_inicio_abrem_a_analise():
    app = _app_local()
    app.button_group(key="atalho_do_inicio").set_value("AAPL").run()
    assert not app.exception
    assert app.session_state["ticker"] == "AAPL"
    assert app.session_state["recentes"][0] == "AAPL"  # e passa a aparecer nos recentes


def test_falha_da_fonte_nao_e_ativo_nao_encontrado(monkeypatch):
    """SEARCH-05: um ativo do catálogo que não carregou é falha da fonte, não código errado."""
    import yfinance

    def sem_conexao(*args, **kwargs):
        raise ConnectionError("sem internet")

    monkeypatch.setattr(yfinance, "download", sem_conexao)
    # sem histórico guardado: RADL3 não tem dados de exemplo nem cópia no cache
    monkeypatch.setattr("src.armazenamento.ler_precos", lambda ticker: pd.DataFrame())
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = False
    app.session_state["ticker"] = "RADL3.SA"
    ir_para(app.run(), "visao_geral")
    assert "o ativo existe, mas os preços não chegaram" in app.error[0].value

    app = AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = False
    app.session_state["ticker"] = "ZZZZ9.SA"
    ir_para(app.run(), "visao_geral")
    assert "Não encontrei **ZZZZ9.SA** no catálogo" in app.error[0].value
