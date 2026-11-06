"""A vista do CNPJ pela porta: uma empresa por leitura (PR 6 do plano da base de CNPJ com sócios, 20/10/2026).

A vista é montada em casa por `scripts.montar_vista_do_cnpj` e publicada no servidor; a busca por CNPJ
(`src/cadastro_da_receita.py`) a lê só por aqui. O desenho é o mesmo da base do CNPJ:
- `vigente/<tabela>/<xx>.parquet` (estabelecimentos, simples e qsa), repartida pelos 2 primeiros caracteres
  da raiz, ordenada pela raiz e em grupos pequenos: a leitura de uma empresa só abre o grupo dela;
- `vigente/participacoes/<xx>.parquet`: o QSA virado, só o sócio pessoa jurídica, repartido e ordenado pela
  raiz da sócia: as empresas de que cada raiz é sócia (o grupo econômico, `base/rede/grupo_do_qsa.py`);
- `mudancas/<tabela>/<xx>.parquet`: as mudanças dos últimos 12 meses publicados;
- `manifesto.json`: o mês do retrato, os meses das mudanças e as linhas e os bytes de cada tabela.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

# por tabela: as chaves da linha e os campos que a busca mostra (as linhas em que só mudou outro campo saem)
MUDANCAS = {
    "estabelecimentos": (
        ("cnpj",), ("situacao_cadastral", "cnae_principal", "uf", "municipio"),
    ),
    "simples": (("cnpj_basico",), ("optante_simples", "optante_mei")),
    "qsa": (("cnpj_basico", "tipo_socio", "raiz_socio_pj"), ("qualificacao", "data_entrada")),
}  # fmt: skip
PARTICIPACOES = "participacoes"
COLUNAS_DAS_PARTICIPACOES = (
    "raiz_socio_pj",
    "cnpj_basico",
    "qualificacao",
    "data_entrada",
)
PREFIXO = 2  # a base reparte pelos 2 primeiros caracteres da raiz
TAMANHO_DA_RAIZ = 8
MANIFESTO = "manifesto.json"
MESES_DAS_MUDANCAS = 12  # a janela das mudanças: os últimos 12 meses publicados


def manifesto(vista: Path) -> dict | None:
    """O manifesto da vista; None se ela ainda não chegou ao servidor."""
    arquivo = vista / MANIFESTO
    if not arquivo.is_file():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))


def da_raiz(vista: Path, grupo: str, tabela: str, raiz: str) -> pd.DataFrame:
    """As linhas da `raiz` em `<grupo>/<tabela>` (vazio se o prefixo não tem arquivo)."""
    arquivo = vista / grupo / tabela / f"{raiz[:PREFIXO]}.parquet"
    if not arquivo.is_file():
        return pd.DataFrame()
    filtro = [("cnpj_basico", "==", raiz)]
    return pq.read_table(arquivo, filters=filtro).to_pandas()


def participacoes(vista: Path) -> Iterator[pd.DataFrame]:
    """O QSA virado inteiro, um prefixo da raiz da sócia por vez (quem exporta o grupo para o portal)."""
    for arquivo in sorted((vista / "vigente" / PARTICIPACOES).glob("*.parquet")):
        yield pq.read_table(arquivo).to_pandas()


def participacoes_da_raiz(vista: Path, raiz: str) -> pd.DataFrame:
    """As empresas de que a `raiz` é sócia pessoa jurídica no retrato vigente (vazio se não há)."""
    arquivo = vista / "vigente" / PARTICIPACOES / f"{raiz[:PREFIXO]}.parquet"
    if not arquivo.is_file():
        return pd.DataFrame(columns=list(COLUNAS_DAS_PARTICIPACOES))
    filtro = [("raiz_socio_pj", "==", raiz)]
    return pq.read_table(arquivo, filters=filtro).to_pandas()
