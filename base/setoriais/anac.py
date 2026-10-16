"""Estatístico do transporte aéreo da ANAC (série 4, PR 4): por empresa, mês e par de aeroportos,
passageiros, carga, assentos, ASK, RPK, combustível... no formato da fonte (colunas em minúsculas).

O arquivo começa com a linha "Atualizado em: AAAA-MM-DD" (guardada em `atualizado_em`) e os campos vêm
entre aspas. A chave da empresa é a sigla (`empresa_sigla`), a mesma da B13.
"""

import csv
import io
import re

import pandas as pd

from base.setoriais import prazos

FONTE = "anac-estatistico"
ATUALIZADO = re.compile(r"Atualizado em:\s*(\d{4}-\d{2}-\d{2})")
TEXTOS = (
    "empresa_sigla", "empresa_nome", "empresa_nacionalidade",
    "aeroporto_de_origem_sigla", "aeroporto_de_origem_nome", "aeroporto_de_origem_uf",
    "aeroporto_de_origem_regiao", "aeroporto_de_origem_pais", "aeroporto_de_origem_continente",
    "aeroporto_de_destino_sigla", "aeroporto_de_destino_nome", "aeroporto_de_destino_uf",
    "aeroporto_de_destino_regiao", "aeroporto_de_destino_pais", "aeroporto_de_destino_continente",
    "natureza", "grupo_de_voo",
)  # fmt: skip
NUMEROS = (
    "passageiros_pagos", "passageiros_gratis", "carga_paga_kg", "carga_gratis_kg", "correio_kg",
    "ask", "rpk", "atk", "rtk", "combustivel_litros", "distancia_voada_km", "decolagens",
    "carga_paga_km", "carga_gratis_km", "correio_km", "assentos", "payload", "horas_voadas",
    "bagagem_kg",
)  # fmt: skip
COLUNAS = ("competencia", *TEXTOS, *NUMEROS, "atualizado_em", "disponivel_em")


def atualizado_em(conteudo: bytes) -> pd.Timestamp | None:
    """A data da linha "Atualizado em" do começo do arquivo (None se não houver)."""
    primeira = conteudo[:200].decode("utf-8-sig", errors="replace").splitlines()[0]
    achado = ATUALIZADO.search(primeira)
    return pd.Timestamp(achado.group(1)) if achado else None


def ler(conteudo: bytes) -> pd.DataFrame:
    """O arquivo inteiro, com a competência (último dia do mês) e `disponivel_em`."""
    texto = io.StringIO(conteudo.decode("utf-8-sig", errors="replace"))
    texto.readline()  # "Atualizado em: ..."
    bruto = pd.read_csv(
        texto, sep=";", quotechar='"', quoting=csv.QUOTE_MINIMAL, dtype=str,
        keep_default_na=False,
    )  # fmt: skip
    bruto.columns = [c.strip().lower() for c in bruto.columns]
    tabela = pd.DataFrame(
        {c: bruto[c].str.strip().replace("", None) for c in TEXTOS if c in bruto}
    )
    for coluna in NUMEROS:
        tabela[coluna] = pd.to_numeric(
            bruto.get(coluna, pd.Series(index=bruto.index, dtype=str)), errors="coerce"
        ).astype(float)
    tabela["competencia"] = prazos.fim_do_mes(bruto["ano"], bruto["mes"])
    tabela["atualizado_em"] = atualizado_em(conteudo)
    tabela["disponivel_em"] = prazos.disponivel_mensal(tabela["competencia"])
    return tabela.reindex(columns=list(COLUNAS))
