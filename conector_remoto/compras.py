"""A ferramenta `compras_publicas` (linha 980, onda 2, PR 6): as compras públicas da empresa.

Um pedido à rota `GET /companies/{cnpj}/public-procurement`, que abre só o bloco `public_procurement` da análise (o
cadastro de fornecedor no SICAF e as compras de saúde do BPS), no conjunto `public_procurement`, desligado por
padrão: a ferramenta só aparece para a chave com esse conjunto no contrato. A resposta tem o formato `blocks` da
análise completa, e o corte no teto da conversa é o mesmo (`enxugar_analise`).
"""

import dataclasses
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from conector_remoto.enxugar import enxugar_analise
from conector_remoto.ferramentas import (
    Cnpj,
    ComoEraEm,
    Pedidos,
    anunciar,
    cnpj_do_pedido,
)

NOME = "compras_publicas"
LIMITE_MAXIMO_POR_LISTA = 200


def registrar(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Põe a ferramenta no servidor (chamada por `registrar_ferramentas`)."""

    @anunciar(servidor, NOME)
    async def compras_publicas(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        limite: Annotated[
            int | None,
            Field(
                ge=1,
                le=LIMITE_MAXIMO_POR_LISTA,
                description="No máximo tantos itens por lista, na ordem da API. Vazio = o que couber na conversa.",
            ),
        ] = None,
    ) -> str:
        numeros = cnpj_do_pedido(cnpj)
        resposta = await pedidos.resposta(
            f"/companies/{numeros}/public-procurement",
            {"known_at": como_era_em.isoformat() if como_era_em else None},
        )
        # a trava de pessoa lê a resposta inteira, também o que o corte deixa de fora
        pedidos.conferir_pessoa(resposta, NOME)
        if resposta.ok:
            resposta = dataclasses.replace(
                resposta, corpo=enxugar_analise(resposta.corpo, limite=limite)
            )
        return pedidos.entregar(resposta, NOME)
