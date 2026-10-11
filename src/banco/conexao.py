"""Conexão com o banco: motor (engine) por URL, teste de saúde e migrações."""

import logging
from functools import lru_cache
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from src.configuracao import (
    PASTA_RAIZ,
    normalizar_url_do_banco,
    url_do_banco,
    url_sem_senha,
)

log = logging.getLogger(__name__)
ARQUIVO_DO_ALEMBIC = PASTA_RAIZ / "alembic.ini"
PASTA_DAS_MIGRACOES = PASTA_RAIZ / "migracoes"


def _ligar_chaves_estrangeiras_no_sqlite(
    conexao_dbapi: object, _registro: object
) -> None:
    # o SQLite só respeita chaves estrangeiras (e o ON DELETE CASCADE) se isto estiver ligado
    cursor = conexao_dbapi.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def criar_engine(url: str | None = None) -> sa.Engine:
    """Um motor novo para a URL (a do ambiente, se não for dada)."""
    url = normalizar_url_do_banco(url) if url else url_do_banco()
    if url.startswith("sqlite"):
        caminho = sa.engine.make_url(url).database
        if caminho and caminho != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    # hide_parameters: os erros do SQLAlchemy citariam os valores da consulta (e-mails, nomes)
    # e iriam parar nos logs
    motor = sa.create_engine(url, pool_pre_ping=True, hide_parameters=True)
    if motor.dialect.name == "sqlite":
        sa.event.listen(motor, "connect", _ligar_chaves_estrangeiras_no_sqlite)
    log.info("Banco configurado: %s", url_sem_senha(url))
    return motor


@lru_cache(maxsize=4)
def _engine_em_cache(url: str) -> sa.Engine:
    return criar_engine(url)


def obter_engine() -> sa.Engine:
    """O motor compartilhado do app (um por URL, criado na primeira vez)."""
    return _engine_em_cache(url_do_banco())


def banco_esta_saudavel(motor: sa.Engine | None = None) -> bool:
    """O banco responde a uma consulta simples? Nunca levanta erro: serve para /saude."""
    try:
        with (motor or obter_engine()).connect() as conexao:
            conexao.execute(sa.text("SELECT 1"))
        return True
    except sa.exc.SQLAlchemyError as erro:
        log.error("Banco indisponível: %s", erro.__class__.__name__)
        return False


def _configuracao_do_alembic(url: str) -> Config:
    configuracao = Config(str(ARQUIVO_DO_ALEMBIC))
    configuracao.set_main_option("script_location", str(PASTA_DAS_MIGRACOES))
    # a URL vai direto para o env.py, sem passar pelo .ini (que trata o "%" como especial)
    configuracao.attributes["url"] = url
    return configuracao


def migrar_para(versao: str = "head", url: str | None = None) -> None:
    """Aplica (ou desfaz, com "base" ou uma versão anterior) as migrações."""
    url = normalizar_url_do_banco(url) if url else url_do_banco()
    configuracao = _configuracao_do_alembic(url)
    if versao == "base" or versao.startswith("-"):
        command.downgrade(configuracao, versao)
    else:
        command.upgrade(configuracao, versao)
