"""Quem entra nas rotas da Administração (`/v1/admin`), e como o corpo de um pedido é lido lá.

Fica à parte para os módulos de rotas da Administração (`administracao`, das organizações e chaves,
`administracao_contas`, das contas do app, e `administracao_registro`, do registro de ações) usarem a
mesma conferência, e não uma cópia dela.

Quem entra: a conta logada, com os termos aceitos **e** administradora no banco, conferida a cada pedido por
`conta_admin`. A Administração tem um `router` só, o daqui, que já nasce com `dependencias_do_admin()`: os
módulos de rotas registram as suas nele, então uma rota nova já nasce fechada (há teste que cobra, rota por
rota). Para qualquer outra conta a resposta é o mesmo 404 de um endereço que não existe, antes de ler o que
foi pedido.
"""

from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from src.administracao import PermissaoNegadaError, exigir_admin
from src.api_v1.acesso import conta_logada, exigir_api_ligada
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario

PEDIDO_INVALIDO = "Pedido inválido: confira os campos."


def conta_admin(conta: Annotated[Usuario, Depends(conta_logada)]) -> Usuario:
    """A conta logada, se for administradora agora (papel e bloqueio relidos do banco); senão o 404 de um
    endereço que não existe."""
    with obter_engine().connect() as conexao:
        try:
            exigir_admin(conexao, conta.id)
        except PermissaoNegadaError as erro:
            # o mesmo corpo da rota inexistente
            raise HTTPException(status_code=404) from erro
    return conta


def sem_cache(resposta: Response) -> None:
    """Nada da Administração fica guardado no navegador nem num intermediário."""
    resposta.headers["Cache-Control"] = "no-store"


Admin = Annotated[Usuario, Depends(conta_admin)]


def dependencias_do_admin() -> list[Any]:
    """As dependências do router da Administração, na ordem: `conta_admin` vem antes de tudo o que a
    rota lê, então a recusa não depende do que foi pedido."""
    return [Depends(exigir_api_ligada), Depends(conta_admin), Depends(sem_cache)]


# o router único da Administração: os módulos de rotas (`administracao`, `administracao_contas` e
# `administracao_registro`) registram as suas aqui, e o app o recebe por `src/api_v1/administracao.py`
router = APIRouter(prefix="/v1/admin", dependencies=dependencias_do_admin())


@contextmanager
def leitura() -> Iterator[sa.Connection]:
    """Uma conexão só de leitura. As funções da regra conferem o administrador de novo nela; se
    recusarem (a conta deixou de ser administradora entre a dependência e a leitura), a resposta é o
    mesmo 404 de um endereço que não existe."""
    try:
        with obter_engine().connect() as conexao:
            yield conexao
    except PermissaoNegadaError as erro:
        raise HTTPException(status_code=404) from erro


class Pedido(BaseModel):
    """A base do corpo de um pedido da Administração: campo a mais é recusado."""

    model_config = ConfigDict(extra="forbid")


def corpo[M: BaseModel](modelo: type[M]) -> Callable[[Request], Coroutine[Any, Any, M]]:
    """A dependência que lê o corpo do pedido como `modelo`.

    A rota não declara o corpo como parâmetro de propósito: o FastAPI leria o JSON antes das dependências,
    e a resposta a quem não é administrador dependeria do que foi mandado. Assim o corpo só é lido depois
    de `conta_admin` (as dependências do router vêm antes das da rota; há teste que cobra)."""

    async def ler(pedido: Request) -> M:
        try:
            return modelo.model_validate_json(await pedido.body())
        except ValidationError:
            # sem encadear: o erro do pydantic repete o que veio no pedido
            raise HTTPException(status_code=422, detail=PEDIDO_INVALIDO) from None

    return ler
