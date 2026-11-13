"""Ajudantes dos testes do chat (linha 903): o dublê do modelo e a caixa de ferramentas sobre a API de
mentira. Nenhuma chamada paga: o dublê devolve voltas escritas no teste e guarda o que recebeu.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence

import httpx

from src.chat.conversa import (
    ChamadaDeFerramenta,
    FimDoTurno,
    ParteDoTurno,
    PedidoAoModelo,
    TextoParcial,
)
from src.chat.custo import UsoDoModelo
from src.chat.ferramentas import CaixaDeFerramentas
from src.planos import LIMITES_DO_CHAT, LimitesDoChat
from tests.ajudantes_do_conector import CHAVE_DE_MENTIRA, api_de_mentira

USO_DA_VOLTA = UsoDoModelo(entrada=1_000, saida=200, cache_lido=500, cache_gravado=100)
SETORES = {"sectors": [{"key": "bancos", "name": "Bancos", "source": "tickerlab"}]}
ROTAS = {"/sectors": httpx.Response(200, json=SETORES)}


def pede(*chamadas: tuple[str, object], texto: str = "") -> list[ParteDoTurno]:
    """Uma volta em que o modelo pede ferramentas (`stop_reason` "tool_use")."""
    pedidas = tuple(
        ChamadaDeFerramenta(id=f"toolu_{i}", nome=nome, entrada=entrada)
        for i, (nome, entrada) in enumerate(chamadas)
    )
    conteudo: list[object] = [{"type": "text", "text": texto}] if texto else []
    conteudo += [
        {"type": "tool_use", "id": c.id, "name": c.nome, "input": c.entrada}
        for c in pedidas
    ]
    partes: list[ParteDoTurno] = [TextoParcial(texto)] if texto else []
    partes.append(FimDoTurno(conteudo, pedidas, "tool_use", USO_DA_VOLTA))
    return partes


def responde(*pedacos: str, parada: str = "end_turn") -> list[ParteDoTurno]:
    """Uma volta que termina com texto."""
    conteudo = [{"type": "text", "text": "".join(pedacos)}]
    return [
        *(TextoParcial(p) for p in pedacos),
        FimDoTurno(conteudo, (), parada, USO_DA_VOLTA),
    ]


class ModeloDeMentira:
    """O `Modelo` dos testes: cada `turno` devolve a próxima volta do roteiro."""

    def __init__(self, *voltas: Sequence[ParteDoTurno | Exception]) -> None:
        self._voltas = list(voltas)
        self.pedidos: list[PedidoAoModelo] = []

    async def turno(self, pedido: PedidoAoModelo) -> AsyncIterator[ParteDoTurno]:
        # a lista de mensagens é a mesma que a conversa continua enchendo: guarda a foto dela agora
        self.pedidos.append(
            PedidoAoModelo(
                pedido.sistema,
                pedido.ferramentas,
                list(pedido.mensagens),
                pedido.max_tokens,
            )
        )
        volta = self._voltas.pop(0)
        for parte in volta:
            if isinstance(parte, Exception):
                raise parte
            yield parte


def caixa_de_mentira(
    rotas: dict[str, httpx.Response] | None = None,
    limites: LimitesDoChat = LIMITES_DO_CHAT,
) -> CaixaDeFerramentas:
    return asyncio.run(
        CaixaDeFerramentas.abrir(
            api_de_mentira(ROTAS if rotas is None else rotas),
            identificador="chat:teste",
            limites=limites,
            chave=CHAVE_DE_MENTIRA,
        )
    )


def transporte_de_mentira(rotas: dict[str, httpx.Response] | None = None):
    """A API de mentira aceitando a chave interna do chat (é a que a rota usa)."""
    from src.chat.ferramentas import CHAVE_INTERNA

    dentro = api_de_mentira(ROTAS if rotas is None else rotas)

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.headers.get("authorization") != f"Bearer {CHAVE_INTERNA}":
            return httpx.Response(401, json={"detail": "invalid_api_key"})
        pedido.headers["authorization"] = f"Bearer {CHAVE_DE_MENTIRA}"
        return dentro.handle_request(pedido)

    return httpx.MockTransport(responder)
