"""Cadastros da ANTT pelo CNPJ (meta das 300 tabelas, lote 3, linha 904): os operadores de transporte
multimodal e o seguro de responsabilidade civil dos transportadores. Fontes `antt-*` do arquivista
(`base/arquivo/lote_cadastros_bcb_antt.py`); a licença é a CC BY da ANTT (família `antt`, citar a ANTT).

- **Formato** (conferido em 13/11/2026 nos arquivos do portal): CSV com `;`. Os multimodais vêm em Latin-1, com a
  vigência no formato `MM/DD/AAAA hh:mm:ss.ffffff` (dos 1.407 registros, 869 têm o dia acima de 12 no segundo
  campo e nenhum no primeiro: é mês na frente, e não dia). O seguro vem em UTF-8, com o CNPJ já formatado
  (`00.000.000/0000-00`) e datas `DD/MM/AAAA`.
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075); o CPF e o CNPJ que não fecha o DV saem e são contados.
  O operador estrangeiro (CNPJ de fachada, país de origem diferente de Brasil) cai fora pelo DV.
- **Ficam de fora** a razão social, o logradouro, o CEP e o e-mail do operador multimodal, e do seguro a placa
  do veículo e o nome do segurado: o seguro fica **uma linha por apólice** (quantos veículos, quantos assentos,
  quantos endossos), nunca por veículo.
- **Sem olhar o futuro:** os arquivos não dizem quando foram publicados (a `data_registro` do seguro é a do
  registro na ANTT, mas cada apólice recebe endossos depois), então a linha vale desde o dia em que o
  arquivista a viu: o dia do retrato.

Sem Streamlit; pandas só.
"""

import io
import re
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import aneel_indicadores as comum
from base import bcb_cadastros as base
from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

FONTE_DOS_MULTIMODAIS = "antt-operadores-multimodais"
FONTE_DO_SEGURO = "antt-seguro-de-responsabilidade-civil"
TABELA_DOS_MULTIMODAIS = "antt_operadores_multimodais"
TABELA_DO_SEGURO = "antt_seguros_de_transportadores"
SEPARADOR = ";"
CODIFICACAO_DOS_MULTIMODAIS = "latin-1"
FORMATO_DA_VIGENCIA = "%m/%d/%Y"
FORMATO_DO_REGISTRO = "%d/%m/%Y %H:%M:%S"
ADESAO_SIM = "sim"
NAO_DIGITOS = re.compile(r"\D")


def _csv(conteudo: bytes, codificacao: str, colunas: Collection[str]) -> pd.DataFrame:
    """O CSV como texto, sem espaços nas pontas; coluna que a ANTT tirou é erro, não coluna vazia."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=codificacao,
        dtype=str,
        keep_default_na=False,
        usecols=lambda coluna: coluna.strip() in colunas,
    )
    bruta.columns = [c.strip() for c in bruta.columns]
    faltam = sorted(set(colunas) - set(bruta.columns))
    if faltam:
        raise KeyError(f"a ANTT deixou de trazer: {', '.join(faltam)}")
    return bruta.apply(lambda serie: serie.str.strip())


def _so_digitos(texto: pd.Series) -> pd.Series:
    return texto.str.replace(NAO_DIGITOS, "", regex=True)


# --- operadores de transporte multimodal ----------------------------------------------------------------
DOS_MULTIMODAIS = {"uf": "uf", "pais_de_origem": "pais_de_origem", "cotm": "cotm"}
COLUNAS_DOS_MULTIMODAIS = (
    "id_na_fonte", "cnpj", "cnpj_basico", *DOS_MULTIMODAIS.values(), "vigencia_ate", "adesao_ao_decreto_1563_95",
)  # fmt: skip


def ler_multimodais(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os operadores multimodais de pessoa jurídica de um retrato e a contagem do que saiu.

    `cotm` é o certificado de operador de transporte multimodal (um por operador e certificado); a vigência
    é o fim da validade dele. A linha repetida por inteiro na fonte (120 em 13/11/2026) é contada."""
    bruta = _csv(
        conteudo,
        CODIFICACAO_DOS_MULTIMODAIS,
        ["cnpj", "vigencia", "adesao_ao_decreto_1563_95", *DOS_MULTIMODAIS],
    )
    tabela, contagem = comum.so_pessoa_juridica(
        bruta.assign(cnpj=_so_digitos(bruta["cnpj"])), "cnpj"
    )
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(tabela, ["cnpj14", "cotm"]),
                **comum.com_cnpj(tabela["cnpj14"]),
                **base.renomeadas(tabela, DOS_MULTIMODAIS),
                "vigencia_ate": base.dia_br(
                    tabela["vigencia"].str[:10], FORMATO_DA_VIGENCIA
                ),
                "adesao_ao_decreto_1563_95": tabela["adesao_ao_decreto_1563_95"]
                .str.lower()
                .map({ADESAO_SIM: True, "não": False, "nao": False})
                .astype("boolean"),
            }
        ),
        contagem,
        {"adesao_ao_decreto_1563_95": "boolean"},
    )


