"""O script que leva o que já está em `bruto/` e traz pessoa para `restrito/` (ADR 0106)."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa

from scripts import mover_acervo_restrito as mover
from src.banco.modelo import coletas

QUANDO = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def acervo_antigo(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path / "acervo"))
    motor = sa.create_engine("sqlite://")
    coletas.metadata.create_all(motor)
    conteudo = b"PK" + b"x" * 50
    sha = hashlib.sha256(conteudo).hexdigest()
    relativo = f"bruto/rfb-cnpj/2026/{sha}.zip"
    arquivo = tmp_path / "acervo" / relativo
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(conteudo)
    with motor.begin() as conexao:
        conexao.execute(
            sa.insert(coletas).values(
                id=uuid4(), fonte="rfb-cnpj", url="https://x/a.zip", situacao="ok",
                sha256=sha, licenca="CC BY", caminho_do_original=relativo,
                baixado_em=QUANDO,
            )
        )  # fmt: skip
    return motor, tmp_path / "acervo", relativo, sha


def _caminho_no_registro(motor):
    with motor.connect() as conexao:
        return conexao.execute(sa.select(coletas.c.caminho_do_original)).scalar_one()


def test_ensaio_nao_mexe_em_nada(acervo_antigo):
    motor, pasta, relativo, _ = acervo_antigo
    with motor.begin() as conexao:
        feitos = mover.mover(conexao, pasta, ensaio=True)
    assert [f.de for f in feitos] == [relativo]
    assert (pasta / relativo).is_file()
    assert _caminho_no_registro(motor) == relativo


def test_move_confere_o_sha_e_atualiza_o_registro(acervo_antigo):
    motor, pasta, relativo, sha = acervo_antigo
    with motor.begin() as conexao:
        mover.mover(conexao, pasta, ensaio=False)
    novo = relativo.replace("bruto/", "restrito/", 1)
    assert not (pasta / relativo).exists()
    assert (pasta / novo).is_file()
    assert _caminho_no_registro(motor) == novo
    assert hashlib.sha256((pasta / novo).read_bytes()).hexdigest() == sha


def test_arquivo_mexido_nao_e_movido(acervo_antigo):
    motor, pasta, relativo, _ = acervo_antigo
    (pasta / relativo).write_bytes(b"corrompido")
    with motor.begin() as conexao, pytest.raises(mover.ErroDeConferencia):
        mover.mover(conexao, pasta, ensaio=False)
    assert (pasta / relativo).is_file()
    assert _caminho_no_registro(motor) == relativo


def test_segunda_rodada_nao_faz_nada(acervo_antigo):
    motor, pasta, _, _ = acervo_antigo
    with motor.begin() as conexao:
        mover.mover(conexao, pasta, ensaio=False)
    with motor.begin() as conexao:
        assert mover.mover(conexao, pasta, ensaio=False) == []
