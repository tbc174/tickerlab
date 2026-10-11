"""Testes do login: regras do TickerLab sobre o que o Google devolve."""

import pytest
import sqlalchemy as sa

from src.autenticacao import (
    IdentidadeDoGoogle,
    LoginInvalidoError,
    emails_de_admin,
    ler_identidade,
    login_esta_configurado,
    registrar_login,
)
from src.banco import modelo
from src.banco.usuarios import buscar_por_google_sub

AUTH_COMPLETO = {
    "redirect_uri": "https://exemplo.ts.net:8443/oauth2callback",
    "cookie_secret": "segredo",
    "client_id": "id",
    "client_secret": "segredo-do-cliente",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


@pytest.fixture
def motor():
    motor = sa.create_engine("sqlite://")
    modelo.metadata.create_all(motor)
    return motor


# --- login_esta_configurado ---
def test_login_configurado_com_todas_as_chaves():
    assert login_esta_configurado({"auth": AUTH_COMPLETO})


@pytest.mark.parametrize("chave", list(AUTH_COMPLETO))
def test_login_nao_configurado_se_falta_uma_chave(chave):
    auth = {k: v for k, v in AUTH_COMPLETO.items() if k != chave}
    assert not login_esta_configurado({"auth": auth})


@pytest.mark.parametrize("segredos", [None, {}, {"auth": {}}, {"auth": None}])
def test_login_nao_configurado_sem_bloco_auth(segredos):
    assert not login_esta_configurado(segredos)


def test_login_nao_configurado_se_ler_os_segredos_falha():
    class SemArquivo(dict):
        def get(self, *_):
            raise FileNotFoundError

    assert not login_esta_configurado(SemArquivo())


def test_chave_vazia_nao_conta():
    assert not login_esta_configurado({"auth": {**AUTH_COMPLETO, "client_id": ""}})


# --- emails_de_admin ---
def test_admins_vem_da_variavel_sem_espacos_e_em_minusculas():
    ambiente = {"TICKERLAB_ADMINS": " Ana@Exemplo.com , , bia@exemplo.com "}
    assert emails_de_admin(ambiente) == ("ana@exemplo.com", "bia@exemplo.com")


def test_sem_variavel_ninguem_e_admin():
    assert emails_de_admin({}) == ()


# --- ler_identidade ---
def test_ler_identidade_completa():
    identidade = ler_identidade(
        {
            "sub": "123",
            "email": " Ana@Exemplo.com ",
            "name": "Ana",
            "picture": "https://exemplo.com/foto.png",
            "email_verified": True,
        }
    )
    assert identidade == IdentidadeDoGoogle(
        "123",
        "ana@exemplo.com",
        "Ana",
        "https://exemplo.com/foto.png",
        email_verificado=True,
    )


@pytest.mark.parametrize(
    "dados", [{}, {"sub": "1"}, {"email": "a@b.com"}, {"sub": " ", "email": "a@b.com"}]
)
def test_identidade_sem_sub_ou_email_e_recusada(dados):
    with pytest.raises(LoginInvalidoError):
        ler_identidade(dados)


def test_email_nao_verificado_e_recusado():
    with pytest.raises(LoginInvalidoError, match="verificado"):
        ler_identidade({"sub": "1", "email": "a@b.com", "email_verified": False})


def test_sem_o_campo_de_verificacao_aceita():
    assert ler_identidade({"sub": "1", "email": "a@b.com"}).email == "a@b.com"


def test_foto_fora_de_https_e_descartada():
    dados = {"sub": "1", "email": "a@b.com", "picture": "http://exemplo.com/f.png"}
    assert ler_identidade(dados).foto_url is None
    dados["picture"] = "javascript:alert(1)"
    assert ler_identidade(dados).foto_url is None


def test_nome_vazio_vira_none():
    assert ler_identidade({"sub": "1", "email": "a@b.com", "name": " "}).nome is None


# --- registrar_login ---
def test_primeiro_login_cria_e_o_segundo_so_atualiza(motor):
    ana = IdentidadeDoGoogle("123", "ana@exemplo.com", "Ana", None)
    usuario, primeira = registrar_login(ana, motor=motor)
    assert primeira and usuario.plano == "gratuito" and not usuario.e_admin

    de_novo, primeira = registrar_login(
        IdentidadeDoGoogle("123", "ana@exemplo.com", "Ana Souza", None), motor=motor
    )
    assert not primeira
    assert de_novo.id == usuario.id and de_novo.nome == "Ana Souza"
    with motor.connect() as conexao:
        assert (
            conexao.execute(sa.select(sa.func.count(modelo.usuarios.c.id))).scalar()
            == 1
        )


def test_email_de_admin_vira_administrador(motor):
    identidade = IdentidadeDoGoogle(
        "9", "chefe@exemplo.com", None, None, email_verificado=True
    )
    usuario, _ = registrar_login(identidade, admins=("chefe@exemplo.com",), motor=motor)
    assert usuario.e_admin


def test_email_de_admin_sem_confirmacao_do_google_nao_vira_administrador(motor):
    nao_confirmado = IdentidadeDoGoogle("9", "chefe@exemplo.com", None, None)
    usuario, _ = registrar_login(
        nao_confirmado, admins=("chefe@exemplo.com",), motor=motor
    )
    assert not usuario.e_admin


def test_ler_identidade_marca_se_o_google_confirmou_o_email():
    com = ler_identidade({"sub": "1", "email": "a@b.com", "email_verified": True})
    sem = ler_identidade({"sub": "1", "email": "a@b.com"})
    assert com.email_verificado is True and sem.email_verificado is False


def test_admin_nao_vale_para_outro_sub_com_email_diferente(motor):
    usuario, _ = registrar_login(
        IdentidadeDoGoogle("2", "outra@exemplo.com", None, None),
        admins=("chefe@exemplo.com",),
        motor=motor,
    )
    assert not usuario.e_admin


def test_identidade_invalida_vira_erro_de_login(motor):
    with pytest.raises(LoginInvalidoError):
        registrar_login(IdentidadeDoGoogle("1", "sem-arroba", None, None), motor=motor)
    with motor.connect() as conexao:
        assert buscar_por_google_sub(conexao, "1") is None
