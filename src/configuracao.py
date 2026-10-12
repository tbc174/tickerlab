"""Configuração do app vinda de variáveis de ambiente (nada de segredo no código)."""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

VARIAVEL_DO_BANCO = "TICKERLAB_DATABASE_URL"
# e-mail de contato que fontes como a SEC exigem em cada consulta (fica no .env, não no Git)
VARIAVEL_DO_CONTATO = "TICKERLAB_CONTATO"
PASTA_RAIZ = Path(__file__).resolve().parent.parent
URL_PADRAO = (
    f"sqlite:///{(PASTA_RAIZ / 'dados_locais' / 'tickerlab.sqlite').as_posix()}"
)
PREFIXOS_POSTGRES = ("postgresql://", "postgres://")


def normalizar_url_do_banco(url: str) -> str:
    """Aceita a forma comum `postgresql://...` e escolhe o driver psycopg 3."""
    for prefixo in PREFIXOS_POSTGRES:
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo) :]
    return url


def url_do_banco() -> str:
    """A URL do banco: a da variável de ambiente ou, no desenvolvimento, um SQLite local."""
    return normalizar_url_do_banco(os.environ.get(VARIAVEL_DO_BANCO) or URL_PADRAO)


def url_sem_senha(url: str) -> str:
    """A mesma URL com a senha escondida, própria para logs e mensagens de erro."""
    return make_url(url).render_as_string(hide_password=True)


def contato() -> str | None:
    """O e-mail de contato do TickerLab (`TICKERLAB_CONTATO`), ou None se não estiver configurado."""
    valor = (os.environ.get(VARIAVEL_DO_CONTATO) or "").strip()
    return valor if "@" in valor else None
