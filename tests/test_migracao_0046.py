"""Migração 0046 (conjuntos suspensos da API externa): sobe, desce e o banco recusa motivo fora da lista.

Roda em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL). O `downgrade`
tira só a tabela nova: o contrato das organizações (`direitos_da_organizacao`) fica como estava.
"""

import os

import pytest
import sqlalchemy as sa

from src.banco.conexao import criar_engine, desfazer_ate, migrar_para

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
TABELA = "conjuntos_suspensos"

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def url(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'conjuntos.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    migrar_para("head", url)
    yield url
    if URL_DE_TESTE:
        migrar_para("base", url)


def _tabelas(url: str) -> set[str]:
    motor = criar_engine(url)
    try:
        return set(sa.inspect(motor).get_table_names())
    finally:
        motor.dispose()


def _gravar(url: str, **valores) -> None:
    motor = criar_engine(url)
    try:
        with motor.begin() as conexao:
            conexao.execute(
                sa.text(
                    f"INSERT INTO {TABELA} (conjunto, suspenso_em, motivo_da_suspensao)"
                    " VALUES (:conjunto, :suspenso_em, :motivo)"
                ),
                valores,
            )
    finally:
        motor.dispose()


def test_sobe_e_desce_sem_tocar_no_contrato(url) -> None:
    assert TABELA in _tabelas(url)
    desfazer_ate("0044", url)
    tabelas = _tabelas(url)
    assert TABELA not in tabelas
    assert "direitos_da_organizacao" in tabelas
    migrar_para("head", url)
    assert TABELA in _tabelas(url)


def test_banco_recusa_motivo_fora_da_lista(url) -> None:
    with pytest.raises(sa.exc.IntegrityError):
        _gravar(url, conjunto="x", suspenso_em="2026-11-03 18:00:00", motivo="qualquer")


def test_banco_recusa_suspenso_sem_motivo(url) -> None:
    with pytest.raises(sa.exc.IntegrityError):
        _gravar(url, conjunto="x", suspenso_em="2026-11-03 18:00:00", motivo=None)


def test_banco_aceita_suspenso_com_motivo_e_reativado_sem_os_dois(url) -> None:
    _gravar(url, conjunto="a", suspenso_em="2026-11-03 18:00:00", motivo="fonte")
    _gravar(url, conjunto="b", suspenso_em=None, motivo=None)
