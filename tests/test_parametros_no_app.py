"""Research etapa 1c: os presets no banco (versões, limites, isolamento) e a página Parâmetros."""

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from src.banco import dados_do_usuario as repo
from src.banco import usuarios as contas
from src.banco.conexao import criar_engine, migrar_para
from src.banco.usuarios import mudar_plano
from src.conformidade import apagar_conta, exportar_meus_dados
from src.planos import LimiteDoPlanoError
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

AGORA = datetime(2026, 10, 11, 20, 0, tzinfo=UTC)


def _usuario(conexao, sub):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    return usuario.id


# --- no banco ------------------------------------------------------------------------------------
def test_cada_mudanca_e_uma_versao_e_nada_e_sobrescrito(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        assert (
            repo.salvar_preset(c, ana, "global", None, {"tecnica.rsi_periodo": 21}) == 1
        )
        assert (
            repo.salvar_preset(c, ana, "global", None, {"tecnica.rsi_periodo": 9}) == 2
        )
        assert (
            repo.salvar_preset(c, ana, "global", None, {"tecnica.rsi_periodo": 9})
            is None
        )
        historico = repo.historico_do_preset(c, ana, "global", None)
        assert [(v.versao, v.parametros) for v in historico] == [
            (2, {"tecnica.rsi_periodo": 9}),
            (1, {"tecnica.rsi_periodo": 21}),
        ]
        (atual,) = repo.presets_atuais(c, ana)
        assert (atual.versao, atual.parametros) == (2, {"tecnica.rsi_periodo": 9})


def test_restaurar_tudo_vira_versao_vazia_e_sai_dos_presets_em_vigor(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        assert (
            repo.salvar_preset(c, ana, "global", None, {}) is None
        )  # nada a restaurar
        repo.salvar_preset(c, ana, "global", None, {"tecnica.rsi_periodo": 21})
        assert repo.salvar_preset(c, ana, "global", None, {}) == 2
        assert repo.presets_atuais(c, ana) == []
        assert len(repo.historico_do_preset(c, ana, "global", None)) == 2


def test_temas_e_ticker_voltam_do_banco_normalizados(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_preset(
            c,
            ana,
            "ativo",
            "petr4",
            {"newsletter.temas": ["risco", "resultados"]},
            plano="pro",
        )
        (p,) = repo.presets_atuais(c, ana)
        assert p.alvo == "PETR4.SA"
        assert p.parametros["newsletter.temas"] == ("resultados", "risco")
        assert repo.historico_do_preset(
            c, ana, "ativo", "PETR4"
        )  # acha pelo código curto


def test_um_usuario_nao_ve_os_parametros_do_outro(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        repo.salvar_preset(c, ana, "global", None, {"tecnica.rsi_periodo": 21})
        assert repo.presets_atuais(c, bia) == []
        assert repo.historico_do_preset(c, bia, "global", None) == []


def test_valores_invalidos_e_combinacoes_quebradas_sao_recusados_no_banco(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        with pytest.raises(repo.DadosInvalidosError, match="Período do RSI"):
            repo.salvar_preset(c, ana, "global", None, {"tecnica.rsi_periodo": 500})
        with pytest.raises(repo.DadosInvalidosError, match="média rápida"):
            repo.salvar_preset(c, ana, "global", None, {"tecnica.media_rapida": 250})


def test_mudar_o_padrao_nao_pode_quebrar_um_ativo_com_parametros_proprios(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_preset(
            c, ana, "ativo", "PETR4.SA", {"tecnica.media_rapida": 100}, plano="pro"
        )
        with pytest.raises(repo.DadosInvalidosError, match="PETR4.SA"):
            repo.salvar_preset(c, ana, "global", None, {"tecnica.media_lenta": 60})
        assert (
            repo.salvar_preset(c, ana, "global", None, {"tecnica.media_lenta": 150})
            == 1
        )


@pytest.mark.parametrize(
    ("plano", "maximo"), [("gratuito", 0), ("plus", 10), ("pro", 50)]
)
def test_limite_de_ativos_com_parametros_proprios(banco, plano, maximo):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        tickers = [f"AAA{i}" for i in range(maximo)]
        for t in tickers:
            repo.salvar_preset(
                c, ana, "ativo", t, {"tecnica.rsi_periodo": 21}, plano=plano
            )
        with pytest.raises(LimiteDoPlanoError):
            repo.salvar_preset(
                c, ana, "ativo", "ZZZZ", {"tecnica.rsi_periodo": 21}, plano=plano
            )
        if tickers:  # quem já tem o ativo pode mudar e restaurar
            assert (
                repo.salvar_preset(
                    c, ana, "ativo", tickers[0], {"tecnica.rsi_periodo": 9}, plano=plano
                )
                == 2
            )
        # o padrão (global) vale em todos os planos
        assert repo.salvar_preset(
            c, ana, "global", None, {"tecnica.rsi_periodo": 15}, plano=plano
        )


def test_exportacao_e_exclusao_da_conta_levam_os_presets(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_preset(
            c, ana, "global", None, {"tecnica.rsi_periodo": 21}, motivo="teste"
        )
        exportado = exportar_meus_dados(c, ana)["parametros_do_research"]
        assert exportado[0]["parametros"] == {"tecnica.rsi_periodo": 21}
        assert exportado[0]["motivo"] == "teste"
        assert apagar_conta(c, ana)
        assert repo.presets_atuais(c, ana) == []


def test_migracao_0007_vai_e_volta(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}"
    migrar_para("head", url=url)
    assert "presets" in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("-1", url=url)
    assert "presets" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url=url)
    assert "presets" in sa.inspect(criar_engine(url)).get_table_names()


# --- na tela -------------------------------------------------------------------------------------
def _campo(escopo, versao, chave, alvo="todos"):
    return f"rp_{escopo}_{alvo}_{versao}_{chave}"


def _app_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "parametros")


def _mudou(app) -> bool:
    return any("●" in tabela.value.to_string() for tabela in app.dataframe)


def test_modo_local_mostra_o_efeito_antes_de_salvar_e_salva_na_sessao():
    app = _app_local()
    assert not app.exception
    assert app.button(key="rpb_salvar").disabled  # nada mudou
    app.number_input(key=_campo("global", 0, "tecnica.rsi_periodo")).set_value(21).run()
    assert not app.exception and _mudou(app)
    assert not app.button(key="rpb_salvar").disabled
    app.button(key="rpb_salvar").click().run()
    (salvo,) = app.session_state["presets_locais"]
    assert (salvo.versao, salvo.parametros) == (1, {"tecnica.rsi_periodo": 21})
    assert app.number_input(key=_campo("global", 1, "tecnica.rsi_periodo")).value == 21
    assert not _mudou(app)  # o salvo virou o "em vigor"


def test_combinacao_invalida_mostra_o_erro_e_bloqueia_o_salvar():
    app = _app_local()
    app.number_input(key=_campo("global", 0, "tecnica.media_rapida")).set_value(
        300
    ).run()
    assert any("média rápida" in e.value for e in app.error)
    assert app.button(key="rpb_salvar").disabled


def test_restaurar_volta_ao_valor_herdado():
    app = _app_local()
    campo = _campo("global", 0, "tecnica.rsi_periodo")
    app.number_input(key=campo).set_value(21).run()
    app.button(key=f"rpb_restaurar_{campo}").click().run()
    assert app.number_input(key=campo).value == 14
    assert app.button(key="rpb_salvar").disabled


def test_aplicar_um_modo_de_leitura_pronto():
    app = _app_local()
    app.selectbox(key="rp_pronto").set_value("longo_prazo").run()
    app.button(key="rpb_aplicar").click().run()
    assert (
        app.selectbox(key=_campo("global", 0, "tecnica.periodicidade")).value
        == "semanal"
    )
    assert (
        app.number_input(key=_campo("global", 0, "editorial.fundamentos")).value == 45
    )
    assert not app.error and not app.button(key="rpb_salvar").disabled


def test_gratuito_salva_o_padrao_e_ve_o_convite_para_parametros_por_ativo(
    banco, monkeypatch
):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("parametros")
    app.number_input(key=_campo("global", 0, "tecnica.rsi_periodo")).set_value(21).run()
    app.button(key="rpb_salvar").click().run()
    assert not app.exception
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as c:
        assert [p.versao for p in repo.presets_atuais(c, ana)] == [1]
    app.button_group(key="rp_escopo").set_value("ativo").run()
    assert any("planos Plus e Pro" in i.value for i in app.info)
    campo = _campo("ativo", 0, "tecnica.rsi_periodo", alvo="PETR4.SA")
    assert app.number_input(key=campo).value == 21  # herdou o seu padrão
    app.number_input(key=campo).set_value(9).run()
    assert app.button(key="rpb_salvar").disabled


def test_pro_salva_por_ativo_e_volta_a_uma_versao_antiga(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("parametros")
    with banco.begin() as c:
        mudar_plano(c, id_do_usuario(banco, "ana"), "pro")
    app = abrir_app("parametros")
    app.button_group(key="rp_escopo").set_value("ativo").run()
    for versao, valor in ((0, 21), (1, 9)):
        campo = _campo("ativo", versao, "tecnica.rsi_periodo", alvo="PETR4.SA")
        app.number_input(key=campo).set_value(valor).run()
        app.button(key="rpb_salvar").click().run()
    assert not app.exception
    app.button(key="rpb_voltar_ativo_1").click().run()  # volta à v1 (RSI 21) como v3
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as c:
        historico = repo.historico_do_preset(c, ana, "ativo", "PETR4.SA")
    assert [(v.versao, v.parametros["tecnica.rsi_periodo"]) for v in historico] == [
        (3, 21), (2, 9), (1, 21),
    ]  # fmt: skip
    assert historico[0].motivo == "volta à versão 1"


# --- os parâmetros ligados às telas que já existiam ----------------------------------------------
def _app_com_parametros(parametros, pagina):
    from src.presets import Preset

    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["presets_locais"] = [
        Preset(escopo="global", parametros=parametros)
    ]
    app.run()
    return ir_para(app, pagina)


def _legendas(app):
    return " ".join(c.value for c in app.caption)


def test_sem_personalizar_as_telas_ficam_como_antes():
    app = _app_local()
    ir_para(app, "visao_geral")
    assert not app.exception
    assert any(m.label == "Perda de um dia ruim (VaR 95%)" for m in app.metric)
    assert app.multiselect[0].value == []
    assert "Usando os seus parâmetros" not in _legendas(app)


def test_visao_geral_usa_o_var_e_as_medias_do_usuario():
    app = _app_com_parametros(
        {
            "quant.var_confianca": 99,
            "tecnica.media_rapida": 20,
            "tecnica.media_lenta": 50,
        },
        "visao_geral",
    )
    assert not app.exception
    assert any(m.label == "Perda de um dia ruim (VaR 99%)" for m in app.metric)
    assert app.multiselect[0].value == [20, 50]
    assert "Usando os seus parâmetros" in _legendas(app)
    assert "Confiança do VaR 99" in _legendas(app)


def test_risco_comeca_na_janela_do_usuario():
    app = _app_com_parametros({"quant.janela_volatilidade": 63}, "risco")
    assert not app.exception
    assert (
        app.radio[0].value == 63 and "63" in app.radio[0].options
    )  # opções viram texto
    assert "Janela da volatilidade 63" in _legendas(app)


def test_correlacao_comeca_no_indice_e_na_janela_do_usuario():
    app = _app_com_parametros(
        {"quant.benchmark": "^GSPC", "quant.janela_correlacao": 60}, "correlacao"
    )
    assert not app.exception
    assert app.selectbox(key="corr_indice").value == "S&P 500"
    assert app.slider(key="corr_janela").value == 60
