"""Termos de embargo do IBAMA (linha 227 da fila; fonte `ibama-embargos`): o arquivo principal
(`termo_de_embargo.csv`, um termo por linha), um retrato inteiro a cada baixada (`base/retratos.py` junta os
retratos numa tabela que só cresce).

- **Formato** (conferido em 04/11/2026 no arquivo guardado; de novo em 13/11/2026, linha 914): `;`, 51
  colunas. O arquivo vem em UTF-8 com BOM e o cabeçalho entre aspas; lido como Latin-1, o BOM grudava
  no 1º cabeçalho e o `SEQ_TAD` sumia. Sem BOM, Latin-1. Aqui entram só as
  que dizem quem, onde, quando e em que situação; geometria da área (`GEOM_AREA_EMBARGADA`), texto livre
  e dados do fiscal ficam de fora. Os outros arquivos do pacote (anexos, enquadramento, polígonos,
  decisões) são tabelas filhas e não entram aqui.
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075): `CPF_CNPJ_EMBARGADO` de 11 dígitos (CPF) sai e
  o nome do embargado vai junto; documento que não fecha o DV também sai. Tudo é contado.
- **Uma linha por `SEQ_TAD`** dentro de um retrato; repetida, fica a primeira. Termo sem `SEQ_TAD` (há
  milhares no arquivo) fica pelo número do termo (`TAD <NUM_TAD>`), para não virar um id vazio só.
- **Data do embargo**: o arquivo traz anos impossíveis (`2925-09-25`, `2090-03-16`); data fora de
  1980 até o dia do retrato vira vazia, nunca é corrigida a olho.
- **Sem olhar o futuro** (`disponivel_no_primeiro`): o embargo vale desde a data dele (ato público),
  ou do desembargo, a que for depois, nunca depois do dia do retrato; sem data, o dia dele.

Sem Streamlit; pandas só.
"""

import codecs
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

FONTE = "ibama-embargos"
SEPARADOR = ";"
CODIFICACAO = "latin-1"
BOM_DO_UTF8 = codecs.BOM_UTF8
PREFIXO_DO_ID_PELO_NUMERO = "TAD "
PRIMEIRO_ANO_VALIDO = pd.Timestamp("1980-01-01")
COLUNAS_DA_FONTE = {
    "SEQ_TAD": "id_na_fonte",
    "NUM_TAD": "numero_do_termo",
    "NOME_EMBARGADO": "nome",
    "CPF_CNPJ_EMBARGADO": "documento",
    "DES_STATUS_FORMULARIO": "situacao_do_termo",
    "SIT_CANCELADO": "cancelado",
    "DAT_EMBARGO": "embargada_em",
    "COD_MUNICIPIO": "codigo_do_municipio",
    "UF": "uf",
    "QTD_AREA_EMBARGADA": "area_embargada_ha",
    "SIT_DESEMBARGO": "desembargado",
    "DAT_DESEMBARGO": "desembargada_em",
    "NUM_AUTO_INFRACAO": "numero_do_auto",
}
TEXTOS = [
    "numero_do_termo", "nome", "situacao_do_termo", "cancelado", "codigo_do_municipio", "uf",
    "desembargado", "numero_do_auto",
]  # fmt: skip
DATAS = ["embargada_em", "desembargada_em"]
# `consta` entra nos valores comparados: sem ele, o registro que sai do arquivo não vira a linha
# `consta` falso e continua constando (linha 907)
VALORES = [*TEXTOS, "area_embargada_ha", *DATAS, "consta"]
COLUNAS = [
    "id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS, "area_embargada_ha", *DATAS,
]  # fmt: skip


def _data(serie: pd.Series, dia: pd.Timestamp) -> pd.Series:
    """Data do arquivo; fora do intervalo possível (typo de ano) vira vazia."""
    datas = pd.to_datetime(serie.str[:10], format="%Y-%m-%d", errors="coerce")
    return datas.where((datas >= PRIMEIRO_ANO_VALIDO) & (datas <= dia))


def _codificacao(conteudo: bytes) -> str:
    """Com BOM, UTF-8 (o `-sig` tira o BOM, e o cabeçalho entre aspas volta a ser lido); sem, Latin-1."""
    return "utf-8-sig" if conteudo.startswith(BOM_DO_UTF8) else CODIFICACAO


def ler_retrato(
    conteudo: bytes, dia: pd.Timestamp
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os embargados de pessoa jurídica de um arquivo (`dia`: o do retrato) e a contagem do que ficou
    de fora."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=_codificacao(conteudo),
        encoding_errors="replace",
        dtype=str,
        keep_default_na=False,
        usecols=lambda c: c in COLUNAS_DA_FONTE,
    ).rename(columns=COLUNAS_DA_FONTE)
    for coluna in COLUNAS_DA_FONTE.values():
        if coluna not in bruta:
            bruta[coluna] = ""
    bruta = bruta.apply(lambda serie: serie.str.strip())
    sem_digitos = bruta["documento"].str.replace(r"\D", "", regex=True)
    fora = sem_digitos.str.len().eq(
        cnpjs.TAMANHO_DO_CPF
    )  # CPF: pessoa física nunca entra
    cnpj = bruta["documento"].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    tabela = bruta[valido].assign(cnpj=cnpj[valido])
    sem_seq = tabela["id_na_fonte"].eq("")
    tabela = tabela.assign(
        id_na_fonte=tabela["id_na_fonte"].mask(
            sem_seq, PREFIXO_DO_ID_PELO_NUMERO + tabela["numero_do_termo"]
        )
    )
    repetido = tabela["id_na_fonte"].duplicated(keep="first")
    tabela = tabela[~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": tabela["id_na_fonte"],
            "cnpj": tabela["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": tabela["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS},
            "area_embargada_ha": pd.to_numeric(
                tabela["area_embargada_ha"].str.replace(",", ".", regex=False),
                errors="coerce",
            ),
            **{c: _data(tabela[c], dia) for c in DATAS},
        }
    )[COLUNAS].reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "pessoa_fisica": int(fora.sum()),
        "cnpj_invalido": int((~valido & ~fora).sum()),
        "id_repetido": int(repetido.sum()),
        "id_pelo_numero_do_termo": int(sem_seq.sum()),
    }
    return pronta, contagem


def disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """Embargo ou desembargo (o que for depois), nunca depois do retrato; sem data, o dia dele."""
    datas = novos[DATAS].max(axis=1)
    return datas.where(datas <= dia, dia).fillna(dia)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_primeiro)


TABELA = "ibama_embargos"
CADASTROS = (
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome="termos",
        fonte=FONTE,
        ler=lambda retrato: ler_retrato(
            motor.original(retrato.caminho), pd.Timestamp(retrato.dia)
        ),
        juntar=juntar_retratos,
        colunas=tuple(COLUNAS),
        datas=tuple(DATAS),
        # o nome real do arquivo principal (conferido no acervo em 13/11/2026, linha 914); os irmãos
        # (`termo_de_embargo_anexo.csv`, `termo_embargo_itens.csv`...) não terminam assim
        url_termina_em="/termo_de_embargo.csv",
    ),
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/ibama_embargos/termos.parquet` (o CSV do termo de embargo)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
