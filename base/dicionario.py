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

from src.banco.coletas import NAO_COMERCIAL, licenca_da_fonte, revenda_da_fonte
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
    # coluna renomeada numa versão maior: nome antigo → nome novo (a porta serve a versão antiga
    # como vista pelo contrato congelado; ADR 0077, item 8; plano, D12)
    renomeadas: dict[str, str] = field(default_factory=dict)
    # conferência dos valores do Parquet contra o contrato (`base/conferencia.py`); preenchido por
    # `_CONFERENCIA`, logo abaixo de `_CONTRATO`. O tipo e a faixa de cada coluna já saem da unidade.
    pasta: str = ""  # onde o Parquet fica dentro de `<acervo>/base/` (vazio: ainda não conferida)
    faixas: dict[str, tuple[float | None, float | None]] = field(
        default_factory=dict
    )  # coluna → (mínimo, máximo); None = sem limite desse lado
    nao_nulas: tuple[str, ...] = ()  # além das chaves, colunas que não aceitam vazio
    # o fato é anunciado antes de acontecer (assembleia, calendário, mandato que começa depois):
    # `aconteceu_em` pode vir depois de `publico_em`
    anuncia_o_futuro: bool = False


_ONDE_DA_REDE = "Parquet em `<acervo>/base/rede/{t}.parquet` (servidor de casa, `scripts/montar_rede.py`)"
LINHAGEM_DA_REDE = (
    "Derivada: o manifesto aponta as tabelas de entrada (com o SHA-256 do conteúdo), as tabelas "
    "conferidas (`emissores_antigos.csv`, `entidades.csv`) e os originais lidos do acervo "
    "(cadastro da CVM, páginas do GLEIF, Empresas e Simples da Receita); a linhagem segue até a "
    "coleta de cada um. " + COM_VERSAO_DO_CODIGO
)
RESSALVA_DA_REDE = (
    "A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita, que "
    "está como a confirmar (não entra em modelo) até a licença ser confirmada; o LEI é do GLEIF "
    "(CC0, citar); os "
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
            "valor": (
                (
                    "Valor da conta; vazio quando a empresa deixou em branco na versão lida do "
                    "ENET (nos dados abertos da CVM, a linha em branco vem como 0)"
                ),
                REAIS,
            ),
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
            "SHA-256 e data da coleta); a tabela é refeita dele. Não é gravada sozinha: o arquivo "
            "lido entra nas origens do manifesto de quem o usa (`rotulos_atraso`, "
            "`demonstracoes_como_era`), ao lado da versão do código que montou a tabela."
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
            "até 90 dias: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois "
            "(o prazo, não a data vista). Desde 10/2026 o arquivista olha os 5 meses mais novos todo "
            "dia: a carteira entregue depois do prazo só vale do dia em que apareceu (`visto_em`). "
            "Antes disso, a data é só o prazo"
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
            "visto_em": (
                (
                    "O dia em que a carteira do fundo apareceu na CVM pela primeira vez, pelas baixadas diárias do "
                    "arquivista (vazio: já estava no arquivo quando a base começou a olhar, em 10/2026; "
                    "vale o prazo)"
                ),
                DATA,
            ),
            "disponivel_em": (
                (
                    "Desde quando a posição era pública (como era na data): o prazo, ou `visto_em` se "
                    "for depois"
                ),
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
            "O do CDA: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois, ou o "
            "dia em que a carteira apareceu (`visto_em`, desde 10/2026) se for depois"
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
            "visto_em": (
                (
                    "O dia em que a carteira do fundo apareceu na CVM pela primeira vez, pelas baixadas "
                    "diárias do arquivista (vazio: já estava no arquivo quando a base começou a olhar, em "
                    "10/2026; vale o prazo)"
                ),
                DATA,
            ),
            "disponivel_em": (
                (
                    "Desde quando a posição era pública (como era na data): o prazo, ou `visto_em` se "
                    "for depois"
                ),
                DATA,
            ),
        },
    ),
    "cda_cotas": Tabela(
        descricao=(
            'As cotas de fundos que cada fundo tem, do bloco 2 do CDA ("cotas de fundos"): quem compra '
            "cotas de FIDC, de FIP, de FII e de outros fundos, com o CNPJ do fundo investido e o tipo dele "
            '(`tipo_do_ativo` = "FIDC" desde ~2009; em 2005 tudo é "Cotas de fundos"). Em jun/2026, '
            "4.531 fundos com R$ 291,8 bi em cotas de 2.403 FIDCs (relatório da base de crédito). Só fundos "
            "(pessoas jurídicas); os nomes ficam no cadastro de fundos. Um Parquet por ano, com versões"
        ),
        fonte="CVM: composição e diversificação das aplicações dos fundos (CDA), bloco 2",
        familia_da_fonte="cvm",
        frequencia="Mensal; de 2005 a 2022 um arquivo por ano, de 2023 em diante um por mês",
        atraso=(
            "O do CDA: `disponivel_em` usa competência + 90 dias, ou o fim do sigilo se depois, ou o "
            "dia em que a carteira apareceu (`visto_em`, desde 10/2026) se for depois"
        ),
        onde=(
            "Parquet por ano em `<acervo>/base/cda_cotas/<ano>.parquet` (servidor de casa, "
            "`scripts/carga_cda.py`, na mesma carga do CDA)"
        ),
        linhagem=(
            "O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do CDA "
            "usado (os mesmos do bloco 4) e a versão do código que gravou."
        ),
        colunas={
            "competencia": ("Mês da carteira (último dia)", DATA),
            "cnpj_fundo": (
                "CNPJ do fundo que tem as cotas (ou da classe, depois da CVM 175)",
                TEXTO,
            ),
            "tipo_do_fundo": (
                (
                    "Tipo do fundo que tem as cotas como a CVM informa; com o CNPJ, identifica o fundo (em "
                    "11/2022 um fundo aparece como FI e como FIP)"
                ),
                TEXTO,
            ),
            "tipo_do_ativo": (
                (
                    'Tipo do fundo investido como o fundo informa ("FIDC", "FI Participações", "FI '
                    'Imobiliário", "Fundos de Índice", "Fundo de Investimento e de Cotas", "Cotas de fundos")'
                ),
                TEXTO,
            ),
            "emissor_ligado": (
                (
                    "O fundo investido é ligado ao administrador ou ao gestor de quem compra (vazio: não "
                    "informado, como em 2005)"
                ),
                SIM_OU_NAO,
            ),
            "cnpj_fundo_investido": (
                "CNPJ do fundo (ou da classe) cujas cotas o fundo tem",
                TEXTO,
            ),
            "id_subclasse": (
                "Código da subclasse investida, depois da CVM 175 (vazio: sem subclasse)",
                TEXTO,
            ),
            "quantidade": ("Quantidade de cotas no fim do mês", NUMERO_DECIMAL),
            "valor": ("Valor de mercado no fim do mês", REAIS),
            "compras": ("Valor comprado no mês", REAIS),
            "vendas": ("Valor vendido no mês", REAIS),
            "confidencial_ate": (
                "Até quando a posição ficou em sigilo (vazio: sem sigilo)",
                DATA,
            ),
            "visto_em": (
                (
                    "O dia em que a carteira do fundo apareceu na CVM pela primeira vez, pelas baixadas "
                    "diárias do arquivista (vazio: já estava no arquivo quando a base começou a olhar, em "
                    "10/2026; vale o prazo)"
                ),
                DATA,
            ),
            "disponivel_em": (
                (
                    "Desde quando a posição era pública (como era na data): o prazo, ou `visto_em` se "
                    "for depois"
                ),
                DATA,
            ),
        },
    ),
    "fidc_informe": Tabela(
        descricao=(
            "O informe mensal de cada FIDC desde 2013, um Parquet por quadro (`tab_I` a `tab_X_7`) e "
            "por ano, no formato da fonte: carteira, prazos, inadimplência por faixa, pré-pagamento, "
            "recompras, cedentes. As colunas mudam com os anos (15 quadros em 2013, 18 em 2026) e são "
            "as do dicionário da CVM (`meta_inf_mensal_fidc.txt`); a base acrescenta as quatro abaixo. "
            "Sem dado pessoal: dos documentos de cedentes só fica CNPJ válido (CPF vira vazio)"
        ),
        fonte="CVM: informe mensal de FIDC",
        familia_da_fonte="cvm",
        frequencia="Mensal; de 2013 a 2024 um arquivo por ano, de 2025 em diante um por mês",
        atraso=(
            "Entregue em até 15 dias; a CVM regrava meses passados (cada regravação vira versão "
            "`<ano>.v<N>`). `disponivel_em` usa competência + 45 dias (o prazo, não a data vista). "
            "Desde 10/2026 o arquivista olha os 4 meses mais novos todo dia: o informe entregue "
            "depois só vale do dia em que apareceu (`visto_em`). Antes disso, a data é só o prazo"
        ),
        onde="Parquet em `<acervo>/base/fidc/informe/<quadro>/<ano>.parquet` (servidor de casa, `scripts/carga_fidc.py`)",
        linhagem=(
            "O `<ano>.json` guarda o SHA-256 da tabela, o endereço e o SHA-256 de cada arquivo do "
            "informe usado, com todas as versões guardadas de onde sai o `visto_em` (no acervo e no "
            "registro de coletas, com a data da coleta e a versão do código que baixou) e a versão "
            "do código que gravou."
        ),
        colunas={
            "competencia": ("Mês do informe (último dia)", DATA),
            "cnpj_fundo": ("CNPJ do fundo (ou da classe, depois da CVM 175)", TEXTO),
            "visto_em": (
                (
                    "O dia em que o informe do fundo apareceu na CVM pela primeira vez, pelas baixadas diárias do "
                    "arquivista (vazio: já estava no arquivo quando a base começou a olhar, em 10/2026; "
                    "vale o prazo)"
                ),
                DATA,
            ),
            "disponivel_em": (
                (
                    "Desde quando o informe era público (como era na data): competência + 45 dias, ou "
                    "`visto_em` se for depois"
                ),
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
    "susep_seguros": Tabela(
        descricao=(
            "Prêmios, sinistros e despesas de seguros por seguradora (código da SUSEP), grupo de ramos, "
            "ramo e mês desde 1995 (SES), no formato da fonte. O cadastro da SUSEP não traz CNPJ e a "
            "B13 ainda não liga o código a uma empresa: todos os códigos estão nos buracos. Uma linha "
            "por valor diferente de cada chave: a revisão de um mês passado vira linha nova, que só vale "
            "desde o dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`)"
        ),
        fonte="SUSEP: SES, base de dados completa (`Ses_seguros.csv` de dentro do ZIP)",
        familia_da_fonte="susep",
        frequencia="Mensal (o ZIP é regerado todo dia)",
        atraso="Agosto/2026 estava publicado em 16/10/2026 (47 dias); a regra usa o fim do mês + 60 dias",
        onde="Parquet por ano em `<acervo>/base/setoriais/susep/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço (`zip#Ses_seguros.csv`) e o SHA-256 de cada baixada usada "
            "e a versão do código."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "coenti": ("Código da seguradora na SUSEP (a chave; 5 dígitos)", TEXTO),
            "cogrupo": ("Código do grupo de ramos", TEXTO),
            "coramo": (
                "Código do ramo (nomes em `Ses_ramos.csv`, guardado no acervo)",
                TEXTO,
            ),
            "premio_direto": (
                "Prêmio direto no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "premio_de_seguros": (
                "Prêmio de seguros no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "premio_retido": (
                "Prêmio retido no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "premio_ganho": ("Prêmio ganho no mês, em R$, como a SUSEP publica", REAIS),
            "sinistro_direto": (
                "Sinistro direto no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "sinistro_retido": (
                "Sinistro retido no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "desp_com": (
                "Despesa de comercialização no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "premio_emitido2": (
                "Prêmio emitido no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "premio_emitido_cap": (
                "Prêmio emitido (capitalização) no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "despesa_resseguros": (
                "Despesa com resseguros no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "sinistro_ocorrido": (
                "Sinistro ocorrido no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "receita_resseguro": (
                "Receita com resseguro no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "sinistros_ocorridos_cap": (
                "Sinistros ocorridos (capitalização) no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "recuperacao_sinistros_ocorridos_cap": (
                "Recuperação de sinistros ocorridos (capitalização) no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "rvne": (
                "Riscos vigentes não emitidos (RVNE) no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "conveniodpvat": (
                "Convênio DPVAT no mês, em R$, como a SUSEP publica",
                REAIS,
            ),
            "consorciosefundos": (
                "Consórcios e fundos no mês, em R$, como a SUSEP publica",
                REAIS,
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
    "amostra_painel": Tabela(
        descricao=(
            "A amostra integrada (ADR 0058): uma linha por companhia e fim de mês, desde jan/2010, com só o "
            "que se sabia dela naquele dia, de todas as fontes da base. Cada bloco usa a linha mais nova já "
            "pública na data (`base/amostra/como_era.py`), e o teste corta a base em cada data para provar que "
            "nada do futuro entra. As canceladas ficam nos meses em que existiam. Por enquanto, só o bloco "
            "universo (quem está e os tickers) e demonstrações (balanço, acumulado no ano e anual, como eram); os "
            "outros entram um por PR"
        ),
        fonte=(
            "Derivado: cadastro da CVM, `rotulos_atraso` (entregas de DFP e ITR), `tickers_no_tempo` e "
            "`demonstracoes_como_era`"
        ),
        familia_da_fonte="cvm",
        frequencia="Mensal (até o último mês fechado)",
        atraso="Nenhum além do de cada fonte: cada coluna vale desde que ficou pública",
        onde="Parquet por ano em `<acervo>/base/amostra/v1/painel/<ano>.parquet` (`scripts/montar_amostra.py`)",
        linhagem=(
            "O `<ano>.json` aponta as tabelas de entrada (com o hash do manifesto de cada uma) e o original "
            "do cadastro; a linhagem segue das tabelas até os originais (`base/linhagem.py`)."
        ),
        colunas={
            "cnpj": ("CNPJ da companhia, no formato 00.000.000/0000-00", TEXTO),
            "data": ("Fim do mês: a linha diz o que se sabia neste dia", DATA),
            "registrada_desde": (
                "Início do registro de companhia aberta vigente na data",
                DATA,
            ),
            "primeira_entrega": (
                "A primeira DFP ou ITR entregue (a companhia só entra depois dela)",
                DATA,
            ),
            "tickers_na_data": (
                "Os códigos de negociação válidos na data, pelo FCA (vazio: nenhum)",
                TEXTO,
            ),
            "com_ticker_na_data": (
                "Tinha ao menos um código válido na data; vazio antes de o FCA trazer códigos (2018): não se sabe",
                SIM_OU_NAO,
            ),
            "balanco_fim": ("Data do balanço mais novo já público na data", DATA),
            "balanco_publico_em": (
                "Quando os valores do balanço usados ficaram públicos (entrega à CVM)",
                DATA,
            ),
            "balanco_grupo": (
                "con (consolidado) ou ind (individual, sem consolidado no período)",
                TEXTO,
            ),
            "ativo_total": ("Ativo total (conta 1)", REAIS),
            "caixa": ("Caixa e equivalentes de caixa", REAIS),
            "patrimonio_liquido": (
                "Patrimônio líquido (consolidado: com os minoritários)",
                REAIS,
            ),
            "divida_bruta": (
                "Empréstimos e financiamentos de curto e de longo prazo, somados",
                REAIS,
            ),
            "acumulado_inicio": (
                "Início do período acumulado do documento mais novo (o início do exercício)",
                DATA,
            ),
            "acumulado_fim": (
                "Fim do período acumulado (o fim do trimestre ou do exercício)",
                DATA,
            ),
            "acumulado_publico_em": (
                "Quando os valores acumulados usados ficaram públicos",
                DATA,
            ),
            "acumulado_grupo": ("con ou ind, no acumulado", TEXTO),
            "receita_acumulado": (
                "Receita do início do exercício ao fim do trimestre (bancos: da intermediação)",
                REAIS,
            ),
            "ebit_acumulado": (
                "Resultado antes do financeiro e dos tributos, acumulado (vazio nos bancos)",
                REAIS,
            ),
            "lucro_acumulado": ("Lucro ou prejuízo do período, acumulado", REAIS),
            "anual_fim": ("Fim do exercício da DFP mais nova já pública", DATA),
            "anual_publico_em": (
                "Quando os valores anuais usados ficaram públicos",
                DATA,
            ),
            "anual_grupo": ("con ou ind, no anual", TEXTO),
            "receita_anual": ("Receita do exercício (bancos: da intermediação)", REAIS),
            "ebit_anual": (
                "Resultado antes do financeiro e dos tributos, no exercício (vazio nos bancos)",
                REAIS,
            ),
            "lucro_anual": ("Lucro ou prejuízo do exercício", REAIS),
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
            f"Yahoo Finance: {NAO_COMERCIAL}."
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
            "(`fato_relevante`, costuma ser o primeiro sinal público). Desde a versão 2.0.0 o "
            "`rotulo` é da companhia que entregou o documento: quando ele fala de outra empresa "
            "(controlada, investida, devedora do CRI), vira `exposicao_a_terceiro` e o `evento` "
            "guarda o que aconteceu com a outra. Desde a 3.0.0 cada versão de uma entrega é uma "
            "linha, com a própria `conhecido_em`: a reapresentação não apaga a data da 1ª versão"
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
                    "O que aconteceu com a própria companhia: recuperacao_judicial, "
                    "recuperacao_extrajudicial, recuperacao_judicial_ou_extrajudicial (a categoria "
                    "da CVM não diz qual e nada antes disse), pedido_de_falencia, falencia ou "
                    "liquidacao; ou exposicao_a_terceiro (o documento fala de outra empresa)"
                ),
                TEXTO,
            ),
            "evento": (
                (
                    "O que aconteceu, com quem for: os mesmos valores do rótulo, sem "
                    "exposicao_a_terceiro"
                ),
                TEXTO,
            ),
            "regra": (
                (
                    "O que decidiu de quem é o evento: categoria_ipe ou fato_relevante (da própria, "
                    "sem sinal contrário), texto_proprio, texto_de_terceiro, securitizadora, "
                    "outra_empresa (palavras achadas) ou contexto_de_terceiro"
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
            "A Receita publica o retrato do mês por volta do dia 10 a 15; ele vale desde "
            "`disponivel_em` (o fim do mês ou, se depois, o dia em que foi baixado). "
            "`data_situacao_especial` é a data que a Receita informa, que pode ser anterior ao "
            "retrato em que a linha apareceu pela primeira vez"
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
            "disponivel_em": (
                (
                    "Desde quando o retrato era público: o fim do mês dele ou, se depois, o dia em "
                    "que o arquivo foi baixado pela primeira vez (atraso, correção ou mês antigo "
                    "baixado depois)"
                ),
                DATA,
            ),
            **_ORIGEM_SEM_ANO,
        },
    ),
    "pgfn_divida": Tabela(
        descricao=(
            "Dívida ativa da União (PGFN) por CNPJ de empresa, um retrato por trimestre guardado: "
            "uma linha por CNPJ, tipo de dívida (não previdenciária, previdenciária, FGTS), região "
            "da PGFN, tipo de devedor, situação e ajuizamento, com quantas inscrições e o valor "
            "somado. Só pessoa jurídica com CNPJ de dígito certo (ADR 0075): pessoa física, CPF e "
            "nome nunca entram; empresário individual e MEI ficam com `trata_como_pessoa`."
        ),
        fonte="PGFN: dados abertos da dívida ativa (SIDA, Previdência e FGTS; `base/pgfn.py`)",
        familia_da_fonte="pgfn",
        frequencia=(
            "Trimestral (a PGFN publica um retrato por trimestre; cada CSV guardado vira um arquivo)"
        ),
        atraso=(
            "O retrato do fim do trimestre sai semanas depois (o de 2026-06 foi gerado em 23/07); "
            "a PGFN não diz quando publicou, então `disponivel_em` é o dia em que o arquivista viu "
            "o arquivo pela primeira vez, e a porta o lê pelo último dia do mês, como as outras "
            "fontes de governo (o conservador; a história começa em 14/10/2026)"
        ),
        onde=(
            "Parquet em `<acervo>/base/pgfn_divida/<AAAA-MM>/<sistema>-<região>-<1º caractere do "
            "CNPJ>.parquet`, 11 por CSV da PGFN (servidor de casa, `scripts/carga_pgfn.py`)"
        ),
        linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
            "tipo_divida": (
                "nao_previdenciaria (SIDA), previdenciaria ou fgts: o arquivo da PGFN de onde veio",
                TEXTO,
            ),
            "regiao": ("Região da PGFN no nome do arquivo (1 a 6, ou NA)", TEXTO),
            "tipo_devedor": ("principal, corresponsavel ou solidario", TEXTO),
            "tipo_situacao": (
                (
                    "Grupo da situação, como a PGFN escreve (Em cobrança, Suspenso por decisão "
                    "judicial, Benefício Fiscal, Garantia)"
                ),
                TEXTO,
            ),
            "situacao_inscricao": (
                "Situação da inscrição, como a PGFN escreve (ATIVA AJUIZADA, ATIVA EM COBRANCA...)",
                TEXTO,
            ),
            "ajuizado": ("Verdadeiro se a cobrança já está na Justiça", SIM_OU_NAO),
            "inscricoes": ("Quantas inscrições somadas nesta linha", NUMERO),
            "valor_consolidado": ("Valor consolidado somado das inscrições", REAIS),
            "primeira_inscricao": (
                "Data da inscrição mais antiga (vazia se a PGFN não informa)",
                DATA,
            ),
            "ultima_inscricao": ("Data da inscrição mais recente", DATA),
            "data_do_retrato": ("Último dia do mês do retrato da PGFN", DATA),
            "gerado_em": (
                "Data dos CSVs dentro do ZIP (informativa: não é a de publicação)",
                DATA,
            ),
            "trata_como_pessoa": (
                (
                    "Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a "
                    "Receita guardada não tem (ADR 0075): nada negativo sobre ele sai da base"
                ),
                SIM_OU_NAO,
            ),
            "disponivel_em": (
                (
                    "Dia em que o arquivista viu o arquivo pela primeira vez (quando ficou "
                    "público para a base)"
                ),
                DATA,
            ),
            **_ORIGEM_SEM_ANO,
        },
    ),
    "debentures_assembleias": Tabela(
        descricao=(
            "Assembleias de debenturistas (`AGDEB`: ata, edital, proposta, instrução de voto), avisos "
            "aos debenturistas e notificações do agente fiduciário que as companhias abertas entregam "
            "à CVM no IPE desde 2003, uma linha por versão entregue. O tema de cada documento sai só "
            "do assunto preenchido pela companhia, sem abrir o PDF (modelo 18, PR 1): cerca de metade "
            "dos assuntos é genérica (`generico`) e só o PDF dirá o tema. `estresse` marca o aperto "
            "de crédito (vencimento antecipado, covenant, repactuação, inadimplemento ou waiver que "
            "não é para reorganizar a empresa nem prêmio de resgate; no aviso, só vencimento antecipado e inadimplemento). "
            "Cobre só quem entrega ao IPE: as emissões ICVM 476 de companhias fechadas ficam de fora "
            "(`relatorio-modelo-18-agente-fiduciario.md`). Conferência à mão de 50 PDFs (17/10/2026): "
            "`estresse` certo em 23 de 26; 3 de 10 genéricos tinham estresse no PDF"
        ),
        fonte="CVM: arquivos anuais do IPE (`cvm-hist-ipe`), lidos por `base/debentures.py`",
        familia_da_fonte="cvm",
        frequencia=(
            "Diária no servidor de casa (`scripts/montar_debentures_assembleias.py`), depois do "
            "arquivista baixar o IPE do ano"
        ),
        atraso=(
            "O documento vale a partir de `publico_em` (entrega da versão à CVM); `referencia` é a data "
            "informada pela companhia e, no edital, é o dia da assembleia, que pode vir depois"
        ),
        onde=(
            "Parquet em `<acervo>/base/debentures_assembleias/debentures_assembleias.parquet` "
            "(servidor de casa, `scripts/montar_debentures_assembleias.py`)"
        ),
        linhagem=(
            "Cada linha guarda o SHA-256 do arquivo anual do IPE de onde veio (`origem_sha256`, que "
            "leva ao registro de coletas) e quando ele foi coletado (`origem_coletada_em`); o "
            "manifesto lista os arquivos anuais lidos. `montado_em` diz quando a tabela foi montada. "
            + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "codigo_cvm": ("Código da companhia na CVM", TEXTO),
            "documento": ("assembleia, aviso ou notificacao_do_agente", TEXTO),
            "especie": (
                (
                    "Espécie do documento da assembleia (Ata, Edital de Convocação, Proposta da "
                    "Administração...); vazia no aviso e na notificação"
                ),
                TEXTO,
            ),
            "assunto": ("Assunto como a companhia preencheu no IPE", TEXTO),
            "emissao": (
                "Número da emissão citada no assunto (vazio se não há nenhuma ou se há mais de uma)",
                NUMERO,
            ),
            "tema_vencimento_antecipado": (
                "O assunto fala de vencimento antecipado (inclui o pedido para não declarar)",
                SIM_OU_NAO,
            ),
            "tema_waiver": (
                "O assunto fala de waiver, renúncia, perdão, anuência ou consentimento prévio",
                SIM_OU_NAO,
            ),
            "tema_covenant": (
                "O assunto fala de covenant, índices ou limites financeiros, alavancagem, dívida líquida ou EBITDA",
                SIM_OU_NAO,
            ),
            "tema_repactuacao": (
                "O assunto fala de repactuação, prorrogação, postergação, carência, suspensão de pagamento ou mudança de taxa, prazo ou cronograma",
                SIM_OU_NAO,
            ),
            "tema_inadimplemento": (
                "O assunto fala de inadimplemento, não pagamento, recuperação judicial ou extrajudicial ou falência",
                SIM_OU_NAO,
            ),
            "tema_garantia": (
                "O assunto fala de garantia, alienação ou cessão fiduciária, fiança, aval ou conta vinculada",
                SIM_OU_NAO,
            ),
            "tema_resgate": (
                "O assunto fala de resgate antecipado, amortização extraordinária ou aquisição facultativa",
                SIM_OU_NAO,
            ),
            "tema_reorganizacao": (
                "O assunto fala de incorporação, cisão, fusão, reorganização, troca de controle ou oferta de ações",
                SIM_OU_NAO,
            ),
            "tema_pagamento": (
                "O assunto avisa pagamento de juros, remuneração, amortização, prêmio ou principal",
                SIM_OU_NAO,
            ),
            "estresse": (
                "O tema é de aperto de crédito (regra na descrição)",
                SIM_OU_NAO,
            ),
            "generico": (
                "O assunto não casa com nenhum tema: só o PDF dirá",
                SIM_OU_NAO,
            ),
            "referencia": (
                "Data informada pela companhia (no edital, o dia da assembleia)",
                DATA,
            ),
            "publico_em": (
                "Entrega da versão do documento à CVM: quando ficou público para a base",
                DATA,
            ),
            "protocolo": (
                "Protocolo de entrega na CVM (de 2003 a 2014, o link, que a CVM não dá protocolo)",
                TEXTO,
            ),
            "versao": (
                "Versão do documento (reapresentação); vazia de 2003 a 2015, quando o IPE não a traz",
                NUMERO,
            ),
            "link": (
                "Link do arquivo no sistema da CVM: identifica a linha (uma entrega pode ter vários arquivos)",
                TEXTO,
            ),
            **_ORIGEM_SEM_ANO,
        },
    ),
    "ratings": Tabela(
        descricao=(
            "Ratings de crédito das companhias abertas lidos dos documentos que elas entregam à CVM "
            "no IPE desde 2003: o relatório da agência (tipo próprio do IPE) e os comunicados, fatos "
            "relevantes e editais que falam do rating. Uma linha por documento baixado e lido, com "
            "a situação da extração (`extraido`; `nao_extraido`: PDF escaneado ou sem nota; "
            "`nao_e_pdf`: Word, ZIP ou PDF quebrado). O mesmo evento (companhia, agência, escala, "
            "nota e data da ação) contado pelo relatório e pelo comunicado vira uma linha só, com a "
            "primeira entrega. v1: o rating principal de cada documento; notas por emissão, uma a "
            "uma, ficam para depois. Conferência à mão: 35 de 36 certas (16/10/2026)"
        ),
        fonte=(
            "CVM: documentos do IPE no sistema de documentos (RAD), fonte `cvm-ipe-rating`, e a "
            "lista dos arquivos anuais do IPE (`base/ratings.py`)"
        ),
        familia_da_fonte="cvm",
        frequencia=(
            "Diária no servidor de casa (`scripts/montar_ratings.py`), depois das rodadas do "
            "coletor, que baixa os documentos de hora em hora, do mais novo ao mais velho"
        ),
        atraso=(
            "O rating vale a partir de `publico_em` (entrega da versão do documento à CVM), nunca "
            "da data do relatório da agência; `data_acao` depois da entrega fica vazia"
        ),
        onde=(
            "Parquet em `<acervo>/base/ratings/ratings.parquet` (servidor de casa, "
            "`scripts/montar_ratings.py`)"
        ),
        linhagem=(
            "Cada linha guarda o SHA-256 do documento no acervo (`origem_sha256`, que leva ao "
            "registro de coletas) e quando ele foi coletado (`origem_coletada_em`); o manifesto "
            "lista os arquivos anuais do IPE e todos os documentos lidos. `montado_em` diz quando a "
            "tabela foi montada. " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "codigo_cvm": ("Código da companhia na CVM", TEXTO),
            "agencia": (
                "fitch, sp, moodys, austin, liberum, sr_rating, lf_rating ou am_best (vazia se não extraído)",
                TEXTO,
            ),
            "escala": ("nacional ou global", TEXTO),
            "nota": (
                "Nota sem sufixos (AA, RD, Aa1): compara documentos da mesma agência",
                TEXTO,
            ),
            "nivel": (
                "Posição da nota na escala (1 = AAA ou Aaa): compara agências",
                NUMERO,
            ),
            "nota_original": (
                "A nota como está no texto (AA(bra), brAAA, Aa1.br)",
                TEXTO,
            ),
            "perspectiva": (
                "estavel, positiva, negativa, em_desenvolvimento, em_observacao_positiva ou em_observacao_negativa",
                TEXTO,
            ),
            "acao": (
                "afirmacao, elevacao, rebaixamento, atribuicao, retirada...",
                TEXTO,
            ),
            "data_acao": (
                "Data da ação da agência lida do texto (vazia se não está ou se vem depois da entrega)",
                DATA,
            ),
            "outras_notas": (
                "As outras notas citadas no documento, separadas por `; `",
                TEXTO,
            ),
            "publico_em": (
                "Entrega da versão do documento à CVM: quando o rating ficou público para a base",
                DATA,
            ),
            "protocolo": (
                "Protocolo de entrega na CVM (de 2003 a 2014, o link, que a CVM não dá protocolo)",
                TEXTO,
            ),
            "versao": ("Versão do documento (reapresentação)", NUMERO),
            "link": ("Link do documento no sistema da CVM", TEXTO),
            "evidencia": (
                "Por que o documento entrou: relatorio_de_agencia (tipo do IPE) ou assunto",
                TEXTO,
            ),
            "situacao_extracao": ("extraido, nao_extraido ou nao_e_pdf", TEXTO),
            "documentos": (
                (
                    "Protocolos de todos os documentos do mesmo evento, pela data de entrega, "
                    "separados por `; ` (pode citar entregas posteriores a `publico_em`)"
                ),
                TEXTO,
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
            "conhecido_em": (
                (
                    "Data em que a CVM recebeu essa versão do FCA; mandada com a empresa fora do "
                    "registro (pedido de registro), vale a partir do registro seguinte"
                ),
                DATA,
            ),
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
    "fca_geral": Tabela(
        descricao=(
            "Cadastro de cada companhia como era em cada FCA desde 2010: categoria do registro (A "
            "ou B), setor de atividade, espécie do controle acionário e mês de fim do exercício, "
            'como a companhia informou naquele formulário. É o cadastro "como era na data" do '
            "modelo 8 (nota i do critério de pronto): o `cad_cia_aberta.csv` só tem o de hoje"
        ),
        fonte="CVM: dados abertos do FCA, tabela de dados gerais (`base/fca_geral.py`)",
        familia_da_fonte="cvm",
        frequencia=_FREQUENCIA_DO_FCA,
        atraso=(
            "Até meses: o acervo só tem a última versão de cada FCA, então `conhecido_em` pode ser "
            "mais tarde que a primeira notícia, nunca mais cedo"
        ),
        onde=_onde_da_historica("fca_geral"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "referencia": ("Data de referência do FCA", DATA),
            "versao": ("Versão do FCA", NUMERO),
            "id_documento": ("Número do documento na CVM", TEXTO),
            "conhecido_em": (
                (
                    "Data em que a CVM recebeu essa versão do FCA; mandada com a empresa fora do "
                    "registro (pedido de registro), vale a partir do registro seguinte"
                ),
                DATA,
            ),
            "categoria": (
                "Categoria do registro na CVM: A (pode emitir ações) ou B",
                TEXTO,
            ),
            "setor": ("Setor de atividade, como a companhia informou", TEXTO),
            "controle_acionario": (
                "Espécie do controle (Privado, Privado Holding, Estatal, Estrangeiro...)",
                TEXTO,
            ),
            "mes_fim_do_exercicio": ("Mês de fim do exercício social", "mês (1 a 12)"),
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
    "bcb_selic_focus": Tabela(
        descricao=(
            "Meta da Selic (SGS 432) e mediana do Focus para a Selic no fim de cada ano, com a safra: "
            "cada revisão é uma linha a mais, que passa a valer em `divulgado_em`. Tabela derivada "
            'da exportação do acervo, sem coleta nova. O Focus é o anual ("Selic no fim do ano"), '
            "não o por reunião. A meta só muda quando o Copom muda; a manutenção não aparece na série"
        ),
        fonte="Banco Central: SGS (série 432) e Focus (API Olinda, expectativas anuais)",
        familia_da_fonte="bcb",
        frequencia="A cada montagem, a partir da exportação do acervo (`base/bcb_selic_focus.py`)",
        atraso=(
            "O valor vale a partir de `divulgado_em` (a safra): a data da pesquisa, no Focus; o dia "
            "da coleta, na meta"
        ),
        onde=(
            "Parquet em `<acervo>/base/bcb_selic_focus/bcb_selic_focus.parquet` (servidor de casa)"
        ),
        linhagem=(
            "Cada linha guarda quando o acervo registrou a observação (`origem_coletada_em`) e o "
            "SHA-256 da exportação de onde saiu (`origem_sha256`); `montado_em` diz quando a tabela "
            "foi montada. " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "serie": (
                "`bcb-sgs-432` (meta da Selic) ou `focus-selic-anual` (mediana do Focus)",
                TEXTO,
            ),
            "referencia": (
                "Dia a que o valor se refere (no Focus, 31/12 do ano esperado)",
                DATA,
            ),
            "valor": ("Taxa ao ano, em % (14,25 = 14,25% ao ano)", "0 a 100"),
            "divulgado_em": ("A safra: quando este valor passou a valer", DATA),
            "publico_em": (
                "Igual a `divulgado_em`: quando o valor ficou público",
                DATA,
            ),
            "origem_coletada_em": ("Quando o acervo registrou a observação", MOMENTO),
            "origem_sha256": (
                "SHA-256 da exportação do acervo de onde a tabela saiu",
                TEXTO,
            ),
            "montado_em": ("Quando a tabela foi montada", MOMENTO),
            "versao_do_codigo": ("Commit do código que montou a tabela", TEXTO),
        },
    ),
    "noticias_fatos": Tabela(
        descricao=(
            "Um fato por linha para as notas de dado (ADR 0093): resultado trimestral (ITR e DFP), "
            "fato relevante (IPE) e reunião do Copom. Tabela derivada: cada linha diz de qual linha de "
            "qual tabela da base saiu (`chave_de_origem`) e quando ficou pública. Sem nenhum dado de pessoa: "
            "o trecho do fato relevante é cortado se citar nome"
        ),
        fonte="Derivado: `demonstracoes_como_era`, `eventos` (CVM) e `bcb_selic_focus` (Banco Central)",
        familia_da_fonte="cvm",
        ressalva_de_revenda="A pauta `copom` vem do Banco Central (`bcb_selic_focus` e a tabela conferida do Copom)",
        frequencia="Diária, no lote da manhã (`base/noticias_fatos.py`)",
        atraso="Nenhum além do de cada origem: o fato vale a partir de `publico_em`",
        onde="Parquet em `<acervo>/base/noticias_fatos/<ano>.parquet` (servidor de casa)",
        linhagem=(
            "`chave_de_origem` aponta a linha da tabela de entrada; `hash_da_linha` cobre a linha e os "
            "números dela (`noticias_numeros`). " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "id_fato": (
                "SHA-256 de `pauta` + `chave_de_origem`: remontar dá o mesmo id",
                TEXTO,
            ),
            "pauta": ("`resultado_trimestral`, `fato_relevante` ou `copom`", TEXTO),
            "versao_do_gatilho": (
                "Versão da regra que criou a linha (`resultado-1.0`)",
                TEXTO,
            ),
            "cnpj": ("CNPJ da companhia (vazio no Copom)", TEXTO),
            "empresa": (
                "Nome da companhia, como a CVM publica (vazio no Copom)",
                TEXTO,
            ),
            "tabela_de_origem": ("Tabela da base de onde o fato saiu", TEXTO),
            "chave_de_origem": ("JSON canônico da chave da linha de origem", TEXTO),
            "aconteceu_em": (
                "Fim do trimestre, data de referência do IPE ou data da reunião",
                DATA,
            ),
            "publico_em": (
                "Quando o documento ficou público (o comunicado do Copom, no dia da reunião)",
                DATA,
            ),
            "coletado_em": ("Quando a origem foi baixada", MOMENTO),
            "link": (
                "Endereço do documento original (CVM) ou do comunicado (Banco Central)",
                TEXTO,
            ),
            "topico": (
                "Fato relevante: tópico da lista fechada (`src/topicos.py`); vazio nas outras pautas",
                TEXTO,
            ),
            "metodo_do_topico": ("Fato relevante: `regra_titulo`", TEXTO),
            "versao_do_topico": ("Fato relevante: versão das regras do tópico", TEXTO),
            "trecho": (
                "Fato relevante: o assunto escrito pela empresa, literal, até 200 caracteres",
                TEXTO,
            ),
            "reapresentacao": (
                "Resultado: o documento é uma versão 2 em diante (verdadeiro/falso)",
                SIM_OU_NAO,
            ),
            "fato_anterior": (
                "Resultado reapresentado: `id_fato` da versão anterior",
                TEXTO,
            ),
            "marcas": (
                "Lista: `dado_em_conferencia`, `fontes_divergem`, `trecho_cortado`",
                TEXTO,
            ),
            "licenca": (
                "Família da fonte (`cvm` ou `bcb`), para a marca de licença",
                TEXTO,
            ),
            "hash_da_linha": ("SHA-256 da linha e dos números dela", TEXTO),
            "versao_do_codigo": ("Commit do código que montou a tabela", TEXTO),
        },
    ),
    "noticias_numeros": Tabela(
        descricao=(
            "Um número por linha de cada fato de `noticias_fatos`, com a conta, o período, a versão e "
            "a data pública de onde saiu, e o cálculo quando o valor não é o publicado (trimestre isolado)"
        ),
        fonte="Derivado: `demonstracoes_como_era` (CVM) e `bcb_selic_focus` (Banco Central)",
        familia_da_fonte="cvm",
        ressalva_de_revenda="Os números do Copom vêm do Banco Central",
        frequencia="Diária, junto com `noticias_fatos`",
        atraso="Nenhum além do de cada origem: cada número vale a partir de `origem_divulgado_em`",
        onde="Parquet em `<acervo>/base/noticias_numeros/<ano>.parquet` (servidor de casa)",
        linhagem=(
            "Cada linha diz a conta, o período, a versão e a data pública da origem; `calculo` mostra a "
            "conta feita quando o valor não é o publicado. " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "id_fato": ("Fato a que o número pertence (`noticias_fatos`)", TEXTO),
            "campo": ("Nome do número (`receita_trimestre`, `meta_selic`...)", TEXTO),
            "valor": ("O número, na unidade da coluna `unidade`", NUMERO_DECIMAL),
            "unidade": ("`reais` ou `pct_ao_ano`", TEXTO),
            "periodo": (
                "Período em texto (`3T26`, `30/09/2026`, `fim de 2026`)",
                TEXTO,
            ),
            "origem_conta": (
                "Conta do plano da CVM ou código da série do Banco Central",
                TEXTO,
            ),
            "origem_periodo": (
                "`acumulado`, `exercicio` ou `posicao` (ou vazio na série do Banco Central)",
                TEXTO,
            ),
            "origem_versao": ("Versão do documento de origem", NUMERO),
            "origem_divulgado_em": ("Quando o valor de origem ficou público", DATA),
            "calculo": (
                "Vazio se é o valor publicado; senão a conta (`acumulado 9M26 - acumulado 6M26`)",
                TEXTO,
            ),
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
            "no prazo, data-base no calendário da empresa e no arquivo do ano). Só entra o "
            "documento que a empresa devia: registrada e ativa no cadastro da CVM na data do "
            "prazo. Ficam de fora o que ela manda para pedir o registro (prazo antes do primeiro "
            "registro ou entre dois registros), o que manda depois do cancelamento e o das "
            "empresas fora do cadastro (quase todas emissores estrangeiros); o manifesto conta "
            "quantos ficaram de fora, por motivo (`fora_dos_exemplos`). Não é coluna para prever: "
            "é a resposta que o modelo tenta acertar (ADR 0027)"
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
            "da DFP e do ITR e do cadastro usados, e o SHA-256 da tabela; `montado_em` é o início "
            "do dia (em Brasília) da montagem: os mesmos originais no mesmo dia dão a mesma tabela. "
            + COM_VERSAO_DO_CODIGO
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
    "colunas_atraso": Tabela(
        descricao=(
            "Colunas do modelo de atraso na entrega (modelo 8) como eram na data da previsão: uma "
            "linha por exemplo de `rotulos_atraso` (mesma chave), só com fatos públicos antes de "
            "`data_da_previsao` (o que chegou no próprio dia fica de fora). Grupos: histórico de "
            "entregas, auditor, dificuldade (só a recuperação judicial da própria companhia, pela "
            "raiz do CNPJ), cadastro (do FCA vigente na data, nunca do cadastro de hoje), balanço e "
            "calendário. O selo de qualidade e os fatos relevantes ficam fora da v1. Vazio = não se "
            "sabia na data. O rótulo não está aqui: junta-se pela chave na hora de treinar"
        ),
        fonte=(
            "CVM: índice da DFP/ITR, FCA (dados gerais, valores mobiliários e auditores), IPE "
            '(insolvência e eventos), demonstrações "como era" e cadastro das companhias'
        ),
        familia_da_fonte="cvm",
        frequencia="Refeita a cada montagem do modelo 8 (`scripts/montar_modelo_8.py`)",
        atraso="Cada coluna usa só o que era público na véspera da previsão",
        onde=(
            "Parquet em `<acervo>/base/colunas_atraso/colunas_atraso.parquet`, com o manifesto ao "
            "lado (servidor de casa, `scripts/montar_modelo_8.py`)"
        ),
        linhagem=(
            "O manifesto (`colunas_atraso.json`) lista cada tabela da base lida (caminho e SHA-256) "
            "e cada arquivo anual do índice e o cadastro; `montado_em` diz quando a tabela foi "
            "montada. " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            **_DOCUMENTO,
            "data_da_previsao": ("Dia da previsão (a própria data-base)", DATA),
            "documentos_anteriores": (
                "DFPs e ITRs anteriores com o resultado já conhecido na véspera",
                NUMERO,
            ),
            "atrasou_o_anterior": (
                "O último documento anterior conhecido atrasou (ou venceu sem entrega)",
                SIM_OU_NAO,
            ),
            "atrasos_nos_ultimos_4": (
                "Atrasos entre os 4 documentos anteriores",
                NUMERO,
            ),
            "atrasos_nos_ultimos_8": (
                "Atrasos entre os 8 documentos anteriores",
                NUMERO,
            ),
            "media_dias_de_atraso_ultimos_4": (
                "Média de dias úteis de atraso nos 4 anteriores (sem entrega: até a previsão)",
                NUMERO_DECIMAL,
            ),
            "folga_media_ultimos_4": (
                "Média de dias úteis entre a entrega e o prazo nos 4 anteriores (negativa: atrasou)",
                NUMERO_DECIMAL,
            ),
            "entregou_o_anterior_no_ultimo_dia": (
                "O último documento anterior foi entregue no dia do prazo",
                SIM_OU_NAO,
            ),
            "reapresentacoes_12_meses": (
                "Versões 2 em diante de DFP/ITR públicas nos 12 meses antes da previsão",
                NUMERO,
            ),
            "auditor_rede_grande": (
                "O auditor do FCA vigente é EY, PwC, KPMG ou Deloitte",
                SIM_OU_NAO,
            ),
            "trocou_de_auditor_12_meses": (
                "Uma troca de auditor ficou pública nos 12 meses antes da previsão",
                SIM_OU_NAO,
            ),
            "anos_com_o_auditor": (
                "Anos desde o início do mandato mais antigo da firma atual no FCA vigente",
                "anos",
            ),
            "ja_entrou_em_recuperacao_judicial": (
                (
                    "Recuperação judicial da própria companhia (raiz do CNPJ) pública no IPE antes "
                    "da previsão; vazio se a companhia não tinha nenhum documento no IPE"
                ),
                SIM_OU_NAO,
            ),
            "setor": ("Setor de atividade no FCA vigente na data", TEXTO),
            "categoria": ("Categoria do registro (A ou B) no FCA vigente", TEXTO),
            "controle_acionario": ("Espécie do controle no FCA vigente", TEXTO),
            "exercicio_fora_de_dezembro": (
                "O exercício social não fecha em dezembro (FCA vigente)",
                SIM_OU_NAO,
            ),
            "anos_de_registro": (
                "Anos desde o último registro na CVM antes da previsão",
                "anos",
            ),
            "tem_acao_na_bolsa": (
                "Ações ou units negociadas em bolsa no FCA vigente",
                SIM_OU_NAO,
            ),
            "segmento_de_listagem": (
                "Segmento de listagem dessas ações (Novo Mercado, Nível 1...)",
                TEXTO,
            ),
            "ativo_total": (
                "Ativo total do último balanço público (consolidado se houver)",
                REAIS,
            ),
            "patrimonio_liquido_negativo": (
                "Patrimônio líquido negativo no último balanço público",
                SIM_OU_NAO,
            ),
            "prejuizo_no_ultimo_exercicio": (
                "Prejuízo na DRE do último exercício (12 meses) público",
                SIM_OU_NAO,
            ),
            "divida_curto_prazo_sobre_caixa": (
                "Empréstimos de curto prazo (2.01.04) sobre caixa (1.01.01); vazio sem caixa",
                NUMERO_DECIMAL,
            ),
            "trimestre": ("Trimestre da data-base (1 a 4)", NUMERO),
            "prazo_perto_de_feriado": (
                "Há feriado nacional nos 7 dias antes do prazo (ou no próprio dia)",
                SIM_OU_NAO,
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
            "mesma empresa), fundo (pelo CNPJ de 14), valor mobiliário (pelo ISIN das carteiras dos "
            "fundos) ou firma de auditoria (pelo código da CVM), com id determinístico "
            "(`base/rede/ids.py`), nome, natureza jurídica e MEI. Vem das tabelas que a base já tem: "
            "cadastro da CVM, FCA, controladas, auditores, empresa ↔ série, cadastro e carteiras de "
            "fundos, IF.data e GLEIF. Empresário individual, pessoa física com CNPJ e MEI ficam sem "
            "nome e com `trata_como_pessoa`"
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
            "tipo": ("empresa, fundo, valor_mobiliario ou auditor", TEXTO),
            "nome": (
                "Nome pela fonte mais confiável (vazio na pessoa com CNPJ)",
                TEXTO,
            ),
            "natureza_juridica": (
                (
                    "Código da natureza jurídica da Receita (2046 = S.A. aberta), nao_informada ou "
                    "nao_se_aplica (valor mobiliário)"
                ),
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
                (
                    "cnpj, cnpj_raiz, lei, isin, ticker, emissor, codigo_cvm_auditor ou "
                    "codigo_<fonte> (codigo_bcb_ifdata...)"
                ),
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
    "ligacoes": Tabela(
        descricao=(
            "Uma linha por relação entre duas entidades da rede (ADR 0077), com as três datas: "
            "sociedade controlada, coligada ou participada da companhia (FRE), entidade do regulador "
            "que opera para a companhia (empresa ↔ série), instituição do conglomerado do líder "
            "(IF.data), firma que audita a companhia (FCA), empresa que emite o valor mobiliário e "
            "fundo que o detém (carteiras do CDA, meses seguidos num período só). Nada é apagado "
            "entre cargas: o que some da fonte fica, encerrado pela carga. Esta é a vista interna; "
            "a publicada (sem pessoas) sai de `base/rede/vistas.py`"
        ),
        fonte=(
            "CVM (FRE, FCA, carteiras dos fundos), Banco Central (IF.data) e os reguladores da "
            "empresa ↔ série"
        ),
        familia_da_fonte="cvm",
        frequencia="Toda noite no servidor de casa; versão nova só quando o conteúdo muda",
        atraso=(
            "O da fonte: o FRE e o FCA pela entrega à CVM, a carteira 90 dias depois do mês, o "
            "IF.data 120 dias depois da data-base; a fonte de governo desde que guardada"
        ),
        onde=_ONDE_DA_REDE.format(t="ligacoes"),
        linhagem=(
            LINHAGEM_DA_REDE
            + " Cada linha leva o `origem_sha256` do arquivo (ou da tabela da base) de onde veio."
        ),
        ressalva_de_revenda=RESSALVA_DA_REDE,
        colunas={
            "de": (
                "A entidade de onde a relação sai (a controlada, o fundo, a firma)",
                TEXTO,
            ),
            "para": (
                "A entidade para onde a relação vai (a companhia, o valor mobiliário)",
                TEXTO,
            ),
            "tipo": (
                (
                    "controlada_de, coligada_de, participada_de (FRE sem o tipo), opera_para, "
                    "do_conglomerado_de, audita, emite ou detem"
                ),
                TEXTO,
            ),
            "papel": (
                (
                    "Detalhe do tipo: comprado, emprestado ou vendido (detem); a via e se é a "
                    "principal (opera_para); lider (do_conglomerado_de)"
                ),
                TEXTO,
            ),
            "participacao": (
                "Participação informada no FRE (vazia nos outros)",
                PONTOS_PERCENTUAIS,
            ),
            "aconteceu_em": (
                "Data do fato: referência do FRE, início do mandato, primeiro mês da carteira",
                DATA,
            ),
            "infracao_em": (
                "Data da infração, nas sanções (vazia nas fontes de hoje)",
                DATA,
            ),
            "publico_em": (
                "Desde quando a relação era pública (como era na data)",
                DATA,
            ),
            "coletado_em": (
                "Quando a base guardou o arquivo de onde veio (registro de coletas)",
                DATA,
            ),
            "ate": ("Até quando valeu, sem incluir o dia (vazio: ainda vale)", DATA),
            "ate_publico_em": (
                (
                    "Desde quando se sabia que tinha acabado: o FRE, o FCA ou a carteira que já não a "
                    "mostra (vazio: ainda vale). Como era em D usa este, não o `ate`"
                ),
                DATA,
            ),
            "situacao": ("vigente ou encerrada", TEXTO),
            "encerrada_por": (
                "fonte (a fonte diz o fim) ou carga (sumiu da fonte nesta carga); vazio se vigente",
                TEXTO,
            ),
            "fonte": ("cvm-fre, cvm-fca, cvm-cda, bcb-ifdata ou empresa_serie", TEXTO),
            "origem_sha256": (
                "SHA-256 do arquivo ou da tabela da base de onde veio",
                TEXTO,
            ),
            "conferido_por": ("regra (código) ou tabela (conferida à mão)", TEXTO),
        },
    ),
    "ma_assessorias": Tabela(
        descricao=(
            "Negócios de M&A do middle market tirados dos posts das assessorias independentes (ADR "
            "0082), uma linha por página de negócio: as empresas, o tipo e o sentido. Só fatos: "
            "nenhum texto do post e nenhuma pessoa física (a equipe da assessoria nem é lida). Sem "
            "data do negócio (a página não tem; `conhecido_em` está em `ma_datas`) e sem "
            "CNPJ das partes (passo 3)"
        ),
        fonte="Sites das assessorias de M&A (IGC Partners), páginas guardadas pelo arquivista",
        familia_da_fonte="assessoria",
        frequencia="Semanal (a coleta é aos domingos); versão nova só quando uma página muda",
        atraso=(
            "Desconhecido: a assessoria posta depois de fechar o negócio, sem dizer quando; a "
            "base só sabe a data da nossa coleta"
        ),
        onde=(
            "Parquet em `<acervo>/base/ma/assessorias/<assessoria>.parquet` (servidor de casa, "
            "`scripts/carga_ma_assessorias.py`)"
        ),
        linhagem=(
            "Cada linha guarda o endereço e o SHA-256 da página no acervo (`url`, `sha256`, que "
            "levam ao registro de coletas) e quando ela foi coletada; o `.json` guarda as páginas "
            "usadas. " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "assessoria": ("Quem postou (`igc`)", TEXTO),
            "url": ("Endereço da página do negócio", TEXTO),
            "sha256": ("SHA-256 da página guardada no acervo", TEXTO),
            "coletado_em": ("Quando o arquivista baixou a página", MOMENTO),
            "tipo": (
                (
                    "Código da taxonomia de M&A (AQ_CONTROLE, AQ_MINORITARIA, FUSAO, JV, VENDA_ATIVO, "
                    "PE_VC, DCM) ou desconhecido"
                ),
                TEXTO,
            ),
            "regra": (
                (
                    "Qual regra do título deu o tipo (divida, fusao, jv, venda_de_ativo, minoritaria, "
                    "majoritaria, participacao, financiamento, rodada, aquisicao); vazio se nenhuma"
                ),
                TEXTO,
            ),
            "alvo": (
                "Empresa(s) comprada(s) ou que recebeu o investimento, separadas por `; `",
                TEXTO,
            ),
            "comprador": ("Quem comprou ou investiu", TEXTO),
            "vendedor": (
                "Quem vendeu, quando não é a própria alvo (controladora, dono do ativo)",
                TEXTO,
            ),
            "outras_partes": (
                "Empresas da página sem papel dito no título (controladora de quem compra)",
                TEXTO,
            ),
            "cliente": (
                "Empresa(s) que a assessoria diz ter assessorado (campo da página)",
                TEXTO,
            ),
            "contraparte": (
                "A(s) outra(s) empresa(s) do negócio, como a página lista",
                TEXTO,
            ),
            "papeis_por": (
                (
                    "titulo (os papéis vieram do título) ou pagina (algum nome não aparece no título e "
                    "o lado veio do campo da página); vazio sem empresas"
                ),
                TEXTO,
            ),
            "lado_da_assessoria": (
                "venda, compra, captacao (dívida ou empréstimo) ou parte (fusão, JV)",
                TEXTO,
            ),
            "setor": (
                "Setor da alvo; vazio enquanto a página não diz (vem do CNPJ no passo 3)",
                TEXTO,
            ),
            "paises": (
                "Países das partes (ISO 3166-1, separados por `;`), sem dizer de quem",
                TEXTO,
            ),
            "valor": (
                "Valor que o título escreve (quase sempre vazio; nas emissões de dívida, o volume)",
                NUMERO_DECIMAL,
            ),
            "moeda": ("BRL ou USD, a do valor", TEXTO),
            "conferencia": (
                (
                    "assessoria (fonte única: declarado por quem assessorou); a confirmação por "
                    "fonte oficial, com a prova, fica em `ma_datas`"
                ),
                TEXTO,
            ),
        },
    ),
    "ma_partes": Tabela(
        descricao=(
            "As empresas de cada negócio de M&A das assessorias (`ma_assessorias`), uma linha por "
            "empresa de cada página, ligadas à rede de entidades (ADR 0077) só por regras exatas: "
            "o nome normalizado contra os nomes da rede e a razão social do CNPJ e, se nada casou, "
            "contra o nome fantasia. Nome de mais de uma entidade fica na dúvida, nunca escolhido; "
            "empresário individual e MEI nunca são ligados (ADR 0075). Série 5 do plano de M&A, "
            "passo 3 (ADR 0082)"
        ),
        fonte=(
            "`ma_assessorias`, a rede (`entidades`, `identificadores`) e o CNPJ aberto da Receita "
            "(razão social e nome fantasia, lidos e descartados: só a raiz fica)"
        ),
        familia_da_fonte="assessoria",
        frequencia="Semanal, junto da extração; versão nova só quando uma entrada muda",
        atraso="O da tabela `ma_assessorias` e o do mês do CNPJ guardado",
        onde=(
            "Parquet em `<acervo>/base/ma/ligacao/partes.parquet` (servidor de casa, "
            "`scripts/carga_ma_assessorias.py`)"
        ),
        linhagem=(
            "O `.json` guarda as tabelas de entrada (com o hash de cada uma) e os arquivos da "
            "Receita usados; a página de cada parte está em `url`. "
            + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "assessoria": ("Quem postou (`igc`)", TEXTO),
            "url": ("Endereço da página do negócio (liga com `ma_assessorias`)", TEXTO),
            "nome": ("O nome da empresa como a página escreve", TEXTO),
            "papel": (
                (
                    "alvo, comprador, vendedor ou outras_partes; vazio quando o negócio não tem papéis "
                    "(dívida, fusão, joint venture, título sem verbo)"
                ),
                TEXTO,
            ),
            "na_pagina": (
                "cliente (a assessorada) ou contraparte: o campo da página em que o nome está",
                TEXTO,
            ),
            "nome_normalizado": (
                (
                    'O nome sem acento, caixa, forma jurídica no fim (S.A., Ltda...) e "Grupo": o '
                    "que se compara"
                ),
                TEXTO,
            ),
            "id_entidade": (
                (
                    "A entidade da rede; para uma fechada que ainda não está na rede, o id que a rede "
                    "dará à raiz dela. Vazio sem ligação ou na dúvida"
                ),
                TEXTO,
            ),
            "cnpj_raiz": ("Os 8 primeiros dígitos do CNPJ da empresa ligada", TEXTO),
            "lei": ("O LEI da entidade ligada, quando a rede tem", TEXTO),
            "ligacao_por": (
                (
                    "nome_exato (rede ou razão social), nome_fantasia, na_duvida (mais de um "
                    "candidato, nome de uma palavra só fora da rede, ou nome fantasia que a razão "
                    "social não tem), holding_estrangeira (CNPJ da dona de fora), "
                    "aberto_depois_do_negocio (a matriz abriu depois do post) ou sem_ligacao"
                ),
                TEXTO,
            ),
            "candidatos": (
                "Quantas entidades têm esse nome (0 sem ligação, 1 ligada, 2 ou mais na dúvida)",
                NUMERO,
            ),
        },
    ),
    "ma_negocios": Tabela(
        descricao=(
            "Uma linha por página de negócio de M&A com o `id_negocio`, o mesmo para as páginas "
            "do mesmo negócio em sites diferentes (as assessorias dos dois lados postam o mesmo "
            "negócio): mesmas partes, assessorias diferentes e tipos que não se contradizem. "
            "Série 5 do plano de M&A, passo 3 (ADR 0082)"
        ),
        fonte="`ma_assessorias` e `ma_partes`",
        familia_da_fonte="assessoria",
        frequencia="Semanal, junto da extração; versão nova só quando uma entrada muda",
        atraso="O da tabela `ma_assessorias`",
        onde=(
            "Parquet em `<acervo>/base/ma/ligacao/negocios.parquet` (servidor de casa, "
            "`scripts/carga_ma_assessorias.py`)"
        ),
        linhagem=(
            "O `.json` guarda as tabelas de entrada com o hash de cada uma. "
            + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "assessoria": ("Quem postou (`igc`)", TEXTO),
            "url": ("Endereço da página do negócio (liga com `ma_assessorias`)", TEXTO),
            "id_negocio": (
                (
                    '"N" + 20 hexadecimais do SHA-256 das partes (entidade ou nome normalizado); '
                    "o de uma página quando as mesmas partes não podem ser juntadas"
                ),
                TEXTO,
            ),
            "paginas_do_negocio": ("Quantas páginas têm este `id_negocio`", NUMERO),
            "paginas_com_as_mesmas_partes": (
                (
                    "Quantas páginas têm as mesmas partes, juntadas ou não (mais de uma do mesmo "
                    "site são posts diferentes)"
                ),
                NUMERO,
            ),
            "duplicata_por": (
                "partes_iguais quando o negócio está em mais de uma página; vazio se só em uma",
                TEXTO,
            ),
        },
    ),
    "ma_datas": Tabela(
        descricao=(
            "Quando cada negócio de M&A das assessorias ficou público, provado, e a confirmação por "
            "fonte oficial; uma linha por página (ADR 0082, série 5 do plano de M&A, passo 4). "
            "`conhecido_em` é a prova mais antiga guardada: a primeira cópia da página no Internet "
            "Archive, o arquivo de sócios do CNPJ em que a compradora aparece como sócia pessoa "
            "jurídica da alvo, ou a nossa primeira coleta. Nunca uma data contada: a entrada na "
            "sociedade é a do fechamento (`fechamento_em`) e não entra na conta"
        ),
        fonte=(
            "`ma_assessorias`, `ma_partes` e `ma_negocios`; a API CDX do Wayback Machine (só as datas "
            "das cópias) e os sócios pessoa jurídica do CNPJ aberto da Receita (raiz, raiz da sócia e "
            "data de entrada; nome, CPF e representante nunca são lidos)"
        ),
        familia_da_fonte="wayback",
        frequencia="Semanal, junto da extração; versão nova só quando uma entrada muda",
        atraso=(
            "O da tabela `ma_assessorias`; a consulta ao Wayback roda na coleta de domingo, depois "
            "da página, e o CNPJ é o do mês mais recente guardado"
        ),
        onde=(
            "Parquet em `<acervo>/base/ma/datas/negocios.parquet` (servidor de casa, "
            "`scripts/carga_ma_assessorias.py`)"
        ),
        linhagem=(
            "Cada data aponta a prova: o endereço e o SHA-256 do original no acervo (a consulta do "
            "Wayback, o ZIP de sócios da Receita ou a página da assessoria). O `.json` guarda as "
            "tabelas e os originais de entrada. " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "assessoria": ("Quem postou (`igc`)", TEXTO),
            "url": ("Endereço da página do negócio (liga com `ma_assessorias`)", TEXTO),
            "id_negocio": ("O negócio (liga com `ma_negocios`)", TEXTO),
            "coletado_em": (
                "Quando o arquivista baixou a página pela primeira vez",
                MOMENTO,
            ),
            "wayback_em": (
                "A cópia mais antiga da página no Wayback que respondeu 200; vazio se nenhuma",
                MOMENTO,
            ),
            "wayback_copia": ("Link da cópia no Wayback, para conferir à mão", TEXTO),
            "wayback_consulta": (
                "Endereço da consulta à API CDX guardada no acervo",
                TEXTO,
            ),
            "wayback_sha256": ("SHA-256 da resposta da consulta guardada", TEXTO),
            "confirmado_por": (
                "rfb-cnpj quando a compradora é sócia PJ da alvo no CNPJ; vazio sem confirmação",
                TEXTO,
            ),
            "confirmacao_url": (
                "Endereço do ZIP de sócios da Receita que confirma",
                TEXTO,
            ),
            "confirmacao_sha256": ("SHA-256 do ZIP guardado no acervo", TEXTO),
            "confirmacao_em": ("Quando o arquivista baixou esse ZIP", MOMENTO),
            "fechamento_em": (
                (
                    "Data de entrada da compradora na sociedade da alvo, como a Receita publica (a "
                    "etapa de fechamento); se ela já era sócia antes, a da primeira entrada"
                ),
                DATA,
            ),
            "conhecido_em": (
                "A prova mais antiga de que o negócio era público (nunca antes dela)",
                MOMENTO,
            ),
            "conhecido_por": (
                "wayback, rfb-cnpj ou coleta: de onde veio o `conhecido_em`",
                TEXTO,
            ),
            "prova_url": ("Endereço do original que prova o `conhecido_em`", TEXTO),
            "prova_sha256": ("SHA-256 desse original", TEXTO),
            "conhecido_em_do_negocio": (
                "O `conhecido_em` mais antigo entre as páginas do mesmo negócio",
                MOMENTO,
            ),
            "conferencia": (
                "confirmado (fonte oficial com a prova apontada) ou assessoria (só o post)",
                TEXTO,
            ),
        },
    ),
    "ma_regua": Tabela(
        descricao=(
            "Régua do middle market de cada negócio de M&A das assessorias: a receita anual da alvo "
            "no último exercício antes do negócio, entre R$ 30 e 500 milhões; uma linha por página "
            "(ADR 0082, item 2; série 5 do plano de M&A, passo 5). Só vale o que era público antes "
            "do `conhecido_em` do negócio (documento entregue no mesmo dia ou depois não entra). "
            "Sem receita conhecida, `desconhecido`: o valor nunca é estimado"
        ),
        fonte=(
            "`ma_datas` e `ma_partes`; a DRE anual da alvo na CVM (`demonstracoes_como_era`), as "
            "receitas lidas à mão em `base/conferidas/ma_receitas.csv` (nota de combinação de "
            "negócios da compradora, balanço publicado da alvo, faixa do CADE) e o porte do CNPJ "
            "aberto da Receita (só raiz e porte são lidos)"
        ),
        familia_da_fonte="assessoria",
        frequencia="Semanal, junto da extração; versão nova só quando uma entrada muda",
        atraso=(
            "O da tabela `ma_datas`; a DRE é a já montada na base e o CNPJ é o do mês mais recente "
            "guardado"
        ),
        onde=(
            "Parquet em `<acervo>/base/ma/regua/negocios.parquet` (servidor de casa, "
            "`scripts/carga_ma_assessorias.py`)"
        ),
        linhagem=(
            "Cada receita diz a fonte e o documento (a entrega à CVM, ou o endereço do documento "
            "lido à mão) e o dia em que ficou público; o porte aponta o ZIP da Receita no acervo "
            "(endereço e SHA-256). O `.json` guarda as tabelas e os originais de entrada. "
            + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "assessoria": ("Quem postou (`igc`)", TEXTO),
            "url": ("Endereço da página do negócio (liga com `ma_datas`)", TEXTO),
            "id_negocio": ("O negócio (liga com `ma_negocios`)", TEXTO),
            "alvo_cnpj_raiz": (
                "Raiz do CNPJ da alvo (vazio sem ligação ou com mais de uma alvo ligada)",
                TEXTO,
            ),
            "conhecido_em_do_negocio": (
                "O `conhecido_em` do negócio (`ma_datas`): o corte do que a régua pode usar",
                MOMENTO,
            ),
            "fechamento_em": (
                "Data do fechamento pelo CNPJ (`ma_datas`), quando há: o exercício é o de antes dela",
                DATA,
            ),
            "middle_market": (
                "sim (receita de 30 a 500 milhões, limites inclusos), nao ou desconhecido",
                TEXTO,
            ),
            "motivo": (
                (
                    "receita, porte_me_epp, sem_receita (alvo com CNPJ sem receita pública antes), "
                    "alvo_sem_cnpj ou varias_alvos"
                ),
                TEXTO,
            ),
            "receita": ("Receita anual da alvo; vazio quando não há documento", REAIS),
            "receita_exercicio_fim": ("Fim do exercício dessa receita", DATA),
            "receita_fonte": (
                "cpc15-compradora, dfp-alvo, balanco-alvo ou cade (no mesmo exercício, nessa ordem)",
                TEXTO,
            ),
            "receita_documento": (
                "O documento: a entrega à CVM (tipo, CNPJ, referência, versão e grupo) ou o endereço",
                TEXTO,
            ),
            "receita_documento_sha256": (
                "SHA-256 do documento no acervo, quando guardado",
                TEXTO,
            ),
            "receita_publico_em": ("Dia em que o documento ficou público", DATA),
            "porte": (
                (
                    "Porte da alvo no CNPJ baixado antes do negócio (01 ME, 03 EPP, 05 demais, 00 "
                    "não informado); vazio se o arquivo é de depois"
                ),
                TEXTO,
            ),
            "porte_publico_em": ("Quando o arquivista baixou esse ZIP", MOMENTO),
            "porte_prova_url": ("Endereço do ZIP `Empresas` da Receita", TEXTO),
            "porte_prova_sha256": ("SHA-256 do ZIP guardado no acervo", TEXTO),
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
    "carteiras_dos_fundos": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_fundo", "tipo", "codigo"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "carteiras_bloco_8": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_fundo", "tipo", "cnpj_emissor"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "cda_cotas": _contrato(modulo=_FIDC, chaves=("competencia", "tipo_do_fundo", "cnpj_fundo", "cnpj_fundo_investido"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde="2005-01-31"),
    "fidc_informe": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_fundo"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
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
    "susep_seguros": _contrato(modulo=_ME, chaves=("competencia", "coenti", "cogrupo", "coramo", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "amostra_painel": _contrato(modulo=_ME, chaves=("cnpj", "data"), datas={"aconteceu_em": "data"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
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
    "insolvencia": _contrato(modulo=_ME, chaves=("cnpj", "protocolo", "versao", "rotulo"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM, versao_do_contrato="3.0.0"),  # 2.0.0 (16/10/2026): rótulo da própria × de terceiro; 3.0.0 (17/10/2026): uma linha por versão da entrega
    "cnpj_situacao_especial": _contrato(modulo="governo_e_sancoes", chaves=("cnpj", "mes_do_retrato"), datas={"aconteceu_em": "data_situacao_especial", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes", versao_do_contrato="2.0.0"),  # 2.0.0 (17/10/2026): público desde `disponivel_em`, não do mês do arquivo
    "pgfn_divida": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cnpj", "tipo_divida", "regiao", "tipo_devedor", "tipo_situacao", "situacao_inscricao", "ajuizado", "data_do_retrato"), datas={"aconteceu_em": "data_do_retrato", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "debentures_assembleias": _contrato(modulo=_FIDC, chaves=("link",), datas={"aconteceu_em": "referencia", "publico_em": "publico_em", "coletado_em": "origem_coletada_em"}, historico_desde="2003-01-01", versao_do_contrato="2.0.0"),  # 2.0.0: o link é a chave (a CVM põe vários arquivos numa entrega; antes de 2015 não há versão)
    "ratings": _contrato(modulo=_FIDC, chaves=("cnpj", "protocolo", "versao"), datas={"aconteceu_em": "data_acao", "publico_em": "publico_em", "coletado_em": "origem_coletada_em"}, historico_desde="2003-01-01"),
    "auditores": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao", "auditor_id", "inicio"), datas={"aconteceu_em": "inicio", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM, versao_do_contrato="2.0.0"),  # 2.0.0 (17/10/2026): a mesma firma tem mandatos seguidos no mesmo FCA
    "fca_geral": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "trocas_de_auditor": _contrato(modulo=_ME, chaves=("cnpj", "efetiva_em", "novo_id"), datas={"aconteceu_em": "efetiva_em", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "curva_juros": _contrato(modulo="macro", chaves=("data_base", "curva", "prazo_anos"), datas={"aconteceu_em": "data_base", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "bcb_selic_focus": _contrato(modulo="macro", chaves=("serie", "referencia", "divulgado_em"), datas={"aconteceu_em": "referencia", "publico_em": "publico_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "noticias_fatos": _contrato(modulo=_ME, chaves=("id_fato",), datas={"aconteceu_em": "aconteceu_em", "publico_em": "publico_em", "coletado_em": "coletado_em"}, historico_desde=_CVM),
    "noticias_numeros": _contrato(modulo=_ME, chaves=("id_fato", "campo"), datas={"publico_em": "origem_divulgado_em"}, historico_desde=_CVM),
    "controladas": _contrato(modulo=_ME, chaves=("cnpj_companhia", "referencia", "versao", "cnpj"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "rotulos_atraso": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia"), datas={"aconteceu_em": "prazo", "publico_em": "primeira_entrega", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "colunas_atraso": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia"), datas={"aconteceu_em": "data_da_previsao", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "empresa_serie": _contrato(modulo=_ME, chaves=("fonte", "chave", "cnpj_companhia"), datas={"aconteceu_em": "desde", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "entidades": _contrato(modulo="rede", chaves=("id_entidade",), datas={"publico_em": "publico_em"}, historico_desde=_CVM),
    "identificadores": _contrato(modulo="rede", chaves=("id_entidade", "sistema", "valor", "desde"), datas={"aconteceu_em": "desde", "publico_em": "publico_em"}, historico_desde=_CVM),
    "ligacoes": _contrato(modulo="rede", chaves=("de", "para", "tipo", "papel", "aconteceu_em", "fonte"), datas={"aconteceu_em": "aconteceu_em", "publico_em": "publico_em", "coletado_em": "coletado_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "ma_assessorias": _contrato(modulo="ma", chaves=("assessoria", "url"), datas={"coletado_em": "coletado_em"}, historico_desde="2026-10-16"),
    "ma_partes": _contrato(modulo="ma", chaves=("assessoria", "url", "nome"), historico_desde="2026-10-16"),
    "ma_negocios": _contrato(modulo="ma", chaves=("assessoria", "url"), historico_desde="2026-10-16"),
    "ma_datas": _contrato(modulo="ma", chaves=("assessoria", "url"), datas={"aconteceu_em": "fechamento_em", "publico_em": "conhecido_em", "coletado_em": "coletado_em"}, historico_desde="2026-10-16"),
    "ma_regua": _contrato(modulo="ma", chaves=("assessoria", "url"), datas={"aconteceu_em": "fechamento_em", "publico_em": "conhecido_em_do_negocio"}, historico_desde="2026-10-16"),
}  # fmt: skip


# conferência dos valores (`base/conferencia.py`): só as tabelas daqui são conferidas na montagem,
# por enquanto como aviso no manifesto. O tipo e a faixa que a unidade já diz não se repetem aqui.
_SEM_NEGATIVO = (0.0, None)
_CONFERENCIA: dict[str, dict[str, object]] = {
    "amostra_painel": {"pasta": "amostra/v1/painel"},
    "eventos": {"pasta": "eventos", "anuncia_o_futuro": True},  # 19% (assembleias, calendários)
    "curva_juros": {
        "pasta": "curva_juros",
        "faixas": {"prazo_anos": _SEM_NEGATIVO, "maior_prazo_anos": _SEM_NEGATIVO, "titulos": _SEM_NEGATIVO},
        "nao_nulas": ("taxa", "disponivel_em"),
    },
    "bcb_selic_focus": {
        "pasta": "bcb_selic_focus",
        "nao_nulas": ("valor", "divulgado_em", "publico_em"),
    },
    "noticias_fatos": {
        "pasta": "noticias_fatos",
        "nao_nulas": ("id_fato", "pauta", "publico_em", "link", "hash_da_linha"),
    },
    "noticias_numeros": {
        "pasta": "noticias_numeros",
        "nao_nulas": ("id_fato", "campo", "valor", "origem_divulgado_em"),
    },
    "pgfn_divida": {
        "pasta": "pgfn_divida",
        "faixas": {"inscricoes": (1.0, None), "valor_consolidado": _SEM_NEGATIVO},
        "nao_nulas": ("cnpj", "cnpj_basico", "data_do_retrato", "disponivel_em", "trata_como_pessoa"),
    },
    "debentures_assembleias": {
        "pasta": "debentures_assembleias",
        "faixas": {"emissao": (1.0, None), "versao": (1.0, None)},
        "nao_nulas": ("cnpj", "documento", "publico_em", "protocolo", "link", "estresse", "generico"),
        "anuncia_o_futuro": True,  # o edital sai antes da assembleia
    },
    "ratings": {
        "pasta": "ratings",
        "faixas": {"nivel": (1.0, None), "versao": (1.0, None)},
        "nao_nulas": ("cnpj", "publico_em", "protocolo", "link", "situacao_extracao", "documentos"),
    },
    "proventos": {
        "pasta": "proventos",
        "faixas": {"dividendos": _SEM_NEGATIVO, "jcp": _SEM_NEGATIVO, "dividendo_total": _SEM_NEGATIVO},
    },
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
        tabela,
        **{
            "granularidade_do_publico_em": "dia",
            **_contrato_de(nome),
            **_CONFERENCIA.get(nome, {}),
        },
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
