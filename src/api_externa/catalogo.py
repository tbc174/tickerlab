"""O catálogo e o consumo da organização na API externa (B-32a, PR 1).

O catálogo diz o que **esta chave** pode ver hoje: cada campo com linha no portão (N3) para um conjunto
e uma finalidade que o contrato da organização (N7) também tem. Passa pelas mesmas duas travas que um
pedido de dado (`acesso.autorizar`), então nada que seria negado aparece, nem o motivo. O consumo é o do
mês da própria organização, com o que falta da quota.

As chaves saem em português; a rota traduz na saída.
"""

from collections.abc import Iterable
from datetime import date

import sqlalchemy as sa

from src.api_externa import envelope
from src.api_externa.acesso import autorizar
from src.api_externa.conjuntos import novidades
from src.api_externa.nomes import para_fora
from src.banco.chaves_da_api import consumo_do_mes, direitos_vigentes
from src.chaves_da_api import ContextoDaChave
from src.planos import limites_da_api
from src.portao_externo import Canal, LinhaDeDireito, Regras, regras_vigentes


def _linhas_liberadas(
    conexao: sa.Connection,
    contexto: ContextoDaChave,
    hoje: date,
    regras: Regras,
) -> Iterable[LinhaDeDireito]:
    contratados = {
        (direito.conjunto, direito.finalidade)
        for direito in direitos_vigentes(conexao, contexto.organizacao_id, hoje)
    }
    for linha in regras.linhas:
        if linha.canal != Canal.API_EXTERNA:
            continue
        if (linha.conjunto, linha.finalidade.value) not in contratados:
            continue
        decisao = autorizar(
            conexao,
            contexto,
            fonte=linha.fonte,
            conjunto=linha.conjunto,
            campo=linha.campo,
            finalidade=linha.finalidade.value,
            hoje=hoje,
            regras=regras,
        )
        if decisao.libera:
            yield linha


def catalogo_da_organizacao(
    conexao: sa.Connection,
    contexto: ContextoDaChave,
    hoje: date,
    regras: Regras | None = None,
) -> dict[str, object]:
    """Os conjuntos, com os campos e as fontes, que a chave pode pedir no dia; vazio se nada."""
    por_conjunto: dict[tuple[str, str], list[dict[str, str]]] = {}
    fontes: set[str] = set()
    for linha in _linhas_liberadas(
        conexao, contexto, hoje, regras or regras_vigentes()
    ):
        chave = (linha.conjunto, linha.finalidade.value)
        por_conjunto.setdefault(chave, []).append(
            {"campo": para_fora(linha.campo), "fonte": linha.fonte}
        )
        fontes.add(linha.fonte)
    for direito in direitos_vigentes(conexao, contexto.organizacao_id, hoje):
        # `research` não tem campo no dicionário (é arquivo de citações): o contrato basta para listar
        if direito.conjunto == novidades.CONJUNTO:
            por_conjunto.setdefault((direito.conjunto, direito.finalidade), [])
    conjuntos = [
        {"conjunto": conjunto, "finalidade": para_fora(finalidade), "campos": campos}
        for (conjunto, finalidade), campos in sorted(por_conjunto.items())
    ]
    return {"conjuntos": conjuntos, "fontes": envelope.fontes_da_resposta(fontes)}


def consumo_da_organizacao(
    conexao: sa.Connection, contexto: ContextoDaChave, dia: date
) -> dict[str, object]:
    """O consumo do mês (UTC) da organização da chave, os limites do plano e o que falta."""
    consumo = consumo_do_mes(conexao, contexto.organizacao_id, dia)
    limites = limites_da_api(contexto.plano_da_api)
    return {
        "mes": dia.strftime("%Y-%m"),
        "pedidos": consumo.pedidos,
        "linhas": consumo.linhas,
        "negados": consumo.negados,
        "plano": contexto.plano_da_api,
        "limites": {
            "por_minuto": limites.pedidos_por_minuto,
            "por_mes": limites.pedidos_por_mes,
            "linhas_por_resposta": limites.linhas_por_resposta,
        },
        "restantes": max(0, limites.pedidos_por_mes - consumo.pedidos),
    }
