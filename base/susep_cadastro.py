"""Cadastro de entidades supervisionadas pela SUSEP (linha 227 da fila; fonte `susep-cadastro`): o
serviço `DadosCadastrais` (OData) devolve de uma vez a lista inteira, um retrato por baixada
(`base/retratos.py` junta os retratos numa tabela que só cresce).

- **Formato** (conferido em 04/11/2026 no arquivo guardado, 371 entidades): `{"value": [...]}`, cada item
  com `mercodigo` (o mercado: 1 a 8 e 99; o código numérico fica como vem), `entcodigofip` (o código FIP,
  a chave), `entnome`, `entcgc` e `dataautorizacao` (`AAAA-MM-DD`). Endereço e telefone o arquivista já tirou.
- **Entidade estrangeira não tem CNPJ** (89 de 371, resseguradores admitidos): a linha fica, com `cnpj`
  vazio. Em 5 delas o arquivo traz um "CNPJ" de zeros e lixo (placeholder): a linha fica, sem CNPJ, e é contada
  em `cnpj_invalido`. Documento de 11 dígitos (CPF) sai e é contado em `pessoa_fisica` (ADR 0075).
- **Uma linha por código FIP** dentro de um retrato; repetido, fica o primeiro.
- **Sem olhar o futuro** (`disponivel_no_primeiro`): o primeiro retrato vale desde a data da autorização
  (ato público da SUSEP), nunca depois do dia do retrato; sem data, o dia dele. O que muda num retrato
  seguinte vale desde o dia dele.

Sem Streamlit; pandas só.
"""

import json
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

FONTE = "susep-cadastro"
FORMATO_DA_DATA = "%Y-%m-%d"
COLUNAS_DA_FONTE = {
    "entcodigofip": "id_na_fonte",
    "mercodigo": "codigo_do_mercado",
    "entnome": "nome",
    "entcgc": "documento",
    "dataautorizacao": "autorizada_em",
}
VALORES = ["codigo_do_mercado", "nome", "cnpj", "autorizada_em"]
COLUNAS = [
    "id_na_fonte", "codigo_do_mercado", "nome", "cnpj", "cnpj_basico", "autorizada_em",
]  # fmt: skip


def _texto(valor: object) -> str:
    return "" if valor is None else str(valor).strip()


def _bruta(conteudo: bytes) -> pd.DataFrame:
    itens = json.loads(conteudo)["value"]
    return pd.DataFrame(
        {
            nova: [_texto(item.get(velha)) for item in itens]
            for velha, nova in COLUNAS_DA_FONTE.items()
        },
        dtype=str,
    )


def ler_retrato(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As entidades de um arquivo e a contagem do que ficou de fora."""
    bruta = _bruta(conteudo)
    cnpj = bruta["documento"].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    sem_digitos = bruta["documento"].str.replace(r"\D", "", regex=True)
    fora = sem_digitos.str.len().eq(
        cnpjs.TAMANHO_DO_CPF
    )  # CPF: pessoa física nunca entra
    tabela = bruta[~fora]
    repetido = tabela["id_na_fonte"].duplicated(keep="first")
    tabela = tabela[~repetido]
    cnpj = cnpj[tabela.index].where(valido[tabela.index], None)
    pronta = pd.DataFrame(
        {
            "id_na_fonte": tabela["id_na_fonte"],
            "codigo_do_mercado": pd.to_numeric(
                motor.sem_vazio(tabela["codigo_do_mercado"]), errors="coerce"
            ).astype("Int64"),
            "nome": motor.sem_vazio(tabela["nome"]),
            "cnpj": cnpj.map(
                lambda c: cnpjs.formatar(c) if isinstance(c, str) else None
            ),
            "cnpj_basico": cnpj.map(
                lambda c: c[: cnpjs.TAMANHO_DA_RAIZ] if isinstance(c, str) else None
            ),
            "autorizada_em": pd.to_datetime(
                tabela["autorizada_em"], format=FORMATO_DA_DATA, errors="coerce"
            ),
        }
    )[COLUNAS].reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "pessoa_fisica": int(fora.sum()),
        "cnpj_invalido": int((bruta["documento"].ne("") & ~valido & ~fora).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """A autorização, nunca depois do retrato; sem data, o dia dele."""
    datas = novos["autorizada_em"]
    return datas.where(datas <= dia, dia).fillna(dia)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_primeiro)


TABELA = "susep_cadastro"
CADASTROS = (
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome="entidades",
        fonte=FONTE,
        ler=lambda retrato: ler_retrato(motor.original(retrato.caminho)),
        juntar=juntar_retratos,
        colunas=tuple(COLUNAS),
        datas=("autorizada_em",),
    ),
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/susep_cadastro/entidades.parquet` (um retrato por baixada)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
