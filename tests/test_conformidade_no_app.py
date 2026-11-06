"""Termos de uso, privacidade, exportar e apagar a conta, dentro do app."""

import json

import streamlit as st

from src import conformidade
from src.banco import dados_do_usuario as repo
from src.banco.modelo import usuarios
from src.banco.usuarios import buscar_por_id
from tests.ajudantes_da_conta import (
    abrir_app,
    entrar_como,
    id_do_usuario,
    ir_para,
)


def _rotulos(app):
    return [b.label for b in app.button]


# a tela do aceite: Continuar e Sair, e os direitos da LGPD para quem não quer aceitar
BOTOES_DO_ACEITE = [
    "Continuar",
    "Sair",
    "Preparar o arquivo",
    "Apagar a minha conta e os meus dados",
]


# --- aceite dos termos ---
def test_primeiro_acesso_pede_o_aceite_e_bloqueia_o_app(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app(aceitar_termos=False)
    assert not app.exception
    assert _rotulos(app) == BOTOES_DO_ACEITE
    # nada do app de verdade antes do aceite: só a palavra que confirma apagar a conta
    assert [c.key for c in app.text_input] == ["confirmar_exclusao"]
    continuar = next(b for b in app.button if b.label == "Continuar")
    assert continuar.disabled  # só libera depois de marcar a caixa


def test_aceitar_libera_o_app_e_fica_registrado(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app(aceitar_termos=False)
    app.checkbox(key="aceite_dos_termos").check().run()
    next(b for b in app.button if b.label == "Continuar").click().run()
    assert not app.exception
    assert "Analisar ativo" in _rotulos(app)
    with banco.connect() as conexao:
        usuario = buscar_por_id(conexao, id_do_usuario(banco, "ana"))
    assert usuario.termos_versao == conformidade.VERSAO_DOS_TERMOS


def test_quem_ja_aceitou_nao_ve_a_tela_de_novo(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    segunda_visita = abrir_app(aceitar_termos=False)
    assert "Analisar ativo" in _rotulos(segunda_visita)


def test_termos_novos_pedem_novo_aceite(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    monkeypatch.setattr(conformidade, "VERSAO_DOS_TERMOS", "2099-01-01")
    app = abrir_app(aceitar_termos=False)
    assert _rotulos(app) == BOTOES_DO_ACEITE


def test_paginas_de_termos_e_privacidade(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("termos")
    assert not app.exception
    texto = " ".join(m.value for m in app.markdown)
    assert "recomendação de investimento" in texto
    ir_para(app, "privacidade")
    assert not app.exception
    texto = " ".join(m.value for m in app.markdown)
    assert "LGPD" in texto and "Stripe" in texto


def test_rodape_tem_links_para_termos_e_privacidade(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    assert not app.exception  # a página inicial monta o rodapé com os dois links


# --- meus dados ---
def test_exportar_prepara_o_arquivo_com_os_dados_da_pessoa(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        repo.salvar_favoritos(conexao, ana, ["AAPL"])
        repo.salvar_simulacao(conexao, ana, "backtest", "Minha", {}, {"numeros": {}})
    app = abrir_app("meus_dados")
    assert not app.exception
    app.button(key="preparar_exportacao").click().run()
    assert not app.exception
    dados = json.loads(app.session_state["exportacao_json"])
    assert dados["perfil"]["email"] == "ana@exemplo.com"
    assert dados["favoritos"] == ["AAPL"]
    assert [s["nome"] for s in dados["simulacoes"]] == ["Minha"]


def test_apagar_so_libera_depois_de_digitar_a_palavra(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("meus_dados")
    assert app.button(key="apagar_minha_conta").disabled
    app.text_input(key="confirmar_exclusao").input("apagar errado").run()
    assert app.button(key="apagar_minha_conta").disabled
    app.text_input(key="confirmar_exclusao").input("APAGAR").run()
    assert not app.button(key="apagar_minha_conta").disabled


def test_apagar_a_conta_remove_tudo_e_sai(banco, monkeypatch):
    saiu = []
    monkeypatch.setattr(st, "logout", lambda: saiu.append(True))
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        repo.salvar_favoritos(conexao, ana, ["AAPL"])
        repo.salvar_simulacao(conexao, ana, "backtest", "Minha", {}, {})
    app = abrir_app("meus_dados")
    app.text_input(key="confirmar_exclusao").input("APAGAR").run()
    app.button(key="apagar_minha_conta").click().run()
    assert saiu == [True]
    with banco.connect() as conexao:
        assert buscar_por_id(conexao, ana) is None
        assert repo.listar_simulacoes(conexao, ana) == []
        assert repo.listar_favoritos(conexao, ana) == []


def test_nao_apaga_se_a_cobranca_nao_puder_ser_encerrada(banco, monkeypatch):
    from src.banco.modelo import assinaturas

    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        conexao.execute(
            assinaturas.insert().values(
                usuario_id=ana,
                stripe_customer_id="cus_1",
                stripe_subscription_id="sub_1",
                status="active",
                cancela_no_fim=False,
                evento_em=1,
            )
        )
    for chave in ("STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "TICKERLAB_URL_PUBLICA"):
        monkeypatch.delenv(
            chave, raising=False
        )  # sem Stripe configurado: não dá para cancelar
    app = abrir_app("meus_dados")
    app.text_input(key="confirmar_exclusao").input("APAGAR").run()
    app.button(key="apagar_minha_conta").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert buscar_por_id(conexao, ana) is not None  # a conta continua


def test_modo_local_nao_tem_dados_pessoais():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "meus_dados")
    assert not app.exception
    assert any("modo local" in i.value for i in app.info)


def test_texto_do_banco_de_usuarios_tem_as_colunas_dos_termos():
    assert {"termos_versao", "termos_aceitos_em"} <= set(usuarios.c.keys())


# --- termos novos não bloqueiam os direitos da LGPD (achado 6c do Codex) ---
def test_sem_aceitar_os_termos_novos_ainda_exporta(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    monkeypatch.setattr(conformidade, "VERSAO_DOS_TERMOS", "2099-01-01")
    app = abrir_app(aceitar_termos=False)
    assert not app.exception
    app.button(key="preparar_exportacao").click().run()
    dados = json.loads(app.session_state["exportacao_json"])
    assert dados["perfil"]["email"] == "ana@exemplo.com"


def test_sem_aceitar_os_termos_novos_ainda_apaga_a_conta(banco, monkeypatch):
    saiu = []
    monkeypatch.setattr(st, "logout", lambda: saiu.append(True))
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    monkeypatch.setattr(conformidade, "VERSAO_DOS_TERMOS", "2099-01-01")
    app = abrir_app(aceitar_termos=False)
    app.text_input(key="confirmar_exclusao").input("APAGAR").run()
    app.button(key="apagar_minha_conta").click().run()
    assert saiu == [True]
    with banco.connect() as conexao:
        assert buscar_por_id(conexao, ana) is None


# --- conta bloqueada no incidente (linha 306; revisão cruzada do Codex no #659) ---
def _aba_aberta_de_quem_vai_ser_bloqueada(banco, monkeypatch):
    """A aba de Meus dados aberta antes do bloqueio, com o botão de apagar já liberado."""
    from tests.ajudantes_da_conta import bloquear_pelo_admin

    monkeypatch.setattr(st, "logout", lambda: None)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("meus_dados")
    ana = id_do_usuario(banco, "ana")
    app.text_input(key="confirmar_exclusao").input("APAGAR").run()
    bloquear_pelo_admin(banco, ana)
    return app, ana


def test_aba_aberta_da_conta_bloqueada_nao_apaga_a_conta(banco, monkeypatch):
    """O callback roda antes do corpo do app (onde a releitura para a conta bloqueada): sem a
    conferência no próprio callback, a aba aberta apagaria a conta e as provas do incidente.
    Vale mesmo dentro do minuto em que a aba ainda não releu a conta."""
    from src.banco.usuarios import TEXTO_DA_CONTA_BLOQUEADA

    app, ana = _aba_aberta_de_quem_vai_ser_bloqueada(banco, monkeypatch)
    app.button(key="apagar_minha_conta").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert buscar_por_id(conexao, ana) is not None
    assert [e.value for e in app.error] == [TEXTO_DA_CONTA_BLOQUEADA]


def test_aba_aberta_da_conta_bloqueada_nao_exporta(banco, monkeypatch):
    app, _ = _aba_aberta_de_quem_vai_ser_bloqueada(banco, monkeypatch)
    app.button(key="preparar_exportacao").click().run()
    assert not app.exception
    assert "exportacao_json" not in app.session_state


def test_os_pdfs_da_conta_bloqueada_nao_saem(banco, monkeypatch):
    """O .zip dos PDFs é montado no clique do download, sem passar pelo corpo do app."""
    import pytest

    from telas.conta import meus_dados

    _, ana = _aba_aberta_de_quem_vai_ser_bloqueada(banco, monkeypatch)
    with pytest.raises(PermissionError):
        meus_dados._meus_pdfs_em_zip(ana)
