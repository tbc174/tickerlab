"""O registro das tabelas ligadas pelo CNPJ que saem pela API externa campo a campo (linha 978, lote 1).

Uma entrada por tabela diz tudo o que o portão e a leitura precisam: a tabela, a fonte (ou as fontes, com a coluna
que diz qual é a da linha), o conjunto do contrato, o bloco e a chave do bloco na resposta, os campos servidos
como a fonte publicou, a coluna da data do fato, a regra da lista (só a data mais nova, uma linha por chave, a
ordem), a licença (que vira a prova da linha de direito) e a frase do que a base cobre.

- `src/portao_externo.py` gera daqui linhas de `DIREITOS_DA_API_EXTERNA`: uma por fonte e campo, no conjunto da entrada e declarando a tabela, para a prontidão (cheia ou de piloto) se conferir nela.
- `src/api_externa/conjuntos/por_tabela.py` lê cada entrada para a análise completa (`ONDE_SAI = ANALISE`) ou
  para a rota do fundo (`ONDE_SAI = FUNDO`).

Tabela nova que tem a raiz do CNPJ (`cnpj_basico`), `disponivel_em` e o contrato com a marca de pessoa entra com
uma entrada aqui, sem mudar a leitura: o bloco abre quando o portão libera um campo dela. O módulo só tem dados
(o portão o importa; nada daqui importa o portão).

Fica de fora, com o porquê:
- `pgfn_divida`: a tabela é agregada; a dívida por inscrição é a linha 979 da fila;
- campos cujo nome a trava do D2.4 nega (`cotistas_pessoa_fisica`, `cnpj_administrador`): a lista dos fundos que
  uma administradora administra espera decisão da Diretoria, porque a ligação é justamente essa coluna;
- o texto livre `motivo_do_cancelamento` do cadastro de administradores (pode trazer nome de pessoa);
- a `faixa` do IDSS: o nome de fora de `faixa` já é o da faixa de concentração dos setores (um nome por coluna);
- de CGU, IBAMA e MTE (conjunto de integridade, ADR 0122, Emenda 1): o texto livre que pode trazer nome de pessoa
  (`nome` e `situacao_do_termo` do embargo; `empregador` e `estabelecimento` da lista suja, que é o endereço da
  propriedade), o `processo` (o nome de fora de `processo` já é o do processo minerário) e o `cadastro` (a fonte
  de cada campo já diz de que cadastro da CGU ele vem).

As entradas de integridade têm `marca_de_pessoa`: a leitura só serve a linha com a marca falsa (MEI, empresário
individual e linha sem a marca nunca saem, nem na contagem) e confere todo texto servido contra CPF e e-mail.
"""

from dataclasses import dataclass

# onde a entrada sai
ANALISE = "analise"
FUNDO = "fundo"
# a licença de cada entrada (a prova da linha de direito sai do portão por esta chave)
LICENCA_DA_CVM = "cvm"
LICENCA_DAS_AGENCIAS = "agencias"
LICENCA_DE_INTEGRIDADE = "integridade"
LICENCA_SEM_TRAVA = "sem_trava"
LICENCA_DE_COMPRAS_PUBLICAS = "compras_publicas"
# a coluna que liga a tabela à empresa: a raiz do CNPJ (o fundo se confere depois pelo CNPJ inteiro)
RAIZ = "cnpj_basico"
CNPJ = "cnpj"
# os blocos da análise e da rota do fundo
REGULADOS = "regulados"
BALANCO_NO_BC = "balanco_no_bc"
ADMINISTRADORA_DE_FII = "administradora_de_fii"
INFORMES_DO_FUNDO = "informes_do_fundo"
SANCOES = "sancoes"
EMBARGOS_AMBIENTAIS = "embargos_ambientais"
LISTA_SUJA = "lista_suja"
REGISTROS_ADICIONAIS = "registros_adicionais"
COMPRAS_PUBLICAS = "compras_publicas"
# o conjunto do contrato das três (o mesmo nome de `src/banco/coletas.py::CONJUNTO_DE_INTEGRIDADE`; este módulo
# só tem dados e não importa o banco)
INTEGRIDADE = "integrity"
# o conjunto sem trava de licença (o mesmo nome de `src/banco/coletas.py::CONJUNTO_SEM_TRAVA_DE_LICENCA`; ADR 0122,
# Emenda 2): Anatel, ANM (TAH), ANP (tancagem) e o PAT do MTE, só para a organização com ele no contrato
SEM_TRAVA_DE_LICENCA = "extended_sources"
# o conjunto das compras públicas (o mesmo nome de `src/banco/coletas.py::CONJUNTO_DE_COMPRAS_PUBLICAS`; ADR 0122,
# Emenda 2; linha 988): o cadastro de fornecedores do SICAF e o Banco de Preços em Saúde, só para a organização com
# ele no contrato
CONJUNTO_DE_COMPRAS_PUBLICAS = "public_procurement"
# a marca de pessoa das tabelas de integridade (`base/sancoes.py`, `base/ibama_embargos.py`, `base/mte_lista_suja.py`)
TRATA_COMO_PESSOA = "trata_como_pessoa"


