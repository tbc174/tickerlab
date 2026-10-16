"""Dicionário de dados da base de ML (série 1, PR 8; ADR 0027, exigência 8).

Um lugar só para dizer o que é cada tabela e cada coluna da base: descrição, unidade, de onde vem,
sob que licença, se pode ser revendida, com que frequência muda, quanto atrasa em relação ao fato e
como chegar de uma linha ao arquivo original (série 2, PR 8; ADR 0055, exigências 11 e 13). O
documento que o Tiago revisa (`docs/dicionario-da-base.md`) é gerado daqui
(`python -m base.dicionario`), e há teste que reclama de coluna nova sem descrição e de documento
desatualizado.
"""

from dataclasses import dataclass, field, replace
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
NUMERO_DECIMAL = "número com decimais, na unidade da fonte"
SIM_OU_NAO = "verdadeiro ou falso"
# tabelas do banco do app que ainda não guardam o commit por linha (exigência 13 da ADR 0055); as
# da base em Parquet guardam no manifesto (série 3, PR 1) e o registro de coletas, por arquivo (PR 3)
SEM_VERSAO_DO_CODIGO = "A versão do código que processou a linha ainda não é guardada."
COM_VERSAO_DO_CODIGO = (
    "`versao_do_codigo` diz o commit que montou a linha (o comando recusa rodar sem saber o commit "
    "ou com mudanças não salvas)."
)
LINHAGEM_DAS_DERIVADAS = (
    " `base/linhagem.py::linhagem_da_tabela` segue cada tabela de entrada pelo manifesto dela até os "
    "originais; se uma entrada foi regravada depois, a derivada não confere até ser remontada."
)
LINHAGEM_DO_FCA = (
    "O `.json` ao lado do Parquet guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada FCA "
    "usado (no acervo e no registro de coletas, fonte `cvm-fca`, com a data da coleta e a versão do "
    "código que baixou) e a versão do código que gravou a tabela."
)
ORIGEM_DO_FCA = (
    (
        "fca (informado no formulário) ou códigos conferidos (tabela "
        "`base/conferidas/codigos_fora_do_fca.csv`: o código veio fora do formato no FCA)"
    ),
    TEXTO,
)
LINHAGEM_DA_CONFERIDA = (
    " As linhas com `origem` = códigos conferidos vêm da tabela conferida, que entra nas origens do "
    "`.json` pelo caminho no repositório e o SHA-256 (`base/linhagem.py` confere o arquivo)."
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
PONTOS_PERCENTUAIS = "pontos percentuais (66,25 = 66,25%)"
# série B: a base histórica no servidor de casa, lida dos originais guardados pelo arquivista
_FREQUENCIA_DA_HISTORICA = (
    "A cada montagem (`scripts/montar_base_historica.py`), que relê todos os arquivos anuais "
    "guardados"
)
_SO_ATE_2022 = (
    "; a CVM tirou estas tabelas do FRE aberto depois de 2022 (Resolução CVM 59): os anos "
    "novos vêm vazios ou quase"
)
LINHAGEM_DA_HISTORICA_SEM_ANO = (
    "Cada linha guarda o SHA-256 do original no acervo (`origem_sha256`, que leva ao registro de "
    "coletas) e quando ele foi coletado (`origem_coletada_em`); `montado_em` diz quando a tabela "
    "foi montada. " + COM_VERSAO_DO_CODIGO
)
LINHAGEM_DA_HISTORICA = (
    LINHAGEM_DA_HISTORICA_SEM_ANO
    + " `ano_do_arquivo` diz de que arquivo anual veio a linha."
)
_ORIGEM_SEM_ANO = {
    "origem_sha256": ("SHA-256 do arquivo original no acervo", TEXTO),
    "origem_coletada_em": ("Quando o arquivista baixou esse original", MOMENTO),
    "montado_em": ("Quando a tabela foi montada", MOMENTO),
    "versao_do_codigo": ("Commit do código que montou a tabela", TEXTO),
}
_ORIGEM_DA_LINHA = {
    "ano_do_arquivo": ("Ano do arquivo da CVM de onde a linha veio", "ano"),
    **_ORIGEM_SEM_ANO,
}


def _onde_da_historica(tabela: str) -> str:
    return (
        f"Parquet em `<acervo>/base/{tabela}/<ano>.parquet` (servidor de casa, "
        "`scripts/montar_base_historica.py`)"
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
    # contrato de dados (ADR 0077, PR 1); preenchido por `_CONTRATO`, logo abaixo de `TABELAS`
    modulo: str = (
        ""  # mercado_e_empresas, credito_e_fidc, ma, governo_e_sancoes, macro, ...
    )
    pessoa: bool = False  # a tabela guarda dado de pessoa natural?
    chaves: tuple[str, ...] = ()  # colunas que identificam uma linha
    datas: dict[str, str] = field(
        default_factory=dict
    )  # as três datas → coluna que já existe
    historico_desde: str = ""  # a partir de quando a base tem dado (ISO)
    granularidade_do_publico_em: str = ""  # "dia", "mes" ou "ano"
    versao_do_contrato: str = "1.0.0"


_ONDE_DA_REDE = "Parquet em `<acervo>/base/rede/{t}.parquet` (servidor de casa, `scripts/montar_rede.py`)"
LINHAGEM_DA_REDE = (
    "Derivada: o manifesto aponta as tabelas de entrada (com o SHA-256 do conteúdo), as tabelas "
    "conferidas (`emissores_antigos.csv`, `entidades.csv`) e os originais lidos do acervo "
    "(cadastro da CVM, páginas do GLEIF, Empresas e Simples da Receita); a linhagem segue até a "
    "coleta de cada um. " + COM_VERSAO_DO_CODIGO
)
RESSALVA_DA_REDE = (
    "A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita, que "
    "está como só uso interno até a licença ser confirmada; o LEI é do GLEIF (CC0, citar); os "
    "códigos dos reguladores seguem a licença de cada um (ver `empresa_serie`)."
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
                (
                    "Dia da entrega à CVM (vale a partir dele, inclusive; a CVM não informa a "
                    "hora). Entrega com a empresa fora de qualquer registro na CVM (pedido de "
                    "registro) vale a partir do registro seguinte: o público só viu o documento "
                    "perto do registro"
                ),
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
            "uf": (
                "Estado da sede, no cadastro de hoje (muda o prazo do ITR de 2024 no RS)",
                TEXTO,
            ),
        },
    ),
    "tickers_no_tempo": Tabela(
        descricao=(
            "Cada código de ação da B3 (bolsa) com a empresa e de quando a quando valeu, juntando "
            "todos os anos do formulário cadastral (FCA): código que sumiu continua aqui. Vale da "
            "entrega do FCA que trouxe o código até a do que veio sem ele (série 4, PR 1); numa data, "
            "vale o FCA de referência mais nova já entregue. Os códigos que a empresa informa fora "
            'do formato (o BTG põe "000000" nas units) entram pela tabela conferida, válidos do 1º '
            "mês em que aparecem nas carteiras dos fundos até o fim do ano do último"
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
            "coletas (com SHA-256 e data da coleta); `primeiro_visto` e `ultimo_visto` são as "
            "entregas dos FCA de onde veio cada código. "
            + LINHAGEM_DO_FCA
            + LINHAGEM_DA_CONFERIDA
        ),
        colunas={
            "codigo": ("Código de negociação na B3 (PETR4, TAEE11)", TEXTO),
            **_EMPRESA,
            "valor_mobiliario": (
                "Tipo do papel (ações ordinárias, preferenciais, units)",
                TEXTO,
            ),
            "primeiro_visto": (
                "Entrega (DT_RECEB) do primeiro FCA vigente com o código: vale desde esse dia",
                DATA,
            ),
            "ultimo_visto": ("Entrega do último FCA vigente com o código", DATA),
            "valido_ate": (
                (
                    "Entrega do FCA que passou a valer sem o código (deixa de valer nesse dia); vazio: "
                    "ainda no FCA mais recente da empresa"
                ),
                DATA,
            ),
            "inicio_negociacao": ("Início da negociação informado pela empresa", DATA),
            "fim_negociacao": (
                "Fim da negociação informado (vazio: ainda negociado)",
                DATA,
            ),
            "origem": ORIGEM_DO_FCA,
        },
    ),
    "valores_mobiliarios": Tabela(
        descricao=(
            "Todos os valores mobiliários de cada companhia em cada FCA (ações, units, BDRs, "
            "debêntures, notas comerciais...), com a data de entrega de cada versão: a mais nova de "
            "cada documento (a única que a CVM publica nos dados abertos), as das baixadas antigas "
            "guardadas no acervo e as versões substituídas buscadas no sistema de documentos da CVM "
            "(RAD) nos anos em que o código mudou. Base do código permanente da ação (série 3). Até "
            "2017 o FCA não traz o código de negociação"
        ),
        fonte="CVM: formulário cadastral (FCA), valores mobiliários",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DO_FCA,
        atraso=_ATRASO_DO_FCA,
        onde=_ONDE_DO_FCA,
        linhagem="`id_documento` (ou `cnpj`, `referencia` e `versao`) diz de qual FCA veio a "
        "linha. " + LINHAGEM_DO_FCA,
        colunas={
            **_EMPRESA,
            "referencia": ("Data de referência do FCA", DATA),
            "versao": ("Versão do documento (fica a mais nova)", NUMERO),
            "id_documento": ("Número do documento na CVM (ID_DOC)", TEXTO),
            "recebido_em": (
                "Data de entrega desta versão à CVM (DT_RECEB): como era na data",
                DATA,
            ),
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
            "origem": (
                "dados abertos (arquivo anual da CVM) ou documento da versão (RAD da CVM)",
                TEXTO,
            ),
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
        linhagem="Derivada de `valores_mobiliarios` na mesma carga. "
        + LINHAGEM_DO_FCA
        + LINHAGEM_DA_CONFERIDA,
        colunas={
            "emissor": ("As 4 letras do emissor", TEXTO),
            **_EMPRESA,
            "primeiro_ano": ("Ano do primeiro FCA com o emissor", NUMERO),
            "ultimo_ano": ("Ano do último FCA com o emissor", NUMERO),
            "primeiro_recebido_em": (
                (
                    "Entrega do primeiro FCA com o emissor (nos códigos conferidos, o 1º mês nas "
                    "carteiras dos fundos): desde quando a ligação é conhecida"
                ),
                DATA,
            ),
            "conflito": (
                "Verdadeiro se o emissor aparece com mais de um CNPJ",
                SIM_OU_NAO,
            ),
            "origem": ORIGEM_DO_FCA,
        },
    ),
    "codigos_invalidos": Tabela(
        descricao=(
            'Códigos de negociação informados fora do formato de ticker (a CSN informa "4030"): não '
            "viram ligação e vão para o relatório de buracos; os da bolsa que aparecem nas carteiras "
            "dos fundos são conferidos um a um e entram em `codigos_fora_do_fca`"
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
            "recebido_em": ("Data de entrega do FCA à CVM (DT_RECEB)", DATA),
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
    "carteiras_bloco_8": Tabela(
        descricao=(
            "As ações e os certificados de depósito que os fundos informam no bloco 8 do CDA "
            '("demais ativos não codificados"), sem o código estruturado, com o CNPJ do emissor que o '
            "próprio fundo informa: em 2020, R$ 1,14 tri (soma dos meses) em ações de companhias com "
            "ticker, ~26% a mais sobre o bloco 4, quase nada repetido entre os blocos. Emissor pessoa "
            "física nunca entra (o CPF é descartado na leitura). Um Parquet por ano, com versões"
        ),
        fonte="CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 8",
        familia_da_fonte="cvm",
        frequencia="Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês",
        atraso=(
            "O do CDA: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois"
        ),
        onde=(
            "Parquet por ano em `<acervo>/base/cda_bloco_8/<ano>.parquet` (servidor de casa, "
            "`scripts/carga_cda.py`, na mesma carga do CDA)"
        ),
        linhagem=(
            "O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do CDA "
            "usado (os mesmos do bloco 4) e a versão do código que gravou."
        ),
        colunas={
            "competencia": ("Mês da carteira (último dia)", DATA),
            "cnpj_fundo": ("CNPJ do fundo (ou da classe, depois da CVM 175)", TEXTO),
            "tipo_do_fundo": ("Tipo do fundo como a CVM informa", TEXTO),
            "fundo": ("Nome do fundo (pessoa jurídica)", TEXTO),
            "tipo": ("comprado, emprestado ou vendido", TEXTO),
            "tipo_do_ativo": (
                "Ação ordinária, ação preferencial... como o fundo informa",
                TEXTO,
            ),
            "cnpj_emissor": (
                "CNPJ do emissor que o fundo informa (só pessoa jurídica)",
                TEXTO,
            ),
            "nome_do_emissor": ("Nome do emissor como o fundo escreve", TEXTO),
            "descricao": ('Descrição do ativo ("PETR3 - PETROBRAS")', TEXTO),
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
        # `cad_fi`; as tabelas `hist_<campo>` repetem um campo com início e fim (`DT_INI_<campo>`,
        # `DT_FIM_<campo>`) e as `registro_*` usam os nomes da CVM 175 (`meta_registro_fundo_classe.txt`)
        colunas={
            "TP_FUNDO": ("Tipo do fundo (FIDC, FI, FII...)", TEXTO),
            "CNPJ_FUNDO": ("CNPJ do fundo", TEXTO),
            "DENOM_SOCIAL": ("Nome do fundo", TEXTO),
            "DT_REG": ("Data do registro na CVM", DATA),
            "DT_CONST": ("Data de constituição", DATA),
            "CD_CVM": ("Código do fundo na CVM", TEXTO),
            "DT_CANCEL": ("Data do cancelamento (vazio: ativo)", DATA),
            "SIT": ("Situação (em funcionamento normal, cancelado...)", TEXTO),
            "DT_INI_SIT": ("Início da situação", DATA),
            "DT_INI_ATIV": ("Início das atividades", DATA),
            "DT_INI_EXERC": ("Início do exercício social", DATA),
            "DT_FIM_EXERC": ("Fim do exercício social", DATA),
            "CLASSE": ("Classe do fundo (Ações, Renda Fixa, FIDC...)", TEXTO),
            "DT_INI_CLASSE": ("Início da classe", DATA),
            "RENTAB_FUNDO": (
                "Indicador de desempenho informado (CDI, Ibovespa...)",
                TEXTO,
            ),
            "CONDOM": ("Condomínio aberto ou fechado", TEXTO),
            "FUNDO_COTAS": ("S se é fundo de cotas", TEXTO),
            "FUNDO_EXCLUSIVO": ("S se é fundo exclusivo", TEXTO),
            "TRIB_LPRAZO": ("S se tem tributação de longo prazo", TEXTO),
            "PUBLICO_ALVO": ("Público-alvo (geral, qualificado, profissional)", TEXTO),
            "ENTID_INVEST": ("S se é entidade de investimento", TEXTO),
            "TAXA_PERFM": ("Taxa de performance", "percentual, como a CVM informa"),
            "INF_TAXA_PERFM": ("Texto sobre a taxa de performance", TEXTO),
            "TAXA_ADM": (
                "Taxa de administração",
                "percentual ao ano, como a CVM informa",
            ),
            "INF_TAXA_ADM": ("Texto sobre a taxa de administração", TEXTO),
            "VL_PATRIM_LIQ": ("Patrimônio líquido", "reais (R$)"),
            "DT_PATRIM_LIQ": ("Data do patrimônio líquido", DATA),
            "CNPJ_ADMIN": ("CNPJ do administrador", TEXTO),
            "ADMIN": ("Nome do administrador (empresa)", TEXTO),
            "PF_PJ_GESTOR": ("PF ou PJ: o gestor é pessoa física ou jurídica", TEXTO),
            "CPF_CNPJ_GESTOR": (
                "CNPJ do gestor; vazio quando o gestor é pessoa física",
                TEXTO,
            ),
            "GESTOR": ("Nome do gestor; vazio quando é pessoa física", TEXTO),
            "CNPJ_AUDITOR": ("CNPJ do auditor", TEXTO),
            "AUDITOR": ("Nome do auditor", TEXTO),
            "CNPJ_CUSTODIANTE": ("CNPJ do custodiante", TEXTO),
            "CUSTODIANTE": ("Nome do custodiante", TEXTO),
            "CNPJ_CONTROLADOR": ("CNPJ do controlador", TEXTO),
            "CONTROLADOR": ("Nome do controlador", TEXTO),
            "INVEST_CEMPR_EXTER": ("S se pode aplicar 100% no exterior", TEXTO),
            "CLASSE_ANBIMA": ("Classificação da Anbima", TEXTO),
        },
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
            + LINHAGEM_DAS_DERIVADAS
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
            "fundos_no_bloco_8": (
                (
                    "Só no painel por empresa: quantos fundos informaram a ação no bloco 8 (demais "
                    "ativos, pelo CNPJ do emissor)"
                ),
                NUMERO,
            ),
            "valor_no_bloco_8": (
                (
                    "Só no painel por empresa: valor de mercado no bloco 8; as colunas sem o sufixo são "
                    "só o bloco 4"
                ),
                REAIS,
            ),
            "quantidade_no_bloco_8": (
                "Só no painel por empresa: quantidade no bloco 8",
                ACOES,
            ),
        },
    ),
    "cobertura_dos_fundos": Tabela(
        descricao=(
            "Por mês desde 2005, quanto do valor comprado pelos fundos chega a um CNPJ de empresa pela "
            "ligação do painel (a meta da tabela conferida é 95% em cada ano)"
        ),
        fonte="Derivado: CVM, CDA (posições) e FCA (emissores), mais as tabelas conferidas",
        familia_da_fonte="cvm",
        frequencia="Mensal, montada junto com o painel dos fundos",
        atraso="O do CDA (os meses mais novos ainda crescem enquanto os fundos entregam)",
        onde="Parquet em `<acervo>/base/fundos/cobertura.parquet` (`scripts/montar_painel_dos_fundos.py`)",
        linhagem=(
            "O `.json` lista as tabelas de entrada (cada ano do CDA e os emissores do FCA, com o "
            "SHA-256 do conteúdo) e o SHA-256 da tabela conferida; guarda a versão do código."
            + LINHAGEM_DAS_DERIVADAS
        ),
        colunas={
            "competencia": ("Mês da carteira", DATA),
            "valor_comprado": ("Valor comprado por todos os fundos", REAIS),
            "valor_com_cnpj": ("A parte desse valor cujo emissor tem CNPJ", REAIS),
            "fracao_com_cnpj": ("valor_com_cnpj ÷ valor_comprado", FRACAO),
        },
    ),
    "buracos_dos_fundos": Tabela(
        descricao=(
            "Os emissores das carteiras dos fundos que ficaram sem CNPJ, do maior valor comprado para o "
            "menor: a lista de trabalho para a próxima conferência (nada some calado)"
        ),
        fonte="Derivado: CVM, CDA (posições) e FCA (emissores), mais as tabelas conferidas",
        familia_da_fonte="cvm",
        frequencia="Mensal, montada junto com o painel dos fundos",
        atraso="O do CDA",
        onde="Parquet em `<acervo>/base/fundos/buracos.parquet` (`scripts/montar_painel_dos_fundos.py`)",
        linhagem=(
            "O `.json` lista as tabelas de entrada (cada ano do CDA e os emissores do FCA, com o "
            "SHA-256 do conteúdo) e o SHA-256 da tabela conferida; guarda a versão do código."
            + LINHAGEM_DAS_DERIVADAS
        ),
        colunas={
            "emissor": ("As 4 posições do emissor sem CNPJ", TEXTO),
            "valor": ("Valor comprado somado em todos os meses", REAIS),
            "primeira": ("Primeiro mês em que aparece", DATA),
            "ultima": ("Último mês em que aparece", DATA),
            "descricao": (
                "Descrição do ativo no CDA (a pista para a conferência)",
                TEXTO,
            ),
            "motivo": (
                (
                    "Por que fica sem empresa, se foi conferido (`emissores_sem_ligacao`); "
                    "vazio: ainda não conferido"
                ),
                TEXTO,
            ),
        },
    ),
    "emissores_sem_ligacao": Tabela(
        descricao=(
            "Tabela conferida à mão: emissores das carteiras dos fundos que ficam sem empresa de "
            "propósito, cada um com o motivo (companhia sem ação na bolsa, como a Comerc e a Granja "
            "Faria; dois CNPJs no período; BDR de empresa de fora; falta de prova). Ficam só no "
            "painel por emissor, e o motivo vai para o relatório de buracos (série 4, PR 3)"
        ),
        fonte="CVM: formulário cadastral (FCA), cadastro de companhias, IPE e descrição no CDA",
        familia_da_fonte="cvm",
        frequencia="Quando a conferência anda (pelos buracos de maior valor)",
        atraso="Nenhum",
        onde="`base/conferidas/emissores_sem_ligacao.csv` no repositório (Git)",
        linhagem=(
            "Cada linha diz a fonte e quando foi conferida; o histórico fica no Git e o painel dos "
            "fundos anota o SHA-256 da tabela no `.json` de cada tabela que monta."
        ),
        colunas={
            "emissor": ("As 4 posições do emissor", TEXTO),
            "cnpj": ("CNPJ, quando é um só e conhecido; vazio nos outros casos", TEXTO),
            "empresa": (
                "Nome no FCA ou no cadastro; sem CNPJ, como o CDA descreve",
                TEXTO,
            ),
            "motivo": ("Por que o emissor fica sem empresa", TEXTO),
            "fonte": ("De onde veio a conferência", TEXTO),
            "conferido_em": ("Dia da conferência", DATA),
        },
    ),
    "emissores_antigos": Tabela(
        descricao=(
            "Tabela conferida à mão: emissores das carteiras dos fundos que saíram da bolsa ou mudaram "
            'de código antes de 2018 (e a CSN, que informa "4030"), ligados ao CNPJ pelo cadastro de '
            "companhias da CVM, um a um, sem casar nome aproximado"
        ),
        fonte="CVM: cadastro de companhias (`cad_cia_aberta.csv`) e descrição do ativo no CDA",
        familia_da_fonte="cvm",
        frequencia="Quando a conferência anda (pelos buracos de maior valor)",
        atraso="Nenhum: a ligação vale para o período em que o emissor aparece nas carteiras",
        onde="`base/conferidas/emissores_antigos.csv` no repositório (Git)",
        linhagem=(
            "Cada linha diz a fonte e quando foi conferida (`fonte`, `conferido_em`); o histórico de "
            "cada mudança fica no Git, e quem usa a tabela anota o SHA-256 dela no próprio `.json`."
        ),
        colunas={
            "emissor": ("As 4 posições do emissor", TEXTO),
            "cnpj": ("CNPJ da companhia no cadastro da CVM", TEXTO),
            "empresa_no_cadastro": ("Nome no cadastro de companhias da CVM", TEXTO),
            "cd_cvm": ("Código da companhia na CVM", TEXTO),
            "registro": ("Data do registro na CVM", DATA),
            "cancelamento": ("Data do cancelamento do registro (vazio: ativa)", DATA),
            "descricao_no_cda": ("Descrição do ativo nas carteiras dos fundos", TEXTO),
            "no_cda": ("Primeiro e último mês nas carteiras (AAAA-MM–AAAA-MM)", TEXTO),
            "observacao": (
                "O que aconteceu com a empresa (incorporação, troca de nome)",
                TEXTO,
            ),
            "fonte": ("De onde veio a ligação", TEXTO),
            "conferido_em": ("Dia da conferência", DATA),
        },
    ),
    "codigos_fora_do_fca": Tabela(
        descricao=(
            "Tabela conferida à mão: códigos de empresas da bolsa que o FCA traz fora do formato (o BTG "
            'informa "000000" nas units, a Marisa "022055"). O CNPJ vem do próprio FCA e o código e o '
            "ISIN, das carteiras dos fundos; a `carga_fca` junta a tabela aos tickers e aos emissores"
        ),
        fonte="CVM: formulário cadastral (FCA) e carteiras dos fundos (CDA)",
        familia_da_fonte="cvm",
        frequencia="Quando a conferência anda (pelos buracos de maior valor)",
        atraso="Nenhum: o código vale do 1º ao último mês em que aparece nas carteiras",
        onde="`base/conferidas/codigos_fora_do_fca.csv` no repositório (Git)",
        linhagem=(
            "Cada linha diz a fonte e quando foi conferida; o histórico fica no Git e a `carga_fca` "
            "anota o SHA-256 da tabela no `.json` dos tickers e dos emissores."
        ),
        colunas={
            "codigo": ("Código de negociação na B3 (BPAC11)", TEXTO),
            "cnpj": ("CNPJ da companhia, como no FCA", TEXTO),
            "empresa": ("Nome da companhia no FCA", TEXTO),
            "valor_mobiliario": ("Tipo do papel (units, ações ordinárias...)", TEXTO),
            "isin": (
                "ISIN do papel nas carteiras dos fundos (a prova do emissor)",
                TEXTO,
            ),
            "primeiro_no_cda": (
                "Primeiro mês em que o código aparece nas carteiras",
                DATA,
            ),
            "ultimo_no_cda": ("Último mês em que o código aparece nas carteiras", DATA),
            "codigo_no_fca": ("O que a empresa escreveu no lugar do código", TEXTO),
            "observacao": ("Nota da conferência", TEXTO),
            "fonte": ("De onde veio cada parte da ligação", TEXTO),
            "conferido_em": ("Dia da conferência", DATA),
        },
    ),
    "anac_estatistico": Tabela(
        descricao=(
            "Estatístico do transporte aéreo da ANAC por empresa, mês e par de aeroportos (passageiros, "
            "carga, assentos, ASK, RPK, combustível...), desde 2000, no formato da fonte. A chave da "
            "empresa é a sigla, a mesma da B13 (empresa ↔ série)"
        ),
        fonte="ANAC: dados estatísticos do transporte aéreo (Dados_Estatisticos.csv)",
        familia_da_fonte="anac",
        frequencia='Mensal (o arquivo inteiro é republicado; a 1ª linha diz "Atualizado em")',
        atraso='Mensal; a regra de "como era na data" usa o fim do mês + 60 dias (agosto/2026 estava '
        "publicado 44 dias depois, medido em 14/10/2026)",
        onde="Parquet por ano em `<acervo>/base/setoriais/anac/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 do arquivo da ANAC usado (no acervo e no "
            "registro de coletas) e a versão do código."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "empresa_sigla": ("Empresa sigla, como a ANAC publica", TEXTO),
            "empresa_nome": ("Empresa nome, como a ANAC publica", TEXTO),
            "empresa_nacionalidade": (
                "Empresa nacionalidade, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_origem_sigla": (
                "Aeroporto de origem sigla, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_origem_nome": (
                "Aeroporto de origem nome, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_origem_uf": (
                "Aeroporto de origem uf, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_origem_regiao": (
                "Aeroporto de origem regiao, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_origem_pais": (
                "Aeroporto de origem pais, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_origem_continente": (
                "Aeroporto de origem continente, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_destino_sigla": (
                "Aeroporto de destino sigla, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_destino_nome": (
                "Aeroporto de destino nome, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_destino_uf": (
                "Aeroporto de destino uf, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_destino_regiao": (
                "Aeroporto de destino regiao, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_destino_pais": (
                "Aeroporto de destino pais, como a ANAC publica",
                TEXTO,
            ),
            "aeroporto_de_destino_continente": (
                "Aeroporto de destino continente, como a ANAC publica",
                TEXTO,
            ),
            "natureza": ("Natureza, como a ANAC publica", TEXTO),
            "grupo_de_voo": ("Grupo de voo, como a ANAC publica", TEXTO),
            "passageiros_pagos": (
                "Passageiros pagos no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "passageiros_gratis": (
                "Passageiros gratis no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "carga_paga_kg": (
                "Carga paga kg no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "carga_gratis_kg": (
                "Carga gratis kg no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "correio_kg": ("Correio kg no mês, como a ANAC publica", NUMERO_DECIMAL),
            "ask": ("Ask no mês, como a ANAC publica", NUMERO_DECIMAL),
            "rpk": ("Rpk no mês, como a ANAC publica", NUMERO_DECIMAL),
            "atk": ("Atk no mês, como a ANAC publica", NUMERO_DECIMAL),
            "rtk": ("Rtk no mês, como a ANAC publica", NUMERO_DECIMAL),
            "combustivel_litros": (
                "Combustivel litros no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "distancia_voada_km": (
                "Distancia voada km no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "decolagens": ("Decolagens no mês, como a ANAC publica", NUMERO_DECIMAL),
            "carga_paga_km": (
                "Carga paga km no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "carga_gratis_km": (
                "Carga gratis km no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "correio_km": ("Correio km no mês, como a ANAC publica", NUMERO_DECIMAL),
            "assentos": ("Assentos no mês, como a ANAC publica", NUMERO_DECIMAL),
            "payload": ("Payload no mês, como a ANAC publica", NUMERO_DECIMAL),
            "horas_voadas": (
                "Horas voadas no mês, como a ANAC publica",
                NUMERO_DECIMAL,
            ),
            "bagagem_kg": ("Bagagem kg no mês, como a ANAC publica", NUMERO_DECIMAL),
            "atualizado_em": ('A data da linha "Atualizado em" do arquivo usado', DATA),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + 60 dias)",
                DATA,
            ),
        },
    ),
    "anp_vendas": Tabela(
        descricao=(
            "Vendas de combustíveis pelas distribuidoras (líquidos, GLP e aviação) por mês, agente, "
            "produto, origem, destino e mercado, desde 2007, no formato da fonte. A ANP escreve o nome "
            "atual da distribuidora também no passado; a ligação à empresa é pela B13"
        ),
        fonte="ANP: vendas de derivados de petróleo e biocombustíveis por distribuidor (liquidos, glp, aviacao)",
        familia_da_fonte="anp",
        frequencia="Mensal",
        atraso='Mensal; a regra de "como era na data" usa o fim do mês + 60 dias (agosto/2026 estava '
        "publicado 44 dias depois, medido em 14/10/2026)",
        onde="Parquet por ano em `<acervo>/base/setoriais/anp/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 dos três zips da ANP usados e a versão do "
            "código; `arquivo` diz de qual CSV do zip veio a linha (atual ou histórico)."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "grupo": ("liquidos, glp ou aviacao (o zip)", TEXTO),
            "agente": ("Agente regulado (a distribuidora), como a ANP escreve", TEXTO),
            "codigo_do_produto": ("Código do produto na ANP", TEXTO),
            "nome_do_produto": ("Nome do produto", TEXTO),
            "descricao_do_produto": (
                "Descrição do produto (vazio no histórico dos líquidos)",
                TEXTO,
            ),
            "codigo_da_embalagem": ("Código da embalagem (só GLP)", TEXTO),
            "regiao_origem": ("Região de origem", TEXTO),
            "uf_origem": ("UF de origem", TEXTO),
            "regiao_destino": ("Região de destino", TEXTO),
            "uf_destino": ("UF de destino", TEXTO),
            "mercado_destino": (
                "Mercado destinatário (posto, consumidor final...)",
                TEXTO,
            ),
            "quantidade": (
                "Quantidade vendida, na unidade da coluna `unidade`",
                NUMERO_DECIMAL,
            ),
            "unidade": ("mil m³ ou mil ton, como no cabeçalho da ANP", TEXTO),
            "arquivo": ("O CSV do zip de onde veio a linha", TEXTO),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + 60 dias)",
                DATA,
            ),
        },
    ),
    "ons_geracao": Tabela(
        descricao=(
            "Geração por usina do ONS, em MWmed por hora, desde 2000, no formato da fonte. A chave da "
            "usina é o `id_ons` (o CEG falta em 41% da geração de 09/2026). Sem ligação à empresa: o "
            "dono da usina só existe no cadastro de hoje, e aplicá-lo ao passado olharia o futuro"
        ),
        fonte="ONS: geração por usina em base horária (dados abertos)",
        familia_da_fonte="ons",
        frequencia="Diária (um arquivo por ano até 2021, por mês depois)",
        atraso="O dia seguinte; a regra usa o instante + 2 dias",
        onde="Parquet por ano em `<acervo>/base/setoriais/ons/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 de cada arquivo do ONS do ano e a versão do "
            "código."
        ),
        colunas={
            "instante": ("Hora (início)", DATA),
            "id_subsistema": ("Subsistema (N, NE, S, SE)", TEXTO),
            "subsistema": ("Nome do subsistema", TEXTO),
            "uf": ("UF da usina", TEXTO),
            "modalidade_de_operacao": ("Modalidade de operação (tipo I, II...)", TEXTO),
            "tipo_de_usina": ("Hidrelétrica, térmica, eólica, fotovoltaica...", TEXTO),
            "combustivel": ("Combustível ou fonte", TEXTO),
            "usina": ("Nome da usina, como o ONS escreve", TEXTO),
            "id_ons": ("Código da usina no ONS (a chave)", TEXTO),
            "ceg": ("Código da usina na ANEEL (vazio quando o ONS não informa)", TEXTO),
            "geracao_mwmed": ("Geração na hora, em MWmed", NUMERO_DECIMAL),
            "disponivel_em": (
                "Desde quando o número era público (instante + 2 dias)",
                DATA,
            ),
        },
    ),
    "aneel_samp": Tabela(
        descricao=(
            "Mercado das distribuidoras de energia (SAMP da ANEEL) por distribuidora, mês, classe de "
            "consumo, modalidade e posto tarifário: consumidores, energia (kWh) e receita (R$), desde "
            "2003, no formato da fonte. As linhas de cada consumidor livre vêm somadas (sem CPF nem "
            "nome). Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O que mudou antes da primeira coleta (10/2026) não aparece"
        ),
        fonte="ANEEL: SAMP, mercado de distribuição (dados abertos, um Parquet por ano)",
        familia_da_fonte="aneel",
        frequencia="Mensal (a ANEEL regera todos os anos a cada mês, perto do dia 15)",
        atraso=(
            "Medido: o SAMP de 15/09/2026 tinha julho completo (46 dias) e agosto pela metade; a regra "
            "usa o fim do mês + 60 dias"
        ),
        onde="Parquet por ano em `<acervo>/base/setoriais/aneel/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do ano usada (uma por "
            "revisão) e a versão do código."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "cnpj": ("CNPJ da distribuidora (14 dígitos; a chave da B13)", TEXTO),
            "sigla": ("Sigla da distribuidora, como a ANEEL escreve", TEXTO),
            "distribuidora": ("Nome da distribuidora, como a ANEEL escreve", TEXTO),
            "tipo_de_mercado": (
                "Regular, refaturamento, compensação de geração distribuída...",
                TEXTO,
            ),
            "modalidade_tarifaria": ("Convencional, azul, verde, branca...", TEXTO),
            "subgrupo_tarifario": ("A1 a A4, AS, B1 a B4", TEXTO),
            "classe_de_consumo": (
                "Residencial, industrial, comercial, rural...",
                TEXTO,
            ),
            "subclasse_de_consumo": ("Subclasse (baixa renda, cooperativa...)", TEXTO),
            "detalhe_do_consumidor": (
                "Detalhe do consumidor (fonte incentivada...)",
                TEXTO,
            ),
            "nucleo_ceg": ("Núcleo do CEG da usina, quando há (texto inteiro)", TEXTO),
            "posto_tarifario": ("Ponta, fora ponta, intermediário", TEXTO),
            "opcao_de_energia": ("Cativo, livre, suprimento, distribuição", TEXTO),
            "detalhe_do_mercado": (
                "O que o valor mede: número de consumidores, energia (kWh), receita (R$), desconto (%)...",
                TEXTO,
            ),
            "valor": (
                "O valor, na unidade do `detalhe_do_mercado` (soma das linhas; média nos percentuais)",
                NUMERO_DECIMAL,
            ),
            "linhas_somadas": (
                "Quantas linhas da fonte (uma por acessante) foram somadas",
                NUMERO_DECIMAL,
            ),
            "gerado_em": (
                "A data de geração do arquivo pela ANEEL, na primeira vez que o valor foi visto",
                DATA,
            ),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + 60 dias; a revisão, desde o dia em que foi vista)",
                DATA,
            ),
            "visto_em": (
                "O dia da baixada do arquivista que trouxe este valor pela primeira vez",
                DATA,
            ),
        },
    ),
    "anatel_acessos": Tabela(
        descricao=(
            "Acessos de banda larga fixa, telefonia móvel e TV por assinatura da Anatel por prestadora "
            "(CNPJ), mês e UF, desde 2005 (móvel), 2007 (banda larga) e 2012 (TV), somados os "
            "municípios. Na móvel de 2005 a 2018 a Anatel publica duas visões dos mesmos acessos "
            "(`recorte` modalidade ou tecnologia): somar as duas conta tudo duas vezes. Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O que mudou antes da primeira coleta (10/2026) não aparece"
        ),
        fonte='Anatel: painéis de dados, acessos (CSVs "_Colunas" de dentro dos ZIPs)',
        familia_da_fonte="anatel",
        frequencia="Mensal",
        atraso="Agosto/2026 estava publicado em 14/10/2026; a regra usa o fim do mês + 60 dias",
        onde=(
            "Parquet por CSV da Anatel em `<acervo>/base/setoriais/anatel/<nome do CSV>.parquet` "
            "(`scripts/carga_setoriais.py`)"
        ),
        linhagem=(
            "O `.json` de cada CSV guarda o endereço (`zip#csv`) e o SHA-256 de cada baixada usada e a "
            "versão do código."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "servico": (
                "banda_larga_fixa, telefonia_movel ou tv_por_assinatura",
                TEXTO,
            ),
            "recorte": (
                "completo; na móvel de 2005 a 2018, modalidade ou tecnologia",
                TEXTO,
            ),
            "cnpj": ("CNPJ da prestadora (14 dígitos; a chave da B13)", TEXTO),
            "empresa": ("Nome da prestadora, como a Anatel escreve", TEXTO),
            "grupo_economico": ("Grupo econômico, como a Anatel escreve", TEXTO),
            "porte_da_prestadora": ("Grande ou pequeno porte", TEXTO),
            "uf": ("UF", TEXTO),
            "regiao_pgo": ("Região do plano geral de outorgas (móvel até 2009)", TEXTO),
            "codigo_nacional": ("DDD (móvel)", TEXTO),
            "modalidade_de_cobranca": ("Pré-pago ou pós-pago (móvel)", TEXTO),
            "tecnologia": ("Tecnologia (FTTH, cabo, GSM, LTE, DTH...)", TEXTO),
            "geracao": ("Geração da tecnologia móvel (2G a 5G)", TEXTO),
            "tipo_de_pessoa": ("Assinante pessoa física ou jurídica", TEXTO),
            "tipo_de_produto": ("Tipo de produto (internet, voz, M2M...)", TEXTO),
            "faixa_de_velocidade": (
                "Faixa de velocidade contratada (banda larga)",
                TEXTO,
            ),
            "meio_de_acesso": ("Fibra, cabo coaxial, rádio, satélite...", TEXTO),
            "tipo_de_acesso_tv": ("Tipo de acesso de TV por assinatura", TEXTO),
            "acessos": (
                "Acessos em serviço no fim do mês, somados os municípios da UF",
                NUMERO_DECIMAL,
            ),
            "arquivo": ("O CSV da Anatel de onde veio a linha", TEXTO),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + 60 dias; a revisão, desde o dia em que foi vista)",
                DATA,
            ),
            "visto_em": (
                "O dia da baixada do arquivista que trouxe este valor pela primeira vez",
                DATA,
            ),
        },
    ),
    "ans_beneficiarios": Tabela(
        descricao=(
            "Beneficiários de planos de saúde por operadora (registro ANS), mês, modalidade, cobertura, "
            "vigência do plano, contratação e financiamento, desde 2017, no formato da fonte. Uma linha por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O que mudou antes da primeira coleta (10/2026) não aparece"
        ),
        fonte="ANS: beneficiários por operadora e carteira (Beneficiarios_operadora_e_carteira.csv)",
        familia_da_fonte="ans",
        frequencia="Sem data fixa: o arquivo de 08/08/2026 ainda era o mesmo em 14/10/2026",
        atraso=(
            "Medido: o arquivo de 08/08/2026 trazia até junho/2026 (39 dias); a regra usa o fim do mês "
            "+ 90 dias"
        ),
        onde="Parquet por ano em `<acervo>/base/setoriais/ans/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do arquivo usada (uma por "
            "revisão) e a versão do código."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "cd_operadora": (
                "Registro da operadora na ANS (a chave da B13, fonte `ans-beneficiarios`)",
                TEXTO,
            ),
            "modalidade": (
                "Medicina de grupo, cooperativa médica, seguradora...",
                TEXTO,
            ),
            "cobertura": ("Médico-hospitalar ou odontológico", TEXTO),
            "vigencia_do_plano": (
                "P (plano posterior à Lei 9.656) ou A (anterior)",
                TEXTO,
            ),
            "contratacao": (
                "Individual ou familiar, coletivo empresarial, por adesão...",
                TEXTO,
            ),
            "financiamento": ("Pré-estabelecido, pós-estabelecido...", TEXTO),
            "beneficiarios": ("Beneficiários no mês", NUMERO_DECIMAL),
            "base_de": (
                "O mês da extração da ANS (`ID_CMPT`) na primeira vez que o valor foi visto",
                DATA,
            ),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + 90 dias; a revisão, desde o dia em que foi vista)",
                DATA,
            ),
            "visto_em": (
                "O dia da baixada do arquivista que trouxe este valor pela primeira vez",
                DATA,
            ),
        },
    ),
    "fre_conselho": Tabela(
        descricao=(
            "Conselho de administração, diretoria e conselho fiscal por companhia e versão do FRE: quantos membros, suplentes, independentes, eleitos pelo controlador e pelos minoritários, desde 2010. Só contagens: nome, CPF, nascimento e currículo dos administradores nem são lidos"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_conselho/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "orgao": ("Órgão da administração, como a CVM escreve", TEXTO),
            "membros": ("Quantas pessoas no órgão (ou no comitê)", NUMERO_DECIMAL),
            "suplentes": ("Quantos suplentes", NUMERO_DECIMAL),
            "independentes": (
                "Quantos conselheiros independentes (pelo cargo informado)",
                NUMERO_DECIMAL,
            ),
            "eleitos_pelo_controlador": (
                "Quantos eleitos pelo controlador (`Eleito_Controlador` = S)",
                NUMERO_DECIMAL,
            ),
            "eleitos_por_minoritarios": (
                "Quantos eleitos pelos minoritários ordinaristas (pelo cargo)",
                NUMERO_DECIMAL,
            ),
            "eleitos_por_preferencialistas": (
                "Quantos eleitos pelos preferencialistas (pelo cargo)",
                NUMERO_DECIMAL,
            ),
            "mandatos_consecutivos_medio": (
                "Média de mandatos consecutivos (vazio quando a CVM não informa)",
                NUMERO_DECIMAL,
            ),
            "participacao_em_reunioes_media": (
                "Média do % de participação em reuniões (vazio quando não informado)",
                NUMERO_DECIMAL,
            ),
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "fre_comites": Tabela(
        descricao=(
            "Comitês (auditoria, risco, remuneração...) por companhia e versão do FRE: quantos membros e suplentes, desde 2010. Só contagens, sem pessoas"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_comites/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "tipo_de_comite": (
                "Tipo de comitê (auditoria, risco, remuneração...)",
                TEXTO,
            ),
            "membros": ("Quantas pessoas no órgão (ou no comitê)", NUMERO_DECIMAL),
            "suplentes": ("Quantos suplentes", NUMERO_DECIMAL),
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "fre_remuneracao": Tabela(
        descricao=(
            "Remuneração total da administração por órgão e exercício (salário, benefícios, bônus, participação nos resultados, ações...), como a CVM publica no FRE, desde 2010, sem os textos livres"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_remuneracao/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "inicio_do_exercicio": ("Início do exercício social", DATA),
            "fim_do_exercicio": ("Fim do exercício social", DATA),
            "orgao": ("Órgão da administração, como a CVM escreve", TEXTO),
            "total_remuneracao": (
                "Como a CVM publica (`Total_Remuneracao`)",
                NUMERO_DECIMAL,
            ),
            "membros": ("Quantas pessoas no órgão (ou no comitê)", NUMERO_DECIMAL),
            "total_do_orgao": (
                "Como a CVM publica (`Total_Remuneracao_Orgao`)",
                NUMERO_DECIMAL,
            ),
            "membros_remunerados": (
                "Como a CVM publica (`Numero_Membros_Remunerados`)",
                NUMERO_DECIMAL,
            ),
            "salario": ("Como a CVM publica (`Salario`)", NUMERO_DECIMAL),
            "beneficios": (
                "Como a CVM publica (`Beneficios_Diretos_Indiretos`)",
                NUMERO_DECIMAL,
            ),
            "participacao_em_comites": (
                "Como a CVM publica (`Participacoes_Comites`)",
                NUMERO_DECIMAL,
            ),
            "outros_fixos": (
                "Como a CVM publica (`Outros_Valores_Fixos`)",
                NUMERO_DECIMAL,
            ),
            "bonus": ("Como a CVM publica (`Bonus`)", NUMERO_DECIMAL),
            "participacao_nos_resultados": (
                "Como a CVM publica (`Participacao_Resultados`)",
                NUMERO_DECIMAL,
            ),
            "participacao_em_reunioes": (
                "Como a CVM publica (`Participacao_Reunioes`)",
                NUMERO_DECIMAL,
            ),
            "outros_variaveis": (
                "Como a CVM publica (`Outros_Valores_Variaveis`)",
                NUMERO_DECIMAL,
            ),
            "comissoes": ("Como a CVM publica (`Comissoes`)", NUMERO_DECIMAL),
            "pos_emprego": ("Como a CVM publica (`Pos_emprego`)", NUMERO_DECIMAL),
            "cessacao_do_cargo": (
                "Como a CVM publica (`Cessacao_Cargo`)",
                NUMERO_DECIMAL,
            ),
            "baseada_em_acoes": (
                "Como a CVM publica (`Baseada_Acoes`)",
                NUMERO_DECIMAL,
            ),
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "fre_remuneracao_extremos": Tabela(
        descricao=(
            "A maior, a menor e a média da remuneração individual por órgão e exercício, como a CVM publica no FRE, desde 2010 (sem a observação em texto livre)"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_remuneracao_extremos/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "inicio_do_exercicio": ("Início do exercício social", DATA),
            "fim_do_exercicio": ("Fim do exercício social", DATA),
            "orgao": ("Órgão da administração, como a CVM escreve", TEXTO),
            "membros": ("Quantas pessoas no órgão (ou no comitê)", NUMERO_DECIMAL),
            "membros_remunerados": (
                "Como a CVM publica (`Numero_Membros_Remunerados`)",
                NUMERO_DECIMAL,
            ),
            "maior": ("Como a CVM publica (`Valor_Maior_Remuneracao`)", NUMERO_DECIMAL),
            "menor": ("Como a CVM publica (`Valor_Menor_Remuneracao`)", NUMERO_DECIMAL),
            "media": ("Como a CVM publica (`Valor_Medio_Remuneracao`)", NUMERO_DECIMAL),
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "fre_diversidade": Tabela(
        descricao=(
            "Gênero, raça e pessoas com deficiência na administração por órgão, como a CVM publica no FRE de 2023 em diante (contagens; vazio nos anos anteriores)"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_diversidade/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "orgao": ("Órgão da administração, como a CVM escreve", TEXTO),
            "genero_feminino": (
                "Como a CVM publica (`genero_feminino`)",
                NUMERO_DECIMAL,
            ),
            "genero_masculino": (
                "Como a CVM publica (`genero_masculino`)",
                NUMERO_DECIMAL,
            ),
            "genero_nao_binario": (
                "Como a CVM publica (`genero_nao_binario`)",
                NUMERO_DECIMAL,
            ),
            "genero_outros": ("Como a CVM publica (`genero_outros`)", NUMERO_DECIMAL),
            "genero_sem_resposta": (
                "Como a CVM publica (`genero_sem_resposta`)",
                NUMERO_DECIMAL,
            ),
            "genero_nao_aplicavel": (
                "Como a CVM publica (`genero_nao_aplicavel`)",
                TEXTO,
            ),
            "raca_amarelo": ("Como a CVM publica (`raca_amarelo`)", NUMERO_DECIMAL),
            "raca_branco": ("Como a CVM publica (`raca_branco`)", NUMERO_DECIMAL),
            "raca_preto": ("Como a CVM publica (`raca_preto`)", NUMERO_DECIMAL),
            "raca_pardo": ("Como a CVM publica (`raca_pardo`)", NUMERO_DECIMAL),
            "raca_indigena": ("Como a CVM publica (`raca_indigena`)", NUMERO_DECIMAL),
            "raca_outros": ("Como a CVM publica (`raca_outros`)", NUMERO_DECIMAL),
            "raca_sem_resposta": (
                "Como a CVM publica (`raca_sem_resposta`)",
                NUMERO_DECIMAL,
            ),
            "raca_nao_aplicavel": ("Como a CVM publica (`raca_nao_aplicavel`)", TEXTO),
            "pcd_pcd": ("Como a CVM publica (`pcd_pcd`)", NUMERO_DECIMAL),
            "pcd_nao_pcd": ("Como a CVM publica (`pcd_nao_pcd`)", NUMERO_DECIMAL),
            "pcd_sem_resposta": (
                "Como a CVM publica (`pcd_sem_resposta`)",
                NUMERO_DECIMAL,
            ),
            "pcd_nao_aplicavel": ("Como a CVM publica (`pcd_nao_aplicavel`)", TEXTO),
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "ofertas_antigas": Tabela(
        descricao=(
            "Ofertas públicas registradas na CVM até a Resolução 160 (ICVM 400, 476 e 555), desde 1989, por CNPJ do emissor, no formato da CVM, uma linha por série ou ativo (sem chave única: a ICVM 476 não tem número de processo). O nome do vendedor e o nome e o documento do ofertante sem CNPJ nunca entram"
        ),
        fonte="CVM: ofertas públicas de distribuição (OFERTA/DISTRIB, ODbL)",
        familia_da_fonte="cvm",
        frequencia="Diária (o ZIP é regerado todo dia)",
        atraso="Nenhum além das datas da própria oferta (`anunciada_em`, `disponivel_em`)",
        onde="Parquet em `<acervo>/base/ofertas/antigas.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `.json` guarda o endereço e o SHA-256 do ZIP de ofertas usado e a versão do código.",
        colunas={
            "numero_processo": ("Como a CVM publica (`Numero_Processo`)", TEXTO),
            "numero_registro_oferta": (
                "Como a CVM publica (`Numero_Registro_Oferta`)",
                TEXTO,
            ),
            "tipo_oferta": ("Como a CVM publica (`Tipo_Oferta`)", TEXTO),
            "tipo_componente_oferta_mista": (
                "Como a CVM publica (`Tipo_Componente_Oferta_Mista`)",
                TEXTO,
            ),
            "tipo_ativo": ("Como a CVM publica (`Tipo_Ativo`)", TEXTO),
            "cnpj_emissor": ("Como a CVM publica (`CNPJ_Emissor`)", TEXTO),
            "nome_emissor": ("Como a CVM publica (`Nome_Emissor`)", TEXTO),
            "cnpj_lider": ("Como a CVM publica (`CNPJ_Lider`)", TEXTO),
            "nome_lider": ("Como a CVM publica (`Nome_Lider`)", TEXTO),
            "cnpj_ofertante": ("Como a CVM publica (`CNPJ_Ofertante`)", TEXTO),
            "nome_ofertante": ("Como a CVM publica (`Nome_Ofertante`)", TEXTO),
            "rito_oferta": ("Como a CVM publica (`Rito_Oferta`)", TEXTO),
            "modalidade_oferta": ("Como a CVM publica (`Modalidade_Oferta`)", TEXTO),
            "modalidade_registro": (
                "Como a CVM publica (`Modalidade_Registro`)",
                TEXTO,
            ),
            "modalidade_dispensa_registro": (
                "Como a CVM publica (`Modalidade_Dispensa_Registro`)",
                TEXTO,
            ),
            "data_abertura_processo": (
                "Como a CVM publica (`Data_Abertura_Processo`)",
                DATA,
            ),
            "data_protocolo": ("Como a CVM publica (`Data_Protocolo`)", DATA),
            "data_dispensa_oferta": (
                "Como a CVM publica (`Data_Dispensa_Oferta`)",
                DATA,
            ),
            "data_registro_oferta": (
                "Como a CVM publica (`Data_Registro_Oferta`)",
                DATA,
            ),
            "data_inicio_oferta": ("Como a CVM publica (`Data_Inicio_Oferta`)", DATA),
            "data_encerramento_oferta": (
                "Como a CVM publica (`Data_Encerramento_Oferta`)",
                DATA,
            ),
            "emissao": ("Como a CVM publica (`Emissao`)", TEXTO),
            "classe_ativo": ("Como a CVM publica (`Classe_Ativo`)", TEXTO),
            "serie": ("Como a CVM publica (`Serie`)", TEXTO),
            "especie_ativo": ("Como a CVM publica (`Especie_Ativo`)", TEXTO),
            "forma_ativo": ("Como a CVM publica (`Forma_Ativo`)", TEXTO),
            "data_emissao": ("Como a CVM publica (`Data_Emissao`)", DATA),
            "data_vencimento": ("Como a CVM publica (`Data_Vencimento`)", DATA),
            "quantidade_sem_lote_suplementar": (
                "Como a CVM publica (`Quantidade_Sem_Lote_Suplementar`)",
                NUMERO_DECIMAL,
            ),
            "quantidade_no_lote_suplementar": (
                "Como a CVM publica (`Quantidade_No_Lote_Suplementar`)",
                NUMERO_DECIMAL,
            ),
            "quantidade_total": (
                "Como a CVM publica (`Quantidade_Total`)",
                NUMERO_DECIMAL,
            ),
            "preco_unitario": ("Como a CVM publica (`Preco_Unitario`)", NUMERO_DECIMAL),
            "valor_total": ("Como a CVM publica (`Valor_Total`)", NUMERO_DECIMAL),
            "oferta_inicial": ("Como a CVM publica (`Oferta_Inicial`)", TEXTO),
            "oferta_incentivo_fiscal": (
                "Como a CVM publica (`Oferta_Incentivo_Fiscal`)",
                TEXTO,
            ),
            "oferta_regime_fiduciario": (
                "Como a CVM publica (`Oferta_Regime_Fiduciario`)",
                TEXTO,
            ),
            "atualizacao_monetaria": (
                "Como a CVM publica (`Atualizacao_Monetaria`)",
                TEXTO,
            ),
            "juros": ("Como a CVM publica (`Juros`)", TEXTO),
            "projeto_audiovisual": (
                "Como a CVM publica (`Projeto_Audiovisual`)",
                TEXTO,
            ),
            "tipo_societario_emissor": (
                "Como a CVM publica (`Tipo_Societario_Emissor`)",
                TEXTO,
            ),
            "tipo_fundo_investimento": (
                "Como a CVM publica (`Tipo_Fundo_Investimento`)",
                TEXTO,
            ),
            "ultimo_comunicado": ("Como a CVM publica (`Ultimo_Comunicado`)", TEXTO),
            "data_comunicado": ("Como a CVM publica (`Data_Comunicado`)", DATA),
            "nr_pessoa_fisica": (
                "Como a CVM publica (`Nr_Pessoa_Fisica`)",
                NUMERO_DECIMAL,
            ),
            "qtd_pessoa_fisica": (
                "Como a CVM publica (`Qtd_Pessoa_Fisica`)",
                NUMERO_DECIMAL,
            ),
            "nr_clube_investimento": (
                "Como a CVM publica (`Nr_Clube_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "qtd_clube_investimento": (
                "Como a CVM publica (`Qtd_Clube_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "nr_fundos_investimento": (
                "Como a CVM publica (`Nr_Fundos_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "qtd_fundos_investimento": (
                "Como a CVM publica (`Qtd_Fundos_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "nr_entidade_previdencia_privada": (
                "Como a CVM publica (`Nr_Entidade_Previdencia_Privada`)",
                NUMERO_DECIMAL,
            ),
            "qtd_entidade_previdencia_privada": (
                "Como a CVM publica (`Qtd_Entidade_Previdencia_Privada`)",
                NUMERO_DECIMAL,
            ),
            "nr_companhia_seguradora": (
                "Como a CVM publica (`Nr_Companhia_Seguradora`)",
                NUMERO_DECIMAL,
            ),
            "qtd_companhia_seguradora": (
                "Como a CVM publica (`Qtd_Companhia_Seguradora`)",
                NUMERO_DECIMAL,
            ),
            "nr_investidor_estrangeiro": (
                "Como a CVM publica (`Nr_Investidor_Estrangeiro`)",
                NUMERO_DECIMAL,
            ),
            "qtd_investidor_estrangeiro": (
                "Como a CVM publica (`Qtd_Investidor_Estrangeiro`)",
                NUMERO_DECIMAL,
            ),
            "nr_instit_intermed_partic_consorcio_distrib": (
                "Como a CVM publica (`Nr_Instit_Intermed_Partic_Consorcio_Distrib`)",
                NUMERO_DECIMAL,
            ),
            "qtd_instit_intermed_partic_consorcio_distrib": (
                "Como a CVM publica (`Qtd_Instit_Intermed_Partic_Consorcio_Distrib`)",
                NUMERO_DECIMAL,
            ),
            "nr_instit_financ_emissora_partic_consorcio": (
                "Como a CVM publica (`Nr_Instit_Financ_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "qtd_instit_financ_emissora_partic_consorcio": (
                "Como a CVM publica (`Qtd_Instit_Financ_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "nr_demais_instit_financ": (
                "Como a CVM publica (`Nr_Demais_Instit_Financ`)",
                NUMERO_DECIMAL,
            ),
            "qtd_demais_instit_financ": (
                "Como a CVM publica (`Qtd_Demais_Instit_Financ`)",
                NUMERO_DECIMAL,
            ),
            "nr_demais_pessoa_juridica_emissora_partic_consorcio": (
                "Como a CVM publica (`Nr_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "qtd_demais_pessoa_juridica_emissora_partic_consorcio": (
                "Como a CVM publica (`Qtd_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "nr_demais_pessoa_juridica": (
                "Como a CVM publica (`Nr_Demais_Pessoa_Juridica`)",
                NUMERO_DECIMAL,
            ),
            "qtd_demais_pessoa_juridica": (
                "Como a CVM publica (`Qtd_Demais_Pessoa_Juridica`)",
                NUMERO_DECIMAL,
            ),
            "nr_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio": (
                "Como a CVM publica (`Nr_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "qdt_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio": (
                "Como a CVM publica (`Qdt_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "nr_outros": ("Como a CVM publica (`Nr_Outros`)", NUMERO_DECIMAL),
            "qtd_outros": ("Como a CVM publica (`Qtd_Outros`)", NUMERO_DECIMAL),
            "qtd_cli_pessoa_fisica": (
                "Como a CVM publica (`Qtd_Cli_Pessoa_Fisica`)",
                NUMERO_DECIMAL,
            ),
            "qtd_cli_pessoa_juridica": (
                "Como a CVM publica (`Qtd_Cli_Pessoa_Juridica`)",
                NUMERO_DECIMAL,
            ),
            "qtd_cli_pessoa_juridica_ligada_adm": (
                "Como a CVM publica (`Qtd_Cli_Pessoa_Juridica_Ligada_Adm`)",
                NUMERO_DECIMAL,
            ),
            "qtd_cli_demais_pessoa_juridica": (
                "Como a CVM publica (`QtD_Cli_Demais_Pessoa_Juridica`)",
                NUMERO_DECIMAL,
            ),
            "qtd_cli_investidor_estrangeiro": (
                "Como a CVM publica (`Qtd_Cli_Investidor_Estrangeiro`)",
                NUMERO_DECIMAL,
            ),
            "qtd_cli_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio": (
                "Como a CVM publica (`Qtd_Cli_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "anunciada_em": (
                "Quando a oferta ficou pública na CVM (registro, dispensa ou comunicado da 476)",
                DATA,
            ),
            "disponivel_em": (
                "Quando a linha inteira era pública (o mais tarde entre o anúncio e o encerramento)",
                DATA,
            ),
        },
    ),
    "ofertas_resolucao_160": Tabela(
        descricao=(
            "Requerimentos de oferta pública pela Resolução CVM 160 (2023 em diante), por CNPJ do emissor, no formato da CVM, sem os textos livres (devedores, garantias, lastro, destinação dos recursos)"
        ),
        fonte="CVM: ofertas públicas de distribuição (OFERTA/DISTRIB, ODbL)",
        familia_da_fonte="cvm",
        frequencia="Diária (o ZIP é regerado todo dia)",
        atraso="Nenhum além das datas da própria oferta (`anunciada_em`, `disponivel_em`)",
        onde="Parquet em `<acervo>/base/ofertas/resolucao_160.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `.json` guarda o endereço e o SHA-256 do ZIP de ofertas usado e a versão do código.",
        colunas={
            "numero_requerimento": (
                "Como a CVM publica (`Numero_Requerimento`)",
                TEXTO,
            ),
            "rito_requerimento": ("Como a CVM publica (`Rito_Requerimento`)", TEXTO),
            "numero_processo": ("Como a CVM publica (`Numero_Processo`)", TEXTO),
            "data_requerimento": ("Como a CVM publica (`Data_requerimento`)", DATA),
            "data_registro": ("Como a CVM publica (`Data_Registro`)", DATA),
            "data_encerramento": ("Como a CVM publica (`Data_Encerramento`)", DATA),
            "status_requerimento": (
                "Como a CVM publica (`Status_Requerimento`)",
                TEXTO,
            ),
            "valor_mobiliario": ("Como a CVM publica (`Valor_Mobiliario`)", TEXTO),
            "tipo_requerimento": ("Como a CVM publica (`Tipo_requerimento`)", TEXTO),
            "bookbuilding": ("Como a CVM publica (`Bookbuilding`)", TEXTO),
            "cnpj_emissor": ("Como a CVM publica (`CNPJ_Emissor`)", TEXTO),
            "nome_emissor": ("Como a CVM publica (`Nome_Emissor`)", TEXTO),
            "cnpj_lider": ("Como a CVM publica (`CNPJ_Lider`)", TEXTO),
            "nome_lider": ("Como a CVM publica (`Nome_Lider`)", TEXTO),
            "grupo_coordenador": ("Como a CVM publica (`Grupo_Coordenador`)", TEXTO),
            "tipo_oferta": ("Como a CVM publica (`Tipo_Oferta`)", TEXTO),
            "emissao": ("Como a CVM publica (`Emissao`)", TEXTO),
            "qtde_total_registrada": (
                "Como a CVM publica (`Qtde_Total_Registrada`)",
                NUMERO_DECIMAL,
            ),
            "valor_total_registrado": (
                "Como a CVM publica (`Valor_Total_Registrado`)",
                NUMERO_DECIMAL,
            ),
            "oferta_inicial": ("Como a CVM publica (`Oferta_inicial`)", TEXTO),
            "oferta_vasos_comunicantes": (
                "Como a CVM publica (`Oferta_vasos_comunicantes`)",
                TEXTO,
            ),
            "publico_alvo": ("Como a CVM publica (`Publico_alvo`)", TEXTO),
            "reabertura_serie": ("Como a CVM publica (`Reabertura_serie`)", TEXTO),
            "titulo_classificado_como_sustentavel": (
                "Como a CVM publica (`Titulo_classificado_como_sustentavel`)",
                TEXTO,
            ),
            "titulo_padronizado": ("Como a CVM publica (`Titulo_padronizado`)", TEXTO),
            "data_deliberacao_aprovou_oferta": (
                "Como a CVM publica (`Data_deliberacao_aprovou_oferta`)",
                DATA,
            ),
            "mercado_negociacao": ("Como a CVM publica (`Mercado_negociacao`)", TEXTO),
            "tipo_lastro": ("Como a CVM publica (`Tipo_lastro`)", TEXTO),
            "regime_fiduciario": ("Como a CVM publica (`Regime_fiduciario`)", TEXTO),
            "ativos_alvo": ("Como a CVM publica (`Ativos_alvo`)", TEXTO),
            "possibilidade_revolvencia": (
                "Como a CVM publica (`Possibilidade_revolvencia`)",
                TEXTO,
            ),
            "fidc_nao_padronizado": (
                "Como a CVM publica (`FIDC_nao_padronizado`)",
                TEXTO,
            ),
            "titulo_incentivado": ("Como a CVM publica (`Titulo_incentivado`)", TEXTO),
            "regime_distribuicao": (
                "Como a CVM publica (`Regime_distribuicao`)",
                TEXTO,
            ),
            "tipo_societario": ("Como a CVM publica (`Tipo_societario`)", TEXTO),
            "administrador": ("Como a CVM publica (`Administrador`)", TEXTO),
            "gestor": ("Como a CVM publica (`Gestor`)", TEXTO),
            "agente_fiduciario": ("Como a CVM publica (`Agente_fiduciario`)", TEXTO),
            "escriturador": ("Como a CVM publica (`Escriturador`)", TEXTO),
            "custodiante": ("Como a CVM publica (`Custodiante`)", TEXTO),
            "avaliador_risco": ("Como a CVM publica (`Avaliador_Risco`)", TEXTO),
            "processo_sei": ("Como a CVM publica (`Processo_SEI`)", TEXTO),
            "endereco_emissor_rede_mundial_computadores": (
                "Como a CVM publica (`Endereco_emissor_rede_mundial_computadores`)",
                TEXTO,
            ),
            "num_invest_pessoa_natural": (
                "Como a CVM publica (`Num_Invest_Pessoa_Natural`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_pessoa_natural": (
                "Como a CVM publica (`Qtde_VM_Pessoa_Natural`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_clube_investimento": (
                "Como a CVM publica (`Num_Invest_Clube_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_clube_investimento": (
                "Como a CVM publica (`Qtde_VM_Clube_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_fundos_investimento": (
                "Como a CVM publica (`Num_Invest_Fundos_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_fundos_investimento": (
                "Como a CVM publica (`Qtde_VM_Fundos_Investimento`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_entidade_previdencia_privada": (
                "Como a CVM publica (`Num_Invest_Entidade_Previdencia_Privada`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_entidade_previdencia_privada": (
                "Como a CVM publica (`Qtde_VM_Entidade_Previdencia_Privada`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_companhia_seguradora": (
                "Como a CVM publica (`Num_Invest_Companhia_Seguradora`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_companhia_seguradora": (
                "Como a CVM publica (`Qtde_VM_Companhia_Seguradora`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_investidor_estrangeiro": (
                "Como a CVM publica (`Num_Invest_Investidor_Estrangeiro`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_investidor_estrangeiro": (
                "Como a CVM publica (`Qtde_VM_Investidor_Estrangeiro`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_instit_intermed_partic_consorcio_distrib": (
                "Como a CVM publica (`Num_Invest_Instit_Intermed_Partic_Consorcio_Distrib`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_instit_intermed_partic_consorcio_distrib": (
                "Como a CVM publica (`Qtde_VM_Instit_Intermed_Partic_Consorcio_Distrib`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_instit_financ_emissora_partic_consorcio": (
                "Como a CVM publica (`Num_Invest_Instit_Financ_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_instit_financ_emissora_partic_consorcio": (
                "Como a CVM publica (`Qtde_VM_Instit_Financ_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_demais_instit_financ": (
                "Como a CVM publica (`Num_Invest_Demais_Instit_Financ`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_demais_instit_financ": (
                "Como a CVM publica (`Qtde_VM_Demais_Instit_Financ`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_demais_pessoa_juridica_emissora_partic_consorcio": (
                "Como a CVM publica (`Num_Invest_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_demais_pessoa_juridica_emissora_partic_consorcio": (
                "Como a CVM publica (`Qtde_VM_Demais_Pessoa_Juridica_Emissora_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_demais_pessoa_juridica": (
                "Como a CVM publica (`Num_Invest_Demais_Pessoa_Juridica`)",
                NUMERO_DECIMAL,
            ),
            "qtde_vm_demais_pessoa_juridica": (
                "Como a CVM publica (`Qtde_VM_Demais_Pessoa_Juridica`)",
                NUMERO_DECIMAL,
            ),
            "num_invest_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio": (
                "Como a CVM publica (`Num_Invest_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "qdte_vm_soc_adm_emp_prop_demais_pess_jurid_emiss_partic_consorcio": (
                "Como a CVM publica (`Qdte_VM_Soc_Adm_Emp_Prop_Demais_Pess_Jurid_Emiss_Partic_Consorcio`)",
                NUMERO_DECIMAL,
            ),
            "anunciada_em": (
                "Quando a oferta ficou pública na CVM (registro, dispensa ou comunicado da 476)",
                DATA,
            ),
            "disponivel_em": (
                "Quando a linha inteira era pública (o mais tarde entre o anúncio e o encerramento)",
                DATA,
            ),
        },
    ),
    "setoriais_buracos": Tabela(
        descricao=(
            "Os códigos das fontes setoriais (sigla da ANAC, agente da ANP) que a B13 não liga a uma "
            "empresa, do maior volume para o menor: a lista de trabalho da próxima conferência"
        ),
        fonte="Derivado: fontes setoriais e a B13 (empresa_serie)",
        familia_da_fonte="anp",
        frequencia="A cada carga das fontes setoriais",
        atraso="Nenhum",
        onde="Parquet em `<acervo>/base/setoriais/buracos.parquet` (`scripts/carga_setoriais.py`)",
        linhagem="O `.json` anota a tabela da B13 usada (SHA-256 do conteúdo) e a versão do código.",
        colunas={
            "chave": ("Código na fonte sem ligação", TEXTO),
            "valor": (
                "Volume somado (passageiros pagos na ANAC, quantidade na ANP)",
                NUMERO_DECIMAL,
            ),
            "primeira": ("Primeiro mês em que aparece", DATA),
            "ultima": ("Último mês em que aparece", DATA),
            "fonte": ("Fonte no registro de coletas", TEXTO),
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
            "data-base. A instituição cujo código é o CNPJ de uma empresa do FCA liga por ele (o Banco "
            "PAN, do conglomerado do BTG, tem ação própria); as outras, pela raiz do CNPJ do líder do "
            "conglomerado. Antes de 2010 (sem FCA) a "
            "ligação chega ao CNPJ, mas não à ação. Instituição sem ação (Caixa, BNDES) fica sem CNPJ"
        ),
        fonte="Derivado: IF.data (cadastro) e CVM, FCA (emissores e tickers)",
        familia_da_fonte="bcb",
        frequencia="Trimestral, montada de novo a cada carga",
        atraso="O do cadastro do IF.data",
        onde="Parquet em `<acervo>/base/bcb/ifdata/ligacao_dos_bancos.parquet` (servidor de casa)",
        linhagem=(
            "O `.json` lista cada cadastro e as tabelas do FCA usados, com o SHA-256 de cada "
            "arquivo, e a versão do código." + LINHAGEM_DAS_DERIVADAS
        ),
        colunas={
            "data_base": ("Data-base do cadastro", DATA),
            "cod_inst": ("Código da instituição no BC", TEXTO),
            "instituicao": ("Nome da instituição", TEXTO),
            "cnpj_raiz": ("Raiz do CNPJ (8 dígitos)", TEXTO),
            "cnpj": ("CNPJ da empresa da bolsa (vazio se não tem ação)", TEXTO),
            "tickers": (
                "Códigos que valiam na data-base (FCA já entregue), separados por vírgula",
                TEXTO,
            ),
            "ligado_por": (
                (
                    "próprio CNPJ (a instituição é a empresa da bolsa, como o Banco PAN) ou líder "
                    "do conglomerado; vazio sem ligação"
                ),
                TEXTO,
            ),
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
    # --- série B: base histórica no servidor de casa (`scripts/montar_base_historica.py`) ---------
    "eventos": Tabela(
        descricao=(
            "Documentos do IPE da CVM desde 2003 (fatos relevantes, comunicados, assembleias, "
            "resultados...), com o tema e a materialidade do tipo de documento. A mesma entrega "
            "reapresentada fica só na versão mais nova."
        ),
        fonte="CVM: dados abertos do IPE (documentos periódicos e eventuais), um arquivo por ano",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DA_HISTORICA + " (o IPE da CVM muda todo dia)",
        atraso="Nenhum além da entrega: o documento vale a partir de `publicado_em`",
        onde=_onde_da_historica("eventos"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "protocolo": ("Protocolo de entrega na CVM", TEXTO),
            "versao": ("Versão da entrega (fica a mais nova)", NUMERO),
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "categoria": ("Categoria do documento, como a CVM publica", TEXTO),
            "tipo": ("Tipo do documento, como a CVM publica (pode vir vazio)", TEXTO),
            "assunto": ("Assunto escrito pela empresa", TEXTO),
            "rotulo": ("Nome curto do tipo de documento (`src/eventos.py`)", TEXTO),
            "tema": ("resultados, proventos, eventos ou risco", TEXTO),
            "materialidade": (
                "Quanto o tipo de documento costuma importar (escolha editorial)",
                "0 a 100",
            ),
            "referencia": ("Data a que o documento se refere", DATA),
            "publicado_em": ("Data de entrega à CVM", DATA),
            "link": ("Endereço do documento original no sistema da CVM", TEXTO),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "negociacoes": Tabela(
        descricao=(
            "Compras e vendas de ações e units por controladores, diretores, conselheiros e pela "
            "própria companhia (tesouraria), declaradas à CVM no VLMO desde 2018"
        ),
        fonte="CVM: dados abertos do VLMO (valores mobiliários negociados e detidos)",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DA_HISTORICA + " (o VLMO é mensal)",
        atraso=(
            "Até 10 dias depois do fim do mês da negociação (Resolução CVM 44); a linha vale a "
            "partir de `entregue_em`"
        ),
        onde=_onde_da_historica("negociacoes"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "fonte": ("De onde veio a declaração (`cvm-vlmo`)", TEXTO),
            "documento": (
                "CNPJ e mês de referência do formulário (`cnpj|AAAA-MM`)",
                TEXTO,
            ),
            "versao": ("Versão do formulário (fica a mais nova)", NUMERO),
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "cargo": (
                (
                    "controlador, diretoria, conselho, conselho_fiscal, outros_orgaos ou "
                    "companhia (tesouraria)"
                ),
                TEXTO,
            ),
            "cargo_descricao": ("Cargo por extenso (vazio no VLMO)", TEXTO),
            "operacao": ("compra ou venda", TEXTO),
            "ativo": (
                "Tipo e característica do valor mobiliário (até 80 letras)",
                TEXTO,
            ),
            "data": ("Data da negociação", DATA),
            "referencia": ("Mês de referência do formulário (1º dia)", DATA),
            "entregue_em": ("Data de entrega do formulário à CVM", DATA),
            "quantidade": ("Quantidade negociada", ACOES),
            "preco": ("Preço unitário informado", "reais (R$) por ação"),
            "valor": ("Volume informado ou, sem ele, quantidade × preço", "reais (R$)"),
            "moeda": ("Moeda (sempre BRL)", TEXTO),
            "plano_10b5_1": ("Plano de negociação da SEC (vazio na CVM)", SIM_OU_NAO),
            "link": ("Endereço do formulário original no sistema da CVM", TEXTO),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "proventos": Tabela(
        descricao=(
            "Dividendos e JCP de cada exercício pelo FRE de todos os anos guardados (a versão de "
            "longo prazo de `fre_proventos`, do app)"
        ),
        fonte="CVM: dados abertos do Formulário de Referência (FRE), tabela de distribuição",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DA_HISTORICA + _SO_ATE_2022,
        atraso=ATRASO_DO_FRE,
        onde=_onde_da_historica("proventos"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "referencia": ("Data de referência do FRE de onde a linha veio", DATA),
            "versao": ("Versão desse FRE (1, 2, 3...)", NUMERO),
            "exercicio": ("Fim do exercício social", DATA),
            "lucro_ajustado": ("Lucro líquido ajustado, base da distribuição", REAIS),
            "dividendo_total": ("Total distribuído (dividendos e JCP)", REAIS),
            "payout": ("Parte do lucro ajustado distribuída", FRACAO),
            "dividendos": ("Dividendos declarados", REAIS),
            "jcp": ("Juros sobre capital próprio declarados", REAIS),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "eventos_de_capital": Tabela(
        descricao=(
            "Desdobramentos, grupamentos, bonificações e aumentos de capital pelo FRE de todos os "
            "anos guardados (a versão de longo prazo de `fre_eventos_de_capital`, do app)"
        ),
        fonte=(
            "CVM: dados abertos do Formulário de Referência (FRE), tabelas de desdobramentos, "
            "grupamentos, bonificações e aumentos de capital"
        ),
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DA_HISTORICA + _SO_ATE_2022,
        atraso=ATRASO_DO_FRE,
        onde=_onde_da_historica("eventos_de_capital"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "referencia": ("Data de referência do FRE de onde a linha veio", DATA),
            "versao": ("Versão desse FRE (1, 2, 3...)", NUMERO),
            "tipo": ("desdobramento, grupamento, bonificação ou aumento", TEXTO),
            "data": ("Data da aprovação ou da deliberação", DATA),
            "acoes_antes": ("Ações antes do evento", ACOES),
            "acoes_depois": ("Ações depois do evento", ACOES),
            "fator": ("Depois ÷ antes (desdobramento de 1 para 10 = 10)", "vezes"),
            "acoes_novas": ("Ações emitidas no aumento de capital", ACOES),
            "valor": ("Valor do aumento de capital", REAIS),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "insolvencia": Tabela(
        descricao=(
            "Rótulos de recuperação judicial ou extrajudicial, pedido de falência, falência e "
            "liquidação lidos do IPE desde 2003, com a evidência de cada um: documento da categoria "
            "própria da CVM (`categoria_ipe`) ou fato relevante que anuncia o pedido "
            "(`fato_relevante`, costuma ser o primeiro sinal público)"
        ),
        fonte="CVM: dados abertos do IPE, um arquivo por ano (`base/rotulos.py`)",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DA_HISTORICA,
        atraso="O rótulo vale a partir de `conhecido_em` (entrega à CVM)",
        onde=_onde_da_historica("insolvencia"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "rotulo": (
                (
                    "recuperacao_judicial, recuperacao_extrajudicial, pedido_de_falencia, falencia "
                    "ou liquidacao"
                ),
                TEXTO,
            ),
            "evidencia": ("categoria_ipe ou fato_relevante", TEXTO),
            "categoria": ("Categoria do documento, como a CVM publica", TEXTO),
            "tipo": ("Tipo do documento, como a CVM publica (pode vir vazio)", TEXTO),
            "assunto": ("Assunto escrito pela empresa", TEXTO),
            "conhecido_em": ("Data de entrega à CVM (quando ficou público)", DATA),
            "referencia": ("Data a que o documento se refere", DATA),
            "protocolo": ("Protocolo de entrega na CVM", TEXTO),
            "versao": ("Versão da entrega", NUMERO),
            "link": ("Endereço do documento original no sistema da CVM", TEXTO),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "cnpj_situacao_especial": Tabela(
        descricao=(
            'Estabelecimentos com "situação especial" no CNPJ da Receita (falido, em recuperação, '
            'em liquidação, intervenção...), um retrato por mês guardado: o histórico "como era na '
            'data" nasce da sequência dos retratos. Nome, endereço, telefone e e-mail nunca entram '
            "(LGPD)."
        ),
        fonte="Receita Federal: dados abertos do CNPJ, arquivos de estabelecimentos",
        familia_da_fonte="rfb-cnpj",
        frequencia="Mensal (a Receita publica um retrato por mês; cada mês guardado vira um arquivo)",
        atraso=(
            "O retrato sai semanas depois do mês; `data_situacao_especial` é a data que a Receita "
            "informa, que pode ser anterior ao retrato em que a linha apareceu pela primeira vez"
        ),
        onde="Parquet em `<acervo>/base/cnpj_situacao_especial/<AAAA-MM>.parquet` (servidor de casa)",
        linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "cnpj_basico": ("Raiz do CNPJ (8 dígitos): a empresa", TEXTO),
            "matriz": ("Verdadeiro na matriz, falso na filial", SIM_OU_NAO),
            "situacao_especial": ("Situação especial, como a Receita escreve", TEXTO),
            "rotulo": (
                (
                    "falencia, recuperacao_judicial, recuperacao_extrajudicial, liquidacao, "
                    "liquidacao_judicial, liquidacao_extrajudicial ou intervencao (vazio nas outras "
                    "situações, como espólio)"
                ),
                TEXTO,
            ),
            "data_situacao_especial": ("Data da situação especial informada", DATA),
            "mes_do_retrato": (
                "Mês do arquivo da Receita de onde a linha veio",
                "AAAA-MM",
            ),
            **_ORIGEM_SEM_ANO,
        },
    ),
    "auditores": Tabela(
        descricao=(
            "Mandatos de auditor independente de cada companhia pelo FCA desde 2010 (firma, início "
            "e fim). A firma é identificada pela rede, lida do nome (KPMG, EY, PwC, Deloitte...), "
            "porque CNPJ e código da CVM vêm errados em parte das linhas. O sócio responsável (nome "
            "e CPF) nunca entra (LGPD)."
        ),
        fonte="CVM: dados abertos do FCA, tabela de auditores (`base/auditores.py`)",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DO_FCA,
        atraso=(
            "Até meses: o acervo só tem a última versão de cada FCA, então `conhecido_em` pode ser "
            "mais tarde que a primeira notícia, nunca mais cedo"
        ),
        onde=_onde_da_historica("auditores"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "referencia": ("Data de referência do FCA", DATA),
            "versao": ("Versão do FCA", NUMERO),
            "id_documento": ("Número do documento na CVM", TEXTO),
            "conhecido_em": ("Data em que a CVM recebeu essa versão do FCA", DATA),
            "auditor_id": (
                (
                    "Identificador da firma: `rede:<nome>` nas redes; senão código da CVM, raiz do "
                    "CNPJ ou nome"
                ),
                TEXTO,
            ),
            "auditor": ("Nome da firma, como a empresa escreveu", TEXTO),
            "auditor_cnpj": (
                "CNPJ da firma informado (14 dígitos; pode estar errado)",
                TEXTO,
            ),
            "codigo_cvm_auditor": ("Código da firma na CVM informado", TEXTO),
            "origem": ("Nacional ou estrangeiro, como a CVM publica", TEXTO),
            "inicio": ("Início do mandato", DATA),
            "fim": ("Fim do mandato (vazio: em curso)", DATA),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "trocas_de_auditor": Tabela(
        descricao=(
            'Rótulo "trocou de auditor": cada troca de firma, montada de todos os anos de '
            "`auditores` na ordem de entrega dos FCAs (uma troca nunca é reescrita depois)"
        ),
        fonte="CVM: dados abertos do FCA, pela tabela `auditores`",
        familia_da_fonte="cvm",
        frequencia="Refeita a cada montagem de `auditores`",
        atraso="A troca vale a partir de `conhecido_em` (entrega do FCA que a mostrou)",
        onde="Parquet em `<acervo>/base/trocas_de_auditor/trocas.parquet` (servidor de casa)",
        linhagem=(
            "`id_documento` leva ao FCA (e dali à linha de `auditores`, que guarda o SHA-256 do "
            "original); `montado_em` diz quando a tabela foi montada. "
            + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "conhecido_em": ("Data de entrega do FCA que mostrou a troca", DATA),
            "efetiva_em": ("Início do mandato da firma nova", DATA),
            "anterior_id": ("Identificador da firma anterior (ver `auditores`)", TEXTO),
            "anterior": ("Nome da firma anterior", TEXTO),
            "novo_id": ("Identificador da firma nova", TEXTO),
            "novo": ("Nome da firma nova", TEXTO),
            "anos_com_o_anterior": ("Tempo com a firma anterior", "anos"),
            "id_documento": ("Número na CVM do FCA que mostrou a troca", TEXTO),
            "montado_em": ("Quando a tabela foi montada", MOMENTO),
            "versao_do_codigo": ("Commit do código que montou a tabela", TEXTO),
        },
    ),
    "curva_juros": Tabela(
        descricao=(
            "Curva de juros própria, sem B3 nem ANBIMA: nominal (Tesouro Prefixado), real (Tesouro "
            "IPCA+) e inflação implícita, nos vértices de 6 meses a 20 anos, só com os títulos sem "
            "cupom, interpolação flat-forward e sem extrapolar (nominal desde 2004, real desde "
            "2005). A taxa do Tesouro Direto tem um spread sobre o mercado secundário."
        ),
        fonte="Tesouro Nacional: taxas diárias do Tesouro Direto (Tesouro Transparente)",
        familia_da_fonte="tesouro-br-direto",
        frequencia="Diária (dias úteis)",
        atraso="Um dia útil: o arquivo do Tesouro sai na manhã seguinte (`disponivel_em`)",
        onde=_onde_da_historica("curva_juros"),
        linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
        colunas={
            "data_base": ("Dia das taxas", DATA),
            "curva": ("nominal, real ou implicita", TEXTO),
            "prazo_anos": ("Vértice da curva (0,5 a 20)", "anos (base 252)"),
            "taxa": ("Taxa ao ano no vértice", FRACAO),
            "titulos": ("Títulos usados na curva do dia", NUMERO),
            "maior_prazo_anos": (
                "Prazo do título mais longo do dia",
                "anos (base 252)",
            ),
            "disponivel_em": ("Dia útil seguinte: quando a taxa ficou pública", DATA),
            **_ORIGEM_SEM_ANO,
        },
    ),
    "controladas": Tabela(
        descricao=(
            "Controladas e coligadas de cada companhia informadas no FRE desde 2010, com a "
            "participação e a data de entrega. O FRE mais novo deixa o tipo da sociedade em branco "
            "em muitas linhas, e o FRE guarda ligações antigas."
        ),
        fonte="CVM: dados abertos do FRE, tabela de participação em sociedades",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DA_HISTORICA,
        atraso=ATRASO_DO_FRE + "; a ligação vale a partir de `conhecido_em`",
        onde=_onde_da_historica("controladas"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj_companhia": ("CNPJ da companhia que informou (14 dígitos)", TEXTO),
            "companhia": ("Nome da companhia", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE (fica a mais nova)", NUMERO),
            "id_documento": ("Número do documento na CVM", TEXTO),
            "conhecido_em": ("Data em que a CVM recebeu essa versão do FRE", DATA),
            "cnpj": ("CNPJ da sociedade (14 dígitos; vazio nas estrangeiras)", TEXTO),
            "razao_social": ("Razão social da sociedade", TEXTO),
            "tipo": ("controlada, coligada ou vazio (não informado)", TEXTO),
            "participacao": (
                "Participação da companhia na sociedade",
                PONTOS_PERCENTUAIS,
            ),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "rotulos_atraso": Tabela(
        descricao=(
            "Rótulo do modelo de atraso na entrega (modelo 8, ADR 0030): uma linha por companhia, "
            "documento (DFP ou ITR) e data-base, com o prazo da CVM, a primeira entrega e se atrasou. "
            "Entram os documentos entregues e os devidos sem entrega (entregou um ano antes, ativa "
            "no prazo, data-base no calendário da empresa e no arquivo do ano). Não entra o "
            "documento com o prazo antes do primeiro registro da empresa (o que ela manda para "
            "pedir o registro, sem prazo a cumprir); o manifesto conta quantos ficaram de fora "
            "(`fora_dos_exemplos`). Não é coluna para prever: é a resposta que o modelo tenta "
            "acertar (ADR 0027)"
        ),
        fonte="CVM: dados abertos da DFP e do ITR (índice das entregas) e cadastro das companhias",
        familia_da_fonte="cvm",
        frequencia="Refeita a cada montagem, com os arquivos anuais e o cadastro mais recentes",
        atraso=(
            "O rótulo de um documento existe a partir do prazo (ou da entrega, se veio antes); uma "
            "falta só conta se o prazo venceu antes da coleta do arquivo do ano"
        ),
        onde=(
            "Parquet em `<acervo>/base/rotulos_atraso/rotulos_atraso.parquet`, com o manifesto ao "
            "lado (servidor de casa, `scripts/montar_base_historica.py`)"
        ),
        linhagem=(
            "O manifesto (`rotulos_atraso.json`) lista o endereço e o SHA-256 de cada arquivo anual "
            "da DFP e do ITR e do cadastro usados, e o SHA-256 da tabela; `montado_em` diz quando "
            "a tabela foi montada. " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            **_EMPRESA,
            **_DOCUMENTO,
            "data_da_previsao": (
                "Dia em que o modelo faz a pergunta (a própria data-base)",
                DATA,
            ),
            "prazo": (
                "Último dia para entregar, com feriados e prorrogações (`src/prazos.py`)",
                DATA,
            ),
            "primeira_entrega": ("Dia da primeira entrega (vazio: não entregou)", DATA),
            "dias_uteis_de_atraso": (
                "Dias úteis entre o prazo e a entrega (ou a montagem, sem entrega); 0 no prazo",
                NUMERO,
            ),
            "atrasou": (
                "Entregou 1 dia útil ou mais depois do prazo, ou não entregou",
                SIM_OU_NAO,
            ),
            "atraso_grave": (
                "Mais de 30 dias corridos de atraso, ou não entregou",
                SIM_OU_NAO,
            ),
            "zona_cinzenta": (
                "Atraso de 1 ou 2 dias úteis: pode ser um feriado estadual ou municipal",
                SIM_OU_NAO,
            ),
            "uf": ("Estado da sede, no cadastro de hoje", TEXTO),
            "mes_fim_do_exercicio": (
                "Mês de fim do exercício (o mais comum nas DFPs da companhia)",
                "mês (1 a 12)",
            ),
            "montado_em": _ORIGEM_SEM_ANO["montado_em"],
            "versao_do_codigo": _ORIGEM_SEM_ANO["versao_do_codigo"],
        },
    ),
    "empresa_serie": Tabela(
        descricao=(
            "De que companhia listada é cada entidade que os reguladores enxergam (operadora de "
            "saúde, distribuidora, banco no Pix, prestadora de telecomunicações, usina, "
            "concessionária de ferrovia, companhia aérea): pelo CNPJ, pelo nome exato ou pela "
            "tabela conferida (`base/conferidas/empresa_serie.csv`), e daí pelas `controladas`. "
            "Os capítulos do NCM do Comex Stat ligam às companhias expostas ao produto "
            "(`via` = `produto`: exposição, não posse). Toda entidade aparece, ligada ou não."
        ),
        fonte=(
            "ANS, ANEEL (SAMP), Banco Central (Pix), Anatel, ANP, ONS, ANTT, ANAC e Comex Stat, "
            "ligados pelo FRE da CVM e pelo FCA (tickers)"
        ),
        familia_da_fonte="cvm",
        frequencia="Refeita a cada montagem, com a safra mais recente de cada fonte",
        atraso=(
            "A ligação vale a partir de `desde` (entrega do FRE que a mostrou); os tickers são os "
            "do FCA mais recente"
        ),
        onde="Parquet em `<acervo>/base/empresa_serie/empresa_serie.parquet` (servidor de casa)",
        linhagem=(
            "`origem_sha256` leva ao arquivo do regulador no acervo de onde a entidade saiu (no "
            "Comex, à versão da tabela conferida); as ligações saem de `controladas`, que guarda "
            "o SHA-256 de cada FRE; `montado_em` diz quando a tabela foi montada. "
            + COM_VERSAO_DO_CODIGO
        ),
        ressalva_de_revenda=(
            "Os nomes e códigos das entidades seguem a licença de cada regulador: CC BY (ANS, "
            "Anatel, ANP, ONS, ANTT, ANAC; citar), ODbL (ANEEL, Banco Central) e Comex Stat a "
            "confirmar com o MDIC."
        ),
        colunas={
            "fonte": ("Fonte do arquivista de onde veio a entidade", TEXTO),
            "chave": (
                (
                    "Como a fonte identifica a entidade: registro ANS, CNPJ, ISPB, nome, sigla ou "
                    "capítulo do NCM"
                ),
                TEXTO,
            ),
            "nome": ("Nome da entidade na fonte (ou na tabela conferida)", TEXTO),
            "raiz": ("Raiz do CNPJ da entidade (8 dígitos), quando há", TEXTO),
            "cnpj_companhia": ("CNPJ da companhia ligada (14 dígitos)", TEXTO),
            "companhia": ("Nome da companhia ligada", TEXTO),
            "via": ("propria, controlada, coligada, sem_tipo ou produto", TEXTO),
            "por": ("cnpj, nome ou tabela (conferida à mão)", TEXTO),
            "participacao": (
                "Participação informada no FRE (vazia no produto)",
                PONTOS_PERCENTUAIS,
            ),
            "desde": ("1ª entrega à CVM de um FRE que mostrava a ligação", DATA),
            "ultima_referencia": (
                "Referência do FRE mais novo que mostra a ligação",
                DATA,
            ),
            "principal": (
                (
                    "A ligação a usar da entidade (ticker hoje, própria, FRE mais recente; nunca no "
                    "produto)"
                ),
                SIM_OU_NAO,
            ),
            "tickers": ("Tickers da companhia no FCA mais recente", TEXTO),
            "origem_sha256": ("SHA-256 do arquivo de onde a entidade saiu", TEXTO),
            "montado_em": ("Quando a tabela foi montada", MOMENTO),
            "versao_do_codigo": ("Commit do código que montou a tabela", TEXTO),
        },
    ),
    "entidades": Tabela(
        descricao=(
            "Uma linha por entidade da rede (ADR 0077): empresa (pela raiz do CNPJ; a filial é a "
            "mesma empresa) ou fundo (pelo CNPJ de 14), com id determinístico (`base/rede/ids.py`), "
            "nome, natureza jurídica e MEI. Vem das tabelas que a base já tem: cadastro da CVM, FCA, "
            "controladas, empresa ↔ série, cadastro de fundos, IF.data e GLEIF. Empresário "
            "individual, pessoa física com CNPJ e MEI ficam sem nome e com `trata_como_pessoa`"
        ),
        fonte=(
            "CVM (cadastro, FCA, FRE, fundos), Banco Central (IF.data), GLEIF, os reguladores da "
            "empresa ↔ série e a Receita (natureza jurídica e opção pelo MEI)"
        ),
        familia_da_fonte="cvm",
        frequencia="Refeita a cada montagem; versão nova só quando o conteúdo muda",
        atraso="O da fonte mais lenta de cada entidade; `publico_em` diz desde quando se sabe dela",
        onde=_ONDE_DA_REDE.format(t="entidades"),
        linhagem=LINHAGEM_DA_REDE,
        ressalva_de_revenda=RESSALVA_DA_REDE,
        colunas={
            "id_entidade": (
                "'E' + 20 hexadecimais do SHA-256 do identificador primário",
                TEXTO,
            ),
            "tipo": ("empresa ou fundo", TEXTO),
            "nome": (
                "Nome pela fonte mais confiável (vazio na pessoa com CNPJ)",
                TEXTO,
            ),
            "natureza_juridica": (
                "Código da natureza jurídica da Receita (2046 = S.A. aberta) ou nao_informada",
                TEXTO,
            ),
            "natureza_fonte": (
                "receita, fonte (CVM ou cadastro de fundos) ou nao_informada",
                TEXTO,
            ),
            "mei": ("Verdadeiro se é MEI hoje (Simples da Receita)", SIM_OU_NAO),
            "trata_como_pessoa": (
                (
                    "Verdadeiro para empresário individual (213-5), grupo 4, MEI e natureza "
                    "não informada: nunca recebe sinal negativo publicado"
                ),
                SIM_OU_NAO,
            ),
            "fontes": (
                "As fontes de onde a entidade saiu, separadas por vírgula",
                TEXTO,
            ),
            "publico_em": (
                "O dia mais antigo em que alguma fonte a tornou pública",
                DATA,
            ),
        },
    ),
    "identificadores": Tabela(
        descricao=(
            "Os identificadores de cada entidade da rede, com de quando a quando valem: CNPJ (com "
            "letras), raiz, LEI, ticker, emissor e códigos dos reguladores (`codigo_<fonte>`). "
            "Resolvidos por regras de código em ordem fixa (1 CNPJ, 2 raiz, 3 LEI, 4 emissor e "
            "ticker, 5 código do regulador, 7 tabela conferida); o mesmo identificador em duas "
            "entidades no mesmo período é conflito e não entra em nenhuma"
        ),
        fonte=(
            "CVM (cadastro, FCA, FRE, fundos), Banco Central (IF.data), GLEIF e os reguladores da "
            "empresa ↔ série"
        ),
        familia_da_fonte="cvm",
        frequencia="Refeita a cada montagem; versão nova só quando o conteúdo muda",
        atraso="O ticker vale da entrega do FCA que o trouxe; o código do IF.data, 120 dias depois",
        onde=_ONDE_DA_REDE.format(t="identificadores"),
        linhagem=LINHAGEM_DA_REDE,
        ressalva_de_revenda=RESSALVA_DA_REDE,
        colunas={
            "id_entidade": ("A entidade (tabela `entidades`)", TEXTO),
            "sistema": (
                "cnpj, cnpj_raiz, lei, ticker, emissor ou codigo_<fonte> (codigo_bcb_ifdata...)",
                TEXTO,
            ),
            "valor": (
                "O identificador (CNPJ sem pontuação, com letras se tiver)",
                TEXTO,
            ),
            "desde": ("Desde quando vale (vazio: sempre)", DATA),
            "ate": ("Até quando valeu, sem incluir o dia (vazio: ainda vale)", DATA),
            "publico_em": (
                "Desde quando a ligação era pública (como era na data)",
                DATA,
            ),
            "regra": (
                "A regra que ligou (1, 2, 3, 4, 5 ou 7; a menor, se várias)",
                NUMERO,
            ),
            "conferido_por": ("regra (código) ou tabela (conferida à mão)", TEXTO),
            "fontes": (
                "As fontes que trouxeram o identificador, separadas por vírgula",
                TEXTO,
            ),
        },
    ),
}


_ME = "mercado_e_empresas"
_FIDC = "credito_e_fidc"
_CVM = "2010-01-01"  # primeiro arquivo da CVM que a base lê (FRE, ITR e DFP de 2010)
_GOVERNO = "2026-10-14"  # as fontes de governo só passaram a ser guardadas neste dia


# módulo, chaves, apelidos das três datas (`aconteceu_em`: quando o fato ocorreu; `publico_em`: quando
# ficou público; `coletado_em`: quando a base o guardou), `historico_desde` e granularidade do
# `publico_em`; só colunas que já existem, sem inventar data onde a fonte não dá
def _contrato(**campos: object) -> dict[str, object]:
    return campos


_CONTRATO = {
    "demonstracoes_como_era": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia", "versao", "demonstracao", "grupo", "conta"), datas={"aconteceu_em": "referencia", "publico_em": "divulgado_em"}, historico_desde=_CVM),
    "achados_de_qualidade": _contrato(modulo=_ME, chaves=("id",), datas={"aconteceu_em": "referencia", "publico_em": "valido_desde", "coletado_em": "calculado_em"}, historico_desde=_CVM),
    "cadastro_das_companhias": _contrato(modulo=_ME, chaves=("cnpj",), datas={"aconteceu_em": "registro"}, historico_desde=_CVM),
    "tickers_no_tempo": _contrato(modulo=_ME, chaves=("codigo", "cnpj"), datas={"aconteceu_em": "inicio_negociacao", "publico_em": "primeiro_visto"}, historico_desde=_CVM),
    "valores_mobiliarios": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao", "valor_mobiliario"), datas={"aconteceu_em": "referencia", "publico_em": "recebido_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "emissores": _contrato(modulo=_ME, chaves=("emissor", "cnpj"), datas={"publico_em": "primeiro_recebido_em"}, historico_desde=_CVM),
    "codigos_invalidos": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "codigo_informado"), datas={"aconteceu_em": "referencia", "publico_em": "recebido_em"}, historico_desde=_CVM),
    "carteiras_dos_fundos": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_fundo", "tipo", "codigo"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "carteiras_bloco_8": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_fundo", "tipo", "cnpj_emissor"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "fidc_informe": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_fundo"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "cadastro_de_fundos": _contrato(modulo=_FIDC, chaves=("CNPJ_FUNDO",), datas={"aconteceu_em": "DT_REG"}, historico_desde=_CVM),
    "painel_dos_fundos": _contrato(modulo=_FIDC, chaves=("competencia", "emissor", "tipo"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "cobertura_dos_fundos": _contrato(modulo=_FIDC, chaves=("competencia",), datas={"aconteceu_em": "competencia"}, historico_desde=_CVM),
    "buracos_dos_fundos": _contrato(modulo=_FIDC, chaves=("emissor",), historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "emissores_antigos": _contrato(modulo=_ME, chaves=("emissor",), datas={"coletado_em": "conferido_em"}, historico_desde=_CVM),
    "emissores_sem_ligacao": _contrato(modulo=_ME, chaves=("emissor",), datas={"coletado_em": "conferido_em"}, historico_desde=_CVM),
    "codigos_fora_do_fca": _contrato(modulo=_ME, chaves=("codigo",), datas={"coletado_em": "conferido_em"}, historico_desde=_CVM),
    "anac_estatistico": _contrato(modulo=_ME, chaves=("competencia", "empresa_sigla", "aeroporto_de_origem_sigla", "aeroporto_de_destino_sigla", "natureza", "grupo_de_voo"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "anp_vendas": _contrato(modulo=_ME, chaves=("competencia", "grupo", "agente", "codigo_do_produto", "uf_origem", "uf_destino", "mercado_destino"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "ons_geracao": _contrato(modulo=_ME, chaves=("instante", "id_ons"), datas={"aconteceu_em": "instante", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "aneel_samp": _contrato(modulo=_ME, chaves=("competencia", "cnpj", "tipo_de_mercado", "modalidade_tarifaria", "subgrupo_tarifario", "classe_de_consumo", "subclasse_de_consumo", "detalhe_do_consumidor", "nucleo_ceg", "posto_tarifario", "opcao_de_energia", "detalhe_do_mercado", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "anatel_acessos": _contrato(modulo=_ME, chaves=("competencia", "servico", "recorte", "cnpj", "uf", "regiao_pgo", "codigo_nacional", "modalidade_de_cobranca", "tecnologia", "geracao", "tipo_de_pessoa", "tipo_de_produto", "faixa_de_velocidade", "meio_de_acesso", "tipo_de_acesso_tv", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "ans_beneficiarios": _contrato(modulo=_ME, chaves=("competencia", "cd_operadora", "modalidade", "cobertura", "vigencia_do_plano", "contratacao", "financiamento", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "fre_conselho": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_comites": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'tipo_de_comite'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_remuneracao": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'fim_do_exercicio', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_remuneracao_extremos": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'fim_do_exercicio', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_diversidade": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "ofertas_antigas": _contrato(modulo=_ME, chaves=('numero_processo', 'numero_registro_oferta', 'cnpj_emissor', 'tipo_ativo', 'classe_ativo', 'serie', 'emissao'), datas={"aconteceu_em": "anunciada_em", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "ofertas_resolucao_160": _contrato(modulo=_ME, chaves=('numero_requerimento', 'cnpj_emissor'), datas={"aconteceu_em": "anunciada_em", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "setoriais_buracos": _contrato(modulo=_ME, chaves=("fonte", "chave"), historico_desde=_GOVERNO),
    "ifdata_valores": _contrato(modulo=_ME, chaves=("data_base", "tipo_instituicao", "cod_inst", "relatorio", "grupo", "conta", "coluna"), datas={"aconteceu_em": "data_base", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "ifdata_cadastro": _contrato(modulo=_ME, chaves=("data_base", "cod_inst"), datas={"aconteceu_em": "data_base"}, historico_desde=_CVM),
    "ligacao_dos_bancos": _contrato(modulo=_ME, chaves=("data_base", "cod_inst"), datas={"aconteceu_em": "data_base"}, historico_desde=_CVM),
    "scr_credito": _contrato(modulo=_FIDC, chaves=("data_base", "uf", "segmento", "cliente", "cnae_ocupacao", "porte", "modalidade", "submodalidade", "origem", "indexador"), datas={"aconteceu_em": "data_base"}, historico_desde=_CVM),
    "padroes_setoriais": _contrato(modulo=_ME, chaves=("data_de_corte", "grupo", "indicador", "versao"), datas={"aconteceu_em": "data_de_corte", "coletado_em": "calculado_em"}, historico_desde=_CVM),
    "fre_proventos": _contrato(modulo=_ME, chaves=("cnpj", "exercicio", "referencia", "versao"), datas={"aconteceu_em": "referencia", "coletado_em": "coletado_em"}, historico_desde=_CVM),
    "fre_eventos_de_capital": _contrato(modulo=_ME, chaves=("cnpj", "tipo", "data", "referencia", "versao"), datas={"aconteceu_em": "data", "coletado_em": "coletado_em"}, historico_desde=_CVM),
    "eventos": _contrato(modulo=_ME, chaves=("protocolo", "versao"), datas={"aconteceu_em": "referencia", "publico_em": "publicado_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "negociacoes": _contrato(modulo=_ME, chaves=("fonte", "documento", "versao", "cnpj", "cargo", "operacao", "ativo", "data"), datas={"aconteceu_em": "data", "publico_em": "entregue_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "proventos": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao"), datas={"aconteceu_em": "referencia", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "eventos_de_capital": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao", "tipo", "data"), datas={"aconteceu_em": "data", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "insolvencia": _contrato(modulo=_ME, chaves=("cnpj", "protocolo", "versao", "rotulo"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "cnpj_situacao_especial": _contrato(modulo="governo_e_sancoes", chaves=("cnpj", "mes_do_retrato"), datas={"aconteceu_em": "data_situacao_especial", "publico_em": "mes_do_retrato", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "auditores": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao", "auditor_id"), datas={"aconteceu_em": "inicio", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "trocas_de_auditor": _contrato(modulo=_ME, chaves=("cnpj", "efetiva_em", "novo_id"), datas={"aconteceu_em": "efetiva_em", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "curva_juros": _contrato(modulo="macro", chaves=("data_base", "curva", "prazo_anos"), datas={"aconteceu_em": "data_base", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "controladas": _contrato(modulo=_ME, chaves=("cnpj_companhia", "referencia", "versao", "cnpj"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "rotulos_atraso": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia"), datas={"aconteceu_em": "prazo", "publico_em": "primeira_entrega", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "empresa_serie": _contrato(modulo=_ME, chaves=("fonte", "chave", "cnpj_companhia"), datas={"aconteceu_em": "desde", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "entidades": _contrato(modulo="rede", chaves=("id_entidade",), datas={"publico_em": "publico_em"}, historico_desde=_CVM),
    "identificadores": _contrato(modulo="rede", chaves=("id_entidade", "sistema", "valor", "desde"), datas={"aconteceu_em": "desde", "publico_em": "publico_em"}, historico_desde=_CVM),
}  # fmt: skip


def _contrato_de(nome: str) -> dict[str, object]:
    if nome not in _CONTRATO:
        raise KeyError(
            f"tabela nova `{nome}`: ponha módulo, chaves, três datas e histórico dela em "
            "`_CONTRATO` (base/dicionario.py) e rode `python -m base.contrato`"
        )
    return _CONTRATO[nome]


TABELAS = {
    nome: replace(
        tabela, **{"granularidade_do_publico_em": "dia", **_contrato_de(nome)}
    )
    for nome, tabela in TABELAS.items()
}


def _datas_em_texto(tabela: Tabela) -> str:
    if not tabela.datas:
        return "nenhuma coluna da tabela traz estas datas"
    return "; ".join(
        f"{apelido} = `{coluna}`" for apelido, coluna in tabela.datas.items()
    )


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
        f"- **Módulo:** {tabela.modulo} · **Contém dado de pessoa:** {'sim' if tabela.pessoa else 'não'}",
        f"- **Chaves:** {', '.join(f'`{c}`' for c in tabela.chaves)}",
        f"- **Três datas:** {_datas_em_texto(tabela)}",
        f"- **Histórico desde:** {tabela.historico_desde} (`publico_em` por {tabela.granularidade_do_publico_em})",
        f"- **Versão do contrato:** {tabela.versao_do_contrato}",
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
