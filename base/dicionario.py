"""Dicionário de dados da base de ML (série 1, PR 8; ADR 0027, exigência 8).

Um lugar só para dizer o que é cada tabela e cada coluna da base: descrição, unidade, de onde vem,
sob que licença, se pode ser revendida, com que frequência muda, quanto atrasa em relação ao fato e
como chegar de uma linha ao arquivo original (série 2, PR 8; ADR 0055, exigências 11 e 13). O
documento que o Tiago revisa (`docs/dicionario-da-base.md`) é gerado daqui
(`python -m base.dicionario`), e há teste que reclama de coluna nova sem descrição e de documento
desatualizado.
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.banco.coletas import SO_USO_INTERNO, licenca_da_fonte, revenda_da_fonte
from src.padroes import MULTIPLOS

ARQUIVO_DO_DOCUMENTO = "docs/dicionario-da-base.md"
TEXTO = "texto"
DATA = "data (dia)"
MOMENTO = "data e hora (UTC)"
REAIS = "reais (R$), já multiplicado pela escala informada"
FRACAO = "fração (0,25 = 25%)"
ACOES = "ações"
NUMERO = "número inteiro"
SIM_OU_NAO = "verdadeiro ou falso"
# tabelas do banco do app que ainda não guardam o commit por linha (exigência 13 da ADR 0055); as
# da base em Parquet guardam no manifesto (série 3, PR 1) e o registro de coletas, por arquivo (PR 3)
SEM_VERSAO_DO_CODIGO = "A versão do código que processou a linha ainda não é guardada."
LINHAGEM_DO_FCA = (
    "O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA "
    "usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do "
    "código que baixou) e a versão do código que gravou a tabela."
)
_ONDE_DO_FCA = (
    "Parquet em `<acervo>/base/fca/` (servidor de casa, `scripts/carga_fca.py`)"
)
_FREQUENCIA_DO_FCA = (
    "Anual (o FCA é entregue até 31/05) e a cada alteração; a carga relê todos os anos"
)
_ATRASO_DO_FCA = (
    "Até meses: a empresa atualiza o FCA quando muda algo; sem ticker até 2017"
)
CARGA_UNICA_DO_FRE = (
    "Carga de uma vez (FRE de 2010 a 2022): a CVM tirou estas tabelas do FRE aberto depois de "
    "2022 (Resolução CVM 59)"
)
ATRASO_DO_FRE = "O FRE é entregue até 5 meses depois do fim do exercício e reapresentado a cada mudança"
LINHAGEM_DO_FRE = (
    "`referencia` e `versao` dizem de qual FRE veio a linha; o zip do ano fica no acervo e no "
    "registro de coletas (fonte `cvm-fre`, com SHA-256 e data da coleta); `coletado_em` diz quando "
    "a linha foi gravada. " + SEM_VERSAO_DO_CODIGO
)


@dataclass(frozen=True)
class Tabela:
    descricao: str
    fonte: str
    familia_da_fonte: str  # em `src/banco/coletas.py` (a licença e a revenda vêm de lá)
    frequencia: str
    atraso: str
    onde: str
    linhagem: str  # de uma linha ao original, à data da coleta e à versão do código
    colunas: dict[str, tuple[str, str]] = field(
        default_factory=dict
    )  # nome → (descrição, unidade)
    ressalva_de_revenda: str = (
        ""  # parte da tabela que não segue a revenda da fonte principal
    )


_EMPRESA = {
    "cnpj": ("CNPJ da companhia, no formato 00.000.000/0000-00", TEXTO),
    "empresa": ("Nome da companhia como a fonte informa", TEXTO),
}
_DOCUMENTO = {
    "documento": ("DFP (demonstrações anuais) ou ITR (informações trimestrais)", TEXTO),
    "referencia": (
        "Data a que o documento se refere (fim do exercício ou do trimestre)",
        DATA,
    ),
}

TABELAS: dict[str, Tabela] = {
    "demonstracoes_como_era": Tabela(
        descricao=(
            "Uma linha por valor diferente que cada conta de cada período já teve (versão 1, "
            "reapresentações e o balanço seguinte refazendo o ano anterior), com o dia em que "
            "ficou público e o dia em que foi trocado. `como_era_em(base, data)` dá a foto."
        ),
        fonte=(
            "CVM: dados abertos de DFP e ITR (versão mais nova) e ENET (versões anteriores, "
            "XML de cada entrega)"
        ),
        familia_da_fonte="cvm",
        frequencia=(
            "Diária no servidor de casa (carga do ENET às 0h30); a base é remontada por ano"
        ),
        atraso=(
            "DFP: até 3 meses depois do fim do exercício; ITR: até 45 dias depois do trimestre "
            "(prazos da CVM, `src/prazos.py`); reapresentações a qualquer momento"
        ),
        onde="Parquet por ano em `<acervo>/base/demonstracoes/<ano>.parquet` (servidor de casa)",
        linhagem=(
            "`cnpj`, `documento`, `referencia` e `versao` dizem qual entrega à CVM publicou o "
            "valor; `origem` diz se veio dos dados abertos ou do XML do ENET. Ao lado de cada "
            "Parquet, `<ano>.json` guarda o SHA-256 da base e o endereço e o SHA-256 de cada "
            "original, que está no acervo e no registro de coletas (com a data da coleta), e a "
            "`versao_do_codigo` (o commit que montou o ano; os anos montados antes da série 3 "
            "ficam sem ela até serem remontados). `base/linhagem.py` refaz o caminho de qualquer "
            "linha e diz se está completo."
        ),
        colunas={
            **_EMPRESA,
            "grupo": ("con (consolidado) ou ind (individual)", TEXTO),
            "demonstracao": (
                "BPA (ativo), BPP (passivo e patrimônio) ou DRE (resultado)",
                TEXTO,
            ),
            "conta": ("Código da conta no plano da CVM (1, 1.01, 3.01...)", TEXTO),
            "descricao": ("Nome da conta como a empresa informou", TEXTO),
            "inicio": (
                "Começo do período (vazio no balanço, que é um saldo numa data)",
                DATA,
            ),
            "fim": ("Fim do período ou data do saldo", DATA),
            "valor": ("Valor da conta; vazio quando a empresa deixou em branco", REAIS),
            **_DOCUMENTO,
            "versao": (
                "Versão do documento que publicou este valor (1, 2, 3...)",
                "número",
            ),
            "ordem": (
                "ultimo (período do próprio documento) ou penultimo (o ano anterior, refeito)",
                TEXTO,
            ),
            "origem": ("dados_abertos ou enet", TEXTO),
            "divulgado_em": (
                "Dia da entrega à CVM (vale a partir dele, inclusive; a CVM não informa a hora)",
                DATA,
            ),
            "ate": (
                "Dia em que outro valor tomou o lugar (vazio: vale até hoje)",
                DATA,
            ),
        },
    ),
    "achados_de_qualidade": Tabela(
        descricao=(
            'Os achados das regras fixas do selo "dado em conferência" (R1 a R11, '
            "`base/regras.py`): o número que chamou a atenção, o esperado e o porquê. Achado que "
            "some é fechado, nunca apagado."
        ),
        fonte="CVM: dados abertos de DFP e ITR, cadastro e eventos do IPE",
        familia_da_fonte="cvm",
        frequencia="Diária no VPS (tarefa `qualidade-cvm` às 8h15)",
        atraso="O do documento conferido; `valido_desde` diz desde quando o achado existe",
        onde="Tabela `achados_de_qualidade` do banco do app (VPS), migração 0026",
        linhagem=(
            "`cnpj`, `documento` e `referencia` levam ao arquivo de DFP ou ITR da CVM, guardado no "
            "acervo e no registro de coletas (fonte `cvm-dfp-itr`, com SHA-256 e data da coleta); "
            "`versao_das_regras` e `calculado_em` dizem com que regras e quando o achado foi "
            "calculado."
        ),
        colunas={
            "id": ("Identificador da linha", "UUID"),
            "regra": ("Regra que apontou (R1 a R11)", TEXTO),
            "cnpj": _EMPRESA["cnpj"],
            **_DOCUMENTO,
            "grupo": (
                "con, ind ou vazio (regras que olham o documento inteiro)",
                TEXTO,
            ),
            "conta": ("Conta apontada, ou vazio", TEXTO),
            "valor": ("O número publicado (na R8, os dias de atraso)", "reais ou dias"),
            "valor_esperado": ("O que a regra esperava encontrar", "reais ou dias"),
            "porque": ("Frase em português que o selo mostra", TEXTO),
            "versao_das_regras": ("Versão das regras que calculou", TEXTO),
            "valido_desde": (
                "Desde quando a informação existia (a entrega do documento)",
                MOMENTO,
            ),
            "calculado_em": ("Quando a tarefa gravou ou atualizou o achado", MOMENTO),
            "fechado_em": (
                "Quando o achado sumiu numa rodada nova (vazio: aberto)",
                MOMENTO,
            ),
        },
    ),
    "cadastro_das_companhias": Tabela(
        descricao=(
            "Cada registro de companhia aberta na CVM, inclusive as que saíram, com a data e o "
            "motivo (sem viés de sobrevivência, ADR 0027, exigência 4)"
        ),
        fonte="CVM: cadastro de companhias abertas (`cad_cia_aberta.csv`)",
        familia_da_fonte="cvm",
        frequencia="Diária (a CVM atualiza o arquivo todo dia útil)",
        atraso="Dias, entre o ato (registro ou cancelamento) e a publicação",
        onde="Lido do acervo quando preciso (`base/cadastro.py::ler_cadastro`)",
        linhagem=(
            "O `cad_cia_aberta.csv` de cada dia fica no acervo e no registro de coletas (com "
            "SHA-256 e data da coleta); a tabela é refeita dele. "
            + SEM_VERSAO_DO_CODIGO
        ),
        colunas={
            **_EMPRESA,
            "registro": ("Data do registro na CVM", DATA),
            "cancelamento": ("Data do cancelamento (vazio: ativa)", DATA),
            "motivo_cancelamento": (
                "Motivo informado pela CVM (voluntário, de ofício...)",
                TEXTO,
            ),
            "situacao": ("Situação do registro (ATIVO, CANCELADA...)", TEXTO),
            "setor": ("Setor de atividade informado à CVM", TEXTO),
        },
    ),
    "tickers_no_tempo": Tabela(
        descricao=(
            "Cada código de ação da B3 (bolsa) com a empresa e o período em que existiu, juntando "
            "todos os anos do formulário cadastral (FCA): código que sumiu continua aqui"
        ),
        fonte="CVM: formulário cadastral (FCA), valores mobiliários",
        familia_da_fonte="cvm",
        frequencia="Anual (o FCA é entregue até 31/05) e a cada alteração",
        atraso="Até meses: a empresa atualiza o FCA quando muda algo",
        onde=(
            "Parquet em `<acervo>/base/fca/tickers.parquet` (servidor de casa, "
            "`scripts/carga_fca.py`); a função é `base/cadastro.py::tickers_no_tempo`"
        ),
        linhagem=(
            "Montada dos zips do FCA de todos os anos, guardados no acervo e no registro de "
            "coletas (com SHA-256 e data da coleta); `primeiro_visto` e `ultimo_visto` dizem de "
            "qual FCA veio cada código. " + LINHAGEM_DO_FCA
        ),
        colunas={
            "codigo": ("Código de negociação na B3 (PETR4, TAEE11)", TEXTO),
            **_EMPRESA,
            "valor_mobiliario": (
                "Tipo do papel (ações ordinárias, preferenciais, units)",
                TEXTO,
            ),
            "primeiro_visto": ("Data do primeiro FCA em que o código apareceu", DATA),
            "ultimo_visto": ("Data do último FCA em que o código apareceu", DATA),
            "inicio_negociacao": ("Início da negociação informado pela empresa", DATA),
            "fim_negociacao": (
                "Fim da negociação informado (vazio: ainda negociado)",
                DATA,
            ),
        },
    ),
    "valores_mobiliarios": Tabela(
        descricao=(
            "Todos os valores mobiliários de cada companhia em cada FCA (ações, units, BDRs, "
            "debêntures, notas comerciais...), na versão mais nova de cada documento. Base do "
            "código permanente da ação (série 3). Até 2017 o FCA não traz o código de negociação"
        ),
        fonte="CVM: formulário cadastral (FCA), valores mobiliários",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DO_FCA,
        atraso=_ATRASO_DO_FCA,
        onde=_ONDE_DO_FCA,
        linhagem="`cnpj`, `referencia` e `versao` dizem de qual FCA veio a linha. "
        + LINHAGEM_DO_FCA,
        colunas={
            **_EMPRESA,
            "referencia": ("Data de referência do FCA", DATA),
            "versao": ("Versão do documento (fica a mais nova)", NUMERO),
            "valor_mobiliario": ("Tipo do papel, como a empresa informa", TEXTO),
            "classe": ("Classe da ação preferencial (Preferencial Classe A...)", TEXTO),
            "codigo_informado": ("Código de negociação como a empresa escreveu", TEXTO),
            "ticker": (
                "O código, se está no formato de ticker da B3 (PETR4); senão vazio",
                TEXTO,
            ),
            "emissor": ("As 4 letras do emissor (PETR), tiradas do ticker", TEXTO),
            "mercado": ("Bolsa, balcão organizado ou balcão não organizado", TEXTO),
            "administradora": (
                "Sigla da entidade administradora do mercado (B3)",
                TEXTO,
            ),
            "inicio_negociacao": (
                "Início da negociação informado (a troca de ticker não muda)",
                DATA,
            ),
            "fim_negociacao": (
                "Fim da negociação informado (vazio: ainda negociado)",
                DATA,
            ),
            "segmento": ("Segmento de listagem (Novo Mercado, Nível 1...)", TEXTO),
            "inicio_listagem": ("Início da listagem no segmento", DATA),
            "fim_listagem": ("Fim da listagem no segmento", DATA),
        },
    ),
    "emissores": Tabela(
        descricao=(
            "Emissor (as 4 letras do ticker e do ISIN: PETR) → CNPJ, com o primeiro e o último ano do "
            "FCA em que apareceu. É a ligação do ISIN das carteiras dos fundos (CDA) com a empresa. Um "
            "emissor com mais de um CNPJ é conflito e fica sem resposta"
        ),
        fonte="CVM: formulário cadastral (FCA), derivado de `valores_mobiliarios`",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DO_FCA,
        atraso=_ATRASO_DO_FCA,
        onde=_ONDE_DO_FCA,
        linhagem="Derivada de `valores_mobiliarios` na mesma carga. " + LINHAGEM_DO_FCA,
        colunas={
            "emissor": ("As 4 letras do emissor", TEXTO),
            **_EMPRESA,
            "primeiro_ano": ("Ano do primeiro FCA com o emissor", NUMERO),
            "ultimo_ano": ("Ano do último FCA com o emissor", NUMERO),
            "conflito": (
                "Verdadeiro se o emissor aparece com mais de um CNPJ",
                SIM_OU_NAO,
            ),
        },
    ),
    "codigos_invalidos": Tabela(
        descricao=(
            'Códigos de negociação informados fora do formato de ticker (a CSN informa "4030"): não '
            "viram ligação e vão para o relatório de buracos"
        ),
        fonte="CVM: formulário cadastral (FCA), derivado de `valores_mobiliarios`",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DO_FCA,
        atraso=_ATRASO_DO_FCA,
        onde=_ONDE_DO_FCA,
        linhagem="Derivada de `valores_mobiliarios` na mesma carga. " + LINHAGEM_DO_FCA,
        colunas={
            **_EMPRESA,
            "referencia": ("Data de referência do FCA", DATA),
            "valor_mobiliario": ("Tipo do papel, como a empresa informa", TEXTO),
            "codigo_informado": ("O código como a empresa escreveu", TEXTO),
        },
    ),
    "carteiras_dos_fundos": Tabela(
        descricao=(
            "As posições em ações de todos os fundos registrados na CVM, por mês, desde 2005 (CDA, "
            "bloco de ações): comprado, emprestado e vendido, com o ISIN e o emissor. Fundos e "
            "posições que saíram continuam (sem viés de sobrevivência). Um Parquet por ano; quando a "
            "CVM regrava um ano, a versão anterior fica como `<ano>.v<N>`"
        ),
        fonte="CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 4",
        familia_da_fonte="cvm",
        frequencia="Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês",
        atraso=(
            "O arquivo sai uns 40 dias depois do mês e o fundo pode deixar uma posição em sigilo por "
            "até 90 dias: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois"
        ),
        onde="Parquet por ano em `<acervo>/base/cda/<ano>.parquet` (servidor de casa, `scripts/carga_cda.py`)",
        linhagem=(
            "O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do CDA "
            "usado (no acervo e no registro de coletas, com a data da coleta e a versão do código que "
            "baixou) e a versão do código que gravou."
        ),
        colunas={
            "competencia": ("Mês da carteira (último dia)", DATA),
            "cnpj_fundo": ("CNPJ do fundo (ou da classe, depois da CVM 175)", TEXTO),
            "tipo_do_fundo": ("Tipo do fundo como a CVM informa", TEXTO),
            "fundo": ("Nome do fundo (pessoa jurídica)", TEXTO),
            "tipo": ("comprado, emprestado ou vendido", TEXTO),
            "codigo": ("Código do ativo informado (ticker)", TEXTO),
            "isin": ("ISIN do ativo: o código permanente", TEXTO),
            "emissor": ("As 4 letras do emissor, tiradas do ISIN", TEXTO),
            "descricao": ("Descrição do ativo informada", TEXTO),
            "quantidade": ("Quantidade no fim do mês", ACOES),
            "valor": ("Valor de mercado no fim do mês", REAIS),
            "compras": ("Valor comprado no mês", REAIS),
            "vendas": ("Valor vendido no mês", REAIS),
            "confidencial_ate": (
                "Até quando a posição ficou em sigilo (vazio: sem sigilo)",
                DATA,
            ),
            "disponivel_em": (
                "Desde quando a posição era pública (como era na data)",
                DATA,
            ),
        },
    ),
    "fidc_informe": Tabela(
        descricao=(
            "O informe mensal de cada FIDC desde 2013, um Parquet por quadro (`tab_I` a `tab_X_7`) e "
            "por ano, no formato da fonte: carteira, prazos, inadimplência por faixa, pré-pagamento, "
            "recompras, cedentes. As colunas mudam com os anos (15 quadros em 2013, 18 em 2026) e são "
            "as do dicionário da CVM (`meta_inf_mensal_fidc.txt`); a base acrescenta as três abaixo. "
            "Sem dado pessoal: dos documentos de cedentes só fica CNPJ válido (CPF vira vazio)"
        ),
        fonte="CVM: informe mensal de FIDC",
        familia_da_fonte="cvm",
        frequencia="Mensal; de 2013 a 2024 um arquivo por ano, de 2025 em diante um por mês",
        atraso=(
            "Entregue em até 15 dias; a CVM regrava meses passados (cada regravação vira versão "
            "`<ano>.v<N>`). `disponivel_em` usa competência + 45 dias"
        ),
        onde="Parquet em `<acervo>/base/fidc/informe/<quadro>/<ano>.parquet` (servidor de casa, `scripts/carga_fidc.py`)",
        linhagem=(
            "O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do "
            "informe usado (no acervo e no registro de coletas, com a data da coleta e a versão do "
            "código que baixou) e a versão do código que gravou."
        ),
        colunas={
            "competencia": ("Mês do informe (último dia)", DATA),
            "cnpj_fundo": ("CNPJ do fundo (ou da classe, depois da CVM 175)", TEXTO),
            "disponivel_em": (
                "Desde quando o informe era público (como era na data)",
                DATA,
            ),
        },
    ),
    "cadastro_de_fundos": Tabela(
        descricao=(
            "O cadastro de fundos da CVM (atual, histórico de administrador, auditor, classe... e o "
            "registro de fundos e classes da CVM 175), com o gestor de cada FIDC: a lista de clientes "
            "possíveis do Capital. Fundos cancelados continuam. Sem dado pessoal: o diretor "
            "responsável e o histórico dele ficam fora; o gestor pessoa física fica só com a marca PF"
        ),
        fonte="CVM: cadastro de fundos (`cad_fi.csv`, `cad_fi_hist.zip`, `registro_fundo_classe.zip`)",
        familia_da_fonte="cvm",
        frequencia="Diária na CVM; a base guarda um retrato a cada carga (versões `<nome>.v<N>`)",
        atraso="Do dia: é um retrato do cadastro na data da coleta; o histórico vem de `cad_fi_hist`",
        onde="Parquet em `<acervo>/base/fidc/cadastro/` (servidor de casa, `scripts/carga_fidc.py`)",
        linhagem=(
            "O `.json` de cada tabela guarda o SHA-256, o endereço e o SHA-256 do arquivo da CVM (no "
            "acervo e no registro de coletas, com a data e a versão do código) e a versão que gravou."
        ),
        colunas={},
    ),
    "painel_dos_fundos": Tabela(
        descricao=(
            "Quem tinha cada empresa em cada mês desde 2005: as posições dos fundos (CDA) somadas por "
            "mês e tipo (comprado, emprestado, vendido), em duas versões: por emissor (sempre) e por "
            "empresa (CNPJ). O emissor vira CNPJ pelo FCA e, no que falta (empresas que saíram antes "
            "de 2018), pela tabela conferida `base/conferidas/emissores_antigos.csv`; cada ano tem "
            "pelo menos 95% do valor comprado com CNPJ (`cobertura`), e o resto está em `buracos`. "
            "Inclui empresas que saíram da bolsa (sem viés de sobrevivência)"
        ),
        fonte="Derivado: CVM, CDA (posições) e FCA (emissores), mais a tabela conferida",
        familia_da_fonte="cvm",
        frequencia="Mensal, montado de novo quando o CDA ou o FCA mudam",
        atraso=(
            "O do CDA: `disponivel_em` é a maior data das posições somadas (o total só era público "
            "quando a última posição dele ficou pública)"
        ),
        onde=(
            "Parquet em `<acervo>/base/fundos/`: `painel_emissor/<ano>`, `painel_empresa/<ano>`, "
            "`cobertura` e `buracos` (servidor de casa, `scripts/montar_painel_dos_fundos.py`)"
        ),
        linhagem=(
            "O `.json` de cada tabela lista as tabelas de entrada (o CDA do ano e os emissores do FCA, "
            "com o SHA-256 do conteúdo anotado no manifesto delas) e o SHA-256 da tabela conferida; "
            "cada entrada tem a própria linhagem até os arquivos da CVM. Guarda a versão do código."
        ),
        colunas={
            "competencia": ("Mês da carteira", DATA),
            "emissor": ("As 4 posições do emissor (só no painel por emissor)", TEXTO),
            "cnpj": ("CNPJ da empresa (só no painel por empresa)", TEXTO),
            "tipo": ("comprado, emprestado ou vendido", TEXTO),
            "fundos": (
                "Quantos fundos tinham a posição (cada fundo uma vez por empresa)",
                NUMERO,
            ),
            "valor": ("Valor de mercado somado", REAIS),
            "quantidade": ("Quantidade somada", ACOES),
            "compras": ("Valor comprado no mês, somado", REAIS),
            "vendas": ("Valor vendido no mês, somado", REAIS),
            "disponivel_em": (
                "Desde quando o total era público (como era na data)",
                DATA,
            ),
        },
    ),
    "ifdata_valores": Tabela(
        descricao=(
            "Balanço, resultado, capital, segmentação e carteira de crédito de cada banco e "
            "conglomerado, por trimestre desde 2000, no formato longo da fonte (uma linha por "
            "instituição, relatório, conta e coluna). Tipo 1 = conglomerado prudencial (desde "
            "mar/2014), 2 = conglomerado financeiro, 3 = instituição individual. Ficam fora o "
            "relatório 15 (câmbio) e as linhas de total sem código de instituição"
        ),
        fonte="Banco Central: IF.data (API Olinda, `IfDataValores`)",
        familia_da_fonte="bcb",
        frequencia="Trimestral (data-base em mar, jun, set e dez)",
        atraso=(
            "Jun/2026 estava publicado em 14/10 (106 dias); `disponivel_em` usa data-base + 120 "
            "dias. O BC revisa: as 8 datas mais novas são baixadas de novo a cada carga e cada "
            "revisão vira versão `<AAAAMM>.v<N>`"
        ),
        onde=(
            "Parquet em `<acervo>/base/bcb/ifdata/valores/tipo_<t>/<AAAAMM>.parquet` (servidor de "
            "casa, `scripts/carga_bcb_credito.py`)"
        ),
        linhagem=(
            "O `<AAAAMM>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada resposta "
            "da API (no acervo e no registro de coletas, fonte `bcb-ifdata`, com a data da coleta) "
            "e a versão do código que gravou."
        ),
        colunas={
            "data_base": ("Fim do trimestre a que o número se refere", DATA),
            "tipo_instituicao": ("1 prudencial, 2 financeiro, 3 individual", NUMERO),
            "cod_inst": (
                "Código da instituição no BC (raiz do CNPJ ou C00... do conglomerado)",
                TEXTO,
            ),
            "relatorio": (
                "Número do relatório (1 Resumo, 2 Ativo, 3 Passivo...)",
                NUMERO,
            ),
            "nome_relatorio": ("Nome do relatório", TEXTO),
            "grupo": ("Grupo da linha, quando o relatório tem", TEXTO),
            "conta": ("Código da conta no relatório", TEXTO),
            "coluna": (
                'Nome da coluna, com a letra da nota ("Disponibilidades (a)")',
                TEXTO,
            ),
            "descricao": ("Fórmula da coluna nas contas do Cosif", TEXTO),
            "saldo": ("Valor da linha", REAIS),
            "disponivel_em": (
                "Desde quando o número era público (como era na data)",
                DATA,
            ),
        },
    ),
    "ifdata_cadastro": Tabela(
        descricao=(
            "O cadastro de cada data-base do IF.data: nome, tipo de controle, segmento, cidade, "
            "conglomerados e CNPJ do líder de cada instituição e conglomerado, com a raiz do CNPJ "
            "que liga à bolsa"
        ),
        fonte="Banco Central: IF.data (API Olinda, `IfDataCadastro`)",
        familia_da_fonte="bcb",
        frequencia="Trimestral, junto com os valores",
        atraso="O dos valores (o cadastro sai com a data-base)",
        onde="Parquet em `<acervo>/base/bcb/ifdata/cadastro/<AAAAMM>.parquet` (servidor de casa)",
        linhagem="Como `ifdata_valores`: o manifesto guarda o endereço e o SHA-256 da resposta.",
        colunas={
            "data_base": ("Data-base do cadastro", DATA),
            "cod_inst": ("Código da instituição no BC", TEXTO),
            "instituicao": ("Nome da instituição", TEXTO),
            "tipo_controle": (
                "Tc: 1 público, 2 privado nacional, 3 estrangeiro",
                TEXTO,
            ),
            "tipo_consolidado": (
                "Tcb: tipo de consolidado bancário (b1, b2...)",
                TEXTO,
            ),
            "tipo_documento": ("Td: tipo de documento contábil", TEXTO),
            "segmento_prudencial": (
                "Sr: segmento da regulação prudencial (S1 a S5)",
                TEXTO,
            ),
            "segmento": ("Segmento da instituição, quando informado", TEXTO),
            "atividade": ("Atividade principal, quando informada", TEXTO),
            "uf": ("UF da sede", TEXTO),
            "municipio": ("Município da sede", TEXTO),
            "conglomerado_financeiro": ("Código do conglomerado financeiro", TEXTO),
            "conglomerado_prudencial": ("Código do conglomerado prudencial", TEXTO),
            "cnpj_lider": ("Raiz do CNPJ da instituição líder (8 dígitos)", TEXTO),
            "inicio_atividade": ("Mês de início da atividade (AAAAMM)", NUMERO),
            "situacao": ("A = ativa", TEXTO),
            "cnpj_raiz": (
                "Raiz do CNPJ usada na ligação: a do líder ou o próprio código, se for CNPJ",
                TEXTO,
            ),
        },
    ),
    "ligacao_dos_bancos": Tabela(
        descricao=(
            "Instituição do IF.data → CNPJ da empresa da bolsa → tickers que valiam no ano, por "
            "data-base. A raiz do CNPJ do líder liga ao CNPJ do FCA; antes de 2010 (sem FCA) a "
            "ligação chega ao CNPJ, mas não à ação. Instituição sem ação (Caixa, BNDES) fica sem CNPJ"
        ),
        fonte="Derivado: IF.data (cadastro) e CVM, FCA (emissores e tickers)",
        familia_da_fonte="bcb",
        frequencia="Trimestral, montada de novo a cada carga",
        atraso="O do cadastro do IF.data",
        onde="Parquet em `<acervo>/base/bcb/ifdata/ligacao_dos_bancos.parquet` (servidor de casa)",
        linhagem=(
            "O `.json` lista cada cadastro e as tabelas do FCA usados, com o SHA-256 de cada "
            "arquivo, e a versão do código."
        ),
        colunas={
            "data_base": ("Data-base do cadastro", DATA),
            "cod_inst": ("Código da instituição no BC", TEXTO),
            "instituicao": ("Nome da instituição", TEXTO),
            "cnpj_raiz": ("Raiz do CNPJ (8 dígitos)", TEXTO),
            "cnpj": ("CNPJ da empresa da bolsa (vazio se não tem ação)", TEXTO),
            "tickers": ("Códigos que valiam no ano, separados por vírgula", TEXTO),
        },
    ),
    "scr_credito": Tabela(
        descricao=(
            "Carteira de crédito do sistema financeiro por mês desde jul/2012 (SCR.data versão 2): "
            "por UF, segmento da instituição, PF ou PJ, CNAE (PJ) ou ocupação (PF), porte, "
            "modalidade, origem dos recursos e indexador, com prazos a vencer, atraso, "
            "inadimplência e ativo problemático. Agregado, sem pessoa nem instituição. A versão 1 "
            "(parou em jun/2025) fica fora"
        ),
        fonte="Banco Central: SCR.data (`scrdata_<ano>.zip`)",
        familia_da_fonte="bcb",
        frequencia="Mensal, um arquivo por ano",
        atraso=(
            "Publicado ~30 dias depois do fim do mês (ago/2026 já estava no arquivo em 09/10); "
            "`disponivel_em` usa data-base + 60 dias. O BC regrava anos passados: os 2 anos mais "
            "novos são baixados de novo a cada carga e cada regravação vira versão `<ano>.v<N>`"
        ),
        onde="Parquet em `<acervo>/base/bcb/scr/<ano>.parquet` (servidor de casa, `scripts/carga_bcb_credito.py`)",
        linhagem=(
            "O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 do arquivo do BC "
            "(no acervo e no registro de coletas, fonte `bcb-scr-base`) e a versão do código."
        ),
        colunas={
            "data_base": ("Fim do mês", DATA),
            "uf": ("UF do cliente", TEXTO),
            "segmento": (
                "Segmento da instituição (Banco, Cooperativa, Financeira...)",
                TEXTO,
            ),
            "cliente": ("PF ou PJ", TEXTO),
            "cnae_ocupacao": ("Seção do CNAE (PJ) ou natureza da ocupação (PF)", TEXTO),
            "porte": ("Porte da empresa (PJ) ou faixa de renda (PF)", TEXTO),
            "modalidade": ("Modalidade do crédito", TEXTO),
            "submodalidade": ("Submodalidade do crédito", TEXTO),
            "origem": ("Origem dos recursos (livres ou direcionados)", TEXTO),
            "indexador": ("Indexador (prefixado, pós-fixado...)", TEXTO),
            "numero_de_operacoes": (
                "Número de operações (vazio quando o BC não informa)",
                NUMERO,
            ),
            "a_vencer_ate_90_dias": ("Carteira a vencer em até 90 dias", REAIS),
            "a_vencer_de_91_ate_360_dias": ("A vencer de 91 a 360 dias", REAIS),
            "a_vencer_de_361_ate_1080_dias": ("A vencer de 361 a 1080 dias", REAIS),
            "a_vencer_de_1081_ate_1800_dias": ("A vencer de 1081 a 1800 dias", REAIS),
            "a_vencer_de_1801_ate_5400_dias": ("A vencer de 1801 a 5400 dias", REAIS),
            "a_vencer_acima_de_5400_dias": ("A vencer acima de 5400 dias", REAIS),
            "carteira_a_vencer": ("Total a vencer", REAIS),
            "vencido_de_15_ate_90_dias": ("Vencido de 15 a 90 dias", REAIS),
            "vencido_acima_de_90_dias": ("Vencido há mais de 90 dias", REAIS),
            "carteira_vencida": ("Total vencido (a partir de 15 dias)", REAIS),
            "carteira_ativa": ("Carteira ativa, como o BC informa", REAIS),
            "carteira_inadimplencia": (
                "Carteira em inadimplência (atraso acima de 90 dias)",
                REAIS,
            ),
            "ativo_problematico": (
                "Ativo problemático (atraso ou reestruturação)",
                REAIS,
            ),
            "disponivel_em": (
                "Desde quando o mês era público (como era na data)",
                DATA,
            ),
        },
    ),
    "padroes_setoriais": Tabela(
        descricao=(
            "Os padrões por setor das notas (ADR 0033): os percentis de cada indicador entre as "
            "empresas de cada grupo de setores (`src/setores.py`), calculados só com os balanços "
            "que eram públicos na data de corte. Dado derivado: recalcular o mesmo corte "
            "substitui as linhas dele."
        ),
        fonte=(
            "Calculado pelo TickerLab das demonstrações da CVM (DFP e ITR, versões do Radar); "
            "nos múltiplos, também o preço da ação (Yahoo Finance)"
        ),
        familia_da_fonte="cvm",
        frequencia=(
            "Um corte por fim de mês; o cron do VPS roda todo dia às 8h30 e só grava o corte "
            "que falta (`scripts/atualizar_padroes.py --so-o-que-falta`)"
        ),
        atraso=(
            "O do balanço mais novo de cada empresa até o corte (DFP até 3 meses, ITR até 45 dias)"
        ),
        onde="Tabela `padroes_setoriais` do banco do app (VPS), migração 0028",
        linhagem=(
            "`data_de_corte` e `versao` (o método, `src/padroes.py::VERSAO_DOS_PADROES`) bastam "
            "para refazer a linha: `python -m scripts.atualizar_padroes --datas <corte>` lê as "
            "versões dos documentos entregues até o corte (`demonstracoes_versoes`), que levam "
            "aos originais do acervo; `calculado_em` diz quando foi gravada. As empresas de cada "
            "percentil não ficam guardadas, só a quantidade."
        ),
        colunas={
            "data_de_corte": (
                "Data de corte: entra só o que era público até ela (fim de cada mês)",
                DATA,
            ),
            "grupo": (
                "Grupo de setores (`src/setores.py`) ou `mercado` (todas as não financeiras)",
                TEXTO,
            ),
            "indicador": (
                "Indicador (`src/padroes.py::INDICADORES`) ou múltiplo de preço",
                TEXTO,
            ),
            "versao": ("Versão do método (`VERSAO_DOS_PADROES`)", TEXTO),
            "empresas": (
                "Quantas empresas do grupo tinham o indicador no corte",
                "número",
            ),
            "percentis": (
                'Os percentis 10 a 90 do indicador no grupo ({"50": 0.08, ...})',
                "a do indicador (fração, vezes ou dias)",
            ),
            "calculado_em": ("Quando a tarefa gravou a linha", MOMENTO),
        },
        ressalva_de_revenda=(
            f"As linhas dos múltiplos ({', '.join(f'`{m}`' for m in MULTIPLOS)}) usam o preço do "
            f"Yahoo Finance: {SO_USO_INTERNO}."
        ),
    ),
    "fre_proventos": Tabela(
        descricao=(
            "Dividendos e juros sobre capital próprio de cada exercício, como a empresa informou "
            "no Formulário de Referência (FRE). O mesmo exercício aparece no FRE de vários anos: "
            "fica o documento mais novo."
        ),
        fonte="CVM: dados abertos do Formulário de Referência (FRE), tabela de distribuição",
        familia_da_fonte="cvm",
        frequencia=CARGA_UNICA_DO_FRE,
        atraso=ATRASO_DO_FRE,
        onde="Tabela `fre_proventos` do banco do app (VPS), migração 0029",
        linhagem=LINHAGEM_DO_FRE,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "exercicio": ("Fim do exercício social", DATA),
            "referencia": ("Data de referência do FRE de onde a linha veio", DATA),
            "versao": ("Versão desse FRE (1, 2, 3...)", "número"),
            "lucro_ajustado": ("Lucro líquido ajustado, base da distribuição", REAIS),
            "dividendo_total": ("Total distribuído (dividendos e JCP)", REAIS),
            "payout": ("Parte do lucro ajustado distribuída", FRACAO),
            "dividendos": ("Dividendos declarados", REAIS),
            "jcp": ("Juros sobre capital próprio declarados", REAIS),
            "coletado_em": ("Quando a carga gravou a linha", MOMENTO),
        },
    ),
    "fre_eventos_de_capital": Tabela(
        descricao=(
            "Desdobramentos, grupamentos, bonificações e aumentos de capital informados no FRE, "
            "para ajustar a quantidade de ações (sem confundir desdobramento com diluição)"
        ),
        fonte=(
            "CVM: dados abertos do Formulário de Referência (FRE), tabelas de desdobramentos, "
            "grupamentos, bonificações e aumentos de capital"
        ),
        familia_da_fonte="cvm",
        frequencia=CARGA_UNICA_DO_FRE,
        atraso=ATRASO_DO_FRE,
        onde="Tabela `fre_eventos_de_capital` do banco do app (VPS), migração 0029",
        linhagem=LINHAGEM_DO_FRE,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "tipo": ("desdobramento, grupamento, bonificação ou aumento", TEXTO),
            "data": ("Data da aprovação ou da deliberação", DATA),
            "quantidade": (
                "Ações depois do evento (no aumento, as ações novas)",
                ACOES,
            ),
            "referencia": ("Data de referência do FRE de onde a linha veio", DATA),
            "versao": ("Versão desse FRE (1, 2, 3...)", "número"),
            "acoes_antes": ("Ações antes do evento", ACOES),
            "acoes_depois": ("Ações depois do evento", ACOES),
            "fator": ("Depois ÷ antes (desdobramento de 1 para 10 = 10)", "vezes"),
            "acoes_novas": ("Ações emitidas no aumento de capital", ACOES),
            "valor": ("Valor do aumento de capital", REAIS),
            "coletado_em": ("Quando a carga gravou a linha", MOMENTO),
        },
    ),
}


def _tabela_em_markdown(nome: str, tabela: Tabela) -> list[str]:
    linhas = [
        f"## `{nome}`",
        "",
        tabela.descricao,
        "",
        f"- **Fonte:** {tabela.fonte}",
        f"- **Licença:** {licenca_da_fonte(tabela.familia_da_fonte)}",
        f"- **Revenda:** {revenda_da_fonte(tabela.familia_da_fonte)}",
        *(
            [f"- **Ressalva de revenda:** {tabela.ressalva_de_revenda}"]
            if tabela.ressalva_de_revenda
            else []
        ),
        f"- **Frequência:** {tabela.frequencia}",
        f"- **Atraso de divulgação:** {tabela.atraso}",
        f"- **Onde fica:** {tabela.onde}",
        f"- **Linhagem:** {tabela.linhagem}",
        "",
        "| Coluna | O que é | Unidade |",
        "|---|---|---|",
    ]
    linhas += [f"| `{c}` | {d} | {u} |" for c, (d, u) in tabela.colunas.items()]
    return [*linhas, ""]


def documento_em_markdown() -> str:
    linhas = [
        "# Dicionário de dados da base de ML",
        "",
        "Gerado por `python -m base.dicionario` a partir de `base/dicionario.py` (não edite à mão).",
        "Exigência 8 do critério de pronto da base (ADR 0027 do autor): para cada tabela, unidade,",
        "frequência, atraso de divulgação, fonte e licença. Exigências 11 e 13 (ADR 0055): se pode",
        "ser revendida (não é parecer jurídico) e a linhagem até o arquivo original.",
        "",
    ]
    for nome, tabela in TABELAS.items():
        linhas += _tabela_em_markdown(nome, tabela)
    return "\n".join(linhas).rstrip("\n") + "\n"


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent.parent / ARQUIVO_DO_DOCUMENTO
    # fim de linha LF também no Windows: o teste compara com o mesmo texto no Linux do CI
    destino.write_text(documento_em_markdown(), encoding="utf-8", newline="\n")
    print(f"dicionário gravado em {destino}")
