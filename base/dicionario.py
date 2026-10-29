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
    "A natureza jurídica e o MEI com `natureza_fonte` = receita vêm do CNPJ aberto da Receita "
    "(CC BY, citar a Receita); o LEI é do GLEIF (CC0, citar); os "
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

_CLASSE_DO_TEXTO = "`sim`, `nao` ou `nao_classificado` (relatório curto demais ou texto ambíguo: nunca no chute)"


def _pareceres(documento: str, relatorio: str, desde: str) -> Tabela:
    """`pareceres_dfp` e `pareceres_itr`: o mesmo formato, um por tipo de documento da CVM (série T, T2)."""
    return Tabela(
        descricao=(
            f"Parecer do auditor de cada {documento} desde {desde}, lido do CSV de pareceres da CVM "
            f"({relatorio}): tipo de opinião (campo da CVM), ênfase e continuidade operacional "
            "(pelos títulos do texto livre, sem palavra solta). Só a classificação é guardada, não o "
            "texto; a declaração dos diretores e o parecer do conselho fiscal ficam de fora. A firma "
            "não está neste CSV: liga-se a `auditores` por CNPJ e data. Documento sem relatório do "
            "auditor não tem linha"
        ),
        fonte=f"CVM: dados abertos do {documento}, CSV de pareceres (`base/pareceres.py`)",
        familia_da_fonte="cvm",
        frequencia="Mensal: a carga relê todos os anos (a CVM reescreve os antigos com reapresentações)",
        atraso=(
            "A entrega à CVM (`DT_RECEB` do arquivo principal); documento enviado com a empresa "
            "fora do registro vale a partir do registro seguinte"
        ),
        onde=_onde_da_historica(f"pareceres_{documento.lower()}"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "referencia": ("Data a que o documento se refere", DATA),
            "versao": (f"Versão do {documento}", NUMERO),
            "id_documento": ("Número do documento na CVM", TEXTO),
            "disponivel_em": (
                "Data em que o documento ficou público (a entrega à CVM, ou o registro da empresa)",
                DATA,
            ),
            "opiniao": (
                (
                    "`sem_ressalva`, `com_ressalva`, `adversa`, `abstencao` (a CVM escreve "
                    '"Negativa de Opinião") ou `nao_classificado` (campo vazio, como em parte de 2010)'
                ),
                TEXTO,
            ),
            "enfase": (
                "Parágrafo de ênfase no relatório: " + _CLASSE_DO_TEXTO,
                TEXTO,
            ),
            "continuidade_operacional": (
                "Incerteza relevante sobre a continuidade operacional apontada pelo auditor: "
                + _CLASSE_DO_TEXTO,
                TEXTO,
            ),
            "caracteres_do_relatorio": (
                "Tamanho do texto do relatório lido (quanto menor, menos confiável a classificação)",
                NUMERO,
            ),
            **_ORIGEM_DA_LINHA,
        },
    )


_ONDE_DO_CNPJ = (
    "Parquet em `<pasta da carga>/{pasta}` (servidor de casa, `scripts/carga_receita_retrato.py`; o "
    "`manifesto.json` da pasta guarda o SHA-256 de cada ZIP lido)"
)
_LINHAGEM_DO_CNPJ = (
    "O `manifesto.json` da carga diz, por mês, o SHA-256 de cada ZIP da Receita lido; o ZIP dos meses "
    "âncora (05/2023, 01/2024, 01/2025 e 01/2026) fica no acervo (`rfb-cnpj`, `cnpj/<AAAA-MM>/`) e leva "
    "ao registro de coletas. A linha não leva a versão do código que a montou."
)
_FREQUENCIA_DO_CNPJ = (
    "Mensal (a Receita publica uma pasta AAAA-MM por mês; a carga anda um mês por vez)"
)
_ATRASO_DO_CNPJ = (
    "A Receita põe a pasta do mês no ar durante o mês; a base conta como público o dia 27 "
    "(`base/receita_diff.py`, valor prudente até a medida no servidor)"
)
_FINALIDADE_DO_CNPJ = (
    "Finalidade: conhecer a empresa com quem se faz negócio (contraparte, crédito, compliance, fornecedor, "
    "M&A), a mesma da publicação pela Receita; base legal: legítimo interesse (LGPD, art. 7º, IX), com o "
    "RIPD da base e a ADR 0106"
)
_RESSALVA_DO_CNPJ = 'CC BY: citar "Receita Federal, dados abertos do CNPJ" e o mês da extração em tudo o que sair'
_CONTATOS_FORA = (
    "Telefone, e-mail e nome fantasia nunca são lidos (LGPD, ADR 0106, item 3.5)"
)

_ESTABELECIMENTO = {
    "cnpj": ("CNPJ com os 14 caracteres (com letras no CNPJ novo)", TEXTO),
    "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
    "matriz": ("Verdadeiro na matriz, falso na filial", SIM_OU_NAO),
    "situacao_cadastral": (
        "Código da situação cadastral da Receita (2 ativa, 3 suspensa, 4 inapta, 8 baixada)",
        TEXTO,
    ),
    "data_situacao_cadastral": (
        "Data da situação cadastral; vazio quando a Receita põe zero",
        DATA,
    ),
    "motivo_situacao": (
        "Código do motivo da situação cadastral, como a Receita publica",
        TEXTO,
    ),
    "pais": (
        "Código do país, só para quem tem sede fora do Brasil; vazio no resto",
        TEXTO,
    ),
    "data_inicio_atividade": (
        "Data de início da atividade; vazio quando a Receita põe zero",
        DATA,
    ),
    "cnae_principal": ("Código da atividade principal (CNAE fiscal, 7 dígitos)", TEXTO),
    "cnae_secundaria": (
        "Códigos das atividades secundárias, separados por vírgula",
        TEXTO,
    ),
    "tipo_logradouro": (
        "Tipo do logradouro (rua, avenida...); vazio nas raízes só com município",
        TEXTO,
    ),
    "logradouro": ("Logradouro; vazio nas raízes só com município", TEXTO),
    "numero": ("Número do endereço; vazio nas raízes só com município", TEXTO),
    "complemento": (
        "Complemento do endereço; vazio nas raízes só com município",
        TEXTO,
    ),
    "bairro": ("Bairro; vazio nas raízes só com município", TEXTO),
    "cep": ("CEP; vazio nas raízes só com município", TEXTO),
    "uf": ("Sigla do estado", TEXTO),
    "municipio": ("Código do município na Receita (não é o código do IBGE)", TEXTO),
    "situacao_especial": (
        "Situação especial, como a Receita escreve; vazio quando não há",
        TEXTO,
    ),
    "data_situacao_especial": ("Data da situação especial informada", DATA),
    "dv_confere": (
        "Falso quando o dígito verificador do CNPJ não confere; a linha fica, não é descartada",
        SIM_OU_NAO,
    ),
}
_SIMPLES = {
    "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
    "optante_simples": (
        "Verdadeiro se a empresa é optante do Simples Nacional",
        SIM_OU_NAO,
    ),
    "data_opcao_simples": (
        "Data da opção pelo Simples; vazio quando a Receita põe zero",
        DATA,
    ),
    "data_exclusao_simples": (
        "Data da exclusão do Simples; vazio quando a Receita põe zero",
        DATA,
    ),
    "optante_mei": ("Verdadeiro se a empresa é MEI", SIM_OU_NAO),
    "data_opcao_mei": (
        "Data do enquadramento como MEI; vazio quando a Receita põe zero",
        DATA,
    ),
    "data_exclusao_mei": (
        "Data do desenquadramento do MEI; vazio quando a Receita põe zero",
        DATA,
    ),
}
_QSA = {
    "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
    "tipo_socio": (
        "1 pessoa jurídica, 2 pessoa física ou 3 estrangeiro, como a Receita publica",
        TEXTO,
    ),
    "raiz_socio_pj": (
        "Raiz do CNPJ do sócio, só quando ele é pessoa jurídica; vazio nos outros",
        TEXTO,
    ),
    "id_pessoa": (
        (
            "Pseudônimo (HMAC com chave fora do Git) do sócio pessoa física; vazio para sócio pessoa "
            "jurídica e para quem se opôs. O nome, que a Receita publica, fica só no esquema "
            "`pessoas` (acervo restrito, fora desta tabela) e atrás do portão dos nomes"
        ),
        TEXTO,
    ),
    "qualificacao": (
        "Código da qualificação do sócio (sócio-administrador, diretor...)",
        TEXTO,
    ),
    "data_entrada": ("Data de entrada na sociedade", DATA),
    "pais": ("Código do país do sócio estrangeiro; vazio no resto", TEXTO),
}


def _mudancas_do_cnpj(
    vigente: dict[str, tuple[str, str]], chave: tuple[str, ...]
) -> dict[str, tuple[str, str]]:
    """As colunas de `<tabela>_mudancas`: o mês, o tipo, a chave e, por valor, o antes e o depois."""
    colunas = {
        "mes": ("Mês do retrato em que a mudança apareceu", "AAAA-MM"),
        "tipo": ("entrou, saiu ou mudou, de um mês para o seguinte", TEXTO),
        **{c: vigente[c] for c in chave},
        "ordem": (
            "Número da linha dentro da chave quando ela se repete (ordenada pelo conteúdo)",
            NUMERO,
        ),
    }
    for coluna, (descricao, unidade) in vigente.items():
        if coluna not in chave:
            colunas[f"{coluna}_antes"] = (f"Antes da mudança. {descricao}", unidade)
            colunas[f"{coluna}_depois"] = (f"Depois da mudança. {descricao}", unidade)
    return colunas


def _tabelas_do_cnpj() -> dict[str, Tabela]:
    """As três tabelas vigentes do CNPJ aberto da Receita e a das mudanças de cada uma (ADR 0106, PRs 4 e 5)."""
    descricoes = {
        "estabelecimentos": (
            "Estabelecimentos (matriz e filiais) do CNPJ aberto da Receita, o retrato mais recente: situação "
            "cadastral, datas, atividade (CNAE), endereço e situação especial. "
            + _CONTATOS_FORA
            + ". O endereço de empresário individual e de MEI deve ficar só até o município e a UF, mas o "
            "leitor da tabela de empresas, que diz quem é quem, ainda não existe: por ora a carga "
            "grava o endereço inteiro de todos, e por isso a tabela conta como dado de pessoa. "
            + _FINALIDADE_DO_CNPJ
        ),
        "simples": (
            "Opção pelo Simples Nacional e pelo MEI de cada empresa do CNPJ aberto da Receita, o retrato mais "
            "recente, com as datas de opção e de exclusão. Sem dado de pessoa além do próprio CNPJ. "
            + _FINALIDADE_DO_CNPJ
        ),
        "qsa": (
            "Quadro de sócios e administradores das empresas do CNPJ aberto da Receita, o retrato mais "
            "recente. Traz tipo, qualificação, data de entrada, país e, para sócio pessoa física, só o "
            "pseudônimo `id_pessoa`. Nome, CPF mascarado e representante legal não entram: o nome "
            "fica no esquema `pessoas` (acervo restrito) e só sai de casa quando o portão dos "
            "nomes abrir (`base/pessoas/portao.py`, fechado, ADR 0106 item 4); CPF inteiro quebra a "
            "carga; faixa etária e representante legal nem são lidos. A porta é o CNPJ: não há busca "
            "por pessoa. Quem se opôs (art. 18) tem o id apagado. "
            + _FINALIDADE_DO_CNPJ
        ),
    }
    vigentes = {"estabelecimentos": _ESTABELECIMENTO, "simples": _SIMPLES, "qsa": _QSA}
    chaves = {
        "estabelecimentos": ("cnpj",),
        "simples": ("cnpj_basico",),
        "qsa": ("cnpj_basico", "tipo_socio", "raiz_socio_pj", "id_pessoa"),
    }
    tabelas: dict[str, Tabela] = {}
    for nome, colunas in vigentes.items():
        comum = {
            "fonte": "Receita Federal: dados abertos do CNPJ (`base/receita_retrato.py`, `scripts/carga_receita_mes.py`)",
            "familia_da_fonte": "rfb-cnpj",
            "frequencia": _FREQUENCIA_DO_CNPJ,
            "atraso": _ATRASO_DO_CNPJ,
            "linhagem": _LINHAGEM_DO_CNPJ,
            "ressalva_de_revenda": _RESSALVA_DO_CNPJ,
        }
        tabelas[f"cnpj_{nome}"] = Tabela(
            descricao=descricoes[nome],
            onde=_ONDE_DO_CNPJ.format(
                pasta=f"vigente/{nome}/<2 primeiros caracteres da raiz>.parquet"
            ),
            colunas=colunas,
            **comum,  # type: ignore[arg-type]
        )
        tabelas[f"cnpj_{nome}_mudancas"] = Tabela(
            descricao=(
                f"O que mudou de um mês para o outro em `cnpj_{nome}`: uma linha por entrada, saída ou "
                "mudança, com o valor de antes e o de depois; aplicadas em ordem sobre o retrato "
                'inicial, devolvem o retrato de qualquer mês (é o histórico "como era na data" do CNPJ). '
                + (
                    "O sócio pessoa física é só o `id_pessoa`; o histórico de quem saiu nunca leva nome. "
                    if nome == "qsa"
                    else ""
                )
                + _FINALIDADE_DO_CNPJ
            ),
            onde=_ONDE_DO_CNPJ.format(pasta=f"mudancas/{nome}/<AAAA-MM>.parquet"),
            colunas=_mudancas_do_cnpj(colunas, chaves[nome]),
            **comum,  # type: ignore[arg-type]
        )
    return tabelas


