"""Capital social e empregados pelo FRE da CVM (série T, T3: o FRE completo para a governança da ficha).

O FRE tem 61 tipos de CSV; os de conselho, comitês e remuneração já são lidos em `base/conselhos.py`.
Aqui entram os que faltavam para a governança:

- `fre_capital_social` (2010 em diante): cada linha de capital (integralizado, subscrito, emitido,
  autorizado) com as quantidades de ações, as classes preferenciais e os títulos conversíveis;
- `fre_empregados` (só do FRE de 2023 em diante, quando a CVM passou a pedir): os empregados por
  região e por posição (liderança ou não), com gênero, raça, faixa etária e PCD, só contagens.

"Como era na data": cada linha leva o `conhecido_em`, a entrega da versão à CVM (`DT_RECEB` do arquivo
principal, pelo `ID_Documento`), como as outras `fre_*`. Texto livre (condições de conversão, prazo de
integralização) não entra.
"""

import unicodedata

import pandas as pd

from base import conselhos

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


def conhecidas_ate(tabela: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """O que já tinha sido entregue à CVM até o `corte` (inclusive): a base vista naquele dia."""
    return tabela[tabela["conhecido_em"] <= corte].reset_index(drop=True)
