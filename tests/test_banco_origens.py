"""Testes de src/banco/origens.py: de onde veio cada cadastro (campanha, PR 1)."""

from datetime import date

import pytest
import sqlalchemy as sa

from src.banco import origens as repo
from src.banco.modelo import metadata
from src.banco.usuarios import apagar_conta, entrar
from src.origem import Origem

DO_GOOGLE = Origem(
    source="google",
    medium="cpc",
    campaign="testamos-ifr2",
    content="reel-1",
    ref=None,
    primeira_visita=date(2026, 12, 7),
)
DO_CRIADOR = Origem(source="instagram", medium="publi", ref="clube-do-robo")


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


def test_grava_e_le_a_origem(conexao, ana):
    assert repo.gravar_origem(conexao, ana.id, DO_GOOGLE) is True
    assert repo.buscar_origem(conexao, ana.id) == DO_GOOGLE


def test_grava_origem_so_na_primeira_vez(conexao, ana):
    repo.gravar_origem(conexao, ana.id, DO_GOOGLE)

    assert repo.gravar_origem(conexao, ana.id, DO_CRIADOR) is False
    assert repo.buscar_origem(conexao, ana.id) == DO_GOOGLE


def test_quem_nao_tem_origem_le_none(conexao, ana):
    assert repo.buscar_origem(conexao, ana.id) is None


def test_origem_e_so_da_propria_pessoa(conexao, ana, bia):
    repo.gravar_origem(conexao, ana.id, DO_GOOGLE)
    repo.gravar_origem(conexao, bia.id, DO_CRIADOR)

    assert repo.buscar_origem(conexao, ana.id) == DO_GOOGLE
    assert repo.buscar_origem(conexao, bia.id) == DO_CRIADOR


def test_apagar_conta_apaga_origem(conexao, ana, bia):
    repo.gravar_origem(conexao, ana.id, DO_GOOGLE)
    repo.gravar_origem(conexao, bia.id, DO_CRIADOR)

    apagar_conta(conexao, ana.id)

    assert repo.buscar_origem(conexao, ana.id) is None
    assert repo.buscar_origem(conexao, bia.id) == DO_CRIADOR