def _tabelas_das_sancoes() -> dict[str, Tabela]:
    """As sanções por CNPJ (`base/sancoes.py`): uma tabela por família de licença, para a marca da CGU
    (só uso interno) não se misturar com a da ANS (vende com atribuição)."""
    colunas = {
        "cadastro": (
            "De que cadastro veio: ceis, cnep, cepim, leniencia ou penalidades (ANS)",
            TEXTO,
        ),
        "id_na_fonte": (
            "O código da sanção na fonte (no CEPIM, que não tem código: o CNPJ e o convênio)",
            TEXTO,
        ),
        "cnpj": _EMPRESA["cnpj"],
        "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
        "categoria": (
            (
                "O tipo da sanção como a fonte escreve (Suspensão, Inidoneidade, Multa Pecuniária, o "
                "motivo do impedimento no CEPIM, Acordo de leniência)"
            ),
            TEXTO,
        ),
        "situacao": (
            "Situação do acordo (leniência) ou da demanda (ANS), como a fonte escreve",
            TEXTO,
        ),
        "assunto": (
            "Tipo do processo na ANS (Consumidor, Econômico-financeiro...)",
            TEXTO,
        ),
        "orgao": (
            "Órgão que aplicou a sanção (no CEPIM, o concedente do convênio)",
            TEXTO,
        ),
        "uf_do_orgao": ("UF do órgão sancionador", TEXTO),
        "esfera_do_orgao": ("Esfera do órgão (FEDERAL, ESTADUAL, MUNICIPAL)", TEXTO),
        "origem_da_informacao": ("Quem informou a sanção à CGU", TEXTO),
        "fundamentacao_legal": ("A lei em que a sanção se baseia", TEXTO),
        "abrangencia": ("Abrangência da sanção, como a CGU escreve", TEXTO),
        "processo": ("Número do processo (no CEPIM, o do convênio)", TEXTO),
        "inicio": (
            (
                "Início da sanção ou do acordo; na ANS, a data da decisão de 1ª instância. Pode "
                "ser depois da publicação (a sanção publicada que só vale adiante)"
            ),
            DATA,
        ),
        "fim": ("Fim da sanção ou do acordo (vazio: sem prazo ou não informado)", DATA),
        "publicado_em": (
            "Publicação oficial (Diário Oficial; na ANS, a da 1ª instância)",
            DATA,
        ),
        "transito_em_julgado": ("Trânsito em julgado, quando a fonte informa", DATA),
        "informado_em": (
            "Quando o órgão informou a sanção à CGU (data de origem da informação)",
            DATA,
        ),
        "valor_multa": ("Valor da multa (CNEP; na ANS, a multa final aplicada)", REAIS),
        "consta": (
            (
                "Verdadeiro enquanto a sanção está no arquivo; falso na linha do dia em que saiu "
                "dele (acabou, foi excluída ou anulada)"
            ),
            SIM_OU_NAO,
        ),
        "trata_como_pessoa": (
            (
                "Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a "
                "Receita guardada não tem (ADR 0075): nada negativo sobre ele sai da base"
            ),
            SIM_OU_NAO,
        ),
        "visto_em": ("Dia do arquivo em que esta versão da linha foi vista", DATA),
        "disponivel_em": (
            (
                "Desde quando a linha vale para a base: no 1º arquivo, a publicação ou a "
                "informação ao órgão (a que for depois), nunca depois do dia do arquivo; depois "
                "dele, o dia do arquivo em que a mudança apareceu"
            ),
            DATA,
        ),
        **_ORIGEM_SEM_ANO,
    }
    comum = (
        "Uma linha por valor diferente de cada sanção: a mudança (situação, fim, valor) vira linha "
        "nova que só vale desde o dia em que foi vista, e a sanção que some do arquivo ganha uma "
        "linha com `consta` falso (`base/setoriais/revisoes.py::como_era_em` dá o retrato de "
        "qualquer dia). Só pessoa jurídica com CNPJ de dígito certo (ADR 0075): pessoa física, CPF "
        "e nome nunca entram, nem a razão social; empresário individual e MEI ficam com "
        "`trata_como_pessoa`. Arquivo com menos da metade das sanções do anterior é pulado: é "
        "arquivo quebrado da fonte, não sanção que acabou."
    )
    atraso = (
        "A fonte não diz quando cada linha entrou no arquivo: no 1º arquivo guardado vale a data "
        "de publicação ou de informação (o que a fonte diz), e depois o dia em que o arquivista viu "
        "a mudança (o conservador; a história guardada começa em 14/10/2026)"
    )
    return {
        "sancoes_cgu": Tabela(
            descricao=(
                "Sanções da CGU por CNPJ de empresa: CEIS (inidôneas e suspensas), CNEP (punidas "
                "pela Lei Anticorrupção, com o valor da multa), CEPIM (entidades sem fins "
                "lucrativos impedidas de receber convênio) e acordos de leniência. "
                + comum
                + " Os efeitos de cada acordo de leniência (o 2º arquivo do ZIP) ainda não entram."
            ),
            fonte=(
                "CGU: Portal da Transparência, download de dados do CEIS, CNEP, CEPIM e acordos "
                "de leniência (`base/sancoes.py`)"
            ),
            familia_da_fonte="cgu",
            frequencia="Diária (o portal gera um arquivo por dia; o arquivista guarda só o que mudou)",
            atraso=atraso,
            onde=(
                "Parquet em `<acervo>/base/sancoes_cgu/<cadastro>.parquet` (servidor de casa, "
                "`scripts/carga_sancoes.py`)"
            ),
            linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
            colunas=colunas,
        ),
        "ans_penalidades": Tabela(
            descricao=(
                "Penalidades aplicadas pela ANS a operadoras de planos de saúde, por CNPJ: o tipo "
                "do processo, a situação da demanda, as datas da 1ª instância e a multa final. "
                + comum
            ),
            fonte="ANS: dados abertos, penalidades aplicadas a operadoras (`base/sancoes.py`)",
            familia_da_fonte="ans",
            frequencia=(
                "Mensal (a ANS recarrega o arquivo inteiro; `NR_COMPETENCIA_CARGA` diz o mês)"
            ),
            atraso=atraso,
            onde=(
                "Parquet em `<acervo>/base/ans_penalidades/penalidades.parquet` (servidor de "
                "casa, `scripts/carga_sancoes.py`)"
            ),
            linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
            colunas=colunas,
        ),
    }


def _tabelas_das_licencas() -> dict[str, Tabela]:
    """As licenças e registros por CNPJ (`base/licencas.py`, Ficha Clara): uma tabela por órgão, com
    as mesmas colunas, para a ficha da empresa ler todas do mesmo jeito."""
    colunas = {
        "cadastro": (
            (
                "De que arquivo veio: afe, cbpf, cbpf_medicamento, medicamentos, saneantes, "
                "cosmeticos, produtos_saude, alimentos (Anvisa); rntrc (ANTT); produto_veterinario, "
                "aviacao_agricola (MAPA); outorgas (Anatel); o tipo de título (ANM); agentes (Ancine)"
            ),
            TEXTO,
        ),
        "id_na_fonte": (
            (
                "O que identifica o registro no arquivo (o código da fonte, ou as colunas que o "
                "identificam juntas por `|`)"
            ),
            TEXTO,
        ),
        "cnpj": _EMPRESA["cnpj"],
        "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
        "registro": (
            (
                "Número da licença na fonte: autorização (AFE), certificado (CBPF), registro do "
                "produto, RNTRC, registro do estabelecimento (MAPA), Fistel da outorga, registro na "
                "Ancine"
            ),
            TEXTO,
        ),
        "processo": ("Número do processo no órgão", TEXTO),
        "categoria": (
            (
                "O tipo, como a fonte escreve: tipo de produto (AFE), tipo de certificado, "
                "categoria regulatória, categoria do transportador, atividade (MAPA), tipo de "
                "outorga, tipo de requerimento (ANM), classificação do agente (Ancine)"
            ),
            TEXTO,
        ),
        "descricao": (
            (
                "O que a licença cobre: atividades (AFE), assunto (CBPF), nome do produto, "
                "classificação (MAPA), serviço notificado (Anatel), substâncias (ANM), natureza "
                "jurídica (Ancine)"
            ),
            TEXTO,
        ),
        "complemento": (
            (
                "Um dado a mais de cada fonte: número novo da AFE, país da fábrica inspecionada "
                "(CBPF), transportador equiparado (RNTRC), característica ou aeronave (MAPA), "
                "Fistel da notificação (Anatel), tipo de uso (ANM), brasileiro independente (Ancine)"
            ),
            TEXTO,
        ),
        "situacao": (
            (
                "A situação como a fonte escreve hoje (ativo, vencido, cancelado, fase atual do "
                "título...): vale desde o dia do arquivo, nunca antes"
            ),
            TEXTO,
        ),
        "uf": ("UF da empresa ou do estabelecimento, quando a fonte informa", TEXTO),
        "municipio": ("Município, quando a fonte informa", TEXTO),
        "concedido_em": (
            "Data da concessão, autorização, inclusão ou registro, quando a fonte informa",
            DATA,
        ),
        "publicado_em": (
            "Publicação da licença (Diário Oficial), quando a fonte informa",
            DATA,
        ),
        "vence_em": (
            (
                "Vencimento da licença ou do registro (nos alimentos da Anvisa, que só dão o mês, "
                "o 1º dia do mês)"
            ),
            DATA,
        ),
        "cancelado_em": ("Cancelamento, quando a fonte informa", DATA),
        "situacao_desde": ("Desde quando vale a situação (só o RNTRC informa)", DATA),
        "consta": (
            (
                "Verdadeiro enquanto o registro está no arquivo; falso na linha do dia em que saiu "
                "dele"
            ),
            SIM_OU_NAO,
        ),
        "trata_como_pessoa": (
            (
                "Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a "
                "Receita guardada não tem (ADR 0075)"
            ),
            SIM_OU_NAO,
        ),
        "visto_em": ("Dia do arquivo em que esta versão da linha foi vista", DATA),
        "disponivel_em": (
            (
                "Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também "
                "no 1º (a fonte publica o estado de hoje sem dizer desde quando)"
            ),
            DATA,
        ),
        **_ORIGEM_SEM_ANO,
    }
    comum = (
        "Uma linha por valor diferente de cada registro: a mudança (situação, vencimento, "
        "cancelamento) vira linha nova que só vale desde o dia em que foi vista, e o registro que "
        "some do arquivo ganha uma linha com `consta` falso (`base/setoriais/revisoes.py::"
        "como_era_em` dá o retrato de qualquer dia). Só CNPJ inteiro de dígito certo, com letras "
        "ou não: CPF e CNPJ mascarado saem na coleta; razão social, nome de fantasia, endereço, "
        "contato e responsável técnico nunca chegam ao acervo. Empresário individual e MEI ficam "
        "com `trata_como_pessoa`. Arquivo com menos da metade dos registros do anterior é pulado."
    )
    atraso = (
        "A fonte publica o estado de hoje sem dizer desde quando: toda linha vale desde o dia em "
        "que o arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam "
        "nas colunas delas"
    )
    frequencia = "Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)"

    def tabela(
        nome: str,
        descricao: str,
        fonte: str,
        familia: str,
        frequencia: str = frequencia,
    ) -> Tabela:
        return Tabela(
            descricao=descricao + " " + comum,
            fonte=fonte + " (`base/licencas.py`)",
            familia_da_fonte=familia,
            frequencia=frequencia,
            atraso=atraso,
            onde=(
                f"Parquet em `<acervo>/base/{nome}/<cadastro>.parquet` (servidor de casa, "
                "`scripts/carga_licencas.py`)"
            ),
            linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
            colunas=colunas,
        )

    return {
        "anvisa_registros": tabela(
            "anvisa_registros",
            (
                "Licenças da Anvisa por CNPJ: autorização de funcionamento (AFE), certificados de "
                "boas práticas de fabricação (CBPF) e os produtos registrados (medicamentos, "
                "saneantes, cosméticos, produtos para saúde e alimentos)."
            ),
            "Anvisa: dados abertos, consultas de empresas e de produtos",
            "anvisa",
        ),
        "antt_rntrc": tabela(
            "antt_rntrc",
            "Transportadores rodoviários de carga com registro na ANTT (RNTRC), por CNPJ.",
            "ANTT: dados abertos, RNTRC (um arquivo por mês, cada um com o cadastro inteiro)",
            "antt",
        ),
        "mapa_sipeagro": tabela(
            "mapa_sipeagro",
            (
                "Estabelecimentos registrados no MAPA (SIPEAGRO) por CNPJ: produto veterinário e "
                "aviação agrícola. Os outros arquivos do SIPEAGRO mascaram o CNPJ e ficam de fora "
                "(nunca se cruza pelo nome)."
            ),
            "MAPA: dados abertos do SIPEAGRO",
            "mapa",
        ),
        "anatel_outorgas": tabela(
            "anatel_outorgas",
            "Prestadoras de telecomunicações com outorga da Anatel, por CNPJ e serviço notificado.",
            "Anatel: dados abertos, prestadoras de serviços de telecomunicações",
            "anatel",
        ),
        "anm_titulos": tabela(
            "anm_titulos",
            (
                "Títulos e requerimentos minerários da ANM por CNPJ do titular (Cadastro Mineiro, "
                'um arquivo por tipo de título). A coluna "Situação" (Sim/Não) da ANM fica de fora: '
                "o sentido não está no dicionário dela."
            ),
            "ANM: dados abertos do Cadastro Mineiro",
            "anm",
        ),
        "ancine_agentes": tabela(
            "ancine_agentes",
            "Agentes econômicos registrados na Ancine, por CNPJ.",
            "Ancine: dados abertos, agentes econômicos regulares",
            "ancine",
        ),
    }


