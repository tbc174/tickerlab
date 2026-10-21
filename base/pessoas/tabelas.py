"""Tabelas do esquema `pessoas`: a pessoa (com nome, só no acervo restrito), os acessos e as oposições."""

import pandas as pd

from base.pessoas import chave as chaves

NIVEL_COM_NOME = (
    2  # o nível 1 é só o id; o 2 guarda nome e CPF mascarado (ADR 0075, Emenda 1)
)
COLUNAS_DE_PESSOAS = (
    "id_pessoa", "nivel", "fonte", "nome", "cpf_mascarado", "cnpj_basico", "qualificacao",
    "data_entrada",
)  # fmt: skip
COLUNAS_DE_ACESSOS = ("id_pessoa", "quando", "quem", "finalidade")
COLUNAS_DE_OPOSICOES = ("id_pessoa", "pedido_em", "prazo_ate", "atendida_em")
SEM_CPF = "00000000000"  # o sócio estrangeiro vem sem CPF
FORMATO_PERMITIDO = rf"\*{{3}}\d{{6}}\*{{2}}|{SEM_CPF}"


def ids_das_linhas(brutas: pd.DataFrame, chave: bytes) -> pd.Series:
    """O `id_pessoa` de cada linha do quadro `pessoas_brutas` (nome e CPF mascarado)."""

    def uma(linha: pd.Series) -> str:
        primeiro, ultimo = chaves.primeiro_e_ultimo(linha["nome_socio"])
        return chaves.id_pessoa(linha["cpf_mascarado"], primeiro, ultimo, chave)

    return brutas.apply(uma, axis=1).astype(str)


def montar_pessoas(brutas: pd.DataFrame, fonte: str, chave: bytes) -> pd.DataFrame:
    """A tabela `pessoas` (nível 2) do quadro `pessoas_brutas`. CPF inteiro quebra (só o mascarado entra)."""
    if brutas.empty:
        return pd.DataFrame(columns=list(COLUNAS_DE_PESSOAS))
    if not brutas["cpf_mascarado"].str.fullmatch(FORMATO_PERMITIDO).all():
        raise ValueError("CPF inteiro no quadro de pessoas: só o mascarado entra")
    saida = pd.DataFrame(
        {
            "id_pessoa": ids_das_linhas(brutas, chave),
            "nivel": NIVEL_COM_NOME,
            "fonte": fonte,
            "nome": brutas["nome_socio"].str.strip(),
            "cpf_mascarado": brutas["cpf_mascarado"],
            "cnpj_basico": brutas["cnpj_basico"],
            "qualificacao": brutas["qualificacao"],
            "data_entrada": brutas["data_entrada"],
        }
    )
    return saida.drop_duplicates().reset_index(drop=True)


def sem_opostos(pessoas: pd.DataFrame, ids_opostos: set[str]) -> pd.DataFrame:
    """A tabela sem quem se opôs (o remonte regrava o resto: `base.parquet.regravar_por_lapide`)."""
    return pessoas[~pessoas["id_pessoa"].isin(ids_opostos)].reset_index(drop=True)


def acessos_vazios() -> pd.DataFrame:
    """`pessoas_acessos`: uma linha por consulta de nome (a API cria; nasce vazia)."""
    return pd.DataFrame(columns=list(COLUNAS_DE_ACESSOS))


def oposicoes_vazias() -> pd.DataFrame:
    """`pessoas_oposicoes`: pedidos de titulares, com o prazo de 15 dias contado."""
    return pd.DataFrame(columns=list(COLUNAS_DE_OPOSICOES))
