"""A página Backtest dentro do app (modo local, dados de exemplo): a validação fora da amostra."""

from streamlit.testing.v1 import AppTest

from tests.ajudantes_da_conta import ir_para

ESTRATEGIA = "Cruzamento de médias"


def _backtest_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=180)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "backtest")
    app.selectbox(key="backtest_estrategia").select(ESTRATEGIA).run()
    assert not app.exception
    return app


def _rotulos_das_metricas(app) -> list[str]:
    return [m.label for m in app.metric]


def test_walk_forward_com_janelas_curtas_mostra_o_sharpe_fora_da_amostra():
    app = _backtest_local()
    app.slider(key=f"validacao_treino_{ESTRATEGIA}").set_value(126).run()
    # cada janela precisa de pelo menos 30 dias (o controle anda de 21 em 21)
    app.slider(key=f"validacao_teste_{ESTRATEGIA}").set_value(42).run()
    assert not app.exception and not app.error
    rotulos = _rotulos_das_metricas(app)
    assert "Sharpe fora da amostra" in rotulos
    assert "Eficiência" in rotulos


def _legendas(app) -> str:
    return " ".join(c.value for c in app.caption)


def test_descontar_o_imposto_mostra_o_valor_pago():
    app = _backtest_local()
    app.checkbox(key="backtest_imposto").check().run()
    assert not app.exception and not app.error
    assert "Imposto pago por" in _legendas(app)


def test_cdi_como_referencia_entra_na_comparacao():
    app = _backtest_local()
    if any(c.key == "backtest_mostrar_cdi" for c in app.checkbox):
        app.checkbox(key="backtest_mostrar_cdi").check().run()
    assert not app.exception and not app.error
    avisos = " ".join(w.value for w in app.warning)
    assert "O CDI rendeu" in _legendas(app) or "CDI" in avisos


def test_mais_numeros_e_operacoes_aparecem():
    app = _backtest_local()
    rotulos = _rotulos_das_metricas(app)
    assert {"Ômega", "Meio Kelly (fração do capital)"} <= set(rotulos)
    assert "Histórico para 95% de confiança" in rotulos
    assert any(e.label.startswith("Ver as ") for e in app.expander)


def test_validacao_mostra_treino_e_teste_e_o_sharpe_deflacionado():
    app = _backtest_local()
    rotulos = _rotulos_das_metricas(app)
    assert "Sharpe da melhor, no treino" in rotulos
    assert "Tentativas contadas" in rotulos


# --- A ficha "Foi sorte?" -----------------------------------------------------------------

DETALHE_TECNICO = "Ver o detalhe técnico"
TITULOS_DO_VEREDITO = (
    "Passou no teste contra a sorte",
    "Não passou no teste contra a sorte",
    "Inconclusivo",
)


def _textos(elementos) -> str:
    return " ".join(m.value for m in elementos)


def _detalhe(app):
    return next(e for e in app.expander if e.label == DETALHE_TECNICO)


def test_backtest_mostra_a_ficha_com_cinco_checagens():
    from src import ficha

    app = _backtest_local()
    textos = _textos(app.markdown)
    for pergunta in (
        ficha.PERGUNTA_FORA_DO_PERIODO,
        ficha.PERGUNTA_CUSTOS,
        ficha.PERGUNTA_ACASO,
        ficha.PERGUNTA_VIZINHOS,
        ficha.PERGUNTA_QUEDAS,
    ):
        assert pergunta in textos
    assert ficha.AVISO in textos


def test_veredito_aparece_antes_do_detalhe():
    app = _backtest_local()
    assert any(t in _textos(app.markdown) for t in TITULOS_DO_VEREDITO)
    assert not any(t in _textos(_detalhe(app).markdown) for t in TITULOS_DO_VEREDITO)


def test_detalhe_tecnico_continua_disponivel():
    app = _backtest_local()
    abas = {t.label for t in _detalhe(app).tabs}
    assert {
        "Treino e teste",
        "Walk-forward",
        "Mapa de parâmetros",
        "Monte Carlo e acaso",
        "Sorte na escolha",
    } <= abas


def test_estrategia_sem_parametro_mostra_nao_se_aplica():
    from src import ficha

    app = _backtest_local()
    app.selectbox(key="backtest_estrategia").select("Comprar e segurar").run()
    assert not app.exception
    assert ficha.SEM_NUMEROS in _textos(app.markdown)


def test_tolerancia_entra_na_checagem_de_quedas():
    app = _backtest_local()
    app.number_input(key="ficha_tolerancia").set_value(5).run()
    assert not app.exception
    assert "você disse aguentar até 5%" in _textos(app.markdown)


# --- Contador de tentativas ---------------------------------------------------------------


def test_ficha_mostra_quantas_variacoes():
    app = _backtest_local()  # a estratégia de abertura e o Cruzamento de médias
    assert "Você testou 2 variações em PETR4.SA" in _textos(app.markdown)


def test_trocar_um_parametro_soma_uma_tentativa():
    app = _backtest_local()
    app.slider(key=f"parametro_{ESTRATEGIA}_curta").set_value(21).run()
    assert not app.exception
    assert "Você testou 3 variações" in _textos(app.markdown)
    app.slider(key=f"parametro_{ESTRATEGIA}_curta").set_value(20).run()
    assert "Você testou 3 variações" in _textos(
        app.markdown
    )  # voltar não conta de novo


def test_com_login_as_tentativas_ficam_na_conta(banco, monkeypatch):
    from src.banco import tentativas
    from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario

    entrar_como(monkeypatch, "duda", "duda@exemplo.com")
    app = abrir_app("backtest")  # 1ª configuração: a estratégia que a página abre
    app.selectbox(key="backtest_estrategia").select(ESTRATEGIA).run()  # 2ª
    assert not app.exception
    with banco.connect() as conexao:
        por_ativo = tentativas.contar_por_ativo(conexao, id_do_usuario(banco, "duda"))
    assert list(por_ativo.values()) == [2]
    volta = abrir_app("backtest")  # sessão nova, só a 1ª configuração de novo
    assert "Você testou 2 variações" in _textos(volta.markdown)  # veio da conta
