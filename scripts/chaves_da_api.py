"""Administração das organizações, chaves e direitos da API externa (N7, D11), sem tela.

    python -m scripts.chaves_da_api [--admin EMAIL] COMANDO ...

No VPS, a pasta `scripts/` não entra na imagem: o arquivo vai pelo stdin para o contêiner do app,
`docker exec -i tickerlab python - COMANDO ... < scripts/chaves_da_api.py` (em `/opt/stacks/tickerlab`).
Comandos: `criar-organizacao`, `conceder-direito`, `suspender-direito`, `reativar-direito`,
`emitir-chave`, `rotacionar-chave`, `revogar-chave`, `suspender-organizacao`,
`reativar-organizacao` e `ver` (chaves pelo prefixo, direitos vigentes e consumo do mês).

Só roda para quem está em `TICKERLAB_ADMINS` **e** é administrador no banco (já entrou no app pelo
Google); `--admin` é dispensável quando a lista tem um e-mail só. Cada comando é uma transação.
A chave nova sai **uma vez**, no stdout, depois do commit: não vai para log, arquivo nem
auditoria (a auditoria leva só ids e o prefixo). Saída 0 deu certo, 1 nada mudou ou erro, 2 recusa
de quem pede ou argumento inválido.
"""

import argparse
import sys
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa

from src.administracao import PermissaoNegadaError, exigir_admin
from src.autenticacao import VARIAVEL_DOS_ADMINS, emails_de_admin
from src.banco import chaves_da_api as cb
from src.banco.conexao import criar_engine
from src.banco.modelo import (
    FINALIDADES_DA_ORGANIZACAO,
    MOTIVOS_DA_SUSPENSAO,
    PLANOS_DA_API,
)
from src.banco.usuarios import buscar_por_email
from src.chaves_da_api import ChaveNova
from src.configuracao import url_do_banco

SAIDA_OK, SAIDA_ERRO, SAIDA_RECUSA = 0, 1, 2
# os erros que o admin pode causar e que a mensagem já explica (sem traceback)
ERROS_ESPERADOS = (
    cb.OrganizacaoInvalidaError,
    cb.OrganizacaoSuspensaError,
    cb.LimiteDeChavesError,
    cb.ChaveInexistenteError,
    ValueError,
)


class NadaMudouError(Exception):
    """A ação não mudou nada (já estava assim, ou o id não é desta organização)."""


def _hoje() -> date:
    # o mesmo dia (UTC) que a medição do consumo usa
    return datetime.now(UTC).date()


def _escolher_admin(pedido: str | None) -> str:
    """O e-mail de quem pede: precisa estar em `TICKERLAB_ADMINS` (a lista do servidor)."""
    lista = emails_de_admin()
    if not lista:
        raise PermissaoNegadaError(f"{VARIAVEL_DOS_ADMINS} está vazia neste servidor.")
    if pedido is None:
        if len(lista) > 1:
            raise PermissaoNegadaError(
                f"{VARIAVEL_DOS_ADMINS} tem mais de um e-mail: diga qual com --admin."
            )
        return lista[0]
    email = pedido.strip().lower()
    if email not in lista:
        raise PermissaoNegadaError(f"Este e-mail não está em {VARIAVEL_DOS_ADMINS}.")
    return email


def _ator(conexao: sa.Connection, email: str) -> uuid.UUID:
    """O id do administrador, conferido no banco (a lista sozinha não basta)."""
    usuario = buscar_por_email(conexao, email)
    if usuario is None:
        raise PermissaoNegadaError(
            "Nenhum administrador com este e-mail no banco: entre no app pelo Google antes."
        )
    exigir_admin(conexao, usuario.id)
    return usuario.id


def _mudou(mudou: bool, texto: str) -> str:
    if not mudou:
        raise NadaMudouError(
            "Nada mudou: já estava assim, ou o id não é desta organização."
        )
    return texto


def _texto_da_chave(nova: ChaveNova, titulo: str) -> str:
    return (
        f"{titulo}: id {nova.chave_id}, prefixo {nova.prefixo}\n"
        "A chave aparece só agora; entregue ao cliente e não guarde cópia:\n"
        f"{nova.valor}"
    )


