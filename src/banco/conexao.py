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


def mensagem_sem_valores(erro: BaseException) -> str | None:
    """A mensagem de um erro do PostgreSQL montada SÓ com identificadores (tipo, código, tabela,
    coluna, restrição). None se o erro não vier do PostgreSQL.

    O texto original não serve: o servidor manda um "DETAIL" com a linha que falhou ("Failing row
    contains (...)", "Key (email)=(...) already exists"), e nos erros de formato até a mensagem
    principal repete o valor recebido. O `hide_parameters` não alcança esse texto.
    """
    diag = getattr(erro, "diag", None)
    sqlstate = getattr(erro, "sqlstate", None)
    if diag is None or sqlstate is None:
        return None
    partes = [f"{type(erro).__name__} (código {sqlstate})"]
    for nome, rotulo in (
        ("table_name", "tabela"),
        ("column_name", "coluna"),
        ("constraint_name", "restrição"),
    ):
        valor = getattr(diag, nome, None)
        if valor:
            partes.append(f"{rotulo} {valor}")
    return "; ".join(partes)


def _erro_sem_valores(contexto: sa.engine.ExceptionContext) -> BaseException | None:
    """Troca o texto do erro do banco antes de ele subir (e de ir para algum log).

    O erro original também é reescrito, porque o SQLAlchemy o encadeia ("from") no erro que
    sobe, e um traceback no log mostraria os dois.
    """
    original = contexto.original_exception
    mensagem = mensagem_sem_valores(original)
    if mensagem is None or contexto.sqlalchemy_exception is None:
        return None
    original.args = (mensagem,)
    erro = contexto.sqlalchemy_exception
    return type(erro)(
        contexto.statement,
        None,
        original,
        hide_parameters=True,
        connection_invalidated=erro.connection_invalidated,
    )


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
    else:  # o PostgreSQL devolve a linha que falhou no texto do erro: só identificadores
        sa.event.listen(motor, "handle_error", _erro_sem_valores)
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


def desfazer_ate(versao: str, url: str | None = None) -> None:
    """Desfaz as migrações até ficar exatamente na `versao` (ex.: "0006")."""
    url = normalizar_url_do_banco(url) if url else url_do_banco()
    command.downgrade(_configuracao_do_alembic(url), versao)
