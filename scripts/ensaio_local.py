"""Prepara o banco do ensaio local da API externa no PC (linha 800): banco, organização, direitos e chave.

    python -m scripts.ensaio_local --saida-da-chave CAMINHO

Usa o banco de `TICKERLAB_DATABASE_URL` (um SQLite, por exemplo `sqlite:///ensaio.db`; recusa o que não for
SQLite, para não tocar num banco de verdade), roda as migrações, cria um administrador de ensaio, a organização
de ensaio, os direitos dos cinco conjuntos da apresentação e uma chave. A chave vai **só** para o arquivo
dado em `--saida-da-chave` (nunca para a tela, o log ou o PR). O roteiro e as rotas que respondem estão em
`docs/casa-de-ma-primeiros-passos.md`, seção 5.

Não solta o portão de produção: a API do ensaio só responde porque quem a sobe põe `TICKERLAB_AMBIENTE=ensaio`
(`base.prontidao.registro_vigente`, que só liga com esse valor exato). Esta ferramenta não mexe no registro.

Roda: manual, no PC do Tiago, antes de subir a API local do ensaio (sem uso em produção nem em cron).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from src.autenticacao import IdentidadeDoGoogle, registrar_login
from src.banco import chaves_da_api as cb
from src.banco.conexao import criar_engine
from src.banco.usuarios import Usuario
from src.configuracao import url_do_banco

EMAIL_DO_ENSAIO = "ensaio@local.test"
NOME_DA_ORGANIZACAO = "Ensaio local"
CONJUNTOS_DO_ENSAIO = ("financials", "companies", "profiles", "funds", "sectors")
FINALIDADE_DO_ENSAIO = "analise"
INICIO_DOS_DIREITOS = date(2026, 1, 1)
SAIDA_OK = 0
SAIDA_RECUSA = 2


def _migrar(url: str) -> None:
    configuracao = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    configuracao.attributes["url"] = url
    command.upgrade(configuracao, "head")


def _administrador(motor: sa.Engine, email: str) -> Usuario:
    identidade = IdentidadeDoGoogle(
        sub="ensaio-local", email=email, nome="Ensaio", foto_url=None,
        email_verificado=True,
    )  # fmt: skip
    usuario, _ = registrar_login(identidade, admins=(email,), motor=motor)
    return usuario


def preparar(url: str, saida_da_chave: Path) -> str:
    """Faz tudo e grava a chave em `saida_da_chave`; devolve o id da organização."""
    _migrar(url)
    motor = criar_engine(url)
    try:
        ator = _administrador(motor, EMAIL_DO_ENSAIO).id
        with motor.begin() as conexao:
            organizacao = cb.criar_organizacao(
                conexao, nome=NOME_DA_ORGANIZACAO, ator_id=ator
            )
            for conjunto in CONJUNTOS_DO_ENSAIO:
                cb.conceder_direito(
                    conexao,
                    organizacao_id=organizacao.id,
                    conjunto=conjunto,
                    finalidade=FINALIDADE_DO_ENSAIO,
                    vigente_desde=INICIO_DOS_DIREITOS,
                    ator_id=ator,
                )
            nova = cb.emitir_chave(conexao, organizacao_id=organizacao.id, ator_id=ator)
        saida_da_chave.write_text(nova.valor, encoding="utf-8")
        return str(organizacao.id)
    finally:
        motor.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--saida-da-chave", type=Path, required=True)
    args = parser.parse_args(argv)
    url = url_do_banco()
    if not url.startswith("sqlite"):
        print("Recusado: o ensaio local só usa SQLite.", file=sys.stderr)
        return SAIDA_RECUSA
    organizacao = preparar(url, args.saida_da_chave)
    print(
        f"Ensaio pronto: organização {organizacao}; a chave está em {args.saida_da_chave}"
    )
    return SAIDA_OK


if __name__ == "__main__":
    sys.exit(main())
