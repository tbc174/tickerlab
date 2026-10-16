"""Mercado das distribuidoras de energia (SAMP da ANEEL; série 4, PR 5): por distribuidora, mês, classe
de consumo, modalidade e posto tarifário, o número de consumidores, a energia (kWh) e a receita (R$),
no formato da fonte (colunas com nomes em português simples).

Um Parquet por ano desde 2003, todo regerado a cada mês (`gerado_em`, a data de geração da ANEEL). O
arquivista guarda o SAMP já sem as colunas do agente acessante (CPF e nome de consumidor livre); sem
elas, 1% a 6% das linhas de um ano repetem a chave (uma por acessante, medido em 2003, 2015, 2024 e
2026). A base soma essas linhas (`linhas_somadas` diz quantas); nos detalhes em "%" (descontos), soma
não faz sentido e fica a média. A chave da distribuidora é o CNPJ (14 dígitos), o mesmo da B13.
"""

import io

import pandas as pd

from base.controladas import cnpj14
from base.setoriais import prazos
from base.setoriais.comum import sem_espacos

FONTE = "aneel-samp"
NOMES = {
    "DatGeracaoConjuntoDados": "gerado_em", "NumCNPJAgenteDistribuidora": "cnpj",
    "SigAgenteDistribuidora": "sigla", "NomAgenteDistribuidora": "distribuidora",
    "NomTipoMercado": "tipo_de_mercado", "DscModalidadeTarifaria": "modalidade_tarifaria",
    "DscSubGrupoTarifario": "subgrupo_tarifario", "DscClasseConsumoMercado": "classe_de_consumo",
    "DscSubClasseConsumidor": "subclasse_de_consumo", "DscDetalheConsumidor": "detalhe_do_consumidor",
    "IdeNucleoCeg": "nucleo_ceg", "DscPostoTarifario": "posto_tarifario",
    "DscOpcaoEnergia": "opcao_de_energia", "DscDetalheMercado": "detalhe_do_mercado",
    "DatCompetencia": "competencia", "VlrMercado": "valor",
}  # fmt: skip
TEXTOS = (
    "sigla", "distribuidora", "tipo_de_mercado", "modalidade_tarifaria", "subgrupo_tarifario",
    "classe_de_consumo", "subclasse_de_consumo", "detalhe_do_consumidor", "nucleo_ceg",
    "posto_tarifario", "opcao_de_energia", "detalhe_do_mercado",
)  # fmt: skip
COLUNAS = (
    "competencia", "cnpj", *TEXTOS, "valor", "linhas_somadas", "gerado_em", "disponivel_em",
)  # fmt: skip
PERCENTUAL = "%"  # o detalhe em percentual ("Desconto Demanda %") vira média, não soma
CHAVE = [
    "competencia",
    "cnpj",
    *[c for c in TEXTOS if c not in ("sigla", "distribuidora")],
]
CARIMBOS = ("gerado_em", "sigla", "distribuidora")  # mudam sem mudar o número


def _nucleo(coluna: pd.Series) -> pd.Series:
    """O núcleo do CEG como texto inteiro ("0", não "0.0")."""
    return pd.to_numeric(coluna, errors="coerce").astype("Int64").astype("string")


def _somar_acessantes(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por chave: a soma das linhas de cada acessante (média nos percentuais)."""
    grupos = tabela.groupby([*CHAVE, *CARIMBOS], dropna=False, sort=False)["valor"]
    somadas = pd.DataFrame(
        {
            "soma": grupos.sum(min_count=1),
            "media": grupos.mean(),
            "linhas_somadas": grupos.size(),
        }
    ).reset_index()
    percentual = (
        somadas["detalhe_do_mercado"].fillna("").str.contains(PERCENTUAL, regex=False)
    )
    somadas["valor"] = somadas["soma"].where(~percentual, somadas["media"])
    return somadas.drop(columns=["soma", "media"])


def ler(conteudo_do_parquet: bytes) -> pd.DataFrame:
    """Um ano do SAMP com a competência (último dia do mês) e `disponivel_em`."""
    tabela = pd.read_parquet(io.BytesIO(conteudo_do_parquet)).rename(columns=NOMES)
    tabela["nucleo_ceg"] = _nucleo(tabela["nucleo_ceg"])
    for coluna in TEXTOS:
        tabela[coluna] = sem_espacos(tabela[coluna], vazio_vira_none=True)
    tabela["cnpj"] = sem_espacos(tabela["cnpj"].map(cnpj14))
    tabela["competencia"] = pd.to_datetime(tabela["competencia"]) + pd.offsets.MonthEnd(
        0
    )
    tabela["gerado_em"] = pd.to_datetime(tabela["gerado_em"])
    tabela["valor"] = pd.to_numeric(tabela["valor"], errors="coerce").astype(float)
    tabela = _somar_acessantes(tabela)
    tabela["disponivel_em"] = prazos.disponivel_mensal(tabela["competencia"])
    return tabela.reindex(columns=list(COLUNAS))