# ---------------------------------------------------------------- comandos
# Cada um recebe a conexão, os argumentos e o id do admin, e devolve o texto da saída.


def _criar_organizacao(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    organizacao = cb.criar_organizacao(
        conexao, nome=args.nome, cnpj=args.cnpj, plano_da_api=args.plano, ator_id=ator
    )
    return f"Organização criada: {organizacao.id} (plano {organizacao.plano_da_api})"


def _conceder_direito(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    direito = cb.conceder_direito(
        conexao,
        organizacao_id=args.organizacao,
        conjunto=args.conjunto,
        finalidade=args.finalidade,
        vigente_desde=args.desde,
        vigente_ate=args.ate,
        ator_id=ator,
    )
    return (
        f"Direito concedido: {direito.id} ({direito.conjunto}, {direito.finalidade}, "
        f"de {direito.vigente_desde} a {direito.vigente_ate or 'sem fim'})"
    )


def _suspender_direito(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    mudou = cb.suspender_direito(
        conexao, organizacao_id=args.organizacao, direito_id=args.direito, ator_id=ator
    )
    return _mudou(mudou, f"Direito suspenso: {args.direito}")


def _reativar_direito(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    mudou = cb.reativar_direito(
        conexao, organizacao_id=args.organizacao, direito_id=args.direito, ator_id=ator
    )
    return _mudou(mudou, f"Direito reativado: {args.direito}")


def _emitir_chave(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    nova = cb.emitir_chave(conexao, organizacao_id=args.organizacao, ator_id=ator)
    return _texto_da_chave(nova, "Chave emitida")


def _rotacionar_chave(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    nova = cb.rotacionar_chave(
        conexao, organizacao_id=args.organizacao, chave_id=args.chave, ator_id=ator
    )
    dias = cb.PRAZO_DA_ROTACAO.days
    return _texto_da_chave(
        nova, f"Chave rotacionada (a antiga vale mais {dias} dias); nova"
    )


def _revogar_chave(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    mudou = cb.revogar_chave(
        conexao, organizacao_id=args.organizacao, chave_id=args.chave, ator_id=ator
    )
    return _mudou(mudou, f"Chave revogada: {args.chave}")


def _suspender_organizacao(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    mudou = cb.suspender_organizacao(
        conexao, organizacao_id=args.organizacao, motivo=args.motivo, ator_id=ator
    )
    return _mudou(mudou, f"Organização suspensa: {args.organizacao}")


def _reativar_organizacao(
    conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID
) -> str:
    mudou = cb.reativar_organizacao(
        conexao, organizacao_id=args.organizacao, ator_id=ator
    )
    return _mudou(mudou, f"Organização reativada: {args.organizacao}")


def _estado_da_chave(chave: cb.ChaveListada) -> str:
    if chave.revogada_em is not None:
        return f"revogada em {chave.revogada_em:%Y-%m-%d}"
    if chave.expira_em is not None:
        return f"de saída, vale até {chave.expira_em:%Y-%m-%d %H:%M} UTC"
    return "ativa"


def _ver(conexao: sa.Connection, args: argparse.Namespace, ator: uuid.UUID) -> str:
    del ator  # só leitura: nada vai para a auditoria
    organizacao = cb.buscar_organizacao(conexao, args.organizacao)
    if organizacao is None:
        raise cb.OrganizacaoInvalidaError("Organização inexistente.")
    hoje = _hoje()
    suspensa = (
        f"suspensa em {organizacao.suspensa_em:%Y-%m-%d} ({organizacao.motivo_da_suspensao})"
        if organizacao.suspensa_em
        else "ativa"
    )
    linhas = [
        f"{organizacao.nome} ({organizacao.id}), plano {organizacao.plano_da_api}, {suspensa}",
        "Chaves (pelo prefixo):",
        *(
            f"  {c.prefixo}  {c.id}  {_estado_da_chave(c)}"
            for c in cb.listar_chaves(conexao, organizacao.id)
        ),
        f"Direitos vigentes em {hoje}:",
        *(
            f"  {d.id}  {d.conjunto}  {d.finalidade}  até {d.vigente_ate or 'sem fim'}"
            for d in cb.direitos_vigentes(conexao, organizacao.id, hoje)
        ),
    ]
    consumo = cb.consumo_do_mes(conexao, organizacao.id, hoje)
    linhas.append(
        f"Consumo de {hoje:%Y-%m} (UTC): pedidos {consumo.pedidos}, "
        f"linhas {consumo.linhas}, negados {consumo.negados}"
    )
    return "\n".join(linhas)


Comando = Callable[[sa.Connection, argparse.Namespace, uuid.UUID], str]


# ---------------------------------------------------------------- argumentos


def _montar_argumentos() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/chaves_da_api.py",
        description="Administra as organizações, chaves e direitos da API externa.",
    )
    parser.add_argument(
        "--admin",
        help=f"e-mail de quem pede (precisa estar em {VARIAVEL_DOS_ADMINS})",
    )
    comandos = parser.add_subparsers(dest="comando", required=True)

    def comando(nome: str, funcao: Comando, ajuda: str) -> argparse.ArgumentParser:
        sub = comandos.add_parser(nome, help=ajuda)
        sub.set_defaults(funcao=funcao)
        return sub

    def com_organizacao(sub: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sub.add_argument("organizacao", type=uuid.UUID, help="id da organização")
        return sub

    criar = comando("criar-organizacao", _criar_organizacao, "cria uma organização")
    criar.add_argument("--nome", required=True)
    criar.add_argument("--cnpj")
    criar.add_argument("--plano", choices=PLANOS_DA_API, default=PLANOS_DA_API[0])

    conceder = com_organizacao(
        comando("conceder-direito", _conceder_direito, "uma linha do contrato")
    )
    conceder.add_argument("--conjunto", required=True)
    conceder.add_argument(
        "--finalidade", choices=FINALIDADES_DA_ORGANIZACAO, required=True
    )
    conceder.add_argument("--desde", type=date.fromisoformat, required=True)
    conceder.add_argument("--ate", type=date.fromisoformat)

    for nome, funcao, ajuda in (
        ("suspender-direito", _suspender_direito, "o conjunto para de sair"),
        ("reativar-direito", _reativar_direito, "o conjunto volta a sair"),
    ):
        com_organizacao(comando(nome, funcao, ajuda)).add_argument(
            "direito", type=uuid.UUID
        )

    com_organizacao(comando("emitir-chave", _emitir_chave, "uma chave nova"))
    for nome, funcao, ajuda in (
        ("rotacionar-chave", _rotacionar_chave, "troca a chave, com prazo"),
        ("revogar-chave", _revogar_chave, "a chave para de entrar na hora"),
    ):
        com_organizacao(comando(nome, funcao, ajuda)).add_argument(
            "chave", type=uuid.UUID, help="id da chave (o `ver` mostra)"
        )

    suspender = com_organizacao(
        comando(
            "suspender-organizacao", _suspender_organizacao, "todas as chaves param"
        )
    )
    suspender.add_argument("--motivo", choices=MOTIVOS_DA_SUSPENSAO, required=True)
    com_organizacao(
        comando("reativar-organizacao", _reativar_organizacao, "as chaves voltam")
    )
    com_organizacao(comando("ver", _ver, "chaves, direitos e consumo do mês"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _montar_argumentos().parse_args(argv)
    motor = criar_engine(url_do_banco())
    try:
        with motor.begin() as conexao:
            ator = _ator(conexao, _escolher_admin(args.admin))
            texto = args.funcao(conexao, args, ator)
    except PermissaoNegadaError as erro:
        print(f"Recusado: {erro}", file=sys.stderr)
        return SAIDA_RECUSA
    except (NadaMudouError, *ERROS_ESPERADOS) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return SAIDA_ERRO
    finally:
        motor.dispose()
    # só depois do commit: uma chave mostrada e desfeita seria uma chave que não entra
    print(texto)
    return SAIDA_OK


if __name__ == "__main__":
    sys.exit(main())
