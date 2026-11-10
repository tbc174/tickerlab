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
    # prospecting: a busca de empresas (linha 794)
    "empresas": "companies",
    "proximo_cursor": "next_cursor",
    "porte": "size",
    "cnae_principal": "cnae_code",
    "uf": "state_code",
    "municipio": "municipality",
    "data_inicio_atividade": "opened_at",
    # sectors: o mercado do setor (molde D, linha 781)
    "setor": "sector",
    "setores": "sectors",
    "por_serie": "by_series",
    "serie": "series",
    "concentracao": "concentration",
    "participacao_dos_membros": "member_shares",
    "membros": "members",
    "avisos": "notes",
    "ano": "year",
    "participantes": "participants",
    "total": "market_total",
    "cr4": "cr4",
    "hhi": "hhi",
    "faixa": "concentration_band",
    "delta_hhi": "hhi_change",
    "meses": "months_of_data",
    "ultimo_mes": "last_month",
    "por_entidade": "share_counted_by_entity",
    "empresa": "company_name",
    "participacao": "market_share",
    "motivo": "membership_reason",
    # credit: os fatos da ficha de crédito (linha 754)
    "situacao_cadastral_na_receita": "rfb_registration_status",
    "situacao_especial_na_receita": "rfb_special_status",
    "fatos_relevantes_12_meses": "material_facts_12m",
    "fundos_em_que_cede": "fidcs_as_assignor",
    "maior_participacao_como_cedente": "largest_assignor_share_in_a_fidc",
    "carteira_dos_fundos_em_que_cede": "fidc_receivables_as_assignor",
    "maior_inadimplencia_dos_fundos_em_que_cede": "highest_fidc_delinquency_as_assignor",
    # profiles: o perfil por CNPJ (linha 736, PR 2), o cadastro e as entregas de DFP e ITR como eram
    "cadastro_na_receita": "registration",
    "entregas": "periodic_filings",
    "prazo": "due_date",
    "primeira_entrega": "first_filed_on",
    "dias_uteis_de_atraso": "business_days_late",
    "situacao_da_entrega": "filing_status",
    # comparables: os pares da companhia aberta (linha 736, PR 3), com os números do último DFP
    "grupo_de_setores": "sector_group",
    "empresa_pedida": "subject_company",
    "pares": "peers",
    "medianas_dos_pares": "peer_medians",
    "exercicio": "fiscal_year_end",
    "receita": "revenue",
    "ebitda": "ebitda",
    "lucro_liquido": "net_income",
    "divida_liquida": "net_debt",
    "margem_ebitda": "ebitda_margin",
    "margem_liquida": "net_margin",
    "roe": "return_on_equity",
    "divida_liquida_sobre_ebitda": "net_debt_to_ebitda",
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
