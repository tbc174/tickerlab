"""Configuração do app vinda de variáveis de ambiente (nada de segredo no código)."""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

VARIAVEL_DO_BANCO = "TICKERLAB_DATABASE_URL"
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
