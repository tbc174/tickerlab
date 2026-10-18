"""Área e produção de café por município: a PAM do IBGE e a cobertura "Café" do MapBiomas, lado a lado.

Duas fontes que medem coisas diferentes, e por isso vão em colunas separadas (nunca somadas):

- **PAM** (Produção Agrícola Municipal, IBGE; tabela 1613 do SIDRA): área colhida (ha) e quantidade
  produzida (t) por município e ano, declaradas pelo levantamento do IBGE e abertas por tipo
  (arábica e canephora/conilon). O ano t sai em setembro ou outubro de t+1.
- **MapBiomas** (Coleção 11, classe 46 "Café"): hectares de lavoura de café vistos por satélite, por
  município, bioma e ano desde 1985 (a soma dos biomas é o município). Mede a área plantada visível,
  não a colhida, e não separa arábica de conilon.

A tabela `area_cafe_municipio` (dicionário da base) tem uma linha por município e ano com as duas
fontes; onde uma delas não tem o número, a coluna fica vazia, nunca zero. Nada aqui importa o
Streamlit: `src/commodities/cafe/mapa.py` monta os dados do mapa a partir destas tabelas.
"""

import io
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from src.ibge_sidra import PAM_CAFE_ARABICA, PAM_CAFE_CANEPHORA, ler_resposta

NIVEL_MUNICIPIO = "6"
VARIAVEL_AREA_COLHIDA = 216
VARIAVEL_QUANTIDADE_PRODUZIDA = 214
CLASSE_CAFE_DO_MAPBIOMAS = 46
ABA_DA_COBERTURA = "COVERAGE_11"
COLUNA_DO_MUNICIPIO_NO_MAPBIOMAS = "geocode"
COLUNA_DA_CLASSE_NO_MAPBIOMAS = "class"
PREFIXO_DO_ANO = "y"  # as colunas de valor da planilha: y1985 … y2025
# a PAM do ano t sai em setembro ou outubro de t+1: folga conservadora para "como era na data"
MES_E_DIA_EM_QUE_A_PAM_SAI = (10, 31)

COLUNAS_DA_PAM = (
    "codigo",
    "nome",
    "uf",
    "ano",
    "area_arabica_ha",
    "area_conilon_ha",
    "area_total_ha",
    "producao_arabica_t",
    "producao_conilon_t",
    "producao_total_t",
)
COLUNAS_DO_MAPBIOMAS = ("codigo", "ano", "area_mapbiomas_ha")
COLUNAS = (
    *COLUNAS_DA_PAM[:4],
    "referencia",
    *COLUNAS_DA_PAM[4:],
    "area_mapbiomas_ha",
    "disponivel_em",
)
_COLUNA_POR_VARIAVEL_E_TIPO = {
    (VARIAVEL_AREA_COLHIDA, PAM_CAFE_ARABICA): "area_arabica_ha",
    (VARIAVEL_AREA_COLHIDA, PAM_CAFE_CANEPHORA): "area_conilon_ha",
    (VARIAVEL_QUANTIDADE_PRODUZIDA, PAM_CAFE_ARABICA): "producao_arabica_t",
    (VARIAVEL_QUANTIDADE_PRODUZIDA, PAM_CAFE_CANEPHORA): "producao_conilon_t",
}


def _nome_e_uf(nome_do_local: str) -> tuple[str, str]:
    """ "Patos de Minas (MG)" → ("Patos de Minas", "MG")."""
    nome, _, uf = nome_do_local.rpartition(" (")
    return nome, uf.rstrip(")")


def _soma_dos_dois_tipos(tabela: pd.DataFrame, arabica: str, conilon: str) -> pd.Series:
    """Total = arábica + conilon só quando os dois têm número (um tipo em sigilo ou ausente deixa o
    total vazio: não vale um total de um tipo só)."""
    return tabela[arabica] + tabela[conilon]


