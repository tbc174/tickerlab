"""A página "Gerar relatório" (Report Studio) dentro do app: prévia, modelos, seções, estilos,
geração, biblioteca e os limites do plano."""

from streamlit.testing.v1 import AppTest

from src import relatorios
from src.banco import dados_do_usuario as repo
from src.banco import pdfs_originais as pdfs
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para


def _app_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "relatorio")


def _baixar(app):
    return [b for b in app.get("download_button") if b.proto.label == "Baixar PDF"]


def _legendas(app) -> str:
    return " ".join(c.value for c in app.caption)


def _secoes(app, tipo="ativo"):
    return relatorios.normalizar_secoes(
        tipo,
        [
            c
            for c in app.session_state[f"relatorio_ordem_{tipo}"]
            if app.session_state[f"relatorio_secao_{tipo}_{c}"]
        ],
    )


def test_no_modo_local_mostra_a_previa_gera_o_pdf_e_oferece_o_download():
    app = _app_local()
    assert not app.exception
    previas = app.session_state["relatorio_previas"]
    assert len(previas) == 1  # a prévia já existe antes de gerar
    imagens, paginas = next(iter(previas.values()))
    assert len(imagens) == 2 and paginas >= 3
    assert all(i.startswith(b"\x89PNG") for i in imagens)
    app.button(key="gerar_pdf").click().run()
    assert not app.exception and not app.error
    gerado = app.session_state["relatorio_gerado"]
    assert gerado["arquivo"] == "tickerlab-PETR4.SA.pdf"
    assert gerado["pdf"].startswith(b"%PDF")
    assert _baixar(app)
    assert not any(b.key == "gerar_pdf" for b in app.button)  # virou "Baixar PDF"


def _gerar_no_tipo(tipo):
    app = _app_local()
    app.button_group(key="tipo_de_relatorio").set_value(tipo).run()
    assert not app.exception
    assert app.session_state["relatorio_previas"]  # a prévia foi montada
    app.button(key="gerar_pdf").click().run()
    assert not app.exception and not app.error
    return app.session_state["relatorio_gerado"]


def test_backtest_gera_o_pdf_da_estrategia_escolhida():
    gerado = _gerar_no_tipo(relatorios.BACKTEST)
    assert gerado["arquivo"] == "tickerlab-backtest-PETR4.SA.pdf"
    assert gerado["pdf"].startswith(b"%PDF")


def test_carteira_gera_o_pdf_com_os_ativos_da_lista():
    gerado = _gerar_no_tipo(relatorios.CARTEIRA)
    assert gerado["arquivo"] == "tickerlab-carteira.pdf"
    assert gerado["pdf"].startswith(b"%PDF")


def test_modelo_executivo_escolhe_menos_secoes_e_mexer_vira_personalizado():
    app = _app_local()
    assert _secoes(app) == relatorios.secoes_do_modelo("ativo", "completo")
    app.button_group(key="relatorio_modelo").set_value("executivo").run()
    assert not app.exception
    assert _secoes(app) == ["resumo", "numeros", "preco", "limites"]
    app.checkbox(key="relatorio_secao_ativo_mensal").check().run()
    assert app.session_state["relatorio_modelo"] == "personalizado"
    assert "mensal" in _secoes(app)


def test_secao_obrigatoria_nao_pode_sair_e_as_setas_mudam_a_ordem():
    app = _app_local()
    assert app.checkbox(key="relatorio_secao_ativo_limites").disabled
    antes = list(app.session_state["relatorio_ordem_ativo"])
    app.button(key="estudio_desce_ativo_resumo").click().run()
    depois = app.session_state["relatorio_ordem_ativo"]
    assert depois[:2] == [antes[1], antes[0]]
    assert app.session_state["relatorio_modelo"] == "personalizado"
    assert app.button(key=f"estudio_sobe_ativo_{depois[0]}").disabled


def test_trocar_o_estilo_atualiza_a_previa():
    app = _app_local()
    app.button_group(key="relatorio_estilo").set_value("terminal").run()
    assert not app.exception
    assert len(app.session_state["relatorio_previas"]) == 2
    assert "Terminal" in _legendas(app) or "visual do site" in _legendas(app)


