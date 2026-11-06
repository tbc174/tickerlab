"""Cadastro de operadoras de planos de saúde da ANS (linha 227 da fila; fonte `ans-operadoras`): as
ativas (`Relatorio_cadop.csv`) e as canceladas (`Relatorio_cadop_canceladas.csv`), um retrato inteiro a
cada baixada (`base/retratos.py` junta os retratos numa tabela que só cresce).

- **Formato** (conferido em 04/11/2026 nos arquivos que o arquivista guardou): `;`, UTF-8, data em
  `AAAA-MM-DD`. O arquivista já tirou do original as colunas de contato e de representante; aqui só
  entram as que o `COLUNAS_DO_CADASTRO_DA_ANS` de `base/arquivo/fontes.py` deixa passar. O arquivo das
  canceladas traz mais duas colunas (`DATA_DESCREDENCIAMENTO` e `MOTIVO_DO_DESCREDENCIAMENTO`).
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075): linha cujo documento é CPF ou não fecha o DV
  sai e é contada.
- **Uma linha por `REGISTRO_OPERADORA`** dentro de um retrato; repetida, fica a primeira.
- **Sem olhar o futuro** (`disponivel_no_primeiro`): o primeiro retrato vale desde a data do registro
  (ato público da ANS), ou do descredenciamento, a que for depois, nunca depois do dia do retrato.
  O que muda num retrato seguinte vale desde o dia dele.

Sem Streamlit; pandas só.
"""

import io
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor
from base.arquivo.fontes import ARQUIVOS_DO_CADASTRO_DA_ANS

FONTE = "ans-operadoras"
ATIVAS = "ativas"
CANCELADAS = "canceladas"
SEPARADOR = ";"
CODIFICACAO = "utf-8-sig"
FORMATO_DA_DATA = "%Y-%m-%d"
COLUNAS_DA_FONTE = {
    "REGISTRO_OPERADORA": "id_na_fonte",
    "CNPJ": "cnpj",
    "RAZAO_SOCIAL": "razao_social",
    "NOME_FANTASIA": "nome_fantasia",
    "MODALIDADE": "modalidade",
    "UF": "uf",
    "DATA_REGISTRO_ANS": "registrada_em",
    "DATA_DESCREDENCIAMENTO": "descredenciada_em",
    "MOTIVO_DO_DESCREDENCIAMENTO": "motivo_do_descredenciamento",
}
TEXTOS = [
    "razao_social",
    "nome_fantasia",
    "modalidade",
    "uf",
    "motivo_do_descredenciamento",
]
DATAS = ["registrada_em", "descredenciada_em"]
VALORES = ["cnpj", *TEXTOS, *DATAS, "situacao"]
COLUNAS = [
    "id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS, *DATAS, "situacao",
]  # fmt: skip


def ler_retrato(conteudo: bytes, situacao: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """As operadoras de pessoa jurídica de um arquivo (`situacao`: `ativas` ou `canceladas`) e a
    contagem do que ficou de fora."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
    )
    bruta = bruta.rename(columns=lambda c: COLUNAS_DA_FONTE.get(c.strip(), c))
    for coluna in COLUNAS_DA_FONTE.values():
        if coluna not in bruta:
            bruta[coluna] = (
                ""  # coluna que a fonte não manda (as ativas não têm descredenciamento)
            )
    bruta = bruta.apply(lambda serie: serie.str.strip())
    cnpj = bruta["cnpj"].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    tabela = bruta[valido].assign(cnpj=cnpj[valido])
    repetido = tabela["id_na_fonte"].duplicated(keep="first")
    tabela = tabela[~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": tabela["id_na_fonte"],
            "cnpj": tabela["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": tabela["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS},
            **{
                c: pd.to_datetime(tabela[c], format=FORMATO_DA_DATA, errors="coerce")
                for c in DATAS
            },
            "situacao": situacao,
        }
    )[COLUNAS].reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """Registro ou descredenciamento (o que for depois), nunca depois do retrato; sem data, ele."""
    datas = novos[DATAS].max(axis=1)
    return datas.where(datas <= dia, dia).fillna(dia)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_primeiro)


TABELA = "ans_operadoras"
CADASTROS = tuple(
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome=situacao,
        fonte=FONTE,
        ler=lambda retrato, situacao=situacao: ler_retrato(
            motor.original(retrato.caminho), situacao
        ),
        juntar=juntar_retratos,
        colunas=tuple(COLUNAS),
        datas=tuple(DATAS),
        url_termina_em="/" + arquivo,
    )
    for situacao, arquivo in ARQUIVOS_DO_CADASTRO_DA_ANS.items()
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/ans_operadoras/{ativas,canceladas}.parquet` (um retrato por baixada, só CNPJ)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