# --- seguro de responsabilidade civil -------------------------------------------------------------------
COLUNAS_DO_SEGURO = (
    "id_na_fonte", "cnpj", "cnpj_basico", "cnpj_basico_seguradora", "numero_da_apolice", "inicio_da_apolice",
    "fim_da_apolice", "registrada_em", "veiculos", "assentos", "endossos",
)  # fmt: skip
DATAS_DO_SEGURO = ("inicio_da_apolice", "fim_da_apolice", "registrada_em")
DA_APOLICE = ("cnpj14", "numero_apolice")
USADAS_DO_SEGURO = (
    "cnpj_seg", "data_registro", "cnpj", "numero_apolice", "inicio_apolice", "fim_apolice",
    "numero_endosso", "placa", "nr_assentos",
)  # fmt: skip


def _por_apolice(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por apólice: início mais antigo, fim mais novo, veículos e assentos (cada placa uma vez)."""
    veiculos = tabela.drop_duplicates([*DA_APOLICE, "placa"])
    assentos = (
        pd.to_numeric(veiculos["nr_assentos"], errors="coerce")
        .groupby([veiculos[c] for c in DA_APOLICE])
        .sum(min_count=1)
    )
    resumo = tabela.groupby(list(DA_APOLICE), sort=False).agg(
        seguradora=("cnpj_seg", "first"),
        inicio=("inicio", "min"),
        fim=("fim", "max"),
        registro=("registro", "min"),
        endossos=("numero_endosso", "nunique"),
    )
    resumo["veiculos"] = veiculos.groupby(list(DA_APOLICE), sort=False)[
        "placa"
    ].nunique()
    resumo["assentos"] = assentos
    return resumo.reset_index()


def ler_seguro(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As apólices de seguro de responsabilidade civil de transportadores de pessoa jurídica de um retrato.

    A placa e o nome do segurado ficam de fora; o CPF e o CNPJ de DV errado saem e são contados."""
    bruta = _csv(conteudo, "utf-8", USADAS_DO_SEGURO)
    tabela, contagem = comum.so_pessoa_juridica(
        bruta.assign(cnpj=_so_digitos(bruta["cnpj"])), "cnpj"
    )
    datas = {
        "inicio": base.dia_br(tabela["inicio_apolice"]),
        "fim": base.dia_br(tabela["fim_apolice"]),
        "registro": base.dia_br(
            tabela["data_registro"], FORMATO_DO_REGISTRO
        ).dt.normalize(),
    }
    apolices = _por_apolice(
        tabela.assign(**datas, cnpj_seg=_so_digitos(tabela["cnpj_seg"]))
    )
    seguradora = apolices["seguradora"].where(
        apolices["seguradora"].str.len() == cnpjs.TAMANHO
    )
    return base.pronta(
        pd.DataFrame(
            {
                "id_na_fonte": motor.chave(apolices, list(DA_APOLICE)),
                **comum.com_cnpj(apolices["cnpj14"]),
                "cnpj_basico_seguradora": seguradora.str[: cnpjs.TAMANHO_DA_RAIZ],
                "numero_da_apolice": apolices["numero_apolice"],
                "inicio_da_apolice": apolices["inicio"],
                "fim_da_apolice": apolices["fim"],
                "registrada_em": apolices["registro"],
                "veiculos": apolices["veiculos"],
                "assentos": apolices["assentos"],
                "endossos": apolices["endossos"],
            }
        ),
        {**contagem, "apolices": len(apolices)},
        {c: "Int64" for c in ("veiculos", "assentos", "endossos")},
    )


# --- montagem -------------------------------------------------------------------------------------------
CADASTRO_DOS_MULTIMODAIS = base.cadastro(
    TABELA_DOS_MULTIMODAIS, "multimodais", FONTE_DOS_MULTIMODAIS, ler_multimodais,
    COLUNAS_DOS_MULTIMODAIS, ("vigencia_ate",),
)  # fmt: skip
CADASTRO_DO_SEGURO = base.cadastro(
    TABELA_DO_SEGURO, "seguros", FONTE_DO_SEGURO, ler_seguro, COLUNAS_DO_SEGURO, DATAS_DO_SEGURO,
)  # fmt: skip
CADASTROS = (CADASTRO_DOS_MULTIMODAIS, CADASTRO_DO_SEGURO)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/antt_operadores_multimodais/multimodais.parquet` e
    `<pasta>/antt_seguros_de_transportadores/seguros.parquet` (um retrato por baixada, só CNPJ)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
