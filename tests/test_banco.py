"""Testes do banco de dados do SaaS: migrações, esquema e usuários.

Rodam em SQLite por padrão. Para rodar no PostgreSQL de verdade (como o GitHub Actions faz), defina
TICKERLAB_TEST_DATABASE_URL com a URL de um banco de TESTE (as tabelas dele são apagadas).
"""

import os
import traceback
import uuid

import pytest
import sqlalchemy as sa

from src.banco import usuarios as repo
from src.banco.conexao import banco_esta_saudavel, criar_engine, migrar_para
from src.banco.modelo import favoritos, preferencias, simulacoes, usuarios
from src.configuracao import (
    VARIAVEL_DO_BANCO,
    normalizar_url_do_banco,
    url_do_banco,
    url_sem_senha,
)

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")


@pytest.fixture
def motor(tmp_path):
    url = URL_DE_TESTE or f"sqlite:///{(tmp_path / 'saas.sqlite').as_posix()}"
    if URL_DE_TESTE:
        # banco de teste compartilhado: começa vazio a cada teste
        migrar_para("base", url)
    migrar_para("head", url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()
    if URL_DE_TESTE:
        migrar_para("base", url)


# --- configuração -------------------------------------------------------------------------


def test_url_do_postgres_usa_o_driver_psycopg():
    assert (
        normalizar_url_do_banco("postgresql://u:s@h:5432/d")
        == "postgresql+psycopg://u:s@h:5432/d"
    )
    assert normalizar_url_do_banco("postgres://u@h/d").startswith(
        "postgresql+psycopg://"
    )
    assert normalizar_url_do_banco("sqlite:///x.db") == "sqlite:///x.db"


def test_url_do_banco_vem_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv(VARIAVEL_DO_BANCO, "postgresql://u:s@h/d")
    assert url_do_banco() == "postgresql+psycopg://u:s@h/d"
    monkeypatch.delenv(VARIAVEL_DO_BANCO)
    assert url_do_banco().startswith("sqlite:///")


def test_senha_nunca_aparece_na_url_dos_logs():
    texto = url_sem_senha(
        "postgresql+psycopg://tickerlab:segredo123@servidor:5432/tickerlab"
    )
    assert "segredo123" not in texto and "***" in texto


# --- migrações e esquema ------------------------------------------------------------------


def test_migracao_cria_todas_as_tabelas(motor):
    tabelas = set(sa.inspect(motor).get_table_names())
    assert {
        "usuarios",
        "preferencias",
        "favoritos",
        "simulacoes",
        "alembic_version",
    } <= tabelas


def test_migracao_pode_ser_desfeita_e_refeita(motor):
    url = motor.url.render_as_string(hide_password=False)
    migrar_para("base", url)
    assert "usuarios" not in sa.inspect(criar_engine(url)).get_table_names()
    migrar_para("head", url)
    assert "usuarios" in sa.inspect(criar_engine(url)).get_table_names()


def test_banco_responde_ao_teste_de_saude(motor):
    assert banco_esta_saudavel(motor)
    assert not banco_esta_saudavel(
        sa.create_engine("sqlite:////pasta/que/nao/existe/x.db")
    )


# --- usuários -----------------------------------------------------------------------------


def test_primeiro_login_cria_o_usuario_com_papel_e_plano_padrao(motor):
    with motor.begin() as conexao:
        usuario, novo = repo.entrar(
            conexao, "google-1", "Ana@Exemplo.com", "Ana", "http://f/1"
        )
    assert novo
    assert usuario.email == "ana@exemplo.com"  # e-mail sempre em minúsculas
    assert (usuario.papel, usuario.plano) == ("usuario", "gratuito")
    assert isinstance(usuario.id, uuid.UUID) and usuario.ultimo_acesso is not None


def test_segundo_login_atualiza_em_vez_de_duplicar(motor):
    with motor.begin() as conexao:
        primeiro, _ = repo.entrar(conexao, "google-1", "ana@exemplo.com", "Ana")
    with motor.begin() as conexao:
        segundo, novo = repo.entrar(
            conexao, "google-1", "ana@novo.com", "Ana Maria", "http://f/2"
        )
        assert repo.contar(conexao) == 1
    assert not novo and segundo.id == primeiro.id
    assert segundo.nome == "Ana Maria" and segundo.email == "ana@novo.com"
    assert segundo.foto_url == "http://f/2"


def test_email_de_administrador_vira_admin_no_cadastro_e_depois(motor):
    admins = ("chefe@exemplo.com",)
    with motor.begin() as conexao:
        chefe, _ = repo.entrar(
            conexao, "g-chefe", "Chefe@Exemplo.com", emails_de_admin=admins
        )
        comum, _ = repo.entrar(
            conexao, "g-comum", "comum@exemplo.com", emails_de_admin=admins
        )
    assert chefe.e_admin and not comum.e_admin
    with (
        motor.begin() as conexao
    ):  # quem já existia e entra na lista de admins vira admin
        promovido, _ = repo.entrar(
            conexao,
            "g-comum",
            "comum@exemplo.com",
            emails_de_admin=(*admins, "comum@exemplo.com"),
        )
    assert promovido.e_admin


def test_login_com_dados_invalidos_e_recusado(motor):
    with motor.begin() as conexao:
        with pytest.raises(ValueError, match="identificador"):
            repo.entrar(conexao, "", "ana@exemplo.com")
        with pytest.raises(ValueError, match="identificador"):
            repo.entrar(conexao, "x" * 65, "ana@exemplo.com")
        with pytest.raises(ValueError, match="e-mail"):
            repo.entrar(conexao, "g1", "sem-arroba")


def test_buscas_por_id_e_por_google_sub(motor):
    with motor.begin() as conexao:
        criado, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
        assert repo.buscar_por_id(conexao, criado.id) == criado
        assert repo.buscar_por_google_sub(conexao, "g1") == criado
        assert repo.buscar_por_google_sub(conexao, "outro") is None
        assert repo.buscar_por_id(conexao, uuid.uuid4()) is None


def test_mudar_plano_e_papel_validam_os_valores(motor):
    with motor.begin() as conexao:
        usuario, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
        repo.mudar_plano(conexao, usuario.id, "pro")
        repo.mudar_papel(conexao, usuario.id, "admin")
        atual = repo.buscar_por_id(conexao, usuario.id)
        assert (atual.plano, atual.papel) == ("pro", "admin")
        with pytest.raises(ValueError, match="Plano desconhecido"):
            repo.mudar_plano(conexao, usuario.id, "ouro")
        with pytest.raises(ValueError, match="Papel desconhecido"):
            repo.mudar_papel(conexao, usuario.id, "dono")
        with pytest.raises(LookupError):
            repo.mudar_plano(conexao, uuid.uuid4(), "pro")


def test_o_banco_recusa_plano_invalido_mesmo_sem_passar_pelo_codigo(motor):
    with motor.begin() as conexao:
        usuario, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.update(usuarios).where(usuarios.c.id == usuario.id).values(plano="vip")
        )


