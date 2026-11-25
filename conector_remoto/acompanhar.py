"""A ferramenta `acompanhar_empresas` (linha 980, onda 2, PR 1): o que mudou em 2 a 5 empresas desde um dia.

É o `o_que_mudou` repetido por empresa (`ferramentas_do_analista.diferenca_da_empresa`), sem rota nova e com os
mesmos conjuntos: a lista que o analista acompanha vem no pedido e não é guardada (guardar pediria migração do
banco). As empresas saem na ordem pedida, sem nota nem ordenação; a que não mudou vem numa linha só, e as fontes e
os avisos, uma vez só no topo. Cada empresa traz até `limite` mudanças por lista: a ferramenta `o_que_mudou` traz o
resto de uma empresa só.
"""

import asyncio
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from conector_remoto.cliente_api import RespostaDaApi
from conector_remoto.enxugar import enxugar_o_que_mudou
from conector_remoto.ferramentas import Pedidos, anunciar, cnpj_do_pedido
from conector_remoto.ferramentas_do_analista import (
    MOTIVO_NAO_DISPONIVEL,
    BlocosPedidos,
    Desde,
    EmpresaNaoDisponivel,
    diferenca_da_empresa,
    exigir_desde_no_passado,
    juntar_sem_repetir,
)

NOME = "acompanhar_empresas"
MINIMO_DE_EMPRESAS = 2
# cada empresa faz até 6 pedidos (3 blocos x 2 dias) e a organização tem 60 por minuto: 5 empresas usam metade
MAXIMO_DE_EMPRESAS = 5
LIMITE_PADRAO_POR_LISTA = 5
LIMITE_MAXIMO_POR_LISTA = 50
# o que vai uma vez só no topo, não em cada empresa
DO_TOPO = ("since", "until", "limits", "sources")
AVISO_DA_LISTA = {
    "code": NOME,
    "text": (
        "Cada empresa da lista é um `o_que_mudou` desde o mesmo dia, na ordem pedida, sem nota nem ordenação. A "
        "empresa sem mudança vem só com `changes_found` 0; a que a base não serve, em `not_available`. Quando "
        "`changes_shown` é menor que `changes_found`, há mais mudanças do que cabem por lista: `o_que_mudou` "
        "com o CNPJ dela traz o resto."
    ),
}

Cnpjs = Annotated[
    list[Annotated[str, Field(max_length=40)]],
    Field(
        description=(
            f"De {MINIMO_DE_EMPRESAS} a {MAXIMO_DE_EMPRESAS} CNPJs (14 caracteres; com ou sem pontuação), a lista "
            "que o analista acompanha. Só pessoa jurídica."
        )
    ),
]
LimitePorLista = Annotated[
    int | None,
    Field(
        ge=1,
        le=LIMITE_MAXIMO_POR_LISTA,
        description=(
            "No máximo quantas mudanças trazer por lista de cada empresa (alteradas, novas e removidas de cada "
            f"bloco). Sem ele, {LIMITE_PADRAO_POR_LISTA}."
        ),
    ),
]


def cnpjs_da_lista(textos: list[str]) -> list[str]:
    """Os CNPJs pedidos, só números e na ordem; `ToolError` se são menos de 2, mais de 5, repetidos ou não são
    CNPJ (antes de qualquer pedido à API)."""
    if not MINIMO_DE_EMPRESAS <= len(textos) <= MAXIMO_DE_EMPRESAS:
        raise ToolError(
            f"Acompanhe de {MINIMO_DE_EMPRESAS} a {MAXIMO_DE_EMPRESAS} empresas por vez: vieram {len(textos)}. "
            "Para mais, divida a lista em duas chamadas."
        )
    numeros = [cnpj_do_pedido(texto) for texto in textos]
    if len(set(numeros)) != len(numeros):
        raise ToolError("Há CNPJ repetido na lista: cada empresa entra uma vez.")
    return numeros