def _tabelas_dos_incentivos() -> dict[str, Tabela]:
    """Os incentivos por CNPJ (`base/incentivos.py`, Ficha Clara): REIDI, CDE e RDE-IED."""
    situacao = {
        "consta": (
            "Verdadeiro enquanto a linha está no arquivo; falso na linha do dia em que saiu dele",
            SIM_OU_NAO,
        ),
        "trata_como_pessoa": (
            (
                "Verdadeiro em empresário individual, natureza do grupo 4, MEI ou CNPJ que a "
                "Receita guardada não tem (ADR 0075)"
            ),
            SIM_OU_NAO,
        ),
        "visto_em": ("Dia do arquivo em que o arquivista viu a linha", DATA),
        "disponivel_em": (
            (
                "Desde quando a linha vale para a base: o dia do arquivo em que foi vista, também "
                "no 1º (a fonte não diz quando publicou cada linha)"
            ),
            DATA,
        ),
        **_ORIGEM_SEM_ANO,
    }
    so_pj = (
        "Só pessoa jurídica: CPF e nome (do cliente, do agente, do investidor, da empresa) saem na "
        "coleta; empresário individual e MEI ficam com `trata_como_pessoa`."
    )
    atraso = (
        "A fonte não diz quando publicou cada linha: toda linha vale desde o dia em que o "
        "arquivista a viu (a história guardada começa em 29/10/2026); as datas da fonte ficam nas "
        "colunas delas"
    )

    def tabela(
        nome: str,
        descricao: str,
        fonte: str,
        familia: str,
        frequencia: str,
        colunas: dict[str, tuple[str, str]],
    ) -> Tabela:
        return Tabela(
            descricao=descricao + " " + so_pj,
            fonte=fonte + " (`base/incentivos.py`)",
            familia_da_fonte=familia,
            frequencia=frequencia,
            atraso=atraso,
            onde=(
                f"Parquet em `<acervo>/base/{nome}/<arquivo>.parquet` (servidor de casa, "
                "`scripts/carga_incentivos.py`)"
            ),
            linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
            colunas={**colunas, **situacao},
        )

    reidi = {
        "id_na_fonte": ("O processo e o projeto juntos por `|`", TEXTO),
        "cnpj": _EMPRESA["cnpj"],
        "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
        "processo": ("Número do processo no MME", TEXTO),
        "projeto": ("Código do projeto no MME", TEXTO),
        "nome_do_projeto": (
            "Nome do projeto (a usina ou a linha de transmissão)",
            TEXTO,
        ),
        "portaria": ("Portaria de enquadramento, como a fonte escreve", TEXTO),
        "uf": ("UF do projeto (NI quando a fonte não identifica)", TEXTO),
        "municipio": ("Município do projeto, como a fonte escreve", TEXTO),
        "portaria_em": ("Início da portaria de enquadramento", DATA),
        "execucao_desde": ("Início da execução do projeto", DATA),
        "execucao_ate": ("Fim previsto da execução do projeto", DATA),
        "valor_com_incidencia": ("Total do projeto com PIS/Pasep e Cofins", REAIS),
        "valor_sem_incidencia": ("Total do projeto sem PIS/Pasep e Cofins", REAIS),
        "valor_do_beneficio": ("Benefício fiscal estimado (a diferença)", REAIS),
    }
    cde = {
        "arquivo": (
            "`mensal` (beneficiários) ou `rede_basica` (descontos na transmissão)",
            TEXTO,
        ),
        "id_na_fonte": ("As colunas da soma juntas por `|`", TEXTO),
        "cnpj_basico": ("Raiz do CNPJ (8 caracteres): a empresa", TEXTO),
        "cnpj": _EMPRESA["cnpj"],
        "mes": ("Mês de referência (o 1º dia do mês)", DATA),
        "distribuidora": ("Sigla da distribuidora (vazio na rede básica)", TEXTO),
        "cnpj_da_distribuidora": (
            "CNPJ da distribuidora, só os números (vazio na rede básica)",
            TEXTO,
        ),
        "classe": ("Código da classe do consumidor, como a ANEEL escreve", TEXTO),
        "grupo_tarifario": (
            "Subgrupo tarifário (código) ou grupo (rede básica)",
            TEXTO,
        ),
        "tipo_de_desconto": (
            "Tipo de subsídio (`SubsCARFI`, `SubsRural`...) ou o código do tipo (rede básica)",
            TEXTO,
        ),
        "valor_do_desconto": (
            "Soma dos subsídios ou descontos pagos pela CDE no mês",
            REAIS,
        ),
        "valor_cobrado": ("Soma da cobrança (só a rede básica informa)", REAIS),
        "linhas": (
            "Quantas linhas da fonte (unidades consumidoras ou agentes) foram somadas",
            NUMERO,
        ),
        "gerado_em": ("Dia em que a ANEEL gerou o arquivo", DATA),
    }
    rde = {
        "id_na_fonte": ("O código, a ocorrência, o mês e o país juntos por `|`", TEXTO),
        "cnpj_basico": (
            "Raiz do CNPJ (8 caracteres) da empresa que recebeu o investimento",
            TEXTO,
        ),
        "codigo_rde": ("Código do registro no RDE-IED", TEXTO),
        "uf": ("UF da empresa que recebeu", TEXTO),
        "pais": ("País do investidor estrangeiro", TEXTO),
        "ocorrencia": ("`REGISTRO EFETUADO` ou `REGISTRO ENCERRADO`", TEXTO),
        "mes": ("Mês da ocorrência (o 1º dia do mês)", DATA),
    }
    return {
        "mme_reidi": tabela(
            "mme_reidi",
            (
                "Projetos de geração e transmissão de energia enquadrados no REIDI (MME), por CNPJ, "
                "com a portaria, a execução e o benefício fiscal. Uma linha por valor diferente de "
                "cada projeto: a mudança vira linha nova desde o dia em que foi vista, e o projeto "
                "que some do arquivo ganha `consta` falso (`como_era_em` dá o retrato de um dia)."
            ),
            "MME: dados abertos, REIDI (processos deferidos)",
            "mme",
            "Mensal (a fonte recarrega o arquivo inteiro; o arquivista guarda só o que mudou)",
            reidi,
        ),
        "aneel_cde": tabela(
            "aneel_cde",
            (
                "Descontos tarifários pagos pela Conta de Desenvolvimento Energético (CDE, ANEEL), "
                "somados por CNPJ, mês, distribuidora, classe, grupo tarifário e tipo de subsídio "
                "(a fonte tem uma linha por unidade consumidora). Cada arquivo da ANEEL (um por "
                "mês; um por ano na rede básica) é um Parquet; a republicação corrigida vira linha "
                "nova."
            ),
            "ANEEL: dados abertos, beneficiários da CDE",
            "aneel",
            "Mensal (um arquivo novo por mês; a ANEEL pode republicar o mês corrigido)",
            cde,
        ),
        "bcb_rde_ied": tabela(
            "bcb_rde_ied",
            (
                "Registros de investimento estrangeiro direto no Banco Central (RDE-IED) pela raiz "
                "do CNPJ da empresa que recebeu, de nov/2011 a dez/2022 (a série parou aí). A moeda "
                "e o valor, sempre vazios na fonte, ficam de fora."
            ),
            "Banco Central: API Olinda, RDE-IED (registros)",
            "bcb",
            "Parada desde dez/2022 (o arquivista confere todo mês)",
            rde,
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
                (
                    "BPA (ativo), BPP (passivo e patrimônio), DRE (resultado, só o primeiro "
                    "nível), DRA (resultado abrangente), DFC_MI ou DFC_MD (fluxo de caixa pelo "
                    "método indireto ou direto) ou DVA (valor adicionado); as quatro últimas "
                    "inteiras, desde a série T1 (contrato 2.0.0). A DMPL fica em `dmpl_como_era`"
                ),
                TEXTO,
            ),
            "conta": (
                "Código da conta no plano da CVM (1, 1.01, 3.01, 6.01, 7.04.01...)",
                TEXTO,
            ),
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
    "dmpl_como_era": Tabela(
        descricao=(
            "A demonstração das mutações do patrimônio líquido (DMPL) como era em cada data: uma "
            "linha por valor diferente que cada célula (conta × coluna do patrimônio) de cada "
            "período já teve, com o dia em que ficou público e o dia em que foi trocado. É a "
            "`demonstracoes_como_era` com uma coluna a mais no fato (`coluna`); "
            "`como_era_em(base, data, formato=FORMATO_DMPL)` dá a foto (série T1)."
        ),
        fonte=(
            "CVM: dados abertos de DFP e ITR (arquivos `_DMPL_con` e `_DMPL_ind`, versão mais "
            "nova) e ENET (versões anteriores, XML de cada entrega)"
        ),
        familia_da_fonte="cvm",
        frequencia="Montada junto com `demonstracoes_como_era`, por ano (opção `--serie-t1`)",
        atraso=(
            "DFP: até 3 meses depois do fim do exercício; ITR: até 45 dias depois do trimestre "
            "(prazos da CVM, `src/prazos.py`); reapresentações a qualquer momento"
        ),
        onde="Parquet por ano em `<acervo>/base/dmpl/<ano>.parquet` (servidor de casa)",
        linhagem=(
            "A mesma de `demonstracoes_como_era`: `cnpj`, `documento`, `referencia` e `versao` "
            "dizem qual entrega publicou o valor e `origem` se veio dos dados abertos ou do ENET; "
            "ao lado de cada Parquet, `<ano>.json` guarda o SHA-256 da base, cada original e a "
            "`versao_do_codigo`."
        ),
        colunas={
            **_EMPRESA,
            "grupo": ("con (consolidado) ou ind (individual)", TEXTO),
            "demonstracao": ("Sempre DMPL", TEXTO),
            "conta": (
                "Código da linha da DMPL no plano da CVM (5.01, 5.04.06...)",
                TEXTO,
            ),
            "coluna": (
                (
                    "Coluna do patrimônio, com nome único entre empresas (`base/dmpl.py`): "
                    "capital_social, reservas_de_capital, reservas_de_lucro, lucros_acumulados, "
                    "outros_resultados_abrangentes, ajustes_de_avaliacao_patrimonial, "
                    "reservas_de_reavaliacao, patrimonio_liquido, patrimonio_liquido_consolidado e "
                    "nao_controladores; outra coluna "
                    "fica com o nome da empresa sem acento; sem_coluna quando veio sem nome"
                ),
                TEXTO,
            ),
            "descricao": ("Nome da linha como a empresa informou", TEXTO),
            "inicio": ("Começo do período", DATA),
            "fim": ("Fim do período", DATA),
            "valor": (
                (
                    "Valor da célula; vazio quando a empresa deixou em branco na versão lida do "
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
                    "Dia da entrega à CVM (vale a partir dele, inclusive); as mesmas regras de "
                    "`demonstracoes_como_era`"
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
    "comex_cafe": Tabela(
        descricao=(
            "Exportações de café por mês, NCM, UF de origem e país de destino, recortadas do Comex Stat "
            "(NCMs 09011110, 09011190, 09012100 e 21011110). A NCM não separa arábica de conilon: o "
            "`tipo` é sempre `total` e o Espírito Santo (quase só conilon) vai marcado em "
            "`proxy_conilon`, sem dividir o volume. Cada coleta do arquivista vira linhas novas "
            "(`divulgado_em`), porque o MDIC revisa meses antigos"
        ),
        fonte="MDIC: Comex Stat, exportação por NCM (EXP_AAAA.csv) e tabela de países",
        familia_da_fonte="comexstat",
        frequencia="Mensal",
        atraso="O mês fecha cerca de 60 dias depois; o `divulgado_em` é a data da coleta do arquivista, "
        "não a do MDIC",
        onde="Parquet em `<acervo>/base/commodities/comex_cafe/` (`scripts/carga_cafe.py`; leitor `base/commodities/comex_cafe.py`)",
        linhagem=(
            "Recorte do `EXP_AAAA.csv` guardado pelo arquivista (fonte `comexstat`); as vias e unidades "
            "da aduana são somadas por mês, NCM, UF e país."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "ncm": ("NCM do café (8 dígitos)", TEXTO),
            "uf_origem": ("UF do produtor/exportador", TEXTO),
            "codigo_do_pais": ("Código do país de destino no Comex", TEXTO),
            "pais_destino": ("Nome do país de destino", TEXTO),
            "vl_fob_usd": ("Valor FOB em dólares", NUMERO_DECIMAL),
            "kg_liquido": ("Peso líquido em quilos", NUMERO_DECIMAL),
            "sacas": ("Sacas de 60 kg (quilos líquidos ÷ 60)", NUMERO_DECIMAL),
            "tipo": ("Sempre `total`: a NCM não separa arábica de conilon", TEXTO),
            "proxy_conilon": (
                "Verdadeiro para o Espírito Santo, pista de conilon (não divide o volume)",
                SIM_OU_NAO,
            ),
            "divulgado_em": (
                "Data da coleta do arquivista em que a linha apareceu (sem olhar o futuro)",
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
    "ccee_pld": Tabela(
        descricao=(
            "PLD (preço de liquidação das diferenças) da CCEE, em R$/MWh, por submercado: por hora e por "
            "dia desde 01/2021, por mês desde 2001 e, de 06/2001 a 12/2020, por semana e patamar de carga "
            "(`semana_por_patamar`: o arquivo horário da CCEE desses anos não é horário, e a fonte "
            "não rotula o patamar; a posição entre as linhas repetidas vai em `ordem`). A média do dia e "
            "a do mês são as que a CCEE publica, não recalculadas aqui. Sem ligação à empresa: é o preço "
            "de um mercado, não de um agente"
        ),
        fonte="CCEE: PLD horário, média diária e média mensal (dados abertos)",
        familia_da_fonte="ccee",
        frequencia="Diária (a CCEE republica o arquivo do ano a cada dia útil)",
        atraso=(
            "O preço do dia sai no dia anterior e a regra usa o dia + 1; a média do mês vale a partir de "
            "2 dias depois do fim do mês; a semana, 7 dias depois do dia que a fonte marca"
        ),
        onde="Parquet por ano em `<acervo>/base/setoriais/ccee/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 de cada arquivo da CCEE lido e a versão do código."
        ),
        colunas={
            "granularidade": ("`hora`, `dia`, `mes` ou `semana_por_patamar`", TEXTO),
            "submercado": (
                "Sudeste, Sul, Nordeste ou Norte, como a CCEE escreve",
                TEXTO,
            ),
            "referencia": (
                "Início do período a que o preço se refere (hora, dia, mês ou semana)",
                MOMENTO,
            ),
            "competencia": ("Mês (último dia)", DATA),
            "ordem": (
                "Posição entre as linhas da fonte que repetem a mesma referência (1 se única)",
                NUMERO,
            ),
            "periodo_de_comercializacao": (
                "Hora do mês (1 a 744) na fonte; vazio nas outras granularidades",
                NUMERO,
            ),
            "pld": ("Preço em R$/MWh", NUMERO_DECIMAL),
            "disponivel_em": ("Desde quando o número era público (ver o atraso)", DATA),
        },
    ),
    "ons_restricao": Tabela(
        descricao=(
            "Restrição de geração eólica e solar do ONS (curtailment): quanto cada usina ou conjunto "
            "deixou de gerar por ordem do operador, uma linha por usina e hora (a fonte traz uma leitura "
            "a cada 30 minutos; aqui, a média das duas). Eólica desde 10/2021, fotovoltaica desde "
            "04/2024. Hora sem restrição fica com a energia não realizada vazia (vazio não é zero). O ONS "
            "fecha a apuração depois: a revisão de uma hora passada vira linha nova, que só vale desde o "
            "dia em que foi vista (`base/setoriais/revisoes.py::como_era_em`). O dono da usina não vem no "
            "arquivo: a ligação à empresa é pelo agente operador, pelo nome exato do agente na B13"
        ),
        fonte="ONS: restrição de operação por constrained-off de usinas eólicas e fotovoltaicas (dados abertos)",
        familia_da_fonte="ons",
        frequencia="Mensal (o ONS acrescenta e revisa os arquivos de meses passados)",
        atraso="O instante + 2 dias (o mesmo da geração por usina)",
        onde="Parquet por tipo e mês em `<acervo>/base/setoriais/ons_restricao/<tipo>_<ano>_<mês>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `.json` de cada arquivo guarda o endereço e o SHA-256 de cada baixada (uma por revisão) e a "
            "versão do código."
        ),
        colunas={
            "instante": ("Hora (início)", MOMENTO),
            "tipo": ("`eolica` ou `fotovoltaica`", TEXTO),
            "id_subsistema": ("Subsistema (N, NE, S, SE)", TEXTO),
            "uf": ("UF da usina", TEXTO),
            "usina": ("Nome da usina ou do conjunto, como o ONS escreve", TEXTO),
            "id_ons": ("Código da usina ou conjunto no ONS (a chave)", TEXTO),
            "ceg": ("Código na ANEEL (vazio nos conjuntos)", TEXTO),
            "agente_operador": ("Agente operador (liga à empresa pela B13)", TEXTO),
            "geracao_mwmed": (
                "Geração verificada, em MWmed (numa hora, igual a MWh)",
                NUMERO_DECIMAL,
            ),
            "referencia_mwmed": (
                "Geração de referência (o que a usina geraria sem a restrição), MWmed",
                NUMERO_DECIMAL,
            ),
            "referencia_final_mwmed": (
                "Referência final, depois do fechamento da apuração, MWmed",
                NUMERO_DECIMAL,
            ),
            "disponibilidade_mwmed": ("Potência disponível, MWmed", NUMERO_DECIMAL),
            "nao_realizada_mwmed": (
                "Energia que deixou de ser gerada por ordem do operador, MWmed (vazio sem restrição)",
                NUMERO_DECIMAL,
            ),
            "minutos_restricao": (
                "Minutos de restrição na hora (soma das leituras; vazio sem restrição)",
                NUMERO,
            ),
            "razao_da_restricao": (
                "Código da razão da restrição (a primeira da hora)",
                TEXTO,
            ),
            "origem_da_restricao": (
                "Código da origem da restrição (a primeira da hora)",
                TEXTO,
            ),
            "leituras": ("Quantas leituras da fonte entraram na linha", NUMERO),
            "disponivel_em": (
                "Desde quando o número era público (instante + 2 dias)",
                DATA,
            ),
            "visto_em": (
                "Dia da coleta em que este valor apareceu (a revisão vale desde aí)",
                DATA,
            ),
        },
    ),
    "ons_capacidade": Tabela(
        descricao=(
            "Capacidade instalada do ONS, uma linha por unidade geradora: potência efetiva (MW), "
            "proprietário, operador, entrada em teste, entrada em operação e desativação. É a foto do "
            "cadastro de hoje (captura de 14/10/2026), não uma série: a unidade vale desde a entrada em "
            "operação, e a potência de hoje vale desde a entrada (mudanças de potência anteriores à "
            "primeira coleta não aparecem; cada coleta que traz outro valor entra como revisão). A "
            "desativação é só uma data na linha: a unidade não some do passado. O proprietário liga à "
            "empresa pelo nome exato do agente na B13"
        ),
        fonte="ONS: capacidade instalada de geração (dados abertos)",
        familia_da_fonte="ons",
        frequencia="Mensal (o ONS regera o cadastro inteiro)",
        atraso="A regra usa a data de entrada em operação (ou em teste, quando falta)",
        onde="Parquet em `<acervo>/base/setoriais/ons_capacidade/capacidade.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `capacidade.json` guarda o endereço e o SHA-256 de cada baixada do cadastro e a versão do código."
        ),
        colunas={
            "id_subsistema": ("Subsistema (N, NE, S, SE)", TEXTO),
            "uf": ("UF da usina", TEXTO),
            "modalidade_de_operacao": ("Modalidade de operação (tipo I, II...)", TEXTO),
            "proprietario": (
                "Agente proprietário, como o ONS escreve (liga à empresa pela B13)",
                TEXTO,
            ),
            "operador": ("Agente operador", TEXTO),
            "tipo_de_usina": ("Hidrelétrica, térmica, eólica, fotovoltaica...", TEXTO),
            "usina": ("Nome da usina", TEXTO),
            "ceg": ("Código na ANEEL", TEXTO),
            "unidade_geradora": ("Nome da unidade geradora", TEXTO),
            "cod_equipamento": ("Código do equipamento no ONS (a chave)", TEXTO),
            "numero_da_unidade": ("Número da unidade na usina", TEXTO),
            "combustivel": ("Combustível ou fonte", TEXTO),
            "entrada_em_teste": ("Data da entrada em teste", DATA),
            "entrada_em_operacao": ("Data da entrada em operação", DATA),
            "desativada_em": ("Data da desativação (vazio: em operação)", DATA),
            "potencia_efetiva_mw": (
                "Potência efetiva da unidade, em MW",
                NUMERO_DECIMAL,
            ),
            "disponivel_em": (
                "Desde quando a unidade existe para quem pergunta (entrada em operação)",
                DATA,
            ),
            "visto_em": (
                "Dia da coleta em que este valor apareceu (a revisão vale desde aí)",
                DATA,
            ),
        },
    ),
    "anp_concessionarios": Tabela(
        descricao=(
            "Concessionários da ANP: uma linha por contrato de exploração e produção de petróleo e gás e "
            "por sócio do consórcio, com a fase (exploração, avaliação ou produção), a bacia, o ambiente "
            "(terra ou mar), o CNPJ do sócio, a participação em pontos percentuais e a marca de quem "
            "opera. É a foto do dia da coleta, sem data própria: o primeiro valor vale desde a coleta que "
            "o trouxe e uma mudança de sócio, de fase ou de participação entra como linha nova, desde o dia "
            "em que foi vista (o que mudou antes da primeira coleta não aparece). O CNPJ vem na fonte "
            "(o leitor recoloca o zero à esquerda): a ligação à empresa é por ele, sem comparar nomes"
        ),
        fonte="ANP: relação de concessionários (dados abertos)",
        familia_da_fonte="anp",
        frequencia="Mensal (a ANP regera o arquivo inteiro)",
        atraso="Sem data própria: vale desde o dia da coleta do arquivista",
        onde="Parquet em `<acervo>/base/setoriais/anp_concessionarios/concessionarios.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `concessionarios.json` guarda o endereço e o SHA-256 de cada baixada do arquivo e a versão do código."
        ),
        colunas={
            "bid": ("Código da rodada de licitação (BID) do contrato", TEXTO),
            "numero_do_contrato": (
                "Número do contrato na ANP (a chave, com o CNPJ)",
                TEXTO,
            ),
            "fase": ("Exploração, Avaliação ou Produção", TEXTO),
            "nome_fantasia": ("Nome do campo ou bloco", TEXTO),
            "bacia": ("Bacia sedimentar", TEXTO),
            "cnpj": ("CNPJ do sócio, com 14 dígitos (liga à empresa)", TEXTO),
            "empresa": ("Nome do sócio, sem o prefixo de operador", TEXTO),
            "operador": ("Verdadeiro na linha de quem opera o contrato", SIM_OU_NAO),
            "participacao_pct": (
                "Participação do sócio no contrato, em pontos percentuais (0 a 100)",
                NUMERO_DECIMAL,
            ),
            "ambiente": ("Terra ou Mar", TEXTO),
            "disponivel_em": (
                "Desde quando o número era público (o dia da coleta que o trouxe)",
                DATA,
            ),
            "visto_em": (
                "Dia da coleta em que este valor apareceu (a mudança vale desde aí)",
                DATA,
            ),
        },
    ),
    "antt_siade": Tabela(
        descricao=(
            "Produção ferroviária da ANTT (SIADE): toneladas úteis (TU) e tonelada-quilômetro útil (TKU) "
            "por mês, ferrovia, mercadoria e par de estações (origem e destino), de 2006 em diante. A "
            "ferrovia vem como sigla (EFC, MRS, RMS...) e liga à empresa pela B13, na chave exata. A ANTT "
            "pode revisar um mês passado: a revisão vira linha nova, desde o dia em que foi vista"
        ),
        fonte="ANTT: SIADE, produção por origem e destino (dados abertos)",
        familia_da_fonte="antt",
        frequencia="Mensal (um CSV por ano)",
        atraso=(
            "Fim do mês + 60 dias, com folga: a ANTT não diz quando publica e ainda não foi medido (só "
            "uma captura, 14/10/2026); pode atrasar um número, nunca adiantar"
        ),
        onde="Parquet por ano em `<acervo>/base/setoriais/antt_siade/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do CSV do ano e a versão do código."
        ),
        colunas={
            "competencia": ("Mês (último dia)", DATA),
            "ferrovia": ("Sigla da ferrovia na ANTT (liga à empresa pela B13)", TEXTO),
            "mercadoria": ("Mercadoria, como a ANTT escreve", TEXTO),
            "estacao_de_origem": ("Estação de origem", TEXTO),
            "uf_de_origem": ("UF da estação de origem", TEXTO),
            "estacao_de_destino": ("Estação de destino", TEXTO),
            "uf_de_destino": ("UF da estação de destino", TEXTO),
            "toneladas_uteis": ("Toneladas úteis transportadas (TU)", NUMERO_DECIMAL),
            "tku": ("Tonelada-quilômetro útil (TKU)", NUMERO_DECIMAL),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + 60 dias)",
                DATA,
            ),
            "visto_em": (
                "Dia da coleta em que este valor apareceu (a revisão vale desde aí)",
                DATA,
            ),
        },
    ),
    "comex_preco_medio": Tabela(
        descricao=(
            "Preço médio de comércio exterior do Comex Stat, em US$ por quilo (valor FOB ÷ quilo "
            "líquido), por fluxo (exportação ou importação), mês, NCM e URF (porto, aeroporto ou posto "
            "de fronteira). A fonte não publica preço: é conta nossa sobre os CSVs de NCM, somando vias, "
            "países e UFs de cada linha. Quilo zero deixa o preço vazio. **Uso interno até a licença do "
            "MDIC**: fora da exportação e do app público. O MDIC revisa meses passados: a revisão vira linha "
            "nova, desde o dia em que foi vista. O nome da URF está em `URF.csv`, outra tabela da fonte"
        ),
        fonte="MDIC: Comex Stat, exportação e importação por NCM (EXP_AAAA.csv e IMP_AAAA.csv)",
        familia_da_fonte="comexstat",
        frequencia="Mensal (um CSV por ano e por fluxo)",
        atraso=(
            "Fim do mês + 60 dias, com folga sobre a divulgação do MDIC (nos primeiros dias úteis do mês "
            "seguinte); pode atrasar um número, nunca adiantar"
        ),
        onde="Parquet por fluxo e ano em `<acervo>/base/setoriais/comex_preco_medio/<fluxo>_<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `.json` de cada arquivo guarda o endereço e o SHA-256 de cada baixada do CSV e a versão do código."
        ),
        colunas={
            "fluxo": ("`exportacao` ou `importacao`", TEXTO),
            "competencia": ("Mês (último dia)", DATA),
            "ncm": ("NCM (8 dígitos)", TEXTO),
            "urf": (
                "Código da URF (unidade da Receita: porto, aeroporto ou posto)",
                TEXTO,
            ),
            "vl_fob_usd": ("Valor FOB somado, em US$", NUMERO_DECIMAL),
            "kg_liquido": ("Quilo líquido somado", NUMERO_DECIMAL),
            "preco_usd_por_kg": (
                "Valor FOB ÷ quilo líquido, em US$ por quilo (vazio com quilo zero)",
                NUMERO_DECIMAL,
            ),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + 60 dias)",
                DATA,
            ),
            "visto_em": (
                "Dia da coleta em que este valor apareceu (a revisão vale desde aí)",
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
    "fre_capital_social": Tabela(
        descricao=(
            "Capital social de cada FRE (integralizado, subscrito, emitido e autorizado), com as ações ordinárias e preferenciais, as classes e os títulos conversíveis em ação"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_capital_social/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "id_capital_social": ("Identificador da linha de capital na CVM", TEXTO),
            "tipo_capital": (
                'integralizado, subscrito, emitido ou autorizado (o "Capital ..." da CVM, sem acento)',
                TEXTO,
            ),
            "autorizado_em": ("Data da autorização ou aprovação do capital", DATA),
            "valor_capital": ("Valor do capital", REAIS),
            "acoes_ordinarias": ("Quantidade de ações ordinárias", ACOES),
            "acoes_preferenciais": ("Quantidade de ações preferenciais", ACOES),
            "acoes_total": ("Quantidade total de ações", ACOES),
            "acoes_por_classe": (
                'Quantidade por classe, como "Preferencial Classe A=1000; Ordinária Classe A=500" (vazio sem classe declarada)',
                TEXTO,
            ),
            "titulos_conversiveis": (
                'Títulos conversíveis em ação, separados por "; " (sem as condições de conversão, texto livre; vazio quando a companhia diz que não há)',
                TEXTO,
            ),
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "fre_empregados": Tabela(
        descricao=(
            "Empregados por região (recorte `local`) e por posição, liderança ou não (recorte `posicao`), com gênero, raça, faixa etária, PCD e região, como a CVM publica no FRE de 2023 em diante (contagens; vazio nos anos anteriores)"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_empregados/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "recorte": ("`local` (por região) ou `posicao` (liderança ou não)", TEXTO),
            "grupo": (
                "A região (Norte, Nordeste, Centro-Oeste, Sudeste, Sul, Exterior) ou a posição (Liderança, Não-liderança), como a CVM escreve",
                TEXTO,
            ),
            **{
                coluna: (f"Como a CVM publica (`{coluna}`)", NUMERO_DECIMAL)
                for coluna in (
                    "genero_feminino",
                    "genero_masculino",
                    "genero_nao_binario",
                    "genero_outros",
                    "genero_sem_resposta",
                    "raca_amarelo",
                    "raca_branco",
                    "raca_preto",
                    "raca_pardo",
                    "raca_indigena",
                    "raca_outros",
                    "raca_sem_resposta",
                    "idade_ate_30",
                    "idade_30_a_50",
                    "idade_acima_50",
                )
            },
            **{
                coluna: (
                    f"Só no recorte `posicao`: como a CVM publica (`{coluna}`)",
                    NUMERO_DECIMAL,
                )
                for coluna in (
                    "pcd_sim",
                    "pcd_nao",
                    "pcd_sem_resposta",
                    "regiao_norte",
                    "regiao_nordeste",
                    "regiao_centro_oeste",
                    "regiao_sudeste",
                    "regiao_sul",
                    "regiao_exterior",
                )
            },
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "fre_acionistas": Tabela(
        descricao=(
            "Posição acionária de cada FRE: os acionistas que a companhia declara (controladores e quem tem 5% ou mais de uma espécie) e os acionistas deles, até a pessoa física, com as ações e o percentual de cada espécie, desde 2010. Empresa e fundo entram com nome e CNPJ; pessoa física (ou CPF, ou nome sem cara de empresa) só somada por grupo, sem nome, CPF, UF nem nacionalidade (ADR 0075, item 5); o representante legal nem é lido"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_acionistas/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "id_acionista": (
                'Identificador do acionista na CVM; nas pessoas somadas, "pf:<grupo>:<controlador S/N>:<acordo S/N>" (o grupo é o `id_acionista_relacionado` ou "raiz")',
                TEXTO,
            ),
            "tipo_acionista": (
                "`pj` (empresa ou fundo), `pf_somada` (pessoas físicas do grupo, somadas), `outros` ou `tesouraria` (as linhas fixas da CVM)",
                TEXTO,
            ),
            "acionista": ("Nome do acionista; só em `pj`", TEXTO),
            "cnpj_acionista": (
                "CNPJ do acionista; só em `pj` (vazio quando a CVM traz só zeros)",
                TEXTO,
            ),
            "id_acionista_relacionado": (
                "De quem a linha é acionista (o `id_acionista` do grupo); vazio na companhia e quando o grupo é pessoa física",
                TEXTO,
            ),
            "tipo_relacionado": ("PJ ou PF: o tipo de quem a linha é acionista", TEXTO),
            "cnpj_acionista_relacionado": (
                "CNPJ de quem a linha é acionista; vazio quando é pessoa física",
                TEXTO,
            ),
            "acoes_ordinarias": ("Ações ordinárias", ACOES),
            "percentual_ordinarias": (
                "Percentual das ações ordinárias (0 a 100)",
                NUMERO_DECIMAL,
            ),
            "acoes_preferenciais": ("Ações preferenciais", ACOES),
            "percentual_preferenciais": (
                "Percentual das ações preferenciais (0 a 100)",
                NUMERO_DECIMAL,
            ),
            "acoes_total": ("Total de ações", ACOES),
            "percentual_total": (
                "Percentual do total de ações (0 a 100)",
                NUMERO_DECIMAL,
            ),
            "controlador": ("O acionista é controlador?", SIM_OU_NAO),
            "acordo_de_acionistas": ("Participa de acordo de acionistas?", SIM_OU_NAO),
            "residente_exterior": ("Reside no exterior? Só em `pj`", SIM_OU_NAO),
            "nacionalidade": ("Nacionalidade; só em `pj`", TEXTO),
            "uf": ("UF; só em `pj`", TEXTO),
            "composicao_em": ("Data da composição do capital informada", DATA),
            "ultima_alteracao_em": ("Data da última alteração da participação", DATA),
            "acionistas_no_grupo": (
                "Quantos acionistas a linha soma (1 fora das pessoas somadas)",
                NUMERO,
            ),
            "conhecido_em": (
                "Entrega desta versão do FRE à CVM (DT_RECEB): como era na data",
                DATA,
            ),
        },
    ),
    "fre_partes_relacionadas": Tabela(
        descricao=(
            "Transações com partes relacionadas de cada FRE, desde 2010: a contraparte, a categoria da relação, os montantes, a taxa e a posição da companhia. Empresa entra com nome e CNPJ; pessoa física (ou CPF, ou sem tipo e nome sem cara de empresa) só somada por tipo e relação, sem nome nem documento (ADR 0075, item 5); o objeto e as garantias (texto livre) nem são lidos"
        ),
        fonte="CVM: formulário de referência (FRE), dados abertos",
        familia_da_fonte="cvm",
        frequencia="Anual, com reapresentações (a CVM reescreve os anos antigos)",
        atraso="A entrega do FRE: `conhecido_em` é o DT_RECEB da versão",
        onde="Parquet em `<acervo>/base/fre_partes_relacionadas/<ano>.parquet` (`scripts/carga_ofertas_e_conselhos.py`)",
        linhagem="O `<ano>.json` guarda o endereço e o SHA-256 de cada baixada do FRE do ano usada e a versão do código.",
        colunas={
            "cnpj": ("CNPJ da companhia (como a CVM escreve)", TEXTO),
            "referencia": ("Data de referência do FRE", DATA),
            "versao": ("Versão do FRE", NUMERO_DECIMAL),
            "id_documento": ("Identificador do documento na CVM", TEXTO),
            "linha": (
                'Posição da transação no documento ("1", "2"...); nas pessoas somadas, "pf:<tipo>:<relacao>"',
                TEXTO,
            ),
            "tipo_pessoa": (
                "PJ, PF ou `nao_informado`, como a companhia declara",
                TEXTO,
            ),
            "contraparte": (
                "Nome da parte relacionada; vazio nas pessoas somadas",
                TEXTO,
            ),
            "cnpj_contraparte": (
                "CNPJ da parte relacionada; vazio nas pessoas somadas",
                TEXTO,
            ),
            "relacao": (
                "Categoria da relação com a companhia (controle_comum, controle_conjunto, controladora, controlada, coligada, administracao, familiar, acionista, outra, nao_informada), tirada do texto livre",
                TEXTO,
            ),
            "data_transacao": ("Data da transação; vazio nas pessoas somadas", DATA),
            "montante_envolvido": (
                "Montante envolvido (soma nas pessoas somadas)",
                REAIS,
            ),
            "saldo_existente": ("Saldo existente (soma nas pessoas somadas)", REAIS),
            "montante_de_interesse": (
                "Montante de interesse da parte relacionada (soma nas pessoas somadas)",
                REAIS,
            ),
            "emprestimo": (
                "É empréstimo ou dívida? (alguma, nas pessoas somadas)",
                SIM_OU_NAO,
            ),
            "taxa_de_juros": (
                'Taxa de juros em % quando é um número ("3,5%"); "CDI + 1%" e "N/A" ficam vazios',
                NUMERO_DECIMAL,
            ),
            "posicao_contratual": (
                "`credor`, `devedor` ou `outra`: a posição da companhia",
                TEXTO,
            ),
            "transacoes": (
                "Quantas transações a linha soma (1 fora das pessoas somadas)",
                NUMERO,
            ),
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
            "revisão vira linha nova da mesma chave, que só vale desde o dia em que foi vista "
            "(`visto_em`; `base/setoriais/revisoes.py::como_era_em`), e a tabela anterior fica "
            "guardada como `<AAAAMM>.v<N>`. O que o BC revisou antes da 1ª coleta guardada "
            "(10/2026) não aparece"
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
                (
                    "Desde quando o número era público (como era na data): o prazo, ou o dia em "
                    "que a revisão do BC foi vista, se for depois"
                ),
                DATA,
            ),
            "visto_em": (
                (
                    "Dia (São Paulo) em que o arquivista baixou a resposta que trouxe este valor; "
                    "vazio se não havia o dia (acervo desligado)"
                ),
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
        atraso=(
            "O dos valores (o cadastro sai com a data-base): `disponivel_em` usa data-base + 120 "
            "dias. O BC revisa: as 8 datas mais novas são baixadas de novo a cada carga e cada "
            "revisão vira linha nova da mesma chave, que só vale desde o dia em que foi vista "
            "(`visto_em`; `base/setoriais/revisoes.py::como_era_em`), e a tabela anterior fica "
            "guardada como `<AAAAMM>.v<N>`. O que o BC revisou antes da 1ª coleta guardada "
            "(10/2026) não aparece"
        ),
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
            "disponivel_em": (
                (
                    "Desde quando o cadastro era público (como era na data): o prazo, ou o dia em "
                    "que a revisão do BC foi vista, se for depois"
                ),
                DATA,
            ),
            "visto_em": (
                (
                    "Dia (São Paulo) em que o arquivista baixou a resposta que trouxe esta linha; "
                    "vazio se não havia o dia (acervo desligado)"
                ),
                DATA,
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
            "novos são baixados de novo a cada carga e cada regravação que muda um número vira "
            "linha nova da mesma chave, que só vale desde o dia em que foi vista (`visto_em`; "
            "`base/setoriais/revisoes.py::como_era_em`), e a tabela anterior fica guardada como "
            "`<ano>.v<N>`. O que o BC revisou antes da 1ª coleta guardada (10/2026) não aparece"
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
                (
                    "Desde quando o mês era público (como era na data): o prazo, ou o dia em que "
                    "a revisão do BC foi vista, se for depois"
                ),
                DATA,
            ),
            "ocorrencia": (
                (
                    "Ordem da linha entre as de mesma chave no arquivo do BC (0, 1...): o BC publica "
                    "mais de uma linha por chave e a base soma todas"
                ),
                NUMERO,
            ),
            "visto_em": (
                (
                    "Dia (São Paulo) em que o arquivista baixou a resposta que trouxe esta linha; "
                    "vazio se não havia o dia (acervo desligado)"
                ),
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
    "cnpj_situacao_cadastral": Tabela(
        descricao=(
            "Situação cadastral de cada estabelecimento do CNPJ (nula, ativa, suspensa, inapta ou "
            'baixada), um retrato por mês guardado: o histórico "como era na data" nasce da '
            "sequência dos retratos. Só o CNPJ e os códigos da Receita entram; nome fantasia, razão "
            "social, endereço e contatos nunca entram (ADR 0106)."
        ),
        fonte="Receita Federal: dados abertos do CNPJ, arquivos de estabelecimentos",
        familia_da_fonte="rfb-cnpj",
        frequencia="Mensal (a Receita publica um retrato por mês; cada mês guardado vira um arquivo)",
        atraso=(
            "A Receita publica o retrato do mês por volta do dia 10 a 15; ele vale desde "
            "`disponivel_em` (o fim do mês ou, se depois, o dia em que foi baixado). "
            "`data_situacao_cadastral` é a data que a Receita informa, que pode ser anterior ao "
            "retrato em que a linha apareceu pela primeira vez"
        ),
        onde="Parquet em `<acervo>/base/cnpj_situacao_cadastral/<AAAA-MM>.parquet` (servidor de casa)",
        linhagem=LINHAGEM_DA_HISTORICA_SEM_ANO,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "cnpj_basico": ("Raiz do CNPJ (8 dígitos): a empresa", TEXTO),
            "matriz": ("Verdadeiro na matriz, falso na filial", SIM_OU_NAO),
            "situacao_cadastral": (
                "Código da situação cadastral: 01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada",
                TEXTO,
            ),
            "data_situacao_cadastral": ("Data da situação cadastral informada", DATA),
            "motivo_situacao": (
                "Código do motivo da situação cadastral, como a Receita publica (tabela de motivos)",
                TEXTO,
            ),
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
    **_tabelas_do_cnpj(),
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
    **_tabelas_das_sancoes(),
    **_tabelas_das_licencas(),
    **_tabelas_dos_incentivos(),
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
    "pareceres_dfp": _pareceres("DFP", "relatório do auditor independente", "2010"),
    "pareceres_itr": _pareceres("ITR", "relatório da revisão especial", "2011"),
    "securitizacao_certificados": Tabela(
        descricao=(
            "Um certificado de recebíveis (CRI, CRA ou outro título de securitização, OTS) por mês, lido "
            "do informe mensal da CVM (quadro `geral`): a securitizadora, o código do certificado, a "
            "emissão, o tipo de lastro e a data em que o informe foi entregue. Só o que o informe "
            "traz de identificação: garantias, contingências e outros textos livres ficam de fora. "
            "A chave é (`competencia`, `cnpj_securitizadora`, `codigo_certificado`)"
        ),
        fonte="CVM: dados abertos do informe mensal de CRI, CRA e OTS (`base/securitizacao.py`)",
        familia_da_fonte="cvm",
        frequencia="Semanal: a carga relê os arquivos anuais (a CVM reescreve os meses com reapresentações)",
        atraso=(
            "A entrega do informe à CVM (`Data_Entrega`); sem ela, a competência mais 120 dias, e nunca "
            "antes de o mês informado acabar. A mediana da entrega é de 58 dias no CRI e no CRA e de "
            "29 no OTS, mas há entrega com anos de atraso: o prazo fixo olharia o futuro"
        ),
        onde=_onde_da_historica("securitizacao_certificados"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "competencia": ("Primeiro dia do mês a que o informe se refere", DATA),
            "cnpj_securitizadora": (
                "CNPJ da securitizadora (emissora), no formato 00.000.000/0000-00",
                TEXTO,
            ),
            "codigo_certificado": (
                "Código de identificação do certificado na CVM",
                TEXTO,
            ),
            "produto": (
                "`CRI`, `CRA` ou `OTS` (outros títulos de securitização)",
                TEXTO,
            ),
            "versao": (
                "Versão do informe; fica a maior de cada certificado e mês",
                NUMERO,
            ),
            "data_entrega": ("Dia em que o informe foi entregue à CVM", DATA),
            "disponivel_em": (
                "Dia em que o informe ficou público: a entrega, ou o piso quando ela falta",
                DATA,
            ),
            "nome_securitizadora": (
                "Nome da securitizadora como o informe traz",
                TEXTO,
            ),
            "numero_emissao": ("Número da emissão", NUMERO),
            "nome_emissao": ("Nome da emissão (séries) como o informe traz", TEXTO),
            "data_emissao": ("Dia da emissão", DATA),
            "quantidade_series": ("Quantidade de séries da emissão", NUMERO),
            "tipo_lastro": ("Tipo de lastro como a CVM classifica", TEXTO),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "securitizacao_cedente_devedor": Tabela(
        descricao=(
            "Cedente e devedor de cada certificado (CRI, CRA e OTS) por mês, do quadro "
            "`cedente_devedor` do informe mensal da CVM. **Cedente e devedor só entram quando são "
            "pessoa jurídica com CNPJ válido**: a linha com CPF, com documento que não fecha ou em "
            "branco fica de fora inteira (nunca nome nem CPF de pessoa física). A CVM não dá o nome: "
            "só o CNPJ; o nome vem do cadastro. Onde o informe não preenche, cedente e devedor "
            "continuam não observáveis. Sem juízo de qualidade sobre o cedente"
        ),
        fonte="CVM: dados abertos do informe mensal de CRI, CRA e OTS (`base/securitizacao.py`)",
        familia_da_fonte="cvm",
        frequencia="Semanal: a carga relê os arquivos anuais (a CVM reescreve os meses com reapresentações)",
        atraso=(
            "A entrega do informe à CVM (`Data_Entrega`); sem ela, a competência mais 120 dias, e nunca "
            "antes de o mês informado acabar"
        ),
        onde=_onde_da_historica("securitizacao_cedente_devedor"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "competencia": ("Primeiro dia do mês a que o informe se refere", DATA),
            "cnpj_securitizadora": (
                "CNPJ da securitizadora (emissora), no formato 00.000.000/0000-00",
                TEXTO,
            ),
            "codigo_certificado": (
                "Código de identificação do certificado na CVM",
                TEXTO,
            ),
            "produto": (
                "`CRI`, `CRA` ou `OTS` (outros títulos de securitização)",
                TEXTO,
            ),
            "versao": (
                "Versão do informe; fica a maior de cada certificado e mês",
                NUMERO,
            ),
            "data_entrega": ("Dia em que o informe foi entregue à CVM", DATA),
            "disponivel_em": (
                "Dia em que o informe ficou público: a entrega, ou o piso quando ela falta",
                DATA,
            ),
            "papel": ("`cedente` ou `devedor`", TEXTO),
            "cnpj": (
                "CNPJ do cedente ou do devedor, no formato 00.000.000/0000-00",
                TEXTO,
            ),
            "percentual": (
                "Percentual informado pela CVM (nos informes lidos, de 0 a 1; a CVM não define a base)",
                NUMERO_DECIMAL,
            ),
            **_ORIGEM_DA_LINHA,
        },
    ),
    "notas_dfp": Tabela(
        descricao=(
            "Texto das notas explicativas (e do resto do PDF) de cada versão de DFP, uma linha por "
            "página com texto, lido do PDF do pacote do ENET da CVM (linha 135 da fila). Serve para "
            "ler a dívida, as contingências e as partes relacionadas por documento "
            "(`src/divida/nota_dfp.py`). Página só de imagem não tem linha (nada é inventado); cada "
            "versão tem as próprias linhas e vale a partir da própria entrega. O texto traz nomes de "
            "administradores e do auditor: a tabela e o original ficam em área restrita"
        ),
        fonte="CVM: ENET, PDF do pacote da DFP (`base/enet_notas.py`)",
        familia_da_fonte="cvm",
        frequencia="Sob demanda: a carga baixa um pacote por vez, de madrugada, e a montagem relê o acervo",
        atraso=(
            "A entrega à CVM (`DT_RECEB` do índice do DFP); documento enviado com a empresa fora do "
            "registro vale a partir do registro seguinte"
        ),
        onde=_onde_da_historica("notas_dfp"),
        linhagem=LINHAGEM_DA_HISTORICA,
        colunas={
            "cnpj": _EMPRESA["cnpj"],
            "empresa": _EMPRESA["empresa"],
            "referencia": ("Data a que a DFP se refere (fim do exercício)", DATA),
            "versao": ("Versão da DFP (cada reapresentação é um documento)", NUMERO),
            "pagina": ("Página do PDF, a partir de 1", NUMERO),
            "texto": (
                "Texto da página como o PDF o entrega, sem conta nem correção",
                TEXTO,
            ),
            "disponivel_em": (
                "Data em que a versão ficou pública (a entrega à CVM, ou o registro da empresa)",
                DATA,
            ),
            "link": ("Endereço do pacote no ENET de onde o texto saiu", TEXTO),
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
    "release_x_oficial": Tabela(
        descricao=(
            "O que a empresa disse no press-release de resultado contra o que entregou à CVM no "
            "ITR ou na DFP do mesmo período: receita líquida, lucro líquido dos controladores e "
            "resultado operacional. Uma linha por valor lido do release, com o valor oficial, a "
            "diferença em R$ e em % e a classe (igual, igual por arredondamento, diferente, release "
            "não mostra, sem ITR). O modelo só copiou o número e o trecho; o código conferiu o "
            "trecho no texto do PDF e fez a comparação. A tabela guarda só números, nenhum texto "
            "do modelo. Diferença não é erro: pode ser ajuste ou outro critério da empresa"
        ),
        fonte=(
            "CVM: índice do IPE (press-releases de resultado) e dados abertos de DFP e ITR "
            "(`demonstracoes_como_era`)"
        ),
        familia_da_fonte="cvm",
        frequencia=(
            "Semanal no servidor de casa: baixa os releases novos, lê em lote e remonta a tabela"
        ),
        atraso=(
            "Vale a partir de `disponivel_em`, a data mais nova entre o release e o documento "
            "oficial: sem as duas pontas, não existe"
        ),
        onde=(
            "Parquet em `<acervo>/base/release_x_oficial/release_x_oficial.parquet` (servidor de casa)"
        ),
        linhagem=(
            "`protocolo` e `link` levam ao PDF do release no IPE da CVM; `sha256_do_documento` é "
            "o SHA-256 dele, igual ao do manifesto. `modelo` e `versao_do_guia` dizem quem leu e "
            "com que instrução; a resposta bruta, o trecho, os tokens e os descartes ficam no "
            "arquivo de leituras ao lado do PDF (`scripts/ler_releases.py`). O valor oficial vem "
            "de `demonstracoes_como_era`, na versão que valia no dia do release. "
            + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "cnpj": ("CNPJ da companhia, no formato 00.000.000/0000-00", TEXTO),
            "protocolo": ("Protocolo da entrega do release no IPE da CVM", TEXTO),
            "versao": ("Versão da entrega do release (1, 2, 3...)", "número inteiro"),
            "periodo": ("Trimestre do release (3T25)", TEXTO),
            "referencia": ("Data de referência do release: o fim do trimestre", DATA),
            "data_entrega": ("Dia em que o release foi entregue à CVM", DATA),
            "link": ("Endereço do PDF do release na CVM", TEXTO),
            "linha": (
                "receita_liquida, lucro_liquido_controladores ou resultado_operacional",
                TEXTO,
            ),
            "periodo_lido": (
                "O período a que o valor do release se refere: trimestre, acumulado_no_ano ou ano",
                TEXTO,
            ),
            "leitura": (
                "Ordem do valor quando o release repete a linha no mesmo período (0, 1...)",
                "número inteiro",
            ),
            "valor_release_reais": (
                "Valor que o release mostra, já em reais (vazio: o release não mostra a linha)",
                REAIS,
            ),
            "unidade_release": (
                "Escala em que o release mostra o valor: unidade, mil, milhoes ou bilhoes",
                TEXTO,
            ),
            "grupo": ("con (consolidado) ou ind (individual) do valor oficial", TEXTO),
            "documento": (
                "ITR ou DFP de onde veio o valor oficial; DFP-ITR no 4º trimestre (o ano da DFP menos os nove meses do ITR)",
                TEXTO,
            ),
            "documento_versao": ("Versão do ITR ou da DFP usada", "número inteiro"),
            "documento_entregue_em": ("Dia da entrega dessa versão à CVM", DATA),
            "valor_oficial_reais": ("Valor do ITR ou da DFP, em reais", REAIS),
            "tolerancia_reais": (
                "Uma unidade do que o release mostra, em reais: até aqui é arredondamento (o release soma parcelas arredondadas)",
                REAIS,
            ),
            "diferenca_reais": ("Valor do release menos o oficial, em reais", REAIS),
            "diferenca_pct": (
                "Diferença em % do valor oficial",
                "pontos percentuais (66,25 = 66,25%)",
            ),
            "classe": (
                "igual, igual (arredondamento), diferente, release não mostra ou sem ITR",
                TEXTO,
            ),
            "disponivel_em": (
                "A data mais nova entre o release e o documento oficial: quando a linha passou a existir",
                DATA,
            ),
            "publico_em": ("Igual a `disponivel_em`", DATA),
            "modelo": ("Modelo que leu o release", TEXTO),
            "versao_do_guia": ("Versão do guia de leitura dado ao modelo", TEXTO),
            "sha256_do_documento": ("SHA-256 do PDF do release", TEXTO),
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
            "ate": (
                (
                    "1ª referência do FRE da companhia que já não mostra a ligação (vazia: ainda "
                    "aparece, ou a companhia parou de entregar o FRE)"
                ),
                DATA,
            ),
            "ate_publico_em": (
                (
                    "Dia em que essa entrega ficou pública: antes dele não se sabia que a ligação "
                    "acabou"
                ),
                DATA,
            ),
            "vigente": (
                (
                    "A ligação aparece no FRE mais novo da companhia; falso quando acabou ou a "
                    "companhia parou de entregar (a última evidência é a `ultima_referencia`)"
                ),
                SIM_OU_NAO,
            ),
            "principal": (
                (
                    "A ligação a usar da entidade (ticker hoje, própria, a que ainda vale, FRE mais "
                    "recente; nunca no produto; na ANEEL, nunca participação minoritária)"
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
                (
                    "Data do fato: referência do FRE, início do mandato, primeiro mês da carteira. "
                    "É o início da validade (valido_de): a ligação vale de `aconteceu_em` até `ate`"
                ),
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
            "ate": (
                (
                    "Até quando valeu, sem incluir o dia (vazio: ainda vale): o fim da validade "
                    "(valido_ate). O que valia em D sabendo o que se sabia em K: "
                    "`base/rede/controle.py::valiam_em`"
                ),
                DATA,
            ),
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
    "ma_candidatos": Tabela(
        descricao=(
            "Documentos que as companhias abertas entregam à CVM no IPE desde 2003 e que podem "
            "anunciar uma operação de M&A (série 1 da base de M&A, ADR 0063), uma linha por versão "
            "entregue: fatos relevantes escolhidos pelo assunto, comunicados ao mercado com o tipo no "
            "assunto e todo edital de OPA. É a lista do que ler, não a lista de operações: favorece "
            "a cobertura, e o assunto genérico (o padrão do sistema da CVM, o vazio, o esclarecimento "
            "sobre notícia) entra sem tipo, para a leitura do texto decidir. Recompra, proventos, "
            "dívida e oferta de ações ficam fora. Cobertura contra as reestruturações declaradas no "
            "FRE (2010 a 2015): 80% das operações com algum fato relevante da companhia no ano "
            "anterior têm fato relevante candidato na janela (92% com os comunicados); lidas à mão 40 perdidas, 36 não tinham fato relevante "
            "sobre a operação (~97% dos que existem). Amostra de ouro: 84 de 85 operações candidatas"
        ),
        fonte="CVM: arquivos anuais do IPE (`cvm-hist-ipe`), lidos por `base/ma_ipe.py`",
        familia_da_fonte="cvm",
        frequencia=(
            "Diária no servidor de casa (`scripts/montar_ma_candidatos.py`), depois do arquivista "
            "baixar o IPE do ano"
        ),
        atraso=(
            "O documento vale a partir de `publico_em` (entrega da versão à CVM), nunca da "
            "`referencia` informada pela companhia"
        ),
        onde=(
            "Parquet em `<acervo>/base/ma/candidatos/candidatos.parquet` (servidor de casa, "
            "`scripts/montar_ma_candidatos.py`)"
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
            "categoria": (
                "Categoria do IPE: Fato Relevante, Comunicado ao Mercado ou o edital de OPA",
                TEXTO,
            ),
            "tipo": ("Tipo do IPE (vazio no fato relevante)", TEXTO),
            "assunto": ("Assunto como a companhia preencheu", TEXTO),
            "tipo_provavel": (
                (
                    "Pista do assunto: OPA, INC_ACOES, FUSAO, CISAO, INC_EMPRESA, JV, UPI, "
                    "PRIVATIZACAO, ALIEN_CONTROLE, VENDA_ATIVO, AQUISICAO (controle ou minoritária) "
                    "ou NEGOCIACAO (memorando, exclusividade); vazia no assunto genérico. Não é o "
                    "tipo da operação: quem diz é o texto"
                ),
                TEXTO,
            ),
            "evidencia": (
                (
                    "Por que entrou: assunto (o assunto dá o tipo provável), assunto_generico (fato "
                    "relevante de assunto padrão ou vazio) ou categoria (edital de OPA)"
                ),
                TEXTO,
            ),
            "referencia": ("Data de referência informada pela companhia", DATA),
            "publico_em": (
                "Entrega da versão do documento à CVM: quando ficou público para a base",
                DATA,
            ),
            "protocolo": (
                "Protocolo de entrega na CVM (de 2003 a 2014, o link, que a CVM não dá protocolo)",
                TEXTO,
            ),
            "versao": ("Versão do documento (reapresentação)", NUMERO),
            "link": ("Link do documento no sistema da CVM", TEXTO),
            **_ORIGEM_SEM_ANO,
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
    "cftc_cot_agro": Tabela(
        descricao=(
            "Posição dos fundos e dos produtores nos futuros de café (Coffee C), açúcar, soja, milho, "
            "boi gordo e algodão, por semana, desde 2006, no formato do relatório Disaggregated da CFTC"
        ),
        fonte="CFTC: Commitments of Traders, Disaggregated Futures Only (fut_disagg_txt)",
        familia_da_fonte="cftc",
        frequencia="Semanal (posição de terça-feira)",
        atraso="Divulgado na sexta-feira; a base conta a segunda-feira seguinte, 15h30 de Nova York "
        "(regra conservadora do `base/commodities/cftc_cot.py`, com as exceções das paralisações do "
        "governo dos EUA em 2018-19 e 2025). `disponivel_em` é o dia seguinte à divulgação",
        onde="Parquet por ano em `<acervo>/base/setoriais/cftc/<ano>.parquet` (`scripts/carga_setoriais.py`)",
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 dos zips da CFTC usados (o histórico de "
            "2006 a 2016 e um zip por ano desde 2017) e a versão do código."
        ),
        colunas={
            "relatorio": ("Terça-feira a que a posição se refere", DATA),
            "contrato": (
                "cafe-arabica, acucar, soja, milho, boi-gordo ou algodao",
                TEXTO,
            ),
            "open_interest": ("Contratos em aberto no mercado, total", NUMERO_DECIMAL),
            "producer_merchant_long": (
                "Produtores e comerciantes: contratos comprados",
                NUMERO_DECIMAL,
            ),
            "producer_merchant_short": (
                "Produtores e comerciantes: contratos vendidos",
                NUMERO_DECIMAL,
            ),
            "swap_long": ("Operadores de swap: contratos comprados", NUMERO_DECIMAL),
            "swap_short": ("Operadores de swap: contratos vendidos", NUMERO_DECIMAL),
            "swap_spread": ("Operadores de swap: posições em spread", NUMERO_DECIMAL),
            "managed_money_long": (
                "Fundos (managed money): contratos comprados",
                NUMERO_DECIMAL,
            ),
            "managed_money_short": (
                "Fundos (managed money): contratos vendidos",
                NUMERO_DECIMAL,
            ),
            "managed_money_spread": (
                "Fundos (managed money): posições em spread",
                NUMERO_DECIMAL,
            ),
            "disponivel_em": (
                "Desde quando o número era público (dia seguinte à divulgação)",
                DATA,
            ),
        },
    ),
    "conab_cafe": Tabela(
        descricao=(
            "Os levantamentos de safra de café da CONAB, como publicados: por safra, levantamento "
            "(1 a 4), tipo (arábica, conilon, total) e UF, a área em formação e em produção, a "
            "produtividade e a produção em mil sacas. Cada levantamento é uma linha a mais, nunca "
            "sobrescreve o anterior. Em tela e API citando a CONAB e a data do levantamento (ADR "
            "0102; licença CC BY-ND 3.0 registrada na marca)"
        ),
        fonte="CONAB: Acompanhamento da Safra Brasileira de Café (planilha de cada levantamento)",
        familia_da_fonte="conab",
        frequencia="Quatro levantamentos por safra (jan/fev, mai, set e dez), coletados pelo arquivista",
        atraso="O número vale a partir de `divulgado_em`, o dia em que a CONAB publicou o levantamento",
        onde="Parquet em `<acervo>/base/commodities/conab_cafe/` (`scripts/carga_cafe.py`; leitor `base/commodities/conab_cafe.py`)",
        linhagem=(
            "A planilha original fica no acervo do arquivista (fonte `conab-cafe-safra`), com data da "
            "coleta e SHA-256; o dia da divulgação vem do 'Publicado em' da página do levantamento "
            "(fonte `conab-cafe-publicacao`). " + COM_VERSAO_DO_CODIGO
        ),
        colunas={
            "safra": ("Ano em que a safra começa (2026 é a safra 2026/27)", NUMERO),
            "levantamento": ("Número do levantamento da safra, de 1 a 4", NUMERO),
            "tipo": ("`arabica`, `conilon` ou `total`", TEXTO),
            "uf": ("Sigla da UF, `OUTROS` (agrupamento da CONAB) ou `BRASIL`", TEXTO),
            "area_formacao_ha": ("Área em formação, em hectares", NUMERO_DECIMAL),
            "area_producao_ha": ("Área em produção, em hectares", NUMERO_DECIMAL),
            "produtividade_sc_ha": (
                "Produtividade, em sacas de 60 kg por hectare",
                NUMERO_DECIMAL,
            ),
            "producao_mil_sacas": ("Produção, em mil sacas de 60 kg", NUMERO_DECIMAL),
            "divulgado_em": ("Dia em que a CONAB divulgou o levantamento", DATA),
            "divulgado_aproximado": (
                "Verdadeiro quando a data da CONAB não foi achada e `divulgado_em` é o dia da coleta",
                SIM_OU_NAO,
            ),
        },
    ),
    "usda_psd_cafe": Tabela(
        descricao=(
            "Balanço mundial do café por país e ano-safra (produção, consumo, estoques, exportação, "
            "importação), em mil sacas de 60 kg, do USDA PSD. Só a produção se separa por tipo "
            "(arabica, conilon = a Robusta do USDA); os demais atributos são do `total`. Cada baixada "
            "semanal guarda as revisões do USDA com a data em que apareceram, para o 'como era na data'"
        ),
        fonte="USDA FAS, PSD Online: Coffee (psd_coffee_csv.zip)",
        familia_da_fonte="usda",
        frequencia="Semanal (o USDA revisa o café em junho e dezembro, com ajustes no meio)",
        atraso="`divulgado_em` é o fim do mês da revisão que o USDA informa na linha (no máximo o dia "
        "da baixada); o CSV só traz a versão mais recente de cada número, então o passado vem das "
        "baixadas guardadas pelo arquivista",
        onde="Parquet em `<acervo>/base/commodities/usda_psd/<dia da baixada>.parquet`",
        linhagem=(
            "Cada parquet nasce de um `psd_coffee_csv.zip` guardado pelo arquivista (SHA-256 no "
            "registro de coletas); a unidade da fonte é conferida (mil sacas de 60 kg) e uma "
            "unidade diferente interrompe a leitura."
        ),
        colunas={
            "codigo_do_pais": ("Código do país no USDA (ex.: BR)", TEXTO),
            "pais": ("Nome do país, como o USDA escreve", TEXTO),
            "ano_safra": ("Ano de início da safra comercial (2024 = 2024/25)", NUMERO),
            "atributo": ("Produção, consumo, estoque final, exportação...", TEXTO),
            "tipo": ("arabica, conilon ou total", TEXTO),
            "valor": ("Valor em mil sacas de 60 kg", NUMERO_DECIMAL),
            "unidade": ("Unidade da fonte, conferida na leitura", TEXTO),
            "divulgado_em": (
                "Quando a revisão ficou pública (fim do mês da revisão)",
                DATA,
            ),
        },
    ),
    "faostat_cafe": Tabela(
        descricao=(
            "Café verde por país e ano da FAO (FAOSTAT): produção em toneladas, área colhida em hectares "
            "e rendimento em kg por hectare, desde 1961. O FAOSTAT não separa arábica de robusta "
            "(`tipo` é sempre `total`; a separação por tipo está no `usda_psd_cafe`). Cada baixada "
            "semanal guarda a fotografia do dia, para o 'como era na data'"
        ),
        fonte="FAO, FAOSTAT: Crops and livestock products (Production_Crops_Livestock_E_All_Data_(Normalized).zip)",
        familia_da_fonte="faostat",
        frequencia="Semanal (a FAO atualiza a base algumas vezes por ano)",
        atraso="A FAO não informa a data de cada revisão: `divulgado_em` é o dia da baixada que o "
        "arquivista guardou, então um número nunca aparece antes de ter sido visto",
        onde="Parquet em `<acervo>/base/commodities/faostat_cafe/<dia da baixada>.parquet`",
        linhagem=(
            "Cada parquet nasce de um zip guardado pelo arquivista (SHA-256 no registro de coletas); "
            "só entram o café verde dos países (os agregados da FAO saem), a unidade da fonte é "
            "conferida (hg/ha vira kg/ha) e uma unidade desconhecida interrompe a leitura. Crédito: "
            "FAO, FAOSTAT, CC BY 4.0."
        ),
        colunas={
            "codigo_do_pais": ("Código M49 do país (ex.: 076 para o Brasil)", TEXTO),
            "pais": ("Nome do país, como a FAO escreve", TEXTO),
            "ano": ("Ano civil da produção", NUMERO),
            "elemento": ("producao, area_colhida ou rendimento", TEXTO),
            "tipo": ("Sempre total: o FAOSTAT não separa arábica de robusta", TEXTO),
            "valor": ("Valor na unidade da coluna `unidade`", NUMERO_DECIMAL),
            "unidade": ("t, ha ou kg/ha", TEXTO),
            "sinalizador": (
                "Sinalizador da FAO (A oficial, E estimado, I imputado...)",
                TEXTO,
            ),
            "divulgado_em": ("Dia da baixada que trouxe este número", DATA),
        },
    ),
    "clima_regiao_cafe": Tabela(
        descricao=(
            "Clima do mês por região produtora de café (13 regiões de `src/commodities/cafe/regioes.py`): "
            "chuva acumulada, Tmín média, dias com Tmín abaixo de 2 °C e Tmáx média, com a normal de "
            "1991–2020 e a anomalia. Duas fontes, uma por linha: as estações automáticas do INMET "
            "(`inmet`; `n_estacoes` diz quantas valeram) e a chuva por satélite do CHIRPS (`chirps`; só "
            "chuva, média dos municípios ponderada pela área de café da PAM) e, depois de dez/2026, a "
            "ponte `chirps-v3-rnl` (CHIRPS v3 `rnl`, outra série: nunca somada à v2 e com normal própria). "
            "Região com menos de 3 estações válidas no mês fica com os valores vazios, nunca zero"
        ),
        fonte=(
            "INMET: dados históricos das estações automáticas (BDMEP), um zip por ano; CHIRPS v2.0 "
            "(UCSB): GeoTIFF mensal global; CHIRPS v3 `rnl` diário (cópia de terceiro no Hugging Face, "
            "CC BY 4.0; soma do mês feita por nós); IBGE: malha municipal (API de malhas)"
        ),
        familia_da_fonte="inmet",
        ressalva_de_revenda=(
            "As linhas `chirps` são do CHIRPS v2.0 (domínio público; citar Funk et al. 2015); as linhas "
            "`chirps-v3-rnl` são do CHIRPS v3 `rnl` (sabor ERA5, não o `sat`), cópia de terceiro no "
            "Hugging Face sob CC BY 4.0 (citar Funk et al. e o autor da cópia); a malha é do IBGE"
        ),
        frequencia="Mensal",
        atraso=(
            'Mensal; a regra de "como era na data" usa o fim do mês + 45 dias para o INMET e + 60 dias '
            "para o CHIRPS (folga conservadora, não medida: conferir com as baixadas do arquivista)"
        ),
        onde=(
            "Parquet por ano em `<acervo>/base/commodities/clima_regiao_cafe/<ano>.parquet` (a carga "
            "segue o molde de `scripts/carga_setoriais.py`)"
        ),
        linhagem=(
            "O `<ano>.json` guarda o endereço e o SHA-256 dos zips do INMET, dos GeoTIFFs do CHIRPS e da "
            "malha usados e a versão do código; `fonte` diz de qual fonte veio a linha. A normal do CHIRPS "
            "(v2.0, média de 1991–2020 por região e mês do ano, 30 anos) é calculada na carga e fica no "
            "Parquet; a data da conta é a da versão gravada. "
            "**Sem olhar o futuro:** vale para os meses (cada `chuva_mm` só usa o que a fonte tinha na "
            "`disponivel_em`), não para a normal: ela é fixa, só muda se o período de referência mudar "
            "(e o que chega depois de 2020 não a altera). Para os meses de 1991–2020 a anomalia é "
            "contra uma normal que inclui anos posteriores a eles: serve para descrever, não para "
            "simular uma decisão da época"
        ),
        colunas={
            "regiao": (
                "Id da região produtora (`src/commodities/cafe/regioes.py`)",
                TEXTO,
            ),
            "competencia": ("Mês (último dia)", DATA),
            "fonte": ("inmet, chirps (v2) ou chirps-v3-rnl", TEXTO),
            "chuva_mm": (
                "Chuva acumulada no mês (média das estações, ou do satélite)",
                "mm",
            ),
            "tmin_media_c": (
                "Média das temperaturas mínimas diárias (vazio no chirps)",
                "°C",
            ),
            "dias_tmin_abaixo_de_2c": (
                "Dias do mês com Tmín abaixo de 2 °C (média das estações; vazio no chirps)",
                "dias",
            ),
            "tmax_media_c": (
                "Média das temperaturas máximas diárias (vazio no chirps)",
                "°C",
            ),
            "n_estacoes": (
                "Estações válidas no mês (80% dos dias com 20 horas de leitura); vazio no chirps",
                NUMERO,
            ),
            "chuva_normal_mm": (
                "Normal 1991–2020 da chuva do mês do ano (10 anos no mínimo)",
                "mm",
            ),
            "chuva_anomalia_mm": ("chuva_mm menos a normal", "mm"),
            "tmin_normal_c": ("Normal 1991–2020 da Tmín média", "°C"),
            "tmin_anomalia_c": ("tmin_media_c menos a normal", "°C"),
            "tmax_normal_c": ("Normal 1991–2020 da Tmáx média", "°C"),
            "tmax_anomalia_c": ("tmax_media_c menos a normal", "°C"),
            "anos_na_normal": (
                "Anos que entraram na normal (vazio quando menos de 10)",
                NUMERO,
            ),
            "disponivel_em": (
                "Desde quando o número era público (fim do mês + a folga da fonte)",
                DATA,
            ),
        },
    ),
    "area_cafe_municipio": Tabela(
        descricao=(
            "Área e produção de café por município e ano, pela PAM do IBGE e pela cobertura de café "
            "do MapBiomas, lado a lado. A PAM traz a área colhida (hectares) e a quantidade produzida "
            "(toneladas) por tipo: arábica, conilon e o total quando os dois têm número. O MapBiomas "
            "traz os hectares de lavoura de café vistos por satélite (classe 46, soma dos biomas do "
            "município). Medem coisas diferentes (colhida contra plantada visível) e nunca se somam; "
            "coluna sem número fica vazia, nunca zero"
        ),
        fonte=(
            "IBGE: PAM, tabela 1613 do SIDRA (variáveis 216 e 214, café arábica e canephora, por "
            "município); MapBiomas: Coleção 11, planilha de cobertura por bioma, estado e município"
        ),
        familia_da_fonte="mapbiomas",
        ressalva_de_revenda=(
            "As colunas da PAM são do IBGE (domínio público; citar o IBGE); a coluna do MapBiomas é "
            "CC BY-SA (citar o projeto MapBiomas, Souza et al. 2020; revenda a confirmar)"
        ),
        frequencia="Anual",
        atraso=(
            'Anual; a regra de "como era na data" usa 31/10 do ano seguinte, quando a PAM já saiu '
            "(setembro ou outubro); a coleção do MapBiomas sai uma vez por ano com todos os anos refeitos"
        ),
        onde=(
            "Parquet único em `<acervo>/base/commodities/area_cafe_municipio/municipios.parquet` (a "
            "carga segue o molde de `scripts/carga_setoriais.py`)"
        ),
        linhagem=(
            "O `municipios.json` guarda o endereço e o SHA-256 da resposta do SIDRA e do zip do "
            "MapBiomas (com a coleção), e a versão do código"
        ),
        colunas={
            "codigo": ("Código do município no IBGE (7 dígitos)", TEXTO),
            "nome": (
                "Nome do município (PAM); vazio quando só o MapBiomas tem o município",
                TEXTO,
            ),
            "uf": ("Sigla da UF", TEXTO),
            "ano": ("Ano da safra (PAM) ou do mapa (MapBiomas)", "ano"),
            "referencia": ("Último dia do ano", DATA),
            "area_arabica_ha": ("Área colhida de café arábica (PAM)", "hectares"),
            "area_conilon_ha": (
                "Área colhida de café canephora/conilon (PAM)",
                "hectares",
            ),
            "area_total_ha": (
                "Arábica + conilon, só quando os dois têm número",
                "hectares",
            ),
            "producao_arabica_t": (
                "Quantidade produzida de arábica (PAM)",
                "toneladas",
            ),
            "producao_conilon_t": (
                "Quantidade produzida de canephora/conilon (PAM)",
                "toneladas",
            ),
            "producao_total_t": (
                "Arábica + conilon, só quando os dois têm número",
                "toneladas",
            ),
            "area_mapbiomas_ha": (
                "Cobertura da classe Café do MapBiomas no município (soma dos biomas)",
                "hectares",
            ),
            "disponivel_em": (
                "Desde quando o número era público (31/10 do ano seguinte, pela PAM)",
                DATA,
            ),
        },
    ),
    "contraparte_cafe": Tabela(
        descricao=(
            "Tabela conferida à mão: fatos públicos e datados das cooperativas e tradings de café "
            "(faturamento, sobras, sacas recebidas, pedido de recuperação judicial, apuração pública), "
            "cada um com fonte, veículo e data, ditos com as nossas palavras. Sem nota, cor nem "
            "conselho e sem pessoa física: a ficha (`base/contrapartes/cafe.py`) junta a situação "
            "especial da Receita e os informes de CRA da CVM e diz o que não sabemos"
        ),
        fonte=(
            "Notícias e documentos públicos (ALMG, Bloomberg Línea, Revista Cultivar, Notícias "
            "Agrícolas, Compre Rural, AgFeed, Brazil Journal)"
        ),
        familia_da_fonte="contrapartes",
        frequencia="Quando a conferência anda (assembleias de março, notícias de recuperação judicial)",
        atraso="O `divulgado_em` é o dia da publicação da notícia ou do documento",
        onde="`base/conferidas/contrapartes_cafe.csv` no repositório (Git)",
        linhagem=(
            "Cada linha diz a fonte, o veículo e quando foi conferida (`fonte`, `conferido_em`); as "
            "páginas de todas as fontes ficam guardadas pelo arquivista (`contrapartes-cafe`) só como "
            "prova, nunca mostradas (ADR 0102); a notícia de recuperação judicial ou fechamento só vira fato da ficha depois de "
            "guardada (antes, fica em 'o que não sabemos'); o histórico de cada mudança fica no Git."
        ),
        colunas={
            "id": (
                "Apelido da contraparte (chave quando não há CNPJ conferido)",
                TEXTO,
            ),
            "cnpj": (
                "CNPJ da entidade no cadastro aberto da Receita (vazio: não confirmado)",
                TEXTO,
            ),
            "nome": ("Nome da cooperativa ou empresa", TEXTO),
            "tipo": ("`cooperativa`, `trading` ou `exportadora`", TEXTO),
            "uf": ("UF da sede", TEXTO),
            "fato": (
                "Tipo do fato (`faturamento`, `pedido_de_recuperacao_judicial`...)",
                TEXTO,
            ),
            "descricao": ('O fato com as nossas palavras, "segundo <veículo>"', TEXTO),
            "valor": (
                "O número do fato, na unidade ao lado (vazio se não há)",
                NUMERO_DECIMAL,
            ),
            "unidade": ("`R$`, `sacas` ou outra", TEXTO),
            "data": ("Quando o fato aconteceu (fim do exercício, dia do pedido)", DATA),
            "divulgado_em": ("Quando ficou público (sem olhar o futuro)", DATA),
            "fonte": ("Endereço público da notícia ou do documento", TEXTO),
            "veiculo": ("Quem publicou", TEXTO),
            "tipo_de_fonte": (
                "`documento_oficial`, `demonstracao_financeira`, `relatorio_da_entidade` ou `noticia`",
                TEXTO,
            ),
            "conferido_em": ("Dia da conferência", DATA),
        },
    ),
}


_ME = "mercado_e_empresas"
_FIDC = "credito_e_fidc"
_CVM = "2010-01-01"  # primeiro arquivo da CVM que a base lê (FRE, ITR e DFP de 2010)
_GOVERNO = "2026-10-14"  # as fontes de governo só passaram a ser guardadas neste dia
_LICENCAS = "2026-10-29"  # as licenças e registros (Ficha Clara) entraram no arquivista neste dia
_INCENTIVOS = "2026-10-29"  # o REIDI, a CDE e o RDE-IED (Ficha Clara) entraram no arquivista neste dia
_COMMODITIES_FAO = "2026-10-19"  # o FAOSTAT só passou a ser guardado em tabela neste dia (PR 14 do café)
_COMMODITIES = (
    "2026-10-18"  # o USDA PSD só passou a ser guardado neste dia (PR 4 do café)
)


# módulo, chaves, apelidos das três datas (`aconteceu_em`: quando o fato ocorreu; `publico_em`: quando
# ficou público; `coletado_em`: quando a base o guardou), `historico_desde` e granularidade do
# `publico_em`; só colunas que já existem, sem inventar data onde a fonte não dá
def _contrato(**campos: object) -> dict[str, object]:
    return campos


_CONTRATO = {
    # 2.0.0: a série T1 pôs a DFC, a DVA e a DRA na tabela (quem não filtra `demonstracao` muda)
    "demonstracoes_como_era": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia", "versao", "demonstracao", "grupo", "conta"), datas={"aconteceu_em": "referencia", "publico_em": "divulgado_em"}, historico_desde=_CVM, versao_do_contrato="2.0.0"),
    "dmpl_como_era": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia", "versao", "grupo", "conta", "coluna"), datas={"aconteceu_em": "referencia", "publico_em": "divulgado_em"}, historico_desde=_CVM),
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
    "comex_cafe": _contrato(modulo=_ME, chaves=("competencia", "ncm", "uf_origem", "codigo_do_pais", "divulgado_em"), datas={"aconteceu_em": "competencia", "publico_em": "divulgado_em"}, historico_desde="2026-10-18"),
    "ons_geracao": _contrato(modulo=_ME, chaves=("instante", "id_ons"), datas={"aconteceu_em": "instante", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "ccee_pld": _contrato(modulo=_ME, chaves=("granularidade", "submercado", "referencia", "ordem"), datas={"aconteceu_em": "referencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "ons_restricao": _contrato(modulo=_ME, chaves=("instante", "tipo", "id_ons", "visto_em"), datas={"aconteceu_em": "instante", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "ons_capacidade": _contrato(modulo=_ME, chaves=("cod_equipamento", "visto_em"), datas={"aconteceu_em": "entrada_em_operacao", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "anp_concessionarios": _contrato(modulo=_ME, chaves=("numero_do_contrato", "cnpj", "visto_em"), datas={"aconteceu_em": "disponivel_em", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "antt_siade": _contrato(modulo=_ME, chaves=("competencia", "ferrovia", "mercadoria", "estacao_de_origem", "estacao_de_destino", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "comex_preco_medio": _contrato(modulo=_ME, chaves=("fluxo", "competencia", "ncm", "urf", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "aneel_samp": _contrato(modulo=_ME, chaves=("competencia", "cnpj", "tipo_de_mercado", "modalidade_tarifaria", "subgrupo_tarifario", "classe_de_consumo", "subclasse_de_consumo", "detalhe_do_consumidor", "nucleo_ceg", "posto_tarifario", "opcao_de_energia", "detalhe_do_mercado", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "anatel_acessos": _contrato(modulo=_ME, chaves=("competencia", "servico", "recorte", "cnpj", "uf", "regiao_pgo", "codigo_nacional", "modalidade_de_cobranca", "tecnologia", "geracao", "tipo_de_pessoa", "tipo_de_produto", "faixa_de_velocidade", "meio_de_acesso", "tipo_de_acesso_tv", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "ans_beneficiarios": _contrato(modulo=_ME, chaves=("competencia", "cd_operadora", "modalidade", "cobertura", "vigencia_do_plano", "contratacao", "financiamento", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "fre_conselho": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_comites": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'tipo_de_comite'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_remuneracao": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'fim_do_exercicio', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_remuneracao_extremos": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'fim_do_exercicio', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_diversidade": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'orgao'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_capital_social": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'id_capital_social'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_empregados": _contrato(modulo=_ME, chaves=('cnpj', 'referencia', 'versao', 'recorte', 'grupo'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde="2023-01-01"),
    "fre_acionistas": _contrato(modulo=_ME, pessoa=True, chaves=('cnpj', 'referencia', 'versao', 'id_acionista'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "fre_partes_relacionadas": _contrato(modulo=_ME, pessoa=True, chaves=('cnpj', 'referencia', 'versao', 'linha'), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "ofertas_antigas": _contrato(modulo=_ME, chaves=('numero_processo', 'numero_registro_oferta', 'cnpj_emissor', 'tipo_ativo', 'classe_ativo', 'serie', 'emissao'), datas={"aconteceu_em": "anunciada_em", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "ofertas_resolucao_160": _contrato(modulo=_ME, chaves=('numero_requerimento', 'cnpj_emissor'), datas={"aconteceu_em": "anunciada_em", "publico_em": "disponivel_em"}, historico_desde=_CVM),
    "susep_seguros": _contrato(modulo=_ME, chaves=("competencia", "coenti", "cogrupo", "coramo", "visto_em"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde=_GOVERNO),
    "amostra_painel": _contrato(modulo=_ME, chaves=("cnpj", "data"), datas={"aconteceu_em": "data"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "setoriais_buracos": _contrato(modulo=_ME, chaves=("fonte", "chave"), historico_desde=_GOVERNO),
    # 2.0.0 (21/10/2026): a revisão do BC é linha nova da mesma chave (`visto_em`), que vale só desde o dia em que foi vista
    "ifdata_valores": _contrato(modulo=_ME, chaves=("data_base", "tipo_instituicao", "cod_inst", "relatorio", "grupo", "conta", "coluna", "visto_em"), datas={"aconteceu_em": "data_base", "publico_em": "disponivel_em"}, historico_desde=_CVM, versao_do_contrato="2.0.0"),
    # 2.0.0 (25/10/2026): a revisão do BC é linha nova da mesma chave (`visto_em`), que vale só desde o dia em que foi vista
    "ifdata_cadastro": _contrato(modulo=_ME, chaves=("data_base", "cod_inst", "visto_em"), datas={"aconteceu_em": "data_base", "publico_em": "disponivel_em"}, historico_desde=_CVM, versao_do_contrato="2.0.0"),
    "ligacao_dos_bancos": _contrato(modulo=_ME, chaves=("data_base", "cod_inst"), datas={"aconteceu_em": "data_base"}, historico_desde=_CVM),
    # 1.1.0 (25/10/2026): declara `publico_em` = `disponivel_em` (data-base + 60 dias); a porta passa a aceitar `como_era_em`
    # 2.0.0 (25/10/2026): a regravação do BC que muda um número é linha nova da mesma chave (`visto_em`)
    "scr_credito": _contrato(modulo=_FIDC, chaves=("data_base", "uf", "segmento", "cliente", "cnae_ocupacao", "porte", "modalidade", "submodalidade", "origem", "indexador", "ocorrencia", "visto_em"), datas={"aconteceu_em": "data_base", "publico_em": "disponivel_em"}, historico_desde=_CVM, versao_do_contrato="2.0.0"),
    "padroes_setoriais": _contrato(modulo=_ME, chaves=("data_de_corte", "grupo", "indicador", "versao"), datas={"aconteceu_em": "data_de_corte", "coletado_em": "calculado_em"}, historico_desde=_CVM),
    "fre_proventos": _contrato(modulo=_ME, chaves=("cnpj", "exercicio", "referencia", "versao"), datas={"aconteceu_em": "referencia", "coletado_em": "coletado_em"}, historico_desde=_CVM),
    "fre_eventos_de_capital": _contrato(modulo=_ME, chaves=("cnpj", "tipo", "data", "referencia", "versao"), datas={"aconteceu_em": "data", "coletado_em": "coletado_em"}, historico_desde=_CVM),
    "eventos": _contrato(modulo=_ME, chaves=("protocolo", "versao"), datas={"aconteceu_em": "referencia", "publico_em": "publicado_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "negociacoes": _contrato(modulo=_ME, chaves=("fonte", "documento", "versao", "cnpj", "cargo", "operacao", "ativo", "data"), datas={"aconteceu_em": "data", "publico_em": "entregue_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "proventos": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao"), datas={"aconteceu_em": "referencia", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "eventos_de_capital": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao", "tipo", "data"), datas={"aconteceu_em": "data", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "insolvencia": _contrato(modulo=_ME, chaves=("cnpj", "protocolo", "versao", "rotulo"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM, versao_do_contrato="3.0.0"),  # 2.0.0 (16/10/2026): rótulo da própria × de terceiro; 3.0.0 (17/10/2026): uma linha por versão da entrega
    "cnpj_situacao_especial": _contrato(modulo="governo_e_sancoes", chaves=("cnpj", "mes_do_retrato"), datas={"aconteceu_em": "data_situacao_especial", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes", versao_do_contrato="2.0.0"),  # 2.0.0 (17/10/2026): público desde `disponivel_em`, não do mês do arquivo
    "cnpj_situacao_cadastral": _contrato(modulo="governo_e_sancoes", chaves=("cnpj", "mes_do_retrato"), datas={"aconteceu_em": "data_situacao_cadastral", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "cnpj_estabelecimentos": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cnpj",), datas={"aconteceu_em": "data_situacao_cadastral"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "cnpj_estabelecimentos_mudancas": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("mes", "cnpj", "ordem"), datas={"publico_em": "mes"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "cnpj_simples": _contrato(modulo="governo_e_sancoes", chaves=("cnpj_basico",), datas={}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "cnpj_simples_mudancas": _contrato(modulo="governo_e_sancoes", chaves=("mes", "cnpj_basico", "ordem"), datas={"publico_em": "mes"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "cnpj_qsa": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cnpj_basico", "tipo_socio", "raiz_socio_pj", "id_pessoa"), datas={"aconteceu_em": "data_entrada"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "cnpj_qsa_mudancas": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("mes", "cnpj_basico", "tipo_socio", "raiz_socio_pj", "id_pessoa", "ordem"), datas={"publico_em": "mes"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "sancoes_cgu": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "inicio", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "ans_penalidades": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "inicio", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "anvisa_registros": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "concedido_em", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_LICENCAS, granularidade_do_publico_em="mes"),
    "antt_rntrc": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "concedido_em", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_LICENCAS, granularidade_do_publico_em="mes"),
    "mapa_sipeagro": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "concedido_em", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_LICENCAS, granularidade_do_publico_em="mes"),
    "anatel_outorgas": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "concedido_em", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_LICENCAS, granularidade_do_publico_em="mes"),
    "anm_titulos": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "concedido_em", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_LICENCAS, granularidade_do_publico_em="mes"),
    "ancine_agentes": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cadastro", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "concedido_em", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_LICENCAS, granularidade_do_publico_em="mes"),
    "mme_reidi": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("id_na_fonte", "visto_em"), datas={"aconteceu_em": "portaria_em", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_INCENTIVOS, granularidade_do_publico_em="mes"),
    "aneel_cde": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("arquivo", "id_na_fonte", "visto_em"), datas={"aconteceu_em": "mes", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_INCENTIVOS, granularidade_do_publico_em="mes"),
    "bcb_rde_ied": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("id_na_fonte", "visto_em"), datas={"aconteceu_em": "mes", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_INCENTIVOS, granularidade_do_publico_em="mes"),
    "pgfn_divida": _contrato(modulo="governo_e_sancoes", pessoa=True, chaves=("cnpj", "tipo_divida", "regiao", "tipo_devedor", "tipo_situacao", "situacao_inscricao", "ajuizado", "data_do_retrato"), datas={"aconteceu_em": "data_do_retrato", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_GOVERNO, granularidade_do_publico_em="mes"),
    "debentures_assembleias": _contrato(modulo=_FIDC, chaves=("link",), datas={"aconteceu_em": "referencia", "publico_em": "publico_em", "coletado_em": "origem_coletada_em"}, historico_desde="2003-01-01", versao_do_contrato="2.0.0"),  # 2.0.0: o link é a chave (a CVM põe vários arquivos numa entrega; antes de 2015 não há versão)
    "ratings": _contrato(modulo=_FIDC, chaves=("cnpj", "protocolo", "versao"), datas={"aconteceu_em": "data_acao", "publico_em": "publico_em", "coletado_em": "origem_coletada_em"}, historico_desde="2003-01-01"),
    "auditores": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao", "auditor_id", "inicio"), datas={"aconteceu_em": "inicio", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM, versao_do_contrato="2.0.0"),  # 2.0.0 (17/10/2026): a mesma firma tem mandatos seguidos no mesmo FCA
    "pareceres_dfp": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao"), datas={"aconteceu_em": "referencia", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "pareceres_itr": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao"), datas={"aconteceu_em": "referencia", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde="2011-01-01"),
    "securitizacao_certificados": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_securitizadora", "codigo_certificado"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde="2019-01-01"),
    "securitizacao_cedente_devedor": _contrato(modulo=_FIDC, chaves=("competencia", "cnpj_securitizadora", "codigo_certificado", "papel", "cnpj", "versao"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde="2019-01-01"),
    "notas_dfp": _contrato(modulo=_ME, pessoa=True, chaves=("cnpj", "referencia", "versao", "pagina"), datas={"aconteceu_em": "referencia", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "fca_geral": _contrato(modulo=_ME, chaves=("cnpj", "referencia", "versao"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "trocas_de_auditor": _contrato(modulo=_ME, chaves=("cnpj", "efetiva_em", "novo_id"), datas={"aconteceu_em": "efetiva_em", "publico_em": "conhecido_em"}, historico_desde=_CVM),
    "curva_juros": _contrato(modulo="macro", chaves=("data_base", "curva", "prazo_anos"), datas={"aconteceu_em": "data_base", "publico_em": "disponivel_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "bcb_selic_focus": _contrato(modulo="macro", chaves=("serie", "referencia", "divulgado_em"), datas={"aconteceu_em": "referencia", "publico_em": "publico_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "release_x_oficial": _contrato(modulo=_ME, chaves=("protocolo", "linha", "periodo_lido", "leitura"), datas={"aconteceu_em": "referencia", "publico_em": "publico_em", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "noticias_fatos": _contrato(modulo=_ME, chaves=("id_fato",), datas={"aconteceu_em": "aconteceu_em", "publico_em": "publico_em", "coletado_em": "coletado_em"}, historico_desde=_CVM),
    "noticias_numeros": _contrato(modulo=_ME, chaves=("id_fato", "campo"), datas={"publico_em": "origem_divulgado_em"}, historico_desde=_CVM),
    "controladas": _contrato(modulo=_ME, chaves=("cnpj_companhia", "referencia", "versao", "cnpj"), datas={"aconteceu_em": "referencia", "publico_em": "conhecido_em", "coletado_em": "origem_coletada_em"}, historico_desde=_CVM),
    "rotulos_atraso": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia"), datas={"aconteceu_em": "prazo", "publico_em": "primeira_entrega", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "colunas_atraso": _contrato(modulo=_ME, chaves=("cnpj", "documento", "referencia"), datas={"aconteceu_em": "data_da_previsao", "coletado_em": "montado_em"}, historico_desde=_CVM),
    "empresa_serie": _contrato(modulo=_ME, chaves=("fonte", "chave", "cnpj_companhia"), datas={"aconteceu_em": "desde", "coletado_em": "montado_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "entidades": _contrato(modulo="rede", chaves=("id_entidade",), datas={"publico_em": "publico_em"}, historico_desde=_CVM),
    "identificadores": _contrato(modulo="rede", chaves=("id_entidade", "sistema", "valor", "desde"), datas={"aconteceu_em": "desde", "publico_em": "publico_em"}, historico_desde=_CVM),
    "ligacoes": _contrato(modulo="rede", chaves=("de", "para", "tipo", "papel", "aconteceu_em", "fonte"), datas={"aconteceu_em": "aconteceu_em", "publico_em": "publico_em", "coletado_em": "coletado_em"}, historico_desde=_CVM, versao_do_contrato="1.1.0"),
    "ma_assessorias": _contrato(modulo="ma", chaves=("assessoria", "url"), datas={"coletado_em": "coletado_em"}, historico_desde="2026-10-16"),
    "ma_candidatos": _contrato(modulo="ma", chaves=("link",), datas={"aconteceu_em": "referencia", "publico_em": "publico_em", "coletado_em": "origem_coletada_em"}, historico_desde="2003-01-01"),
    "ma_partes": _contrato(modulo="ma", chaves=("assessoria", "url", "nome"), historico_desde="2026-10-16"),
    "ma_negocios": _contrato(modulo="ma", chaves=("assessoria", "url"), historico_desde="2026-10-16"),
    "ma_datas": _contrato(modulo="ma", chaves=("assessoria", "url"), datas={"aconteceu_em": "fechamento_em", "publico_em": "conhecido_em", "coletado_em": "coletado_em"}, historico_desde="2026-10-16"),
    "conab_cafe": _contrato(modulo="macro", chaves=("safra", "levantamento", "tipo", "uf", "divulgado_em"), datas={"publico_em": "divulgado_em"}, historico_desde="2026-02-05", versao_do_contrato="1.1.0"),
    "ma_regua": _contrato(modulo="ma", chaves=("assessoria", "url"), datas={"aconteceu_em": "fechamento_em", "publico_em": "conhecido_em_do_negocio"}, historico_desde="2026-10-16"),
    "cftc_cot_agro": _contrato(modulo=_ME, chaves=("relatorio", "contrato"), datas={"aconteceu_em": "relatorio", "publico_em": "disponivel_em"}, historico_desde="2006-06-13"),
    "usda_psd_cafe": _contrato(modulo="macro", chaves=("codigo_do_pais", "ano_safra", "atributo", "tipo", "divulgado_em"), datas={"aconteceu_em": "divulgado_em", "publico_em": "divulgado_em"}, historico_desde=_COMMODITIES),
    "faostat_cafe": _contrato(modulo="macro", chaves=("codigo_do_pais", "ano", "elemento", "divulgado_em"), datas={"aconteceu_em": "divulgado_em", "publico_em": "divulgado_em"}, historico_desde=_COMMODITIES_FAO),
    "clima_regiao_cafe": _contrato(modulo="macro", chaves=("regiao", "competencia", "fonte"), datas={"aconteceu_em": "competencia", "publico_em": "disponivel_em"}, historico_desde="1981-01-31", granularidade_do_publico_em="mes"),
    "area_cafe_municipio": _contrato(modulo="macro", chaves=("codigo", "ano"), datas={"aconteceu_em": "referencia", "publico_em": "disponivel_em"}, historico_desde="1985-12-31"),
    "contraparte_cafe": _contrato(modulo="macro", chaves=("id", "fato", "data"), datas={"aconteceu_em": "data", "publico_em": "divulgado_em", "coletado_em": "conferido_em"}, historico_desde="2004-07-01"),
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
    "release_x_oficial": {
        "pasta": "release_x_oficial",
        "nao_nulas": ("classe", "disponivel_em", "publico_em", "sha256_do_documento"),
    },
    "noticias_fatos": {
        "pasta": "noticias_fatos",
        "nao_nulas": ("id_fato", "pauta", "publico_em", "link", "hash_da_linha"),
    },
    "noticias_numeros": {
        "pasta": "noticias_numeros",
        "nao_nulas": ("id_fato", "campo", "valor", "origem_divulgado_em"),
    },
    "sancoes_cgu": {
        "pasta": "sancoes_cgu",
        "faixas": {"valor_multa": _SEM_NEGATIVO},
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
        "anuncia_o_futuro": True,  # a sanção publicada pode começar a valer depois
    },
    "anvisa_registros": {
        "pasta": "anvisa_registros",
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "antt_rntrc": {
        "pasta": "antt_rntrc",
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "mapa_sipeagro": {
        "pasta": "mapa_sipeagro",
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "anatel_outorgas": {
        "pasta": "anatel_outorgas",
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "anm_titulos": {
        "pasta": "anm_titulos",
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "ancine_agentes": {
        "pasta": "ancine_agentes",
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "mme_reidi": {
        "pasta": "mme_reidi",
        "nao_nulas": ("id_na_fonte", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "aneel_cde": {
        "pasta": "aneel_cde",
        "nao_nulas": ("arquivo", "id_na_fonte", "cnpj", "cnpj_basico", "linhas", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "bcb_rde_ied": {
        "pasta": "bcb_rde_ied",
        "nao_nulas": ("id_na_fonte", "cnpj_basico", "codigo_rde", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
    },
    "ans_penalidades": {
        "pasta": "ans_penalidades",
        "faixas": {"valor_multa": _SEM_NEGATIVO},
        "nao_nulas": ("cadastro", "cnpj", "cnpj_basico", "consta", "trata_como_pessoa", "visto_em", "disponivel_em"),
        "anuncia_o_futuro": True,  # a decisão de 1ª instância vem antes da publicação, mas não sempre
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
    "ma_candidatos": {
        "pasta": "ma/candidatos",
        "faixas": {"versao": (1.0, None)},
        "nao_nulas": ("cnpj", "publico_em", "protocolo", "link", "evidencia"),
        "anuncia_o_futuro": True,  # a referência do IPE pode ser a assembleia que vai aprovar
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
