"""Migração 0043 (chaves da API externa, N7): sobe, desce e as travas valem no próprio banco.

Rodam em SQLite por padrão e no PostgreSQL de verdade no CI (TICKERLAB_TEST_DATABASE_URL), como os
testes da sala e da originação: o banco migrado, não só o código, recusa a finalidade de treino, um
canal que não seja o da API externa e consumo com a chave de outra organização.
"""

import os
import uuid
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa

from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import metadata

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
TABELAS = {
    "organizacoes",
    "chaves_da_api",
    "direitos_da_organizacao",
    "consumo_da_api",
}
AGORA = datetime(2026, 10, 22, 12, tzinfo=UTC)

pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def motor(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'chaves.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    migrar_para("head", url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()
    if URL_DE_TESTE:
        migrar_para("base", url)


def _url(motor):
    return motor.url.render_as_string(hide_password=False)


def _tabelas(url):
    motor = criar_engine(url)
    try:
        return set(sa.inspect(motor).get_table_names())
    finally:
        motor.dispose()


def _inserir(motor, tabela, **valores):
    # a tabela do modelo só traduz os tipos (UUID vira texto no SQLite); quem recusa é o banco migrado
    alvo = metadata.tables[tabela]
    with motor.begin() as conexao:
        conexao.execute(sa.insert(alvo).values(**valores))


def _organizacao_e_chave(motor):
    organizacao_id = uuid.uuid4()
    chave_id = uuid.uuid4()
    _inserir(
        motor, "organizacoes", id=organizacao_id, nome="Alfa", plano_da_api="piloto"
    )
    _inserir(
        motor,
        "chaves_da_api",
        id=chave_id,
        organizacao_id=organizacao_id,
        prefixo=uuid.uuid4().hex[:8],
        hash_da_chave=uuid.uuid4().hex * 2,
    )
    return organizacao_id, chave_id


def test_migracao_0043_desce_e_sobe_de_novo(motor):
    url = _url(motor)
    assert _tabelas(url) >= TABELAS
    anterior = _revisao_anterior()
    desfazer_ate(anterior, url)
    tabelas = _tabelas(url)
    assert not TABELAS & tabelas
    assert "usuarios" in tabelas
    migrar_para("head", url)
    assert _tabelas(url) >= TABELAS


def _revisao_anterior():
    from pathlib import Path

    texto = (
        Path(__file__).resolve().parent.parent
        / "migracoes"
        / "versions"
        / "0043_chaves_da_api.py"
    ).read_text(encoding="utf-8")
    for linha in texto.splitlines():
        if linha.startswith("down_revision"):
            return linha.split("=")[1].strip().strip('"')
    raise AssertionError("0043 sem down_revision")


def test_plano_da_api_fora_da_lista_recusado_pelo_banco(motor):
    with pytest.raises(sa.exc.IntegrityError):
        _inserir(
            motor, "organizacoes", id=uuid.uuid4(), nome="Alfa", plano_da_api="ouro"
        )


def test_suspensa_sem_motivo_recusada_pelo_banco(motor):
    with pytest.raises(sa.exc.IntegrityError):
        _inserir(
            motor,
            "organizacoes",
            id=uuid.uuid4(),
            nome="Alfa",
            plano_da_api="piloto",
            suspensa_em=AGORA,
        )


def test_prefixo_repetido_recusado_pelo_banco(motor):
    organizacao_id, _ = _organizacao_e_chave(motor)
    _inserir(
        motor,
        "chaves_da_api",
        id=uuid.uuid4(),
        organizacao_id=organizacao_id,
        prefixo="abcdefgh",
        hash_da_chave="a" * 64,
    )
    with pytest.raises(sa.exc.IntegrityError):
        _inserir(
            motor,
            "chaves_da_api",
            id=uuid.uuid4(),
            organizacao_id=organizacao_id,
            prefixo="abcdefgh",
            hash_da_chave="b" * 64,
        )


@pytest.mark.parametrize("finalidade", ["treino", "outra"])
def test_direito_de_treino_recusado_pelo_banco(motor, finalidade):
    organizacao_id, _ = _organizacao_e_chave(motor)
    with pytest.raises(sa.exc.IntegrityError):
        _inserir(
            motor,
            "direitos_da_organizacao",
            id=uuid.uuid4(),
            organizacao_id=organizacao_id,
            conjunto="cvm-dfp-itr",
            finalidade=finalidade,
            vigente_desde=date(2026, 10, 22),
        )


@pytest.mark.parametrize("canal", ["api_interna", "tela"])
def test_consumo_so_no_canal_da_api_externa(motor, canal):
    organizacao_id, chave_id = _organizacao_e_chave(motor)
    with pytest.raises(sa.exc.IntegrityError):
        _inserir(
            motor,
            "consumo_da_api",
            organizacao_id=organizacao_id,
            chave_id=chave_id,
            dia=date(2026, 10, 22),
            canal=canal,
            finalidade="analise",
            conjunto="cvm-dfp-itr",
        )


def test_consumo_com_chave_de_outra_organizacao_recusado_pelo_banco(motor):
    _, chave_da_alfa = _organizacao_e_chave(motor)
    beta, _ = _organizacao_e_chave(motor)
    with pytest.raises(sa.exc.IntegrityError):
        _inserir(
            motor,
            "consumo_da_api",
            organizacao_id=beta,
            chave_id=chave_da_alfa,
            dia=date(2026, 10, 22),
            canal="api_externa",
            finalidade="analise",
            conjunto="cvm-dfp-itr",
        )