def test_atalho_da_visao_geral_abre_o_relatorio_do_ativo():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "visao_geral")
    app.button(key="atalho_relatorio_ativo").click().run()
    assert not app.exception
    assert app.session_state["tipo_de_relatorio"] == "ativo"
    assert any(b.key == "gerar_pdf" for b in app.button)  # já na página do relatório


def test_gratuito_nao_gera_backtest_e_ve_o_convite_do_pro(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio")
    app.button_group(key="tipo_de_relatorio").set_value("backtest").run()
    assert not app.exception
    assert "faz parte do plano Pro" in " ".join(i.value for i in app.info)
    assert not any(b.key == "gerar_pdf" for b in app.button)


def test_gratuito_conta_o_uso_uma_vez_e_para_no_limite(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio")
    app.button(key="gerar_pdf").click().run()
    assert not app.exception
    assert "1 de 3 relatórios" in _legendas(app)
    app.run()  # rodar de novo (ou clicar duas vezes) não gera nem conta outro
    assert "1 de 3 relatórios" in _legendas(app)
    with banco.begin() as conexao:
        ana = id_do_usuario(banco, "ana")
        for _ in range(2):
            repo.registrar_relatorio(conexao, ana, "ativo")
    app.run()
    assert "3 de 3 relatórios" in _legendas(app)
    assert app.button(key="estudio_nova_versao").disabled


def test_biblioteca_guarda_reabre_e_exclui_sem_devolver_o_limite(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio")
    app.button_group(key="relatorio_estilo").set_value("institucional").run()
    app.button(key="gerar_pdf").click().run()
    assert not app.exception
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        (item,) = repo.biblioteca_de_relatorios(conexao, ana)
    assert item.titulo == "PETR4.SA: retorno, risco e comportamento"
    assert item.parametros["estilo"] == "institucional"
    assert item.parametros["secoes"][-1] == "limites"
    assert "versão 1" in _legendas(app)

    app.button_group(key="relatorio_estilo").set_value("research").run()
    app.button(key=f"estudio_reabrir_{item.id}").click().run()
    assert not app.exception
    assert app.session_state["relatorio_estilo"] == "institucional"

    app.button(key=f"estudio_excluir_{item.id}").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert repo.biblioteca_de_relatorios(conexao, ana) == []
        assert repo.contar_relatorios_recentes(conexao, ana) == 1  # o limite não volta


def test_gerar_guarda_o_pdf_original_igual_ao_entregue(banco, monkeypatch):
    # Master v3, C.4 (ADR 0021): a biblioteca guarda o PDF exato que a pessoa baixou
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio")
    app.button(key="gerar_pdf").click().run()
    assert not app.exception
    entregue = app.session_state["relatorio_gerado"]["pdf"]
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        (item,) = repo.biblioteca_de_relatorios(conexao, ana)
        assert pdfs.baixar_pdf_original(conexao, ana, item.id) == entregue
    (original,) = [b for b in app.get("download_button") if b.proto.label == "Original"]
    assert not original.proto.disabled
    assert "guardado por 1 ano" in _legendas(app)


def test_salvar_configuracao_guarda_na_conta_e_sobrevive_as_outras_preferencias(
    banco, monkeypatch
):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio")
    app.button_group(key="relatorio_modelo").set_value("executivo").run()
    app.button_group(key="relatorio_estilo").set_value("terminal").run()
    app.button(key="estudio_salvar_config").click().run()
    assert not app.exception
    app.selectbox(key="ticker").set_value("VALE3.SA").run()  # muda outra preferência
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        guardadas = repo.carregar_preferencias(conexao, ana)
    assert guardadas["ticker"] == "VALE3.SA"
    assert guardadas["relatorio"]["modelo"] == "executivo"
    assert guardadas["relatorio"]["estilo"] == "terminal"
    assert guardadas["relatorio"]["secoes"]["ativo"] == [
        "resumo",
        "numeros",
        "preco",
        "limites",
    ]


def test_biblioteca_no_modo_local_explica_que_nada_e_guardado():
    app = _app_local()
    assert "nada é guardado" in " ".join(i.value for i in app.info)
