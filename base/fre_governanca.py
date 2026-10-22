"""Capital social, empregados, acionistas e partes relacionadas pelo FRE da CVM (série T, T3: o FRE completo para a governança da ficha).

O FRE tem 61 tipos de CSV; os de conselho, comitês e remuneração já são lidos em `base/conselhos.py`.
Aqui entram os que faltavam para a governança:

- `fre_capital_social` (2010 em diante): cada linha de capital (integralizado, subscrito, emitido,
  autorizado) com as quantidades de ações, as classes preferenciais e os títulos conversíveis;
- `fre_empregados` (só do FRE de 2023 em diante, quando a CVM passou a pedir): os empregados por
  região e por posição (liderança ou não), com gênero, raça, faixa etária e PCD, só contagens;
- `fre_acionistas` (2010 em diante): quem tem 5% ou mais e a cadeia de acionistas até a pessoa física;
- `fre_partes_relacionadas` (2010 em diante): as transações com partes relacionadas (item 11.2).

Pessoa física (ADR 0075): até o parecer jurídico, entra só como número somado, sem nome, CPF, id, UF
ou nacionalidade; o representante legal nem é lido. A base olha para empresas.

"Como era na data": cada linha leva o `conhecido_em`, a entrega da versão à CVM (`DT_RECEB` do arquivo
principal, pelo `ID_Documento`), como as outras `fre_*`. Texto livre (condições de conversão, prazo de
integralização) não entra.
"""

import re
import unicodedata

import pandas as pd

from base import conselhos
from base.cnpj import TAMANHO as TAMANHO_DO_CNPJ
from base.cnpj import TAMANHO_DO_CPF

CAPITAL = {
    "ID_Capital_Social": "id_capital_social",
    "Tipo_Capital": "tipo_capital",
    "Data_Autorizacao_Aprovacao": "autorizado_em",
    "Valor_Capital": "valor_capital",
    "Quantidade_Acoes_Ordinarias": "acoes_ordinarias",
    "Quantidade_Acoes_Preferenciais": "acoes_preferenciais",
    "Quantidade_Total_Acoes": "acoes_total",
}
COLUNAS_DO_CAPITAL = (
    *conselhos.COLUNAS_DO_DOCUMENTO, *CAPITAL.values(), "acoes_por_classe",
    "titulos_conversiveis", "conhecido_em",
)  # fmt: skip
# o que as companhias escrevem no lugar do título quando não têm nenhum (comparado sem acento)
SEM_TITULO = ("", "-", "0", "na", "n/a", "n.a", "inexistente", "inexistentes", "nenhum")
SEM_TITULO_NO_COMECO = ("nao ha", "nao se aplica", "nao aplicavel")
SEPARADOR = "; "

GRUPO_DO_RECORTE = {"local": "Local", "posicao": "Posicao"}
GENERO = {
    "Quantidade_Feminino": "genero_feminino", "Quantidade_Masculino": "genero_masculino",
    "Quantidade_Nao_Binario": "genero_nao_binario", "Quantidade_Outros": "genero_outros",
    "Quantidade_Sem_Resposta": "genero_sem_resposta",
}  # fmt: skip
RACA = {
    "Quantidade_Amarelo": "raca_amarelo", "Quantidade_Branco": "raca_branco",
    "Quantidade_Preto": "raca_preto", "Quantidade_Pardo": "raca_pardo",
    "Quantidade_Indigena": "raca_indigena", "Quantidade_Outros": "raca_outros",
    "Quantidade_Sem_Resposta": "raca_sem_resposta",
}  # fmt: skip
IDADE = {
    "Quantidade_Ate30Anos": "idade_ate_30", "Quantidade_30a50Anos": "idade_30_a_50",
    "Quantidade_Acima50Anos": "idade_acima_50",
}  # fmt: skip
PCD = {
    "Quantidade_PCD": "pcd_sim", "Quantidade_Nao_PCD": "pcd_nao",
    "Quantidade_Sem_Resposta": "pcd_sem_resposta",
}  # fmt: skip
REGIAO = {
    "Quantidade_Norte": "regiao_norte", "Quantidade_Nordeste": "regiao_nordeste",
    "Quantidade_Centro_Oeste": "regiao_centro_oeste", "Quantidade_Sudeste": "regiao_sudeste",
    "Quantidade_Sul": "regiao_sul", "Quantidade_Exterior": "regiao_exterior",
}  # fmt: skip
# recorte → tabela do FRE → contagens; a região por posição só existe no recorte por posição
EMPREGADOS: dict[str, dict[str, dict[str, str]]] = {
    "local": {
        "empregado_local_declaracao_genero": GENERO,
        "empregado_local_declaracao_raca": RACA,
        "empregado_local_faixa_etaria": IDADE,
    },
    "posicao": {
        "empregado_posicao_declaracao_genero": GENERO,
        "empregado_posicao_declaracao_raca": RACA,
        "empregado_posicao_faixa_etaria": IDADE,
        "empregado_PCD": PCD,
        "empregado_posicao_local": REGIAO,
    },
}
COLUNAS_DOS_EMPREGADOS = (
    *conselhos.COLUNAS_DO_DOCUMENTO, "recorte", "grupo", *GENERO.values(), *RACA.values(),
    *IDADE.values(), *PCD.values(), *REGIAO.values(), "conhecido_em",
)  # fmt: skip