def test_google_sub_e_unico_no_banco(motor):
    with motor.begin() as conexao:
        repo.entrar(conexao, "g1", "a@exemplo.com")
    with pytest.raises(sa.exc.IntegrityError), motor.begin() as conexao:
        conexao.execute(
            sa.insert(usuarios).values(
                id=uuid.uuid4(), google_sub="g1", email="b@exemplo.com"
            )
        )


def test_apagar_a_conta_apaga_tudo_do_usuario_e_so_dele(motor):
    with motor.begin() as conexao:
        ana, _ = repo.entrar(conexao, "g-ana", "ana@exemplo.com")
        bia, _ = repo.entrar(conexao, "g-bia", "bia@exemplo.com")
        for dono in (ana, bia):
            conexao.execute(
                sa.insert(preferencias).values(
                    usuario_id=dono.id, dados={"periodo": "2y"}
                )
            )
            conexao.execute(
                sa.insert(favoritos).values(usuario_id=dono.id, ticker="PETR4.SA")
            )
            conexao.execute(
                sa.insert(simulacoes).values(
                    id=uuid.uuid4(),
                    usuario_id=dono.id,
                    tipo="backtest",
                    nome="teste",
                    parametros={"a": 1},
                    resultado={"b": 2},
                )
            )
    with motor.begin() as conexao:
        assert repo.apagar_conta(conexao, ana.id)
        assert not repo.apagar_conta(conexao, ana.id)  # já não existe
    with motor.connect() as conexao:
        for tabela in (preferencias, favoritos, simulacoes):
            donos = {linha.usuario_id for linha in conexao.execute(sa.select(tabela))}
            assert donos == {bia.id}, tabela.name


def test_json_guarda_e_devolve_estruturas(motor):
    parametros = {
        "estrategia": "Cruzamento de médias",
        "curta": 20,
        "usar_cdi": True,
        "lista": [1, 2.5],
    }
    with motor.begin() as conexao:
        usuario, _ = repo.entrar(conexao, "g1", "a@exemplo.com")
        conexao.execute(
            sa.insert(simulacoes).values(
                id=uuid.uuid4(),
                usuario_id=usuario.id,
                tipo="backtest",
                nome="n",
                parametros=parametros,
                resultado={"retorno": 0.12},
            )
        )
        linha = conexao.execute(sa.select(simulacoes)).one()
    assert linha.parametros == parametros and linha.resultado == {"retorno": 0.12}


def test_erros_do_banco_nao_citam_os_valores_da_consulta(motor):
    """Os valores (e-mails, nomes) não podem vazar para os logs pelas mensagens de erro."""
    segredo = "pessoa.secreta@exemplo.com"
    with pytest.raises(sa.exc.IntegrityError) as erro, motor.begin() as conexao:
        conexao.execute(
            sa.insert(usuarios).values(
                id=uuid.uuid4(), google_sub=None, email=segredo, papel="usuario"
            )
        )
    assert segredo not in str(erro.value)
    # nem no traceback completo (o erro original vem encadeado e iria junto para um log)
    assert segredo not in "".join(traceback.format_exception(erro.value))


def test_identificador_duplicado_nao_aparece_no_erro(motor):
    """No PostgreSQL, a violação de unicidade traz "Key (google_sub)=(...) already exists"."""
    segredo = "google-sub-secreto-123"
    with motor.begin() as conexao:
        repo.entrar(conexao, segredo, "a@exemplo.com")
    with pytest.raises(sa.exc.IntegrityError) as erro, motor.begin() as conexao:
        conexao.execute(
            sa.insert(usuarios).values(
                id=uuid.uuid4(),
                google_sub=segredo,
                email="b@exemplo.com",
                papel="usuario",
            )
        )
    assert segredo not in "".join(traceback.format_exception(erro.value))


def test_mensagem_sem_valores_usa_so_identificadores():
    from types import SimpleNamespace

    from src.banco.conexao import mensagem_sem_valores

    class UniqueViolation(Exception):
        sqlstate = "23505"
        diag = SimpleNamespace(
            table_name="usuarios",
            column_name=None,
            constraint_name="usuarios_email_key",
            message_detail="Key (email)=(x@y.com) already exists.",
        )

    texto = mensagem_sem_valores(
        UniqueViolation("Key (email)=(x@y.com) already exists.")
    )
    assert texto == (
        "UniqueViolation (código 23505); tabela usuarios; restrição usuarios_email_key"
    )
    assert mensagem_sem_valores(ValueError("não é do banco")) is None
