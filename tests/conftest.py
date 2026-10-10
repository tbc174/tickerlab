"""Configuração comum dos testes."""

import pytest

from src.armazenamento import VARIAVEL_DO_CAMINHO


@pytest.fixture(autouse=True)
def banco_de_precos_isolado(tmp_path, monkeypatch):
    """Cada teste usa um banco SQLite novo: nenhum teste lê ou escreve o banco de verdade."""
    monkeypatch.setenv(VARIAVEL_DO_CAMINHO, str(tmp_path / "precos_de_teste.sqlite"))
