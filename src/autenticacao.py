"""Login com o Google: a parte que não depende do Streamlit (e por isso é testável).

O `st.login` do Streamlit faz o redirecionamento e guarda a sessão num cookie. Aqui ficam as
regras do TickerLab: quando o login é obrigatório, o que aceitar do Google e como virar usuário.
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

import sqlalchemy as sa

from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario, entrar

log = logging.getLogger(__name__)

VARIAVEL_DOS_ADMINS = "TICKERLAB_ADMINS"
CHAVES_DO_LOGIN = (
    "redirect_uri",
    "cookie_secret",
    "client_id",
    "client_secret",
    "server_metadata_url",
)


class LoginInvalidoError(Exception):
    """O Google respondeu, mas a identidade não serve para criar uma conta."""


@dataclass(frozen=True)
class IdentidadeDoGoogle:
    sub: str
    email: str
    nome: str | None
    foto_url: str | None
    email_verificado: bool = (
        False  # só quem o Google confirmou pode virar administrador
    )


def login_esta_configurado(segredos: Mapping | None) -> bool:
    """O bloco `[auth]` do `secrets.toml` tem tudo o que o `st.login` exige?

    Sem ele o app roda em modo local (sem contas), como no desenvolvimento.
    """
    try:
        auth = (segredos or {}).get("auth")
        return bool(auth) and all(auth.get(chave) for chave in CHAVES_DO_LOGIN)
    except (AttributeError, FileNotFoundError, KeyError, TypeError):
        return False


def emails_de_admin(ambiente: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """E-mails que viram administradores no primeiro login (`TICKERLAB_ADMINS`, separados por vírgula)."""
    texto = (ambiente if ambiente is not None else os.environ).get(
        VARIAVEL_DOS_ADMINS, ""
    )
    return tuple(e.strip().lower() for e in texto.split(",") if e.strip())


def ler_identidade(usuario_do_google: Mapping) -> IdentidadeDoGoogle:
    """Valida o que o Google devolveu (`st.user`) e separa os campos que o app guarda.

    Recusa e-mail que o Google não verificou: sem isso, alguém poderia registrar o e-mail de
    outra pessoa (inclusive o de um administrador).
    """
    sub = str(usuario_do_google.get("sub") or "").strip()
    email = str(usuario_do_google.get("email") or "").strip().lower()
    if not sub or not email:
        raise LoginInvalidoError("O Google não informou o identificador ou o e-mail.")
    if usuario_do_google.get("email_verified") is False:
        raise LoginInvalidoError("O Google diz que este e-mail não foi verificado.")
    nome = str(usuario_do_google.get("name") or "").strip() or None
    foto = str(usuario_do_google.get("picture") or "").strip() or None
    if foto is not None and not foto.startswith("https://"):
        foto = None  # só imagens por HTTPS entram na tela
    return IdentidadeDoGoogle(
        sub=sub,
        email=email,
        nome=nome,
        foto_url=foto,
        email_verificado=usuario_do_google.get("email_verified") is True,
    )


def registrar_login(
    identidade: IdentidadeDoGoogle,
    admins: tuple[str, ...] = (),
    motor: sa.Engine | None = None,
) -> tuple[Usuario, bool]:
    """Cria o usuário no primeiro login ou atualiza o acesso. Devolve (usuário, primeira vez?)."""
    try:
        with (motor or obter_engine()).begin() as conexao:
            return entrar(
                conexao,
                google_sub=identidade.sub,
                email=identidade.email,
                nome=identidade.nome,
                foto_url=identidade.foto_url,
                # o e-mail só dá o papel de administrador se o Google o confirmou
                emails_de_admin=admins if identidade.email_verificado else (),
            )
    except ValueError as erro:
        raise LoginInvalidoError(str(erro)) from erro
