"""Acessos de telecomunicações da Anatel (série 4, PR 5): banda larga fixa, telefonia móvel e TV por
assinatura, por prestadora (CNPJ) e mês, somados por UF (sem o município).

A Anatel publica um CSV "_Colunas" por período, uma linha por município e um mês por coluna (150 MB por
ano na banda larga). A base soma os municípios de cada UF e põe o mês na linha; as outras colunas ficam
como a fonte, com nomes em português simples. A velocidade exata (`Velocidade`) sai: a faixa fica.

Na telefonia móvel de 2005 a 2018 a Anatel publica **duas visões dos mesmos acessos** (por modalidade
de cobrança e por tecnologia): a coluna `recorte` diz qual é, e somar as duas conta tudo duas vezes. A
chave da prestadora é o CNPJ (14 dígitos), o mesmo da B13 (todos têm 14 dígitos: nenhum CPF).
"""

import io
import re

import pandas as pd

from base.setoriais import prazos
from base.setoriais.comum import sem_espacos

FONTE = "anatel-acessos"
LINHAS_POR_PEDACO = 200_000
MES = re.compile(r"^\d{4}-\d{2}$")
SERVICOS = {
    "Banda_Larga_Fixa": "banda_larga_fixa",
    "Telefonia_Movel": "telefonia_movel",
    "TV_Assinatura": "tv_por_assinatura",
}
RECORTES = {"_Modalidade_": "modalidade", "_Tecnologia_": "tecnologia"}
SEM_RECORTE = "completo"
NOMES = {
    "CNPJ": "cnpj", "Empresa": "empresa", "Grupo Econômico": "grupo_economico",
    "Porte da Prestadora": "porte_da_prestadora", "UF": "uf", "Região PGO": "regiao_pgo",
    "Código Nacional": "codigo_nacional", "Modalidade de Cobrança": "modalidade_de_cobranca",
    "Tecnologia": "tecnologia", "Tecnologia Geração": "geracao", "Tipo de Pessoa": "tipo_de_pessoa",
    "Tipo de Produto": "tipo_de_produto", "Faixa de Velocidade": "faixa_de_velocidade",
    "Meio de Acesso": "meio_de_acesso", "Tipo Acesso TV": "tipo_de_acesso_tv",
}  # fmt: skip
FORA = ("Município", "Código IBGE Município", "Velocidade")  # o que a soma por UF tira
TEXTOS = tuple(NOMES.values())
COLUNAS = (
    "competencia",
    "servico",
    "recorte",
    *TEXTOS,
    "acessos",
    "arquivo",
    "disponivel_em",
)
CARIMBOS = (
    "arquivo",
    "empresa",
    "grupo_economico",
    "porte_da_prestadora",
)  # nomes que mudam
CHAVE = ["competencia", "servico", "recorte", *[c for c in TEXTOS if c not in CARIMBOS]]


def servico_e_recorte(arquivo: str) -> tuple[str, str]:
    """O serviço e o recorte pelo nome do CSV ("Acessos_Telefonia_Movel_2009..._Modalidade_Colunas")."""
    servico = next((s for nome, s in SERVICOS.items() if nome in arquivo), None)
    if servico is None:
        raise ValueError(f"CSV da Anatel de serviço desconhecido: {arquivo}")
    recorte = next((r for nome, r in RECORTES.items() if nome in arquivo), SEM_RECORTE)
    return servico, recorte


def _somar_pedaco(pedaco: pd.DataFrame) -> pd.DataFrame:
    meses = [c for c in pedaco.columns if MES.match(c)]
    dimensoes = [c for c in pedaco.columns if c not in meses and c not in FORA]
    numeros = pedaco[meses].apply(
        lambda coluna: pd.to_numeric(
            coluna.str.replace(",", ".", regex=False), errors="coerce"
        )
    )
    return (
        pd.concat([pedaco[dimensoes], numeros], axis=1)
        .groupby(dimensoes, sort=False)
        .sum(min_count=1)
    )


def ler(conteudo: bytes, arquivo: str) -> pd.DataFrame:
    """Um CSV "_Colunas" da Anatel, somado por UF, um mês por linha, com `disponivel_em`."""
    servico, recorte = servico_e_recorte(arquivo)
    pedacos = pd.read_csv(
        io.BytesIO(conteudo), sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False,
        chunksize=LINHAS_POR_PEDACO,
    )  # fmt: skip
    somas = [_somar_pedaco(pedaco) for pedaco in pedacos]
    largo = pd.concat(somas).groupby(
        level=list(range(somas[0].index.nlevels)), sort=False
    )
    longo = (
        largo.sum(min_count=1)
        .rename_axis(columns="mes")
        .stack(future_stack=True)
        .dropna()
        .rename("acessos")
        .reset_index()
        .rename(columns=NOMES)
    )
    tabela = pd.DataFrame(
        {c: sem_espacos(longo[c], vazio_vira_none=True) for c in TEXTOS if c in longo}
    )
    tabela["competencia"] = pd.to_datetime(longo["mes"] + "-01") + pd.offsets.MonthEnd(
        0
    )
    tabela["servico"], tabela["recorte"], tabela["arquivo"] = servico, recorte, arquivo
    tabela["acessos"] = longo["acessos"].astype(float)
    tabela["disponivel_em"] = prazos.disponivel_mensal(tabela["competencia"])
    return tabela.reindex(columns=list(COLUNAS))
