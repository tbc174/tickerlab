"""Versão do código que processou cada número (série 3 da base de ML, PR 1; ADR 0055, exigência 13)."""

import pytest

from src import versao_do_codigo as vc


def test_versao_vem_da_imagem(monkeypatch):
    """No contêiner, o build grava o commit em TICKERLAB_VERSAO."""
    monkeypatch.setenv(vc.VARIAVEL, "7ddaf09c1e")
    assert vc.versao_do_codigo(
        git=lambda: pytest.fail("não devia perguntar ao Git")
    ) == ("7ddaf09c1e")


def test_sem_a_variavel_usa_o_git(monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL, raising=False)
    assert vc.versao_do_codigo(git=lambda: ("deadbeef", False)) == "deadbeef"


def test_git_com_mudancas_nao_salvas_marca_a_versao(monkeypatch):
    """Um número feito com código fora de qualquer commit não pode fingir que é daquele commit."""
    monkeypatch.delenv(vc.VARIAVEL, raising=False)
    assert vc.versao_do_codigo(git=lambda: ("deadbeef", True)) == "deadbeef-modificado"


def test_sem_variavel_nem_git_a_versao_e_desconhecida(monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL, raising=False)
    assert vc.versao_do_codigo(git=lambda: None) == vc.DESCONHECIDA


def test_carga_da_base_recusa_versao_desconhecida(monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL, raising=False)
    with pytest.raises(vc.VersaoDesconhecidaError, match="TICKERLAB_VERSAO"):
        vc.exigir_versao_do_codigo(git=lambda: None)


def test_carga_da_base_recusa_codigo_modificado(monkeypatch):
    """A base vendável (ADR 0055) só aceita números que se refazem a partir de um commit."""
    monkeypatch.delenv(vc.VARIAVEL, raising=False)
    with pytest.raises(vc.VersaoDesconhecidaError, match="modificado"):
        vc.exigir_versao_do_codigo(git=lambda: ("deadbeef", True))


def test_git_de_verdade_responde_algo():
    """Na cópia do repositório, o Git real devolve um commit (ou None fora de um repositório)."""
    resposta = vc._perguntar_ao_git()
    assert resposta is None or (
        len(resposta[0]) == 40 and isinstance(resposta[1], bool)
    )