@dataclass(frozen=True)
class TabelaPorCnpj:
    """Uma tabela ligada pelo CNPJ que sai campo a campo.

    `fontes`: as fontes que alimentam a tabela; com mais de uma, `coluna_da_fonte` diz a da linha (o valor dela,
    em `fonte_pelo_valor`). `ordem`: as colunas da lista (`-` na frente: da maior para a menor), depois da data do
    fato (sempre da mais nova para a mais velha). `so_a_data_mais_nova`: a lista só tem a data do fato mais nova
    já pública no dia. `uma_por`: de cada valor destas colunas, só a primeira linha na ordem (a versão mais nova
    de um informe, por exemplo). `marca_de_pessoa`: a coluna que marca a linha de pessoa (MEI, empresário
    individual); com ela, só sai a linha com a marca falsa, e todo texto servido passa pela varredura de CPF e
    e-mail (achou: a resposta inteira cai, nunca sai um "não achou" falso). `diz_o_retrato`: a lista é a edição
    vigente de um cadastro em retratos (a lista suja do MTE), e o corpo diz o dia da mudança mais nova que a base viu
    nela até o dia pedido (`retrato_da_lista`); o registro que saiu da lista não aparece, nem como situação atual."""

    tabela: str
    fontes: tuple[str, ...]
    conjunto: str
    onde_sai: str
    bloco: str
    chave: str
    campos: tuple[str, ...]
    data_do_fato: str
    licenca: str
    cobertura: str
    ordem: tuple[str, ...] = ()
    so_a_data_mais_nova: bool = False
    uma_por: tuple[str, ...] = ()
    coluna_da_fonte: str | None = None
    fonte_pelo_valor: tuple[tuple[str, str], ...] = ()
    marca_de_pessoa: str | None = None
    diz_o_retrato: bool = False


