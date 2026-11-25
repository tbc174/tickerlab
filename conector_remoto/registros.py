"""A ferramenta `registros_nas_agencias` (linha 980, onda 2, PR 5): os registros da empresa nas agências.

Um pedido à rota `GET /companies/{cnpj}/registrations`, que abre só os blocos de agência reguladora do registro de
tabelas por CNPJ (`regulated_activities`: ANEEL e ANS; `additional_records`, com o conjunto `extended_sources`:
Anatel, ANM, ANP e PAT), cada um pelo portão do conjunto dele, sem abrir o resto da análise. A resposta tem o
formato `blocks` da análise completa, e o corte no teto da conversa é o mesmo (`enxugar_analise`).
"""

import dataclasses
from typing import Annotated, Literal

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

NOME = "registros_nas_agencias"
LIMITE_MAXIMO_POR_LISTA = 200
BLOCOS_DA_ROTA = ("regulated_activities", "additional_records")


def registrar(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Põe a ferramenta no servidor (chamada por `registrar_ferramentas`)."""

    @anunciar(servidor, NOME)
    async def registros_nas_agencias(
        cnpj: Cnpj,
        como_era_em: ComoEraEm = None,
        blocos: Annotated[
            list[Literal["regulated_activities", "additional_records"]] | None,
            Field(
                max_length=len(BLOCOS_DA_ROTA),
                description=(
                    "Só estes blocos, pelos nomes de `blocks`: regulated_activities (ANEEL e ANS) ou "
                    "additional_records (Anatel, ANM, ANP e PAT). Vazio = os que a chave vê."
                ),
            ),
        ] = None,
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
            f"/companies/{numeros}/registrations",
            {"known_at": como_era_em.isoformat() if como_era_em else None},
        )
        # a trava de pessoa lê a resposta inteira, também o que o corte deixa de fora
        pedidos.conferir_pessoa(resposta, NOME)
        if resposta.ok:
            resposta = dataclasses.replace(
                resposta,
                corpo=enxugar_analise(resposta.corpo, blocos=blocos, limite=limite),
            )
        return pedidos.entregar(resposta, NOME)
