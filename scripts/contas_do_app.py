"""Bloquear uma conta do app só, durante um incidente (plano de incidente, passo 4), sem tela.

    python -m scripts.contas_do_app [--admin EMAIL] COMANDO ...

No VPS, a pasta `scripts/` não entra na imagem: o arquivo vai pelo stdin para o contêiner do app,
`docker exec -i tickerlab python - COMANDO ... < scripts/contas_do_app.py` (em `/opt/stacks/tickerlab`).
Comandos: `bloquear-conta ID --motivo M` (encerra as sessões na hora e para o login),
`desbloquear-conta ID` (o login volta; as sessões encerradas não) e `ver-conta ID`.

A conta vai sempre pelo id (o painel de admin mostra), nunca pelo e-mail, e a saída não mostra e-mail
nem nome. Só roda para quem está em `TICKERLAB_ADMINS` **e** é administrador no banco, como o
`chaves_da_api.py`. Cada comando é uma transação, registrada na auditoria só com ids. Saída 0 deu
certo, 1 nada mudou ou erro, 2 recusa de quem pede ou argumento inválido.
"""

import argparse
import sys
import uuid
from collections.abc import Callable, Sequence

import sqlalchemy as sa

from src.administracao import (
    OperacaoInvalidaError,
    PermissaoNegadaError,
    admin_do_servidor,
    ator_do_servidor,
    bloquear_conta,
    desbloquear_conta,
)
from src.autenticacao import VARIAVEL_DOS_ADMINS
from src.banco.conexao import criar_engine
from src.banco.modelo import MOTIVOS_DO_BLOQUEIO
from src.banco.usuarios import buscar_por_id
from src.configuracao import url_do_banco

SAIDA_OK, SAIDA_ERRO, SAIDA_RECUSA = 0, 1, 2

Comando = Callable[[sa.Connection, argparse.Namespace, uuid.UUID], str]


def _bloquear(conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID) -> str:
    encerradas = bloquear_conta(
        conexao, ator, args.conta, args.motivo, pelo_servidor=True
    )
    sessoes = (
        "1 sessão encerrada" if encerradas == 1 else f"{encerradas} sessões encerradas"
    )
    return (
        f"Conta {args.conta} bloqueada ({args.motivo}); {sessoes}. A versão clássica para em "
        "até 1 minuto."
    )


def _desbloquear(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    desbloquear_conta(conexao, ator, args.conta)
    return (
        f"Conta {args.conta} desbloqueada: o login volta (as sessões encerradas, não)."
    )


def _ver(conexao: sa.Connection, args: argparse.Namespace, _ator: uuid.UUID) -> str:
    conta = buscar_por_id(conexao, args.conta)
    if conta is None:
        raise OperacaoInvalidaError("Usuário não encontrado.")
    situacao = (
        f"bloqueada desde {conta.bloqueada_em.isoformat()} ({conta.motivo_do_bloqueio})"
        if conta.bloqueada_em is not None
        else "não está bloqueada"
    )
    return f"Conta {conta.id}: papel {conta.papel}, plano {conta.plano}; {situacao}."


def _montar_argumentos() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/contas_do_app.py",
        description="Bloqueia ou desbloqueia uma conta do app no incidente.",
    )
    parser.add_argument(
        "--admin",
        help=f"e-mail de quem pede (precisa estar em {VARIAVEL_DOS_ADMINS})",
    )
    comandos = parser.add_subparsers(dest="comando", required=True)

    def comando(nome: str, funcao: Comando, ajuda: str) -> argparse.ArgumentParser:
        sub = comandos.add_parser(nome, help=ajuda)
        sub.set_defaults(funcao=funcao)
        sub.add_argument("conta", type=uuid.UUID, help="id da conta (o painel mostra)")
        return sub

    bloquear = comando(
        "bloquear-conta", _bloquear, "encerra as sessões e para o login da conta"
    )
    bloquear.add_argument("--motivo", choices=MOTIVOS_DO_BLOQUEIO, required=True)
    comando("desbloquear-conta", _desbloquear, "o login da conta volta")
    comando("ver-conta", _ver, "papel, plano e bloqueio da conta")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _montar_argumentos().parse_args(argv)
    motor = criar_engine(url_do_banco())
    try:
        with motor.begin() as conexao:
            ator = ator_do_servidor(conexao, admin_do_servidor(args.admin))
            texto = args.funcao(conexao, args, ator)
    except PermissaoNegadaError as erro:
        print(f"Recusado: {erro}", file=sys.stderr)
        return SAIDA_RECUSA
    except OperacaoInvalidaError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return SAIDA_ERRO
    finally:
        motor.dispose()
    print(texto)
    return SAIDA_OK


if __name__ == "__main__":
    sys.exit(main())
