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
    "capital_social": "share_capital",
    "n_estabelecimentos": "active_establishments",
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
    # events: os documentos do IPE e as trocas de auditor (linha 736, PR 4)
    "eventos": "events",
    "tipo_de_evento": "event_type",
    "protocolo": "filing_id",
    "categoria": "category",
    "link": "document_url",
    "efetiva_em": "effective_on",
    "anterior": "previous",
    "novo": "new",
    "anos_com_o_anterior": "years_with_previous",
    # links: os vínculos da empresa na rede, pelo FRE e pelo FCA (linha 736, PR 5)
    "vinculos": "links",
    "profundidade": "depth",
    "salto": "hops",
    "de": "from",
    "para": "to",
    "id_na_rede": "entity_id",
    "raiz_do_cnpj": "cnpj_root",
    "participacao_no_capital": "ownership_pct",
    # buyers: quem já se mexeu num setor (linha 810, PR 4), só pessoa jurídica
    "compradores": "buyers",
    "total_de_compradores": "total_buyers",
    "sinais": "signals",
    "provas": "evidence",
    "quantas": "count",
    "exemplos": "examples",
    "desde": "since",
    "empresas_ativas": "active_companies",
    "empresa_do_setor": "sector_company",
    "data_entrada": "entry_date",
    "ainda_socio": "stake_still_held",
    "entrou_como_socio": "took_stake",
    "fundo_socio": "fund_stake",
    "controla_no_setor": "controls_in_sector",
    # research: as fontes que a pesquisa provou (linha 830), só órgão público
    "gerado_em": "generated_at",
    "dias": "days",
    "total_de_novidades": "total_news",
    "orgao": "agency",
    "fonte_url": "source_url",
    "data": "date",
    "trecho": "excerpt",
    "recorte": "excerpt_cut",
    "sha256": "original_sha256",
    "posicao": "location",
    # assets: os ativos físicos nas bases das agências (linha 845), só pessoa jurídica
    "contratos_de_petroleo_e_gas": "oil_gas_contracts",
    "barragens_de_mineracao": "mining_dams",
    "royalties_de_mineracao": "mining_royalties",
    "achou": "found",
    "dado_mais_novo": "latest_published_at",
    "cobertura": "coverage",
    "nao_coberto": "not_covered",
    "periodo": "period",
    "numero_do_contrato": "contract_number",
    "bid": "bid_round",
    "fase": "phase",
    "nome_fantasia": "field_or_block_name",  # na ANP, o nome do campo ou do bloco do contrato
    "bacia": "basin",
    "ambiente": "onshore_offshore",
    "participacao_pct": "contract_share_pct",
    "operador": "is_operator",
    "id": "dam_id",  # no SIGBM, o identificador da barragem
    "nome_mina": "mine_name",
    "categoria_risco": "risk_category",
    "dano_potencial": "potential_damage",
    "nivel_emergencia": "emergency_level",
    "situacao_operacional": "operating_status",
    "altura_atual_m": "height_m",
    "volume_atual_m3": "reservoir_volume_m3",
    "processo": "mining_process",
    "substancia": "substance",
    "valor_recolhido": "cfem_paid_brl",
    "recolhido_12_meses": "cfem_paid_last_12_months_brl",
    "ultima_competencia": "last_paid_month",
    "Tipo_Fundo": "fund_type",  # o campo do portão do sinal do FIP (não sai como chave)
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
