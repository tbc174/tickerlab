"""`telas.comum._presets_guardados`: de onde vêm os presets em vigor (sessão local, conta ou falha)."""

from types import SimpleNamespace

import streamlit as st

from telas import comum


def test_modo_local_le_os_presets_da_sessao(monkeypatch):
    monkeypatch.setattr(st, "session_state", {"presets_locais": ["a", "b"]})
    assert comum._presets_guardados(None) == ["a", "b"]


def test_modo_local_sem_presets_devolve_lista_vazia(monkeypatch):
    monkeypatch.setattr(st, "session_state", {})
    assert comum._presets_guardados(None) == []


def test_modo_local_devolve_copia(monkeypatch):
    guardados = ["a"]
    monkeypatch.setattr(st, "session_state", {"presets_locais": guardados})
    comum._presets_guardados(None).append("b")
    assert guardados == ["a"]


def test_conta_le_do_banco_com_o_id_do_usuario(monkeypatch):
    chamadas = []

    class _Conexao:
        def __enter__(self):
            return "conexao"

        def __exit__(self, *args):
            return False

    class _Engine:
        def connect(self):
            return _Conexao()

    def falso_presets_atuais(conexao, usuario_id):
        chamadas.append((conexao, usuario_id))
        return ["do-banco"]

    monkeypatch.setattr(comum, "obter_engine", lambda: _Engine())
    monkeypatch.setattr(comum, "presets_atuais", falso_presets_atuais)
    assert comum._presets_guardados(SimpleNamespace(id=7)) == ["do-banco"]
    assert chamadas == [("conexao", 7)]


def test_falha_do_banco_avisa_e_devolve_lista_vazia(monkeypatch):
    avisos = []

    def quebra():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(comum, "obter_engine", quebra)
    monkeypatch.setattr(st, "warning", avisos.append)
    assert comum._presets_guardados(SimpleNamespace(id=1)) == []
    assert len(avisos) == 1
