"""Ambiente do Alembic: descobre a URL do banco e roda as migrações."""

from alembic import context

from src.banco.conexao import criar_engine
from src.banco.modelo import metadata
from src.configuracao import url_do_banco

configuracao = context.config


def _url() -> str:
    # `migrar_para` passa a URL por attributes; a linha de comando usa a variável de ambiente
    return configuracao.attributes.get("url") or url_do_banco()


def rodar_migracoes() -> None:
    motor = criar_engine(_url())
    with motor.connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=metadata,
            render_as_batch=conexao.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
    motor.dispose()


if context.is_offline_mode():
    raise SystemExit("As migrações só rodam conectadas ao banco (modo online).")
rodar_migracoes()