REGISTRO: tuple[TabelaPorCnpj, ...] = (
    TabelaPorCnpj(
        tabela="aneel_indicadores_comerciais",
        fontes=("aneel-fiscalizacao",),
        conjunto="profiles",
        onde_sai=ANALISE,
        bloco=REGULADOS,
        chave="indicadores_comerciais_da_aneel",
        campos=(
            "sigla_do_agente",
            "tipo_de_outorga",
            "referencia",
            "municipio_ibge",
            "unidades_ativas",
            "unidades_faturadas",
            "faturas",
            "faturas_sem_leitura",
            "refaturamentos",
            "pedidos_de_ressarcimento_de_dano",
            "ressarcimentos_indeferidos",
            "valor_pago_de_ressarcimento",
            "postos_de_atendimento",
            "unidades_suspensas_por_inadimplencia",
            "suspensoes_indevidas",
            "valor_de_compensacao_por_suspensao_indevida",
        ),
        data_do_fato="referencia",
        licenca=LICENCA_DAS_AGENCIAS,
        cobertura=(
            "Indicadores comerciais das distribuidoras de energia na ANEEL (INDGER), por mês e município, do mês "
            "mais novo já público; a lista vem dos municípios com mais unidades consumidoras ativas."
        ),
        ordem=("-unidades_ativas", "municipio_ibge"),
        so_a_data_mais_nova=True,
    ),
    TabelaPorCnpj(
        tabela="ans_idss",
        fontes=("ans-qualidade",),
        conjunto="profiles",
        onde_sai=ANALISE,
        bloco=REGULADOS,
        chave="idss_da_ans",
        campos=(
            "registro_operadora",
            "modalidade",
            "indice",
            "ano_avaliacao",
            "ano_base",
            "valor",
        ),
        data_do_fato="ano_base",
        licenca=LICENCA_DAS_AGENCIAS,
        cobertura=(
            "Índice de Desempenho da Saúde Suplementar (IDSS) das operadoras de plano de saúde na ANS, do ano-base "
            "mais novo já público, com o índice geral e os de cada dimensão."
        ),
        ordem=("indice",),
        so_a_data_mais_nova=True,
    ),
    TabelaPorCnpj(
        tabela="ifdata_valores",
        fontes=("bcb-ifdata",),
        conjunto="financials",
        onde_sai=ANALISE,
        bloco=BALANCO_NO_BC,
        chave="ifdata",
        campos=(
            "data_base",
            "tipo_instituicao",
            "relatorio",
            "nome_relatorio",
            "grupo",
            "conta",
            "coluna",
            "descricao",
            "saldo",
        ),
        data_do_fato="data_base",
        licenca=LICENCA_DAS_AGENCIAS,
        cobertura=(
            "IF.data do Banco Central: balanço, resultado e capital da instituição financeira e do conglomerado "
            "que ela lidera, na data-base mais nova já pública (data-base mais 120 dias), a partir do resumo."
        ),
        ordem=("tipo_instituicao", "relatorio", "grupo", "conta", "coluna"),
        so_a_data_mais_nova=True,
    ),
    TabelaPorCnpj(
        tabela="fii_administradores",
        fontes=("cvm-fii-administradores",),
        conjunto="funds",
        onde_sai=ANALISE,
        bloco=ADMINISTRADORA_DE_FII,
        chave="registro_de_administradora",
        campos=(
            "razao_social",
            "nome_comercial",
            "situacao",
            "uf",
            "registrado_em",
            "cancelado_em",
            "situacao_desde",
        ),
        data_do_fato="registrado_em",
        licenca=LICENCA_DA_CVM,
        cobertura=(
            "Cadastro da CVM de administradores de fundos imobiliários (FII): o registro da empresa como "
            "administradora, com a situação e as datas."
        ),
    ),
    TabelaPorCnpj(
        tabela="fii_informe_mensal",
        fontes=("cvm-fii-mensal",),
        conjunto="funds",
        onde_sai=FUNDO,
        bloco=INFORMES_DO_FUNDO,
        chave="informe_mensal_do_fii",
        campos=(
            "referencia",
            "versao",
            "entregue_em",
            "tipo_fundo_classe",
            "nome_do_fundo",
            "publico_alvo",
            "codigo_isin",
            "fundo_exclusivo",
            "mandato",
            "segmento_de_atuacao",
            "tipo_de_gestao",
            "prazo_de_duracao",
            "negocia_em_bolsa",
            "funciona_desde",
            "cotistas",
            "valor_do_ativo",
            "patrimonio_liquido",
            "cotas_emitidas",
            "valor_patrimonial_da_cota",
            "taxa_de_administracao_pct",
            "rentabilidade_efetiva_no_mes",
            "rentabilidade_patrimonial_no_mes",
            "dividend_yield_no_mes",
        ),
        data_do_fato="referencia",
        licenca=LICENCA_DA_CVM,
        cobertura=(
            "Informe mensal do fundo imobiliário (FII) na CVM, um por mês de referência, na versão mais nova já "
            "entregue no dia."
        ),
        ordem=("-versao",),
        uma_por=("referencia",),
    ),
    TabelaPorCnpj(
        tabela="fip_informe",
        fontes=("cvm-fip-trimestral", "cvm-fip-quadrimestral"),
        conjunto="funds",
        onde_sai=FUNDO,
        bloco=INFORMES_DO_FUNDO,
        chave="informe_do_fip",
        campos=(
            "competencia",
            "periodicidade",
            "tipo_fundo_classe",
            "nome_do_fundo",
            "entidade_de_investimento",
            "publico_alvo",
            "patrimonio_liquido",
            "cotas",
            "valor_patrimonial_da_cota",
            "cotistas",
            "capital_comprometido",
            "capital_subscrito",
            "capital_integralizado",
            "investido_em_cotas_de_fip",
            "cotistas_empresa_nao_financeira",
            "cotistas_nao_residentes",
            "cotistas_previdencia_fechada",
            "cotistas_regime_proprio",
        ),
        data_do_fato="competencia",
        licenca=LICENCA_DA_CVM,
        cobertura=(
            "Informe periódico do fundo de investimento em participações (FIP) na CVM, por competência; cada "
            "informe traz a periodicidade."
        ),
        coluna_da_fonte="periodicidade",
        fonte_pelo_valor=(
            ("trimestral", "cvm-fip-trimestral"),
            ("quadrimestral", "cvm-fip-quadrimestral"),
        ),
    ),
    # CGU, IBAMA e MTE (ADR 0122, Emenda 1, 18/11/2026): só no conjunto de integridade, que se concede por linha
    # do contrato da organização; só a linha de pessoa jurídica
    TabelaPorCnpj(
        tabela="sancoes_cgu",
        fontes=("cgu-ceis", "cgu-cnep", "cgu-cepim", "cgu-leniencia"),
        conjunto=INTEGRIDADE,
        onde_sai=ANALISE,
        bloco=SANCOES,
        chave="sancoes_da_cgu",
        campos=(
            "categoria",
            "situacao",
            "assunto",
            "orgao",
            "uf_do_orgao",
            "esfera_do_orgao",
            "origem_da_informacao",
            "fundamentacao_legal",
            "abrangencia",
            "inicio",
            "fim",
            "publicado_em",
            "transito_em_julgado",
            "informado_em",
            "valor_multa",
        ),
        data_do_fato="inicio",
        licenca=LICENCA_DE_INTEGRIDADE,
        cobertura=(
            "Cadastros da CGU no Portal da Transparência: empresas inidôneas e suspensas (CEIS), punidas pela "
            "Lei Anticorrupção (CNEP), entidades sem fins lucrativos impedidas (CEPIM) e acordos de leniência; "
            "cada registro como a CGU publicou, enquanto consta do cadastro. Pelo known_at, o registro conta como público a partir do último dia do mês em que apareceu."
        ),
        ordem=("categoria",),
        coluna_da_fonte="cadastro",
        fonte_pelo_valor=(
            ("ceis", "cgu-ceis"),
            ("cnep", "cgu-cnep"),
            ("cepim", "cgu-cepim"),
            ("leniencia", "cgu-leniencia"),
        ),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    TabelaPorCnpj(
        tabela="ibama_embargos",
        fontes=("ibama-embargos",),
        conjunto=INTEGRIDADE,
        onde_sai=ANALISE,
        bloco=EMBARGOS_AMBIENTAIS,
        chave="embargos_do_ibama",
        campos=(
            "numero_do_termo",
            "numero_do_auto",
            "embargada_em",
            "area_embargada_ha",
            "uf",
            "codigo_do_municipio",
            "cancelado",
            "desembargado",
            "desembargada_em",
        ),
        data_do_fato="embargada_em",
        licenca=LICENCA_DE_INTEGRIDADE,
        cobertura=(
            "Termos de embargo do IBAMA (Dados Abertos do IBAMA), com a área, o município e se o embargo foi "
            "cancelado ou levantado; cada termo como o IBAMA publicou. Pelo known_at, o termo conta como público a partir do último dia do mês em que apareceu."
        ),
        ordem=("numero_do_termo",),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    TabelaPorCnpj(
        tabela="mte_lista_suja",
        fontes=("mte-lista-suja",),
        conjunto=INTEGRIDADE,
        onde_sai=ANALISE,
        bloco=LISTA_SUJA,
        chave="lista_suja_do_mte",
        campos=(
            "ano_da_acao",
            "uf",
            "cnae",
            "trabalhadores",
            "incluida_em",
        ),
        data_do_fato="incluida_em",
        licenca=LICENCA_DE_INTEGRIDADE,
        cobertura=(
            "Cadastro de Empregadores que tenham submetido trabalhadores a condições análogas à de escravo, do "
            "Ministério do Trabalho e Emprego: diz se a empresa consta da lista vigente na edição mais nova que "
            "a base guarda até o dia pedido, com a data do retrato (o dia da mudança mais nova que a base viu na "
            "lista); o registro que saiu da lista não aparece. Cada registro como o MTE publicou, sem o nome do "
            "empregador nem o endereço do estabelecimento. Pelo known_at, o registro conta como público a partir "
            "do último dia do mês em que apareceu."
        ),
        ordem=("ano_da_acao",),
        marca_de_pessoa=TRATA_COMO_PESSOA,
        diz_o_retrato=True,
    ),
    # lote 2 da ADR 0122, Emenda 2 (19/11/2026): a licença da fonte não trava, só no conjunto sem trava de licença
    TabelaPorCnpj(
        tabela="anatel_pados",
        fontes=("anatel-pados",),
        conjunto=SEM_TRAVA_DE_LICENCA,
        onde_sai=ANALISE,
        bloco=REGISTROS_ADICIONAIS,
        chave="processos_sancionadores_da_anatel",
        campos=(
            "processo",
            "tema",
            "servico",
            "status_do_processo",
            "fase",
            "situacao_do_pagamento",
            "multa_aplicada",
        ),
        data_do_fato="disponivel_em",
        licenca=LICENCA_SEM_TRAVA,
        cobertura=(
            "Processos de apuração de descumprimento de obrigações (PADOs) da Anatel, com o tema, o serviço, a fase, a multa aplicada e a situação do pagamento; cada processo como a Anatel publicou."
        ),
        ordem=("processo",),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    TabelaPorCnpj(
        tabela="anatel_produtos_homologados",
        fontes=("anatel-homologados",),
        conjunto=SEM_TRAVA_DE_LICENCA,
        onde_sai=ANALISE,
        bloco=REGISTROS_ADICIONAIS,
        chave="produtos_homologados_na_anatel",
        campos=(
            "numero_da_homologacao",
            "certificado",
            "situacao_do_certificado",
            "situacao_do_requerimento",
            "tipo_do_produto",
            "categoria",
            "modelo",
            "nome_comercial",
            "pais_do_fabricante",
            "data_da_homologacao",
            "validade_do_certificado",
        ),
        data_do_fato="data_da_homologacao",
        licenca=LICENCA_SEM_TRAVA,
        cobertura=(
            "Produtos de telecomunicações homologados pela Anatel em nome da empresa, com o certificado, a situação, o modelo e o país do fabricante; cada homologação como a Anatel publicou."
        ),
        ordem=("numero_da_homologacao",),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    TabelaPorCnpj(
        tabela="anm_tah",
        fontes=("anm-tah",),
        conjunto=SEM_TRAVA_DE_LICENCA,
        onde_sai=ANALISE,
        bloco=REGISTROS_ADICIONAIS,
        chave="taxa_anual_por_hectare_da_anm",
        campos=(
            "processo",
            "ano_do_processo",
            "fase_do_processo",
            "superintendencia",
            "hectares",
            "valor_total",
            "valor_pago",
            "data_da_quitacao",
        ),
        data_do_fato="data_da_quitacao",
        licenca=LICENCA_SEM_TRAVA,
        cobertura=(
            "Taxa Anual por Hectare (TAH) paga à ANM pelos processos minerários da empresa, com a fase, a área e os valores; cada pagamento como a ANM publicou."
        ),
        ordem=("processo",),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    TabelaPorCnpj(
        tabela="anp_tancagem",
        fontes=("anp-tancagem",),
        conjunto=SEM_TRAVA_DE_LICENCA,
        onde_sai=ANALISE,
        bloco=REGISTROS_ADICIONAIS,
        chave="tancagem_na_anp",
        campos=(
            "codigo_da_instalacao",
            "segmento",
            "tipo_da_unidade",
            "grupo_de_produtos",
            "uf",
            "municipio",
            "tancagem_m3",
            "data_da_posicao",
        ),
        data_do_fato="data_da_posicao",
        licenca=LICENCA_SEM_TRAVA,
        cobertura=(
            "Capacidade de tancagem autorizada pela ANP nas instalações da empresa, por grupo de produtos, na posição mais nova já pública no dia; cada instalação como a ANP publicou."
        ),
        ordem=("codigo_da_instalacao", "grupo_de_produtos"),
        so_a_data_mais_nova=True,
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    TabelaPorCnpj(
        tabela="mte_pat",
        fontes=("mte-pat",),
        conjunto=SEM_TRAVA_DE_LICENCA,
        onde_sai=ANALISE,
        bloco=REGISTROS_ADICIONAIS,
        chave="pat_do_mte",
        campos=(
            "registro_no_pat",
            "situacao",
            "matriz_ou_filial",
            "uf",
            "municipio",
            "data_do_cadastro",
            "trabalhadores_atendidos",
            "trabalhadores_ate_5_salarios",
            "trabalhadores_acima_de_5_salarios",
        ),
        data_do_fato="data_do_cadastro",
        licenca=LICENCA_SEM_TRAVA,
        cobertura=(
            "Programa de Alimentação do Trabalhador (PAT) do Ministério do Trabalho e Emprego: o registro da empresa como beneficiária, facilitadora ou fornecedora, com a situação e os trabalhadores atendidos; cada registro como o MTE publicou."
        ),
        ordem=("registro_no_pat",),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    # as compras públicas (linha 988): a cópia reduzida já tira o empresário individual e a pessoa física que o
    # próprio SICAF aponta e, do BPS, o número do processo de compra (`base/recorte_dos_cadastros.py`)
    TabelaPorCnpj(
        tabela="comprasgov_sicaf",
        fontes=("comprasgov-sicaf",),
        conjunto=CONJUNTO_DE_COMPRAS_PUBLICAS,
        onde_sai=ANALISE,
        bloco=COMPRAS_PUBLICAS,
        chave="cadastro_no_sicaf",
        campos=(
            "ativo",
            "habilitado_a_licitar",
            "cnae",
            "descricao_do_cnae",
            "natureza_juridica",
            "descricao_da_natureza_juridica",
            "porte",
            "descricao_do_porte",
            "municipio",
            "uf",
        ),
        data_do_fato="disponivel_em",
        licenca=LICENCA_DE_COMPRAS_PUBLICAS,
        cobertura=(
            "Cadastro de fornecedores do governo federal (SICAF) nos dados abertos do Compras.gov.br: se o "
            "fornecedor está ativo e habilitado a licitar, com a atividade, a natureza jurídica, o porte e o "
            "município; cada registro como o Compras.gov.br publicou."
        ),
        ordem=("uf", "municipio"),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
    TabelaPorCnpj(
        tabela="bps_compras",
        fontes=("bps",),
        conjunto=CONJUNTO_DE_COMPRAS_PUBLICAS,
        onde_sai=ANALISE,
        bloco=COMPRAS_PUBLICAS,
        chave="compras_no_bps",
        campos=(
            "data_da_compra",
            "ano_da_compra",
            "instituicao",
            "cnpj_da_instituicao",
            "esfera",
            "uf",
            "municipio",
            "catmat",
            "item",
            "descricao_do_pdm",
            "descricao_da_classe",
            "generico",
            "registro_na_anvisa",
            "cnpj_do_fabricante",
            "tipo_de_compra",
            "unidade_de_fornecimento",
            "quantidade",
            "preco_unitario",
            "preco_total",
        ),
        data_do_fato="data_da_compra",
        licenca=LICENCA_DE_COMPRAS_PUBLICAS,
        cobertura=(
            "Banco de Preços em Saúde (BPS) do Ministério da Saúde: as compras de medicamentos e produtos de saúde "
            "em que a empresa é a fornecedora, com a instituição compradora, o item, a quantidade e o preço; cada "
            "compra como o Ministério da Saúde publicou."
        ),
        ordem=("item",),
        marca_de_pessoa=TRATA_COMO_PESSOA,
    ),
)


def do_bloco(bloco: str) -> tuple[TabelaPorCnpj, ...]:
    """As entradas de um bloco, na ordem do registro."""
    return tuple(entrada for entrada in REGISTRO if entrada.bloco == bloco)


def blocos(onde_sai: str) -> tuple[str, ...]:
    """Os blocos que saem num lugar (a análise ou a rota do fundo), na ordem do registro."""
    return tuple(dict.fromkeys(e.bloco for e in REGISTRO if e.onde_sai == onde_sai))
