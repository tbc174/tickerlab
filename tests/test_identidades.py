"""Identidades e sessões de login (migração 0039; plano do login com Microsoft e e-mail, PR 1).

Uma conta pode entrar por mais de um provedor (Google, Microsoft, e-mail com código). Contas só se
juntam pelo e-mail quando ele foi confirmado dos dois lados; sem isso, alguém que declarasse o e-mail
de outra pessoa cairia na conta dela.
"""

import os
import uuid

import pytest
import sqlalchemy as sa

from src.banco.conexao import criar_engine, desfazer_ate, migrar_para
from src.banco.modelo import favoritos, identidades, usuarios

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")

# o mesmo banco PostgreSQL do CI para todos os testes de banco: um por vez (como em test_banco.py)
pytestmark = pytest.mark.xdist_group("postgres")


@pytest.fixture
def url(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'saas.sqlite').as_posix()}"
    if URL_DE_TESTE:
        migrar_para("base", url)
    yield url
    if URL_DE_TESTE:
        migrar_para("base", url)


@pytest.fixture
def motor(url):
    migrar_para("head", url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


def _id_no_banco(motor: sa.Engine, id_: uuid.UUID) -> object:
    # SQL escrito à mão (o modelo da 0037 ainda tem google_sub obrigatório): o SQLite guarda o UUID
    # em hexadecimal
    return id_.hex if motor.dialect.name == "sqlite" else id_


def _estrangeira_em_cascata(inspecao: sa.Inspector, tabela: str) -> None:
    (estrangeira,) = inspecao.get_foreign_keys(tabela)
    assert estrangeira["referred_table"] == "usuarios"
    assert estrangeira.get("options", {}).get("ondelete") == "CASCADE"


# --- migração ------------------------------------------------------------------------------


def test_migracao_0039_cria_identidades_sessoes_e_codigos(motor):
    inspecao = sa.inspect(motor)
    assert {c["name"] for c in inspecao.get_columns("identidades")} == {
        "id",
        "usuario_id",
        "provedor",
        "sub",
        "email",
        "email_confirmado",
        "criada_em",
        "ultimo_uso",
    }
    assert {c["name"] for c in inspecao.get_columns("sessoes_de_login")} == {
        "id",
        "usuario_id",
        "hash_do_token",
        "provedor",
        "criada_em",
        "expira_em",
        "ultimo_uso",
        "encerrada_em",
    }
    assert {c["name"] for c in inspecao.get_columns("codigos_de_entrada")} == {
        "id",
        "hash_do_email",
        "hash_do_codigo",
        "criado_em",
        "expira_em",
        "tentativas",
        "usado_em",
    }
    _estrangeira_em_cascata(inspecao, "identidades")
    _estrangeira_em_cascata(inspecao, "sessoes_de_login")
    # o código ainda não é de conta nenhuma (pode ser o primeiro acesso): sem chave estrangeira
    assert inspecao.get_foreign_keys("codigos_de_entrada") == []
    # a conta criada por e-mail ou pela Microsoft não tem identificador do Google
    google_sub = next(
        c for c in inspecao.get_columns("usuarios") if c["name"] == "google_sub"
    )
    assert google_sub["nullable"]


def _conta(conexao: sa.Connection, email: str = "ana@exemplo.com") -> uuid.UUID:
    id_ = uuid.uuid4()
    conexao.execute(sa.insert(usuarios).values(id=id_, email=email))
    return id_


def _identidade(usuario_id: uuid.UUID, provedor: str = "google", sub: str = "google-1"):
    return sa.insert(identidades).values(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        provedor=provedor,
        sub=sub,
        email="ana@exemplo.com",
        email_confirmado=True,
    )


def test_mesma_identidade_nao_se_repete_no_banco(motor):
    with motor.begin() as conexao:
        ana = _conta(conexao)
        conexao.execute(_identidade(ana))
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(_identidade(_conta(conexao, "outra@exemplo.com")))


def test_banco_recusa_provedor_desconhecido(motor):
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(_identidade(_conta(conexao), provedor="github"))


def test_migracao_0039_cria_uma_identidade_por_google_sub(url):
    """Quem já tinha conta continua achando a conta: cada `google_sub` vira uma identidade do Google."""
    migrar_para("0037", url)
    motor = criar_engine(url)
    ana, bia = uuid.uuid4(), uuid.uuid4()
    with motor.begin() as conexao:
        for id_, sub, email in (
            (ana, "g-ana", "ana@exemplo.com"),
            (bia, "g-bia", "bia@exemplo.com"),
        ):
            conexao.execute(
                sa.text(
                    "INSERT INTO usuarios (id, google_sub, email, papel, plano) "
                    "VALUES (:id, :sub, :email, 'usuario', 'gratuito')"
                ),
                {"id": _id_no_banco(motor, id_), "sub": sub, "email": email},
            )
        # o que é da conta (no SQLite a tabela usuarios é recriada: não pode apagar em cascata)
        conexao.execute(
            sa.text("INSERT INTO favoritos (usuario_id, ticker) VALUES (:id, 'PETR4')"),
            {"id": _id_no_banco(motor, ana)},
        )
    migrar_para("head", url)
    with motor.connect() as conexao:
        linhas = conexao.execute(
            sa.select(
                identidades.c.usuario_id,
                identidades.c.provedor,
                identidades.c.sub,
                identidades.c.email,
                identidades.c.email_confirmado,
            ).order_by(identidades.c.sub)
        ).all()
        favoritos_depois = conexao.execute(
            sa.select(favoritos.c.usuario_id, favoritos.c.ticker)
        ).all()
    assert [tuple(linha) for linha in linhas] == [
        (ana, "google", "g-ana", "ana@exemplo.com", True),
        (bia, "google", "g-bia", "bia@exemplo.com", True),
    ]
    assert [tuple(linha) for linha in favoritos_depois] == [(ana, "PETR4")]
    # e o caminho de volta: as tabelas novas somem e as contas (e o que é delas) ficam
    desfazer_ate("0037", url)
    inspecao = sa.inspect(motor)
    assert "identidades" not in inspecao.get_table_names()
    assert "sessoes_de_login" not in inspecao.get_table_names()
    with motor.connect() as conexao:
        contas = conexao.execute(sa.text("SELECT COUNT(*) FROM usuarios")).scalar()
        favoritos_na_volta = conexao.execute(
            sa.text("SELECT COUNT(*) FROM favoritos")
        ).scalar()
    assert (contas, favoritos_na_volta) == (2, 1)
    motor.dispose()


def test_migracao_0039_nao_volta_com_conta_sem_google(url):
    """Voltar apagaria a conta criada por e-mail ou pela Microsoft: a migração recusa."""
    migrar_para("head", url)
    motor = criar_engine(url)
    with motor.begin() as conexao:
        conexao.execute(
            sa.insert(usuarios).values(id=uuid.uuid4(), email="eva@exemplo.com")
        )
    with pytest.raises(RuntimeError, match="não volta sozinha"):
        desfazer_ate("0037", url)
    with motor.connect() as conexao:
        assert (
            conexao.execute(sa.select(sa.func.count()).select_from(usuarios)).scalar()
            == 1
        )
    motor.dispose()
