"""Configuração comum dos testes."""

import pytest

from src.acervo import VARIAVEL_DA_PASTA
from src.armazenamento import VARIAVEL_DO_CAMINHO
from src.banco.conexao import criar_engine, migrar_para


@pytest.fixture(autouse=True)
def banco_de_precos_isolado(tmp_path, monkeypatch):
    """Cada teste usa um banco SQLite novo: nenhum teste lê ou escreve o banco de verdade."""
    monkeypatch.setenv(VARIAVEL_DO_CAMINHO, str(tmp_path / "precos_de_teste.sqlite"))
    # o acervo do arquivo original (src/acervo.py) também fica na pasta do teste
    monkeypatch.setenv(VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco SQLite com as migrações aplicadas, usado pelo app como `TICKERLAB_DATABASE_URL`."""
    url = f"sqlite:///{(tmp_path / 'conta.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()
