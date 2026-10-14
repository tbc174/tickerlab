"""Carteiras dos fundos desde 2005, "como era na data" (série 3 da base de ML, PR 4; pedido 1 da
sessão "FactSet").

Lê o bloco de ações do CDA (`cda_fi_BLC_4_*.csv`) dos arquivos anuais (2005–2022) e mensais (2023
em diante). O inventário de 14/10/2026 achou as mesmas 21 colunas de 2005 a 2022; na CVM 175 só
mudam `CNPJ_FUNDO` → `CNPJ_FUNDO_CLASSE` e `TP_FUNDO` → `TP_FUNDO_CLASSE`. Os tipos de posição
(comprado, emprestado, vendido) e a codificação são os do app (`src/fundos_cvm.py`), para a tela e a
base dizerem o mesmo.

- **Em pedaços:** o bloco de 2022 tem 510 MB descompactado; só as colunas usadas são lidas.
- **Código permanente:** o `CD_ISIN` está em todas as linhas; o emissor sai dele (`base/fca.py`).
- **"Como era na data":** o arquivo não diz quando ficou público. A posição só vale a partir de 90
  dias depois da competência (o arquivo sai uns 40 dias depois e o sigilo pode ir a 90) ou do fim do
  sigilo (`DT_CONFID_APLIC`), o que vier depois. Regra conservadora: pode atrasar um número, nunca
  adiantar.
"""

import io
import zipfile
from collections.abc import Iterator
from datetime import date

import pandas as pd

from base.fca import emissor_do_isin
from src.detentores import COMPRADO, EMPRESTADO, VENDIDO
from src.fundos_cvm import CODIFICACAO_DA_CVM, TIPOS

TIPOS_DE_POSICAO = (COMPRADO, EMPRESTADO, VENDIDO)  # os valores da coluna `tipo`

LINHAS_POR_PEDACO = 500_000
DIAS_ATE_FICAR_PUBLICA = 90
COLUNAS = (
    "competencia", "cnpj_fundo", "tipo_do_fundo", "fundo", "tipo", "codigo", "isin", "emissor",
    "descricao", "quantidade", "valor", "compras", "vendas", "confidencial_ate",
)  # fmt: skip
# o nome de antes da CVM 175 → o de depois (o mesmo dado)
NOMES_NOVOS = {"CNPJ_FUNDO": "CNPJ_FUNDO_CLASSE", "TP_FUNDO": "TP_FUNDO_CLASSE"}
USADAS = (
    "CNPJ_FUNDO_CLASSE", "TP_FUNDO_CLASSE", "DENOM_SOCIAL", "DT_COMPTC", "TP_APLIC", "CD_ATIVO",
    "CD_ISIN", "DS_ATIVO", "QT_POS_FINAL", "VL_MERC_POS_FINAL", "VL_AQUIS_NEGOC", "VL_VENDA_NEGOC",
    "DT_CONFID_APLIC",
)  # fmt: skip


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0.0)


def _texto(serie: pd.Series) -> pd.Series:
    return serie.str.strip().replace("", None)


def _do_pedaco(bruto: pd.DataFrame) -> pd.DataFrame:
    bruto = bruto.rename(columns=NOMES_NOVOS)
    bruto = bruto[bruto["TP_APLIC"].isin(TIPOS)]
    isin = _texto(bruto["CD_ISIN"])
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime(bruto["DT_COMPTC"], errors="coerce"),
            "cnpj_fundo": bruto["CNPJ_FUNDO_CLASSE"].str.strip(),
            "tipo_do_fundo": _texto(bruto["TP_FUNDO_CLASSE"]),
            "fundo": bruto["DENOM_SOCIAL"].str.strip().str[:200],
            "tipo": bruto["TP_APLIC"].map(TIPOS),
            "codigo": _texto(bruto["CD_ATIVO"]),
            "isin": isin,
            "emissor": isin.map(emissor_do_isin),
            "descricao": _texto(bruto["DS_ATIVO"]),
            "quantidade": _numero(bruto["QT_POS_FINAL"]),
            "valor": _numero(bruto["VL_MERC_POS_FINAL"]),
            "compras": _numero(bruto["VL_AQUIS_NEGOC"]),
            "vendas": _numero(bruto["VL_VENDA_NEGOC"]),
            "confidencial_ate": pd.to_datetime(
                bruto["DT_CONFID_APLIC"], errors="coerce"
            ),
        }
    ).dropna(subset=["competencia"])


def ler_posicoes_historicas(
    conteudo_do_zip: bytes, tamanho: int = LINHAS_POR_PEDACO
) -> Iterator[pd.DataFrame]:
    """As posições em ações de todos os fundos num arquivo do CDA, em pedaços de `tamanho` linhas.

    Lê em fluxo de dentro do zip: o bloco descompactado (510 MB em 2022) nunca fica inteiro na memória.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next(n for n in arquivo.namelist() if "_BLC_4_" in n)
        with arquivo.open(nome) as cabeca:
            cabecalho = pd.read_csv(
                cabeca, sep=";", encoding=CODIFICACAO_DA_CVM, nrows=0
            ).columns
        usadas = [c for c in cabecalho if NOMES_NOVOS.get(c, c) in USADAS]
        with arquivo.open(nome) as fluxo:
            for bruto in pd.read_csv(
                fluxo, sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace",
                dtype=str, keep_default_na=False, usecols=usadas, chunksize=tamanho,
            ):  # fmt: skip
                yield _do_pedaco(bruto).reset_index(drop=True)[list(COLUNAS)]


def disponivel_em(posicoes: pd.DataFrame) -> pd.Series:
    """Desde quando cada posição era pública: competência + 90 dias, ou o fim do sigilo se depois."""
    prazo = posicoes["competencia"] + pd.Timedelta(days=DIAS_ATE_FICAR_PUBLICA)
    return pd.concat([prazo, posicoes["confidencial_ate"]], axis=1).max(axis=1)


def como_era_em(posicoes: pd.DataFrame, data: date) -> pd.DataFrame:
    """Só as posições que já eram públicas em `data` (a coluna `disponivel_em` precisa existir)."""
    return posicoes[posicoes["disponivel_em"] <= pd.Timestamp(data)]