def sem_acento(texto: str) -> str:
    """Minúsculas e sem acento, para comparar o que cada companhia escreve do seu jeito."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def numero(serie: pd.Series) -> pd.Series:
    """Número do CSV da CVM (ponto decimal; vírgula em parte dos anos novos); vazio vira NaN."""
    return pd.to_numeric(
        serie.str.strip().str.replace(",", ".", regex=False), errors="coerce"
    ).astype(float)


def _tipo_de_capital(serie: pd.Series) -> pd.Series:
    """ "Capital Integralizado" → `integralizado` (os quatro tipos do FRE)."""
    return (
        serie.str.strip().map(sem_acento).str.removeprefix("capital ").replace("", None)
    )


def _acoes_por_classe(conteudo_do_zip: bytes) -> pd.Series:
    """`ID_Capital_Social` → "Preferencial Classe A=1000; Preferencial Classe B=2000"."""
    colunas = ["ID_Capital_Social", "Tipo_Classe_Acao_Preferencial", "Quantidade_Acoes"]
    classes = conselhos._tabela(conteudo_do_zip, "capital_social_classe_acao", colunas)
    if classes.empty:
        return pd.Series(dtype=str)
    classes = classes.assign(
        texto=classes["Tipo_Classe_Acao_Preferencial"].str.strip()
        + "="
        + numero(classes["Quantidade_Acoes"]).map(
            lambda q: f"{q:.0f}" if pd.notna(q) else ""
        )
    )
    return classes.groupby("ID_Capital_Social", sort=False)["texto"].agg(SEPARADOR.join)


def _e_titulo(texto: str) -> bool:
    simples = sem_acento(texto).strip(" .;-")
    return simples not in SEM_TITULO and not simples.startswith(SEM_TITULO_NO_COMECO)


def _titulos_conversiveis(conteudo_do_zip: bytes) -> pd.Series:
    """`ID_Capital_Social` → nomes dos títulos conversíveis em ação (sem as condições, texto livre)."""
    colunas = ["ID_Capital_Social", "Titulo_Conversivel_Acao"]
    titulos = conselhos._tabela(
        conteudo_do_zip, "capital_social_titulo_conversivel", colunas
    )
    titulos = titulos.assign(nome=titulos["Titulo_Conversivel_Acao"].str.strip())
    titulos = titulos[titulos["nome"].map(_e_titulo)]
    if titulos.empty:
        return pd.Series(dtype=str)
    return titulos.groupby("ID_Capital_Social", sort=False)["nome"].agg(SEPARADOR.join)


def ler_capital_social(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Cada linha de capital do FRE, com as classes preferenciais e os títulos conversíveis."""
    bruto = conselhos._tabela(
        conteudo_do_zip, "capital_social", [*conselhos.DOCUMENTO, *CAPITAL]
    )
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS_DO_CAPITAL))
    tabela = conselhos._documento(bruto, conselhos.entregas(conteudo_do_zip))
    identificador = bruto["ID_Capital_Social"].str.strip()
    tabela["id_capital_social"] = identificador
    tabela["tipo_capital"] = _tipo_de_capital(bruto["Tipo_Capital"])
    tabela["autorizado_em"] = pd.to_datetime(
        bruto["Data_Autorizacao_Aprovacao"].str.strip(), errors="coerce"
    )
    for velho in ("Valor_Capital", *list(CAPITAL)[4:]):
        tabela[CAPITAL[velho]] = numero(bruto[velho])
    # `str` mesmo quando nenhuma linha tem classe ou título (o `map` daria número vazio)
    tabela["acoes_por_classe"] = identificador.map(
        _acoes_por_classe(conteudo_do_zip)
    ).astype("str")
    tabela["titulos_conversiveis"] = identificador.map(
        _titulos_conversiveis(conteudo_do_zip)
    ).astype("str")
    tabela = tabela.drop_duplicates()
    return conselhos._so_com_data(tabela).reindex(columns=list(COLUNAS_DO_CAPITAL))


