"""A tabela única de nomes da API externa: português dentro, inglês fora (ADR 0108, D6 e D7).

Quem integra lê endereços, campos e códigos em inglês; as tabelas, os contratos e o código continuam em
português. A tradução mora só aqui, e um nome sem tradução não sai (`para_fora` levanta `KeyError`):
assim um campo novo não escapa para fora sem ter passado por esta tabela. Há teste que impede o nome de
fora de virar coluna do dicionário ou chave de contrato.

Identificadores que já são os mesmos nas duas línguas (o CNPJ) passam como estão.
"""

from collections.abc import Mapping

IDENTIFICADORES = frozenset({"cnpj", "cnpjs"})

NOMES_DE_FORA: Mapping[str, str] = {
    # os tempos (D6)
    "publico_em": "published_at",
    "visto_em": "observed_at",
    "referencia": "reference_period",
    "versao": "revision",
    "aconteceu_em": "valid_from",
    "coletado_em": "collected_at",
    "como_era_em": "known_at",
    "valia_em": "valid_at",
    # o envelope de cada campo e as fontes da resposta
    "valor": "value",
    "fonte": "source",
    "fontes": "sources",
    "licenca": "license",
    "atribuicao": "attribution",
    # o catálogo
    "conjuntos": "datasets",
    "conjunto": "dataset",
    "finalidade": "purpose",
    "campos": "fields",
    "campo": "field",
    "analise": "analysis",
    "credito": "credit",
    "treino": "training",
    # o consumo e os limites
    "mes": "month",
    "pedidos": "requests",
    "linhas": "rows",
    "negados": "denied",
    "plano": "plan",
    "limites": "limits",
    "por_minuto": "requests_per_minute",
    "por_mes": "requests_per_month",
    "linhas_por_resposta": "rows_per_response",
    "restantes": "remaining_requests",
    # o lote
    "itens": "items",
    "situacao_do_item": "status",
    "maximo_do_lote": "max_batch_size",
}


def para_fora(nome: str) -> str:
    """O nome que sai pela API. `KeyError` se o nome não tem tradução (e então não deve sair)."""
    if nome in IDENTIFICADORES:
        return nome
    return NOMES_DE_FORA[nome]


def traduzir_chaves(dentro: object) -> object:
    """Troca toda chave de dicionário, em qualquer profundidade, pelo nome de fora; os valores ficam."""
    if isinstance(dentro, Mapping):
        return {
            para_fora(str(chave)): traduzir_chaves(valor)
            for chave, valor in dentro.items()
        }
    if isinstance(dentro, list | tuple):
        return [traduzir_chaves(item) for item in dentro]
    return dentro
