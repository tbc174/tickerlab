"""A tabela única de nomes da API externa: português dentro, inglês fora (ADR 0108, D6 e D7).

Quem integra lê endereços, campos e códigos em inglês; as tabelas, os contratos e o código continuam em
português. A tradução mora só aqui, e um nome sem tradução não sai (`para_fora` levanta `KeyError`):
assim um campo novo não escapa para fora sem ter passado por esta tabela. Há teste que impede o nome de
fora de virar coluna do dicionário ou chave de contrato.

Identificadores que já são os mesmos nas duas línguas (o CNPJ) passam como estão.
"""

from collections.abc import Mapping

IDENTIFICADORES = frozenset({"cnpj", "cnpjs", "isin"})

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
    # Os campos dos conjuntos. A tradução vale para a coluna em toda tabela: nome genérico ("situacao",
    # "tipo", "inicio") ganha nome de fora genérico, e o sentido de cada um vai no catálogo do conjunto.
    # financials: as demonstrações como eram em cada entrega
    "demonstracao": "statement",
    "grupo": "group",
    "conta": "account",
    "descricao": "description",
    "inicio": "start",
    "fim": "end",
    "documento": "document",
    "origem": "origin",
    "ate": "valid_until",
    # funds: o cadastro, o custo da taxa e a carteira
    "nome": "name",
    "classe": "class",
    "situacao": "state",
    "taxa_administracao_pct_ao_ano": "management_fee_pct_per_year",
    "texto_taxa_administracao": "management_fee_note",
    "taxa_performance_pct": "performance_fee_pct",
    "texto_taxa_performance": "performance_fee_note",
    "patrimonio_liquido": "net_assets",
    "data_do_patrimonio_liquido": "net_assets_date",
    "sem_taxa": "without_fee",
    "com_taxa": "with_fee",
    "ficou_com_a_taxa": "fee_amount",
    "fracao_do_resultado": "fee_share_of_return",
    "competencia": "reporting_month",
    "codigo": "code",
    "emissor": "issuer",
    "tipo": "kind",
    "quantidade": "quantity",
    # funds: a forma da resposta
    "cadastro": "profile",
    "custo_da_taxa": "fee_cost",
    "hipotese": "assumptions",
    "capital_inicial": "initial_amount",
    "retorno_suposto": "assumed_return",
    "prazos": "horizons",
    "anos": "years",
    "carteira": "holdings",
    "posicoes": "positions",
    "cortada": "truncated",
    # companies: a situação cadastral da Receita
    "situacao_cadastral": "registration_status",
    "data_situacao_cadastral": "registration_status_date",
    "motivo_situacao": "registration_status_reason",
    "matriz": "head_office",
    "mes_do_retrato": "snapshot_month",
    # companies: o histórico datado do nome, da natureza jurídica e do Simples (linha 686)
    "razao_social": "legal_name",
    "natureza_juridica": "legal_nature_code",
    "optante_simples": "simples_nacional",
    "data_opcao_simples": "simples_nacional_since",
    "data_exclusao_simples": "simples_nacional_until",
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
