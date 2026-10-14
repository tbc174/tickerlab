"""Testes de src/banco/pulse.py: a última vez que cada pessoa abriu o Pulse."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from src.banco import pulse as repo
from src.banco.modelo import metadata, pulse
from src.banco.usuarios import apagar_conta, entrar

AGORA = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)


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


def test_sem_visita_devolve_none(conexao, ana):
    assert repo.ultima_visita(conexao, ana.id) is None


def test_marcar_e_ler_a_visita_com_fuso(conexao, ana):
    repo.marcar_visita(conexao, ana.id, AGORA)
    assert repo.ultima_visita(conexao, ana.id) == AGORA


def test_visita_nova_substitui_a_anterior(conexao, ana):
    repo.marcar_visita(conexao, ana.id, AGORA)
    repo.marcar_visita(conexao, ana.id, AGORA + timedelta(days=1))
    assert repo.ultima_visita(conexao, ana.id) == AGORA + timedelta(days=1)


def test_visita_mais_velha_nao_volta_o_relogio(conexao, ana):
    """Duas abas: a que abriu antes e marca depois não apaga a visita mais nova."""
    repo.marcar_visita(conexao, ana.id, AGORA)
    repo.marcar_visita(conexao, ana.id, AGORA - timedelta(hours=1))
    assert repo.ultima_visita(conexao, ana.id) == AGORA


def test_visita_de_uma_conta_nao_aparece_na_outra(conexao, ana, bia):
    repo.marcar_visita(conexao, ana.id, AGORA)
    assert repo.ultima_visita(conexao, bia.id) is None


def test_apagar_a_conta_apaga_a_visita(conexao, ana, bia):
    repo.marcar_visita(conexao, ana.id, AGORA)
    repo.marcar_visita(conexao, bia.id, AGORA)
    apagar_conta(conexao, ana.id)
    assert repo.ultima_visita(conexao, ana.id) is None
    assert repo.ultima_visita(conexao, bia.id) == AGORA


def test_visita_sem_fuso_e_recusada(conexao, ana):
    with pytest.raises(ValueError, match="fuso"):
        repo.marcar_visita(conexao, ana.id, datetime(2026, 10, 13, 18, 0))  # noqa: DTZ001


# --- vereditos da ficha vistos no Pulse (PR E2) ---------------------------------------------


def test_sem_visita_nao_ha_vereditos_vistos(conexao, ana):
    assert repo.vereditos_vistos(conexao, ana.id) == {}


def test_marcar_a_visita_com_os_vereditos_guarda_os_dois(conexao, ana):
    repo.marcar_visita(conexao, ana.id, AGORA, {"sim-1": "passou"})
    repo.marcar_visita(
        conexao, ana.id, AGORA + timedelta(days=1), {"sim-1": "não passou"}
    )
    assert repo.vereditos_vistos(conexao, ana.id) == {"sim-1": "não passou"}
    assert repo.ultima_visita(conexao, ana.id) == AGORA + timedelta(days=1)


def test_marcar_sem_vereditos_nao_apaga_os_guardados(conexao, ana):
    repo.marcar_visita(conexao, ana.id, AGORA, {"sim-1": "passou"})
    repo.marcar_visita(conexao, ana.id, AGORA + timedelta(days=1))
    assert repo.vereditos_vistos(conexao, ana.id) == {"sim-1": "passou"}


def test_visita_mais_velha_nao_volta_os_vereditos(conexao, ana):
    repo.marcar_visita(conexao, ana.id, AGORA, {"sim-1": "passou"})
    repo.marcar_visita(
        conexao, ana.id, AGORA - timedelta(hours=1), {"sim-1": "não passou"}
    )
    assert repo.vereditos_vistos(conexao, ana.id) == {"sim-1": "passou"}


def test_vereditos_estranhos_no_banco_ficam_de_fora(conexao, ana):
    repo.marcar_visita(conexao, ana.id, AGORA)
    conexao.execute(
        sa.update(pulse).values(
            vereditos={
                "sim-1": "passou",
                "sim-2": 3,
                "sim-3": None,
                "x" * 100: "passou",
            }
        )
    )
    assert repo.vereditos_vistos(conexao, ana.id) == {"sim-1": "passou"}


def test_vereditos_de_uma_conta_nao_aparecem_na_outra(conexao, ana, bia):
    repo.marcar_visita(conexao, ana.id, AGORA, {"sim-ana": "passou"})
    assert repo.vereditos_vistos(conexao, bia.id) == {}