def ler_pam(linhas: Sequence[Mapping[str, str]]) -> pd.DataFrame:
    """A resposta do SIDRA (tabela 1613: área colhida e quantidade produzida, café arábica e
    canephora, por município) numa linha por município e ano, com as colunas `COLUNAS_DA_PAM`."""
    por_municipio_e_ano: dict[tuple[str, int], dict[str, object]] = {}
    for valor in ler_resposta(linhas):
        tipo = valor.categorias[0] if valor.categorias else None
        coluna = _COLUNA_POR_VARIAVEL_E_TIPO.get((valor.variavel, tipo))
        if valor.nivel != NIVEL_MUNICIPIO or coluna is None:
            continue
        nome, uf = _nome_e_uf(valor.nome_do_local)
        ano = int(valor.periodo)
        linha = por_municipio_e_ano.setdefault(
            (valor.local, ano),
            {"codigo": valor.local, "nome": nome, "uf": uf, "ano": ano},
        )
        linha[coluna] = valor.valor
    tabela = pd.DataFrame(list(por_municipio_e_ano.values())).reindex(
        columns=list(COLUNAS_DA_PAM)
    )
    tabela["area_total_ha"] = _soma_dos_dois_tipos(
        tabela, "area_arabica_ha", "area_conilon_ha"
    )
    tabela["producao_total_t"] = _soma_dos_dois_tipos(
        tabela, "producao_arabica_t", "producao_conilon_t"
    )
    return tabela.sort_values(["codigo", "ano"]).reset_index(drop=True)


def _planilha(arquivo: Path | bytes) -> io.BytesIO:
    """A .xlsx em memória: o MapBiomas distribui a planilha dentro de um zip (a própria .xlsx também é
    um zip, mas sem outra .xlsx dentro)."""
    dados = arquivo if isinstance(arquivo, bytes) else Path(arquivo).read_bytes()
    with zipfile.ZipFile(io.BytesIO(dados)) as pacote:
        planilhas = [m for m in pacote.namelist() if m.lower().endswith(".xlsx")]
        if planilhas:
            dados = pacote.read(planilhas[0])
    return io.BytesIO(dados)


def ler_mapbiomas(
    arquivo: Path | bytes, classe: int = CLASSE_CAFE_DO_MAPBIOMAS
) -> pd.DataFrame:
    """A planilha de cobertura por município do MapBiomas (aba `COVERAGE_11`: uma linha por bioma ×
    município × classe, um ano por coluna) → hectares da classe por município e ano, somando os
    biomas. Município sem linha da classe fica fora (não é zero: pode não ter sido mapeado)."""
    cobertura = pd.read_excel(
        _planilha(arquivo),
        sheet_name=ABA_DA_COBERTURA,
        dtype={COLUNA_DO_MUNICIPIO_NO_MAPBIOMAS: str},
    )
    da_classe = cobertura[cobertura[COLUNA_DA_CLASSE_NO_MAPBIOMAS] == classe]
    colunas_de_ano = [
        c
        for c in da_classe.columns
        if str(c).startswith(PREFIXO_DO_ANO) and str(c)[len(PREFIXO_DO_ANO) :].isdigit()
    ]
    longa = da_classe.melt(
        id_vars=[COLUNA_DO_MUNICIPIO_NO_MAPBIOMAS],
        value_vars=colunas_de_ano,
        var_name="ano",
        value_name="area_mapbiomas_ha",
    )
    longa["ano"] = longa["ano"].str.removeprefix(PREFIXO_DO_ANO).astype(int)
    soma = longa.groupby([COLUNA_DO_MUNICIPIO_NO_MAPBIOMAS, "ano"], as_index=False)[
        "area_mapbiomas_ha"
    ].sum(min_count=1)
    return soma.rename(columns={COLUNA_DO_MUNICIPIO_NO_MAPBIOMAS: "codigo"})[
        list(COLUNAS_DO_MAPBIOMAS)
    ]


def juntar(pam: pd.DataFrame, mapbiomas: pd.DataFrame) -> pd.DataFrame:
    """As duas fontes lado a lado, uma linha por município e ano (união: município que só uma fonte
    tem fica com a coluna da outra vazia). `referencia` é o fim do ano e `disponivel_em` segue a
    PAM, a mais lenta das duas."""
    tabela = pam.merge(mapbiomas, on=["codigo", "ano"], how="outer")
    tabela["ano"] = tabela["ano"].astype(int)
    tabela["referencia"] = pd.to_datetime(tabela["ano"].astype(str) + "-12-31")
    mes, dia = MES_E_DIA_EM_QUE_A_PAM_SAI
    tabela["disponivel_em"] = pd.to_datetime(
        (tabela["ano"] + 1).astype(str) + f"-{mes:02d}-{dia:02d}"
    )
    return (
        tabela.reindex(columns=list(COLUNAS))
        .sort_values(["codigo", "ano"])
        .reset_index(drop=True)
    )