def _nao_consultados_pela_chave(diferencas: Iterable[dict]) -> list[object]:
    """Os blocos que a chave não vê ou o analista não pediu: iguais em toda empresa, saem uma vez no topo."""
    return juntar_sem_repetir(
        [
            {
                "not_consulted": [
                    b
                    for b in d.get("not_consulted", [])
                    if b.get("reason") != MOTIVO_NAO_DISPONIVEL
                ]
            }
            for d in diferencas
        ],
        "not_consulted",
    )


def _da_empresa(diferenca: dict, limite: int) -> dict[str, object]:
    """A linha da empresa: só o CNPJ e a contagem se nada mudou; senão, os blocos enxutos e o que a base não serviu
    dela (o bloco que a chave não vê sai no topo)."""
    da_base = [
        b
        for b in diferenca.get("not_consulted", [])
        if b.get("reason") == MOTIVO_NAO_DISPONIVEL
    ]
    if not diferenca.get("changes_found"):
        linha: dict[str, object] = {"cnpj": diferenca["cnpj"], "changes_found": 0}
    else:
        enxuta = enxugar_o_que_mudou(diferenca, limite=limite)
        linha = {
            chave: valor
            for chave, valor in (
                enxuta if isinstance(enxuta, dict) else diferenca
            ).items()
            if chave not in DO_TOPO and chave != "not_consulted"
        }
    # sem mudança não quer dizer nada se um bloco a base não serviu: o bloco vai junto, nas duas formas
    if da_base:
        linha["not_available_blocks"] = da_base
    return linha


def montar_a_lista(
    diferencas: dict[str, dict | None], limite: int, desde: date
) -> dict[str, object]:
    """A resposta da ferramenta, da diferença de cada empresa na ordem pedida (`None`: a base não a serve)."""
    servidas = [d for d in diferencas.values() if d is not None]
    ate = next((d["until"] for d in servidas if d.get("until")), None)
    return {
        "since": desde.isoformat(),
        "until": ate or datetime.now(UTC).date().isoformat(),
        "companies_with_changes": sum(1 for d in servidas if d.get("changes_found")),
        "companies": [_da_empresa(d, limite) for d in servidas],
        "not_available": [cnpj for cnpj, d in diferencas.items() if d is None],
        "not_consulted": _nao_consultados_pela_chave(servidas),
        "limits": [*juntar_sem_repetir(list(servidas), "limits"), AVISO_DA_LISTA],
        "sources": juntar_sem_repetir(list(servidas), "sources"),
    }


async def _diferenca_ou_nada(
    pedidos: Pedidos, numeros: str, desde: date, blocos: list[str] | None
) -> dict | None:
    """A diferença da empresa, ou `None` se a base não a serve (as outras da lista seguem)."""
    try:
        return await diferenca_da_empresa(
            pedidos, numeros, desde, blocos, ferramenta=NOME
        )
    except EmpresaNaoDisponivel:
        return None


def registrar(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Põe a ferramenta no servidor (chamada por `registrar_ferramentas`)."""

    @anunciar(servidor, NOME)
    async def acompanhar_empresas(
        cnpjs: Cnpjs,
        desde: Desde,
        blocos: BlocosPedidos = None,
        limite: LimitePorLista = None,
    ) -> str:
        numeros = cnpjs_da_lista(cnpjs)
        exigir_desde_no_passado(desde)
        pedidos_dos_blocos = list(blocos) if blocos else None
        # as empresas correm juntas: a espera é a de uma empresa, não a soma de cinco
        resultados = await asyncio.gather(
            *(
                _diferenca_ou_nada(pedidos, n, desde, pedidos_dos_blocos)
                for n in numeros
            ),
            return_exceptions=True,
        )
        diferencas: dict[str, dict | None] = {}
        for numero, resultado in zip(numeros, resultados, strict=True):
            if isinstance(resultado, BaseException):
                raise resultado
            diferencas[numero] = resultado
        corpo = montar_a_lista(diferencas, limite or LIMITE_PADRAO_POR_LISTA, desde)
        return pedidos.entregar(RespostaDaApi(200, corpo), NOME)
