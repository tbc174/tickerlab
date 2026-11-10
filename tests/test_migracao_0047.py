"""Migração 0047 (membros da organização): sobe, desce e o banco recusa a conta em duas organizações.

Roda em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL). O `downgrade`
tira só a tabela nova: organizações, contas e o contrato ficam como estavam.
"""

import os
import uuid

import pytest
import sqlalchemy as sa

from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import membros_da_organizacao, organizacoes, usuarios

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
TABELA = "membros_da_organizacao"
ANTERIOR = "0045"

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def url(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'membros.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    migrar_para("head", url)
    yield url
    if URL_DE_TESTE:
        # a volta da 0039 recusa conta sem identidade do Google: as contas do teste saem antes
        _gravar(url, sa.delete(usuarios))
        _gravar(url, sa.delete(organizacoes))
        migrar_para("base", url)


def _tabelas(url: str) -> set[str]:
    motor = criar_engine(url)
    try:
        return set(sa.inspect(motor).get_table_names())
    finally:
        motor.dispose()


def _gravar(url: str, comando: sa.Executable) -> None:
    motor = criar_engine(url)
    try:
        with motor.begin() as conexao:
            conexao.execute(comando)
    finally:
        motor.dispose()


def _conta(url: str) -> uuid.UUID:
    conta = uuid.uuid4()
    _gravar(url, sa.insert(usuarios).values(id=conta, email=f"{conta.hex}@exemplo.com"))
    return conta


def _organizacao(url: str) -> uuid.UUID:
    organizacao = uuid.uuid4()
    _gravar(
        url,
        sa.insert(organizacoes).values(
            id=organizacao, nome=f"Exemplo {organizacao.hex[:6]}"
        ),
    )
    return organizacao


def _vincular(url: str, conta: uuid.UUID, organizacao: uuid.UUID) -> None:
    _gravar(
        url,
        sa.insert(membros_da_organizacao).values(
            usuario_id=conta, organizacao_id=organizacao
        ),
    )


def _membros(url: str) -> int:
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            return conexao.execute(
                sa.text(f"SELECT COUNT(*) FROM {TABELA}")
            ).scalar_one()
    finally:
        motor.dispose()


def test_sobe_e_desce_sem_tocar_nas_organizacoes(url) -> None:
    assert TABELA in _tabelas(url)
    conta, organizacao = _conta(url), _organizacao(url)
    _vincular(url, conta, organizacao)
    desfazer_ate(ANTERIOR, url)
    tabelas = _tabelas(url)
    assert TABELA not in tabelas
    assert {"organizacoes", "direitos_da_organizacao", "usuarios"} <= tabelas
    migrar_para("head", url)
    assert TABELA in _tabelas(url)
    assert _membros(url) == 0


def test_banco_recusa_a_conta_em_duas_organizacoes(url) -> None:
    conta = _conta(url)
    _vincular(url, conta, _organizacao(url))
    with pytest.raises(sa.exc.IntegrityError):
        _vincular(url, conta, _organizacao(url))


def test_banco_recusa_conta_ou_organizacao_que_nao_existe(url) -> None:
    with pytest.raises(sa.exc.IntegrityError):
        _vincular(url, uuid.uuid4(), _organizacao(url))
    with pytest.raises(sa.exc.IntegrityError):
        _vincular(url, _conta(url), uuid.uuid4())


def test_apagar_a_organizacao_ou_a_conta_leva_o_vinculo(url) -> None:
    conta, organizacao = _conta(url), _organizacao(url)
    _vincular(url, conta, organizacao)
    _gravar(url, sa.delete(organizacoes).where(organizacoes.c.id == organizacao))
    assert _membros(url) == 0
    _vincular(url, conta, _organizacao(url))
    _gravar(url, sa.delete(usuarios).where(usuarios.c.id == conta))
    assert _membros(url) == 0