def _empregados_do_recorte(
    conteudo_do_zip: bytes, recorte: str, tabelas: dict[str, dict[str, str]]
) -> pd.DataFrame | None:
    """Uma linha por documento e grupo (a região ou a posição), juntando as tabelas do recorte."""
    grupo = GRUPO_DO_RECORTE[recorte]
    recebidos = conselhos.entregas(conteudo_do_zip)
    chaves = [*conselhos.COLUNAS_DO_DOCUMENTO, "grupo", "conhecido_em"]
    juntas: pd.DataFrame | None = None
    for nome, contagens in tabelas.items():
        bruto = conselhos._tabela(
            conteudo_do_zip, nome, [*conselhos.DOCUMENTO, grupo, *contagens]
        )
        if bruto.empty:
            continue
        parte = conselhos._documento(bruto, recebidos)
        parte["grupo"] = bruto[grupo].str.strip()
        for velho, novo in contagens.items():
            parte[novo] = numero(bruto[velho])
        parte = parte.drop_duplicates(subset=chaves)
        juntas = (
            parte if juntas is None else juntas.merge(parte, on=chaves, how="outer")
        )
    if juntas is None:
        return None
    return juntas.assign(recorte=recorte)


def ler_empregados(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Empregados por região e por posição (FRE de 2023 em diante); vazio nos anos anteriores."""
    partes = [
        parte
        for recorte, tabelas in EMPREGADOS.items()
        if (parte := _empregados_do_recorte(conteudo_do_zip, recorte, tabelas))
        is not None
    ]
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DOS_EMPREGADOS))
    juntas = pd.concat(partes, ignore_index=True)
    return conselhos._so_com_data(juntas).reindex(columns=list(COLUNAS_DOS_EMPREGADOS))


# --- pessoas: a base olha para empresas (ADR 0075) ------------------------------------------------
# Até o parecer jurídico, pessoa física só entra como número somado: sem nome, CPF, id, UF ou
# nacionalidade. O representante legal do acionista (quase sempre pessoa) nem é lido.
PF, PJ = "PF", "PJ"
CPF_NO_TEXTO = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
# o que só empresa, fundo ou ente público tem no nome (comparado sem acento); MEI, EI e EIRELI ficam
# de fora de propósito: a razão social deles é o nome da pessoa (ADR 0075, Emenda 1, regra 3.7)
EMPRESA_NO_NOME = re.compile(
    r"\b(s\.?\s?a|s/a|ltda|cia|companhia|participacoes|holding|fundo|fip|fia|fii|fidc|banco|"
    r"bank|inc|llc|ltd|plc|corp|corporation|gmbh|ag|nv|bv|spa|sarl|lp|trust|capital|"
    r"investimentos|gestora|asset|empresa|centrais|fundacao|instituto|associacao|cooperativa|"
    r"uniao|tesouro|governo|estado d[eo]|municipio|prefeitura|bndes|bndespar)\b"
)
SIM_OU_NAO = {"S": True, "N": False}


def parece_empresa(nome: str) -> bool:
    """O nome tem algo que só empresa, fundo ou ente público tem ("S.A.", "Ltda", "Fundo", "União")?"""
    return bool(EMPRESA_NO_NOME.search(sem_acento(nome)))


def _digitos(serie: pd.Series) -> pd.Series:
    return serie.str.replace(r"\D", "", regex=True)


def _cnpj_ou_nada(serie: pd.Series) -> pd.Series:
    """O CNPJ com 14 dígitos, ou vazio (sem documento, só zeros ou com cara de CPF)."""
    digitos = _digitos(serie)
    valido = (digitos.str.len() == TAMANHO_DO_CNPJ) & digitos.str.strip("0").ne("")
    return serie.str.strip().where(valido)


def _e_pessoa(tipo: pd.Series, documento: pd.Series, nome: pd.Series) -> pd.Series:
    """Pessoa física declarada, com documento de CPF, ou sem tipo e com nome que não é de empresa."""
    sem_tipo = tipo.str.strip().eq("")
    return (
        tipo.str.strip().eq(PF)
        | _digitos(documento).str.len().eq(TAMANHO_DO_CPF)
        | (sem_tipo & ~nome.map(parece_empresa))
    )


def _sim_ou_nao(serie: pd.Series) -> pd.Series:
    return serie.str.strip().str.upper().map(SIM_OU_NAO).astype("boolean")


def conferir_sem_cpf(tabela: pd.DataFrame, colunas: tuple[str, ...]) -> pd.DataFrame:
    """Rede de segurança: um CPF numa coluna de nome ou documento para a carga (nunca grava)."""
    for coluna in colunas:
        if tabela[coluna].dropna().astype(str).str.contains(CPF_NO_TEXTO).any():
            raise ValueError(
                f"CPF na coluna {coluna}: a linha de pessoa não foi somada"
            )
    return tabela


# --- acionistas (item 15.1 do FRE) ------------------------------------------------------------------
QUANTIDADES_DO_ACIONISTA = {
    "Quantidade_Acao_Ordinaria_Circulacao": "acoes_ordinarias",
    "Percentual_Acao_Ordinaria_Circulacao": "percentual_ordinarias",
    "Quantidade_Acao_Preferencial_Circulacao": "acoes_preferenciais",
    "Percentual_Acao_Preferencial_Circulacao": "percentual_preferenciais",
    "Quantidade_Total_Acoes_Circulacao": "acoes_total",
    "Percentual_Total_Acoes_Circulacao": "percentual_total",
}
ACIONISTA = (
    "ID_Acionista", "Acionista", "Tipo_Pessoa_Acionista", "CPF_CNPJ_Acionista",
    "ID_Acionista_Relacionado", "Tipo_Pessoa_Acionista_Relacionado",
    "CPF_CNPJ_Acionista_Relacionado", *QUANTIDADES_DO_ACIONISTA, "Nacionalidade", "Sigla_UF",
    "Residente_Exterior", "Data_Composicao_Capital_Social", "Data_Ultima_Alteracao",
    "Acionista_Controlador", "Participante_Acordo_Acionistas",
)  # fmt: skip
# as linhas que a CVM põe em todo grupo e que não são acionistas (comparadas sem acento)
LINHAS_SEM_ACIONISTA = {"outros": "outros", "acoes tesouraria": "tesouraria"}
COLUNAS_DOS_ACIONISTAS = (
    *conselhos.COLUNAS_DO_DOCUMENTO, "id_acionista", "tipo_acionista", "acionista",
    "cnpj_acionista", "id_acionista_relacionado", "tipo_relacionado",
    "cnpj_acionista_relacionado", *QUANTIDADES_DO_ACIONISTA.values(), "controlador",
    "acordo_de_acionistas", "residente_exterior", "nacionalidade", "uf", "composicao_em",
    "ultima_alteracao_em", "acionistas_no_grupo", "conhecido_em",
)  # fmt: skip
SOMADAS_DA_PF = ("acionistas_no_grupo", *QUANTIDADES_DO_ACIONISTA.values())
GRUPO_DA_PF = (
    *conselhos.COLUNAS_DO_DOCUMENTO, "id_acionista_relacionado", "tipo_relacionado",
    "cnpj_acionista_relacionado", "controlador", "acordo_de_acionistas", "conhecido_em",
)  # fmt: skip
PF_SOMADA = "pf_somada"
LETRA = {True: "S", False: "N"}


def _tipo_do_acionista(bruto: pd.DataFrame, pessoa: pd.Series) -> pd.Series:
    """`pj`, `pf_somada`, `outros` ou `tesouraria` (as duas linhas fixas de cada grupo da CVM)."""
    nome = bruto["Acionista"].str.strip().map(sem_acento)
    sem_tipo = bruto["Tipo_Pessoa_Acionista"].str.strip().eq("")
    fixa = nome.map(LINHAS_SEM_ACIONISTA).where(sem_tipo)
    tipo = pd.Series("pj", index=bruto.index).where(~pessoa, PF_SOMADA)
    return fixa.fillna(tipo)


def _relacionado(bruto: pd.DataFrame) -> pd.DataFrame:
    """De quem a linha é acionista (o grupo); quando o grupo é uma pessoa, só fica o tipo `PF`."""
    tipo = bruto["Tipo_Pessoa_Acionista_Relacionado"].str.strip()
    documento = bruto["CPF_CNPJ_Acionista_Relacionado"]
    pessoa = tipo.eq(PF) | _digitos(documento).str.len().eq(TAMANHO_DO_CPF)
    identificador = bruto["ID_Acionista_Relacionado"].str.strip().replace("", None)
    return pd.DataFrame(
        {
            "id_acionista_relacionado": identificador.where(~pessoa),
            "tipo_relacionado": tipo.where(~pessoa, PF).replace("", None),
            "cnpj_acionista_relacionado": _cnpj_ou_nada(documento).where(~pessoa),
        },
        index=bruto.index,
    )


def _somar_pessoas(tabela: pd.DataFrame) -> pd.DataFrame:
    """As pessoas físicas de cada grupo viram uma linha só: quantas são e quanto têm somado."""
    pessoas = tabela[tabela["tipo_acionista"] == PF_SOMADA]
    if pessoas.empty:
        return tabela
    somadas = (
        pessoas.groupby(list(GRUPO_DA_PF), dropna=False, sort=False)[
            list(SOMADAS_DA_PF)
        ]
        .sum(min_count=1)
        .reset_index()
    )
    # id estável e sem nada da pessoa: o grupo e o que a companhia declarou
    somadas["id_acionista"] = (
        "pf:" + somadas["id_acionista_relacionado"].fillna("raiz")
        + ":" + somadas["controlador"].map(LETRA).fillna("-")
        + ":" + somadas["acordo_de_acionistas"].map(LETRA).fillna("-")
    )  # fmt: skip
    somadas["tipo_acionista"] = PF_SOMADA
    empresas = tabela[tabela["tipo_acionista"] != PF_SOMADA]
    return pd.concat([empresas, somadas], ignore_index=True)


def ler_acionistas(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os acionistas de cada FRE com 5% ou mais, e os acionistas deles até a pessoa física; as
    pessoas físicas entram somadas por grupo, sem nome nem documento (ADR 0075)."""
    bruto = conselhos._tabela(
        conteudo_do_zip, "posicao_acionaria", [*conselhos.DOCUMENTO, *ACIONISTA]
    )
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS_DOS_ACIONISTAS))
    pessoa = _e_pessoa(
        bruto["Tipo_Pessoa_Acionista"], bruto["CPF_CNPJ_Acionista"], bruto["Acionista"]
    )
    tabela = conselhos._documento(bruto, conselhos.entregas(conteudo_do_zip))
    tabela["id_acionista"] = bruto["ID_Acionista"].str.strip()
    tabela["tipo_acionista"] = _tipo_do_acionista(bruto, pessoa)
    empresa = tabela["tipo_acionista"].eq("pj")
    tabela["acionista"] = bruto["Acionista"].str.strip().where(empresa)
    tabela["cnpj_acionista"] = _cnpj_ou_nada(bruto["CPF_CNPJ_Acionista"]).where(empresa)
    tabela = tabela.join(_relacionado(bruto))
    for velho, novo in QUANTIDADES_DO_ACIONISTA.items():
        tabela[novo] = numero(bruto[velho])
    tabela["controlador"] = _sim_ou_nao(bruto["Acionista_Controlador"])
    tabela["acordo_de_acionistas"] = _sim_ou_nao(
        bruto["Participante_Acordo_Acionistas"]
    )
    tabela["residente_exterior"] = _sim_ou_nao(bruto["Residente_Exterior"]).where(
        empresa
    )
    for velho, novo in (("Nacionalidade", "nacionalidade"), ("Sigla_UF", "uf")):
        tabela[novo] = bruto[velho].str.strip().replace("", None).where(empresa)
    for velho, novo in (
        ("Data_Composicao_Capital_Social", "composicao_em"),
        ("Data_Ultima_Alteracao", "ultima_alteracao_em"),
    ):
        tabela[novo] = pd.to_datetime(bruto[velho].str.strip(), errors="coerce")
    tabela["acionistas_no_grupo"] = 1
    tabela = _somar_pessoas(conselhos._so_com_data(tabela.drop_duplicates()))
    tabela = tabela.reindex(columns=list(COLUNAS_DOS_ACIONISTAS))
    return conferir_sem_cpf(
        tabela, ("acionista", "cnpj_acionista", "cnpj_acionista_relacionado")
    )


