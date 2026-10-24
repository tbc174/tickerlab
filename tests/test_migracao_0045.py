"""Migração 0045 (bloqueio de conta em incidente): sobe, desce e o banco migrado guarda a regra.

Roda em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL): o banco
migrado, não só o modelo, precisa ter as duas colunas e recusar o bloqueio sem motivo; o `downgrade`
tira só a marca do bloqueio, nenhum dado da conta.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import favoritos, usuarios
from tests.test_identidades import _voltar_ao_zero

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
COLUNAS_NOVAS = {"bloqueada_em", "motivo_do_bloqueio"}
AGORA = datetime(2026, 10, 24, 16, 0, tzinfo=UTC)

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def url(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'bloqueio.sqlite').as_posix()}"
    if URL_DE_TESTE:
        _voltar_ao_zero(url)
    migrar_para("head", url)
    yield url
    if URL_DE_TESTE:
        _voltar_ao_zero(url)


def _colunas(url: str) -> set[str]:
    motor = criar_engine(url)
    try:
        return {c["name"] for c in sa.inspect(motor).get_columns("usuarios")}
    finally:
        motor.dispose()


def _inserir(url: str, **bloqueio: object) -> uuid.UUID:
    """Uma conta pelo modelo (que, no `head`, é igual ao banco migrado)."""
    motor = criar_engine(url)
    usuario_id = uuid.uuid4()
    try:
        with motor.begin() as conexao:
            conexao.execute(
                sa.insert(usuarios).values(
                    id=usuario_id,
                    email=f"{usuario_id.hex[:8]}@exemplo.com",
                    google_sub=f"g-{usuario_id.hex[:8]}",  # a descida da 0039 pede
                    criado_em=AGORA,
                    **bloqueio,
                )
            )
    finally:
        motor.dispose()
    return usuario_id


def test_sobe_e_desce_sem_perder_a_conta(url) -> None:
    assert _colunas(url) >= COLUNAS_NOVAS
    _inserir(url, bloqueada_em=AGORA, motivo_do_bloqueio="abuso")
    desfazer_ate("0044", url)
    assert not _colunas(url) & COLUNAS_NOVAS
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            assert (
                conexao.execute(sa.text("SELECT count(*) FROM usuarios")).scalar() == 1
            )
    finally:
        motor.dispose()
    migrar_para("head", url)
    assert _colunas(url) >= COLUNAS_NOVAS


def _favoritos(url: str) -> int:
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            return conexao.execute(sa.text("SELECT count(*) FROM favoritos")).scalar()
    finally:
        motor.dispose()


def test_sobe_e_desce_sem_apagar_os_dados_ligados_a_conta(url) -> None:
    """No SQLite a 0045 recria `usuarios`: com as chaves estrangeiras ligadas, apagar a tabela
    velha levaria junto, em cascata, tudo o que é da conta (favoritos, relatórios, simulações)."""
    usuario_id = _inserir(url)
    motor = criar_engine(url)
    try:
        with motor.begin() as conexao:
            conexao.execute(
                sa.insert(favoritos).values(usuario_id=usuario_id, ticker="PETR4.SA")
            )
    finally:
        motor.dispose()
    desfazer_ate("0044", url)
    assert _favoritos(url) == 1
    migrar_para("head", url)
    assert _favoritos(url) == 1


@pytest.mark.parametrize(
    "bloqueio",
    [
        {"bloqueada_em": AGORA},
        {"motivo_do_bloqueio": "abuso"},
        {"bloqueada_em": AGORA, "motivo_do_bloqueio": "porque_sim"},
    ],
)
def test_o_banco_migrado_recusa_bloqueio_pela_metade(url, bloqueio) -> None:
    with pytest.raises(sa.exc.IntegrityError):
        _inserir(url, **bloqueio)


def test_o_banco_migrado_aceita_os_motivos_do_desenho(url) -> None:
    for motivo in ("abuso", "acesso_de_terceiro", "incidente", "pedido_do_titular"):
        _inserir(url, bloqueada_em=AGORA, motivo_do_bloqueio=motivo)
