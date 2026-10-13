"""Testes de src/banco/tentativas.py: quantas variações cada pessoa testou em cada ativo."""

import pytest
import sqlalchemy as sa

from src.banco import tentativas as repo
from src.banco.modelo import metadata
from src.banco.usuarios import apagar_conta, entrar


@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "sub-ana", "ana@exemplo.com", "Ana")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "sub-bia", "bia@exemplo.com", "Bia")[0]


def test_mesma_configuracao_conta_uma_vez(conexao, ana):
    repo.registrar_tentativa(conexao, ana.id, "PETR4.SA", "a" * 64)
    repo.registrar_tentativa(conexao, ana.id, "PETR4.SA", "a" * 64)
    repo.registrar_tentativa(conexao, ana.id, "PETR4.SA", "b" * 64)
    assert repo.contar_tentativas(conexao, ana.id, "PETR4.SA") == 2


def test_contagem_e_por_ativo(conexao, ana):
    repo.registrar_tentativa(conexao, ana.id, "PETR4.SA", "a" * 64)
    repo.registrar_tentativa(conexao, ana.id, "VALE3.SA", "a" * 64)
    assert repo.contar_tentativas(conexao, ana.id, "PETR4.SA") == 1
    assert repo.contar_por_ativo(conexao, ana.id) == {"PETR4.SA": 1, "VALE3.SA": 1}


def test_contagem_e_so_da_propria_pessoa(conexao, ana, bia):
    for letra in "abc":
        repo.registrar_tentativa(conexao, ana.id, "PETR4.SA", letra * 64)
    repo.registrar_tentativa(conexao, bia.id, "PETR4.SA", "a" * 64)
    assert repo.contar_tentativas(conexao, ana.id, "PETR4.SA") == 3
    assert repo.contar_tentativas(conexao, bia.id, "PETR4.SA") == 1
    assert repo.contar_por_ativo(conexao, bia.id) == {"PETR4.SA": 1}


def test_ativo_sem_tentativas_conta_zero(conexao, ana):
    assert repo.contar_tentativas(conexao, ana.id, "PETR4.SA") == 0


def test_teto_por_pessoa(conexao, ana, monkeypatch):
    monkeypatch.setattr(repo, "TETO_POR_PESSOA", 3)
    for letra in "abcde":
        repo.registrar_tentativa(conexao, ana.id, "PETR4.SA", letra * 64)
    assert repo.contar_tentativas(conexao, ana.id, "PETR4.SA") == 3


def test_apagar_a_conta_apaga_as_tentativas(conexao, ana, bia):
    repo.registrar_tentativa(conexao, ana.id, "PETR4.SA", "a" * 64)
    repo.registrar_tentativa(conexao, bia.id, "PETR4.SA", "a" * 64)
    apagar_conta(conexao, ana.id)
    assert (
        conexao.execute(
            sa.select(sa.func.count()).select_from(repo.tentativas)
        ).scalar()
        == 1
    )