# --- transações com partes relacionadas (item 11.2 do FRE) -------------------------------------------
PARTE = (
    "Parte_Relacionada", "Tipo_Pessoa", "Documento_Parte_Relacionada", "Relacao_Emissor",
    "Data_Transacao", "Montante_Envolvido", "Saldo_Existente",
    "Montante_Interesse_Parte_Relacionada", "Emprestimo_Divida", "Taxa_Juros",
    "Posicao_Contratual_Emissor",
)  # fmt: skip
MONTANTES = {
    "Montante_Envolvido": "montante_envolvido",
    "Saldo_Existente": "saldo_existente",
    "Montante_Interesse_Parte_Relacionada": "montante_de_interesse",
}
# a relação com a companhia é texto livre; fica só a categoria, procurada nesta ordem (a primeira
# que casa vale: "ambas são controladas pela X" é controle comum, não controlada)
RELACOES = (
    ("controle_comum", r"controle comum|mesmo controlador|controladas? (pel[ao]|por)|ambas"),
    ("controle_conjunto", r"joint venture|controle (compartilhado|conjunto)|controlada em conjunto"),
    ("controladora", r"controlador"),
    ("controlada", r"controlada|subsidiaria"),
    ("coligada", r"coligada"),
    ("administracao", r"administrador|diretor|conselheir|pessoal.chave|administracao"),
    ("familiar", r"conjuge|parente|familiar|\bfilh[oa]s?\b|\birma[os]?\b|\bpai\b|\bmae\b"),
    ("acionista", r"acionista|socio|cotista"),
)  # fmt: skip
POSICOES = ("credor", "devedor", "outra")
COLUNAS_DAS_PARTES = (
    *conselhos.COLUNAS_DO_DOCUMENTO, "linha", "tipo_pessoa", "contraparte", "cnpj_contraparte",
    "relacao", "data_transacao", *MONTANTES.values(), "emprestimo", "taxa_de_juros",
    "posicao_contratual", "transacoes", "conhecido_em",
)  # fmt: skip
GRUPO_DAS_PESSOAS = (
    *conselhos.COLUNAS_DO_DOCUMENTO, "tipo_pessoa", "relacao", "conhecido_em",
)  # fmt: skip
SEM_TIPO = "nao_informado"


