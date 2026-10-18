"""Identidades e sessões de login (migração 0039; plano do login com Microsoft e e-mail, PR 1).

Uma conta pode entrar por mais de um provedor (Google, Microsoft, e-mail com código). Contas só se
juntam pelo e-mail quando ele foi confirmado dos dois lados; sem isso, alguém que declarasse o e-mail
de outra pessoa cairia na conta dela.
"""

import os
import uuid

import pytest
import sqlalchemy as sa

from src.banco import usuarios as repo
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


# --- entrar por identidade: a regra de juntar contas ---------------------------------------


def _microsoft(sub="ms-1", email="ana@exemplo.com", confirmado=True, **extra):
    return repo.IdentidadeDoProvedor("microsoft", sub, email, confirmado, **extra)


def _pelo_email(email="ana@exemplo.com"):
    # o e-mail com código prova o e-mail: o identificador é o próprio e-mail
    return repo.IdentidadeDoProvedor("email", email, email, True)


def _identidades_da_conta(conexao, usuario_id):
    return conexao.execute(
        sa.select(identidades.c.provedor, identidades.c.sub)
        .where(identidades.c.usuario_id == usuario_id)
        .order_by(identidades.c.provedor)
    ).all()


def test_primeira_vez_pela_microsoft_cria_conta_sem_google_sub(motor):
    with motor.begin() as conexao:
        conta, primeira = repo.entrar_por_identidade(conexao, _microsoft(nome="Ana"))
        assert primeira and conta.google_sub is None
        assert (conta.email, conta.nome, conta.plano) == (
            "ana@exemplo.com",
            "Ana",
            "gratuito",
        )
        assert _identidades_da_conta(conexao, conta.id) == [("microsoft", "ms-1")]


def test_mesma_identidade_entra_na_mesma_conta(motor):
    with motor.begin() as conexao:
        primeira, _ = repo.entrar_por_identidade(conexao, _microsoft())
        de_novo, nova = repo.entrar_por_identidade(conexao, _microsoft())
    assert de_novo.id == primeira.id and not nova


def test_email_confirmado_junta_com_a_conta_do_google(motor):
    with motor.begin() as conexao:
        do_google, _ = repo.entrar(
            conexao, "g-ana", "Ana@Exemplo.com", email_confirmado=True
        )
        pelo_email, nova = repo.entrar_por_identidade(conexao, _pelo_email())
        assert pelo_email.id == do_google.id and not nova
        assert _identidades_da_conta(conexao, do_google.id) == [
            ("email", "ana@exemplo.com"),
            ("google", "g-ana"),
        ]


def test_email_nao_confirmado_nao_junta(motor):
    """A Microsoft de empresa não prova o e-mail: quem o declara não entra na conta de quem o tem."""
    with motor.begin() as conexao:
        do_google, _ = repo.entrar(
            conexao, "g-ana", "ana@exemplo.com", email_confirmado=True
        )
        invasor, nova = repo.entrar_por_identidade(
            conexao, _microsoft(confirmado=False)
        )
    assert nova and invasor.id != do_google.id


def test_conta_com_email_nao_confirmado_nao_captura_quem_chega_depois(motor):
    """Quem declarou o e-mail sem prova antes não fica com a conta de quem prova o e-mail depois."""
    with motor.begin() as conexao:
        invasor, _ = repo.entrar_por_identidade(conexao, _microsoft(confirmado=False))
        dona, nova = repo.entrar_por_identidade(conexao, _pelo_email())
    assert nova and dona.id != invasor.id


def test_juntar_pelo_google_preenche_o_google_sub(motor):
    """A versão clássica acha a conta pelo google_sub: a conta criada por e-mail ganha o dela."""
    with motor.begin() as conexao:
        pelo_email, _ = repo.entrar_por_identidade(conexao, _pelo_email())
        do_google, nova = repo.entrar(
            conexao, "g-ana", "ana@exemplo.com", email_confirmado=True
        )
    assert do_google.id == pelo_email.id and not nova
    assert do_google.google_sub == "g-ana"


def test_entrar_do_google_grava_a_identidade(motor):
    with motor.begin() as conexao:
        conta, _ = repo.entrar(conexao, "g-ana", "ana@exemplo.com")
        assert _identidades_da_conta(conexao, conta.id) == [("google", "g-ana")]


def test_conta_antiga_do_google_sem_identidade_ganha_a_dela(motor):
    """Conta criada pela versão clássica entre a migração e esta versão: achada pelo google_sub."""
    with motor.begin() as conexao:
        antiga = _conta(conexao)
        conexao.execute(
            sa.update(usuarios)
            .where(usuarios.c.id == antiga)
            .values(google_sub="g-ana")
        )
        conta, nova = repo.entrar(conexao, "g-ana", "ana@exemplo.com")
        assert conta.id == antiga and not nova
        assert _identidades_da_conta(conexao, antiga) == [("google", "g-ana")]


def test_admin_so_pelo_google_com_email_confirmado(motor):
    admins = ("ana@exemplo.com",)
    with motor.begin() as conexao:
        pela_microsoft, _ = repo.entrar_por_identidade(
            conexao, _microsoft(), emails_de_admin=admins
        )
        assert not pela_microsoft.e_admin
        pelo_google, _ = repo.entrar(
            conexao, "g-ana", "ana@exemplo.com", emails_de_admin=admins
        )
        assert not pelo_google.e_admin  # o Google não confirmou o e-mail
        confirmado, _ = repo.entrar(
            conexao,
            "g-ana",
            "ana@exemplo.com",
            emails_de_admin=admins,
            email_confirmado=True,
        )
        assert confirmado.e_admin
        # e a conta da Microsoft continua sem o papel (o Google sem confirmação não se juntou a ela)
        assert not repo.buscar_por_id(conexao, pela_microsoft.id).e_admin


def test_identidades_de_contas_diferentes_nao_se_misturam(motor):
    with motor.begin() as conexao:
        ana, _ = repo.entrar_por_identidade(conexao, _microsoft())
        bia, _ = repo.entrar_por_identidade(
            conexao, _microsoft(sub="ms-2", email="bia@exemplo.com")
        )
        assert ana.id != bia.id
        assert _identidades_da_conta(conexao, bia.id) == [("microsoft", "ms-2")]


@pytest.mark.parametrize(
    "identidade",
    [
        repo.IdentidadeDoProvedor("github", "x", "ana@exemplo.com", True),
        repo.IdentidadeDoProvedor("microsoft", " ", "ana@exemplo.com", True),
        repo.IdentidadeDoProvedor("microsoft", "x" * 256, "ana@exemplo.com", True),
        repo.IdentidadeDoProvedor("microsoft", "x", "sem-arroba", True),
    ],
)
def test_identidade_invalida_recusada(motor, identidade):
    with pytest.raises(ValueError), motor.begin() as conexao:
        repo.entrar_por_identidade(conexao, identidade)