def categoria_da_relacao(texto: str) -> str:
    """ "Sociedade sob controle comum" → `controle_comum`; vazio → `nao_informada`; o resto, `outra`."""
    simples = sem_acento(texto).strip()
    if not simples:
        return "nao_informada"
    return next(
        (nome for nome, padrao in RELACOES if re.search(padrao, simples)), "outra"
    )


def _taxa(serie: pd.Series) -> pd.Series:
    """A taxa só quando é um número ("3,5%"); "CDI + 1%", "N/A" e "Meta atuarial" ficam vazios."""
    limpa = serie.str.strip().str.removesuffix("%").str.strip()
    return numero(limpa.where(limpa.str.fullmatch(r"-?\d+([.,]\d+)?"), ""))


def _soma(serie: pd.Series) -> float:
    return serie.sum(min_count=1)


def _somar_partes_pessoas(tabela: pd.DataFrame) -> pd.DataFrame:
    """As transações com pessoas viram uma linha por relação: quantas e quanto somam."""
    pessoas = tabela[tabela["contraparte"].isna()]
    if pessoas.empty:
        return tabela
    somas = {montante: (montante, _soma) for montante in MONTANTES.values()}
    somadas = (
        pessoas.groupby(list(GRUPO_DAS_PESSOAS), dropna=False, sort=False)
        .agg(transacoes=("transacoes", "sum"), **somas)
        .reset_index()
    )
    somadas["linha"] = "pf:" + somadas["tipo_pessoa"] + ":" + somadas["relacao"]
    empresas = tabela[tabela["contraparte"].notna()]
    return pd.concat([empresas, somadas], ignore_index=True)


def ler_partes_relacionadas(conteudo_do_zip: bytes) -> pd.DataFrame:
    """As transações com partes relacionadas de cada FRE: a contraparte só quando é empresa; com
    pessoa (ou sem como saber), só a soma por relação, sem nome nem documento (ADR 0075)."""
    bruto = conselhos._tabela(
        conteudo_do_zip, "transacao_parte_relacionada", [*conselhos.DOCUMENTO, *PARTE]
    )
    if bruto.empty:
        return pd.DataFrame(columns=list(COLUNAS_DAS_PARTES))
    tipo = bruto["Tipo_Pessoa"].str.strip()
    nome = bruto["Parte_Relacionada"].str.strip()
    pessoa = _e_pessoa(tipo, bruto["Documento_Parte_Relacionada"], nome)
    tabela = conselhos._documento(bruto, conselhos.entregas(conteudo_do_zip))
    # a CVM não dá id à transação: a posição dela no documento (a mesma em toda baixada)
    tabela["linha"] = (tabela.groupby("id_documento").cumcount() + 1).astype(str)
    tabela["tipo_pessoa"] = tipo.replace("", SEM_TIPO)
    tabela["contraparte"] = nome.where(~pessoa)
    tabela["cnpj_contraparte"] = _cnpj_ou_nada(
        bruto["Documento_Parte_Relacionada"]
    ).where(~pessoa)
    tabela["relacao"] = bruto["Relacao_Emissor"].map(categoria_da_relacao)
    tabela["data_transacao"] = pd.to_datetime(
        bruto["Data_Transacao"].str.strip(), errors="coerce"
    )
    for velho, novo in MONTANTES.items():
        tabela[novo] = numero(bruto[velho])
    tabela["emprestimo"] = _sim_ou_nao(bruto["Emprestimo_Divida"])
    tabela["taxa_de_juros"] = _taxa(bruto["Taxa_Juros"])
    posicao = bruto["Posicao_Contratual_Emissor"].str.strip().map(sem_acento)
    tabela["posicao_contratual"] = posicao.where(posicao.isin(POSICOES))
    tabela["transacoes"] = 1
    tabela = _somar_partes_pessoas(conselhos._so_com_data(tabela))
    tabela = tabela.reindex(columns=list(COLUNAS_DAS_PARTES))
    return conferir_sem_cpf(tabela, ("contraparte", "cnpj_contraparte"))


def conhecidas_ate(tabela: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """O que já tinha sido entregue à CVM até o `corte` (inclusive): a base vista naquele dia."""
    return tabela[tabela["conhecido_em"] <= corte].reset_index(drop=True)
