"""Histórico do IDSS das operadoras de planos de saúde da ANS (meta das 300 tabelas pelo CNPJ, linha 904;
fonte `ans-qualidade`, pasta `historico_idss-020`): a nota de cada operadora em cada índice e ano de
avaliação, um retrato inteiro a cada baixada (`base/retratos.py` junta os retratos).

- **Três arquivos, um cadastro cada** (`de_2009`, `de_2012`, `de_2016`): `pda-020-historico-idss-2009_2011`,
  `-2012_2015` e `-2016_<último ano>`. O último muda de nome todo ano, então cada cadastro é achado pelo
  prefixo e fica com o endereço do retrato mais novo (os outros são contados em `enderecos_ignorados`).
- **Formato** (conferido em 13/11/2026 nos arquivos guardados): `;`, UTF-8, aspas, CRLF. Depois de
  `REGISTRO_OPERADORA;CNPJ;RAZAO_SOCIAL;MODALIDADE`, uma coluna por `<ÍNDICE>_<ANO DA AVALIAÇÃO>_<ANO BASE>`
  (a fonte escreve `IDSS_2010__2009`, com dois sublinhados). A nota vem com vírgula decimal (`0,5222`),
  `ND` (não disponível: não vira linha, é contada) ou, no arquivo de 2009 a 2011, uma faixa
  (`0,40 a 0,59`, guardada como texto em `faixa`).
- **Formato longo**: uma linha por operadora, índice e ano de avaliação. A razão social fica de fora.
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075): CPF e CNPJ que não fecha o DV saem e são contados.
- **Sem olhar o futuro**: o arquivo não diz quando cada nota saiu, então o primeiro retrato vale desde o
  dia dele (a leitura mais estreita).

Sem Streamlit; pandas só.
"""

import io
import re
from collections.abc import Collection
from datetime import datetime
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

FONTE = "ans-qualidade"
TABELA = "ans_idss"
SEPARADOR = ";"
CODIFICACAO = "utf-8-sig"
EXTENSAO = ".csv"
PREFIXOS = {
    "de_2009": "/pda-020-historico-idss-2009_",
    "de_2012": "/pda-020-historico-idss-2012_",
    "de_2016": "/pda-020-historico-idss-2016_",
}
# `IDSS_2016_2015`, e também `IDSS_2010__2009` (dois sublinhados, como está na fonte)
COLUNA_DE_NOTA = re.compile(
    r"^(?P<indice>ID[A-Z]+)_+(?P<avaliacao>\d{4})_+(?P<base>\d{4})$"
)
NAO_DISPONIVEL = "ND"
NUMERO = re.compile(r"^\d*,?\d+$")
FAIXA = re.compile(r"^\d*,?\d+ a \d*,?\d+$")
FIXAS = ["REGISTRO_OPERADORA", "cnpj14", "MODALIDADE"]

COLUNAS = (
    "id_na_fonte", "cnpj", "cnpj_basico", "registro_operadora", "modalidade", "indice",
    "ano_avaliacao", "ano_base", "valor", "faixa",
)  # fmt: skip
VALORES = ["cnpj", "modalidade", "ano_base", "valor", "faixa", "consta"]
# os três arquivos viram três Parquets lidos juntos (`union_by_name`): o tipo de cada coluna é fixo, mesmo
# quando ela vem toda vazia num arquivo (a `faixa` do de 2016, o `valor` do de 2009)
TIPOS = {
    **dict.fromkeys(
        (
            "id_na_fonte",
            "cnpj",
            "cnpj_basico",
            "registro_operadora",
            "modalidade",
            "indice",
            "faixa",
        ),
        "string",
    ),
    "ano_avaliacao": "int64",
    "ano_base": "int64",
    "valor": "float64",
}


def ler_csv(conteudo: bytes) -> pd.DataFrame:
    """O CSV da ANS como texto, sem espaços nas pontas (nome de coluna e valor)."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
    )
    bruta.columns = [c.strip() for c in bruta.columns]
    return bruta.apply(lambda serie: serie.str.strip())


def so_pessoa_juridica(bruta: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """As operadoras com CNPJ de DV certo (o CNPJ de 14 caracteres em `cnpj14`) e quantas saíram."""
    cnpj = bruta["CNPJ"].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    de_cpf = (
        bruta["CNPJ"].str.replace(r"\D", "", regex=True).map(cnpjs.cpf_confere)
        & ~valido
    )
    contagem = {
        "linhas": len(bruta),
        "pessoa_fisica": int(de_cpf.sum()),
        "cnpj_invalido": int((~valido & ~de_cpf).sum()),
    }
    tabela = bruta[valido].assign(cnpj14=cnpj[valido])
    repetido = tabela["REGISTRO_OPERADORA"].duplicated(keep="first")
    contagem["id_repetido"] = int(repetido.sum())
    return tabela[~repetido], contagem


def notas_em_linhas(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por operadora e coluna de nota, com o índice e os anos tirados do nome da coluna."""
    notas = [c for c in tabela.columns if COLUNA_DE_NOTA.match(c)]
    longa = tabela[[*FIXAS, *notas]].melt(
        id_vars=FIXAS, value_vars=notas, var_name="coluna", value_name="nota"
    )
    partes = longa["coluna"].str.extract(COLUNA_DE_NOTA)
    return longa.assign(
        indice=partes["indice"],
        ano_avaliacao=partes["avaliacao"].astype(int),
        ano_base=partes["base"].astype(int),
    )


def _contar_notas(
    nota: pd.Series, e_numero: pd.Series, e_faixa: pd.Series
) -> dict[str, int]:
    """Quantas notas não viram linha: `ND`, vazias e as de forma desconhecida."""
    nao_disponivel = nota.eq(NAO_DISPONIVEL)
    vazia = nota.eq("")
    return {
        "nao_disponivel": int(nao_disponivel.sum()),
        "sem_nota": int(vazia.sum()),
        "nota_desconhecida": int(
            (~(e_numero | e_faixa | nao_disponivel | vazia)).sum()
        ),
    }


def ler_retrato(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As notas do IDSS das operadoras de pessoa jurídica de um arquivo e a contagem do que saiu."""
    tabela, contagem = so_pessoa_juridica(ler_csv(conteudo))
    longa = notas_em_linhas(tabela)
    e_numero = longa["nota"].str.fullmatch(NUMERO)
    e_faixa = longa["nota"].str.fullmatch(FAIXA)
    contagem.update(_contar_notas(longa["nota"], e_numero, e_faixa))
    longa = longa[e_numero | e_faixa]
    e_numero = e_numero[longa.index]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": motor.chave(
                longa.assign(avaliacao=longa["ano_avaliacao"].astype(str)),
                ["REGISTRO_OPERADORA", "indice", "avaliacao"],
            ),
            "cnpj": longa["cnpj14"].map(cnpjs.formatar),
            "cnpj_basico": longa["cnpj14"].str[: cnpjs.TAMANHO_DA_RAIZ],
            "registro_operadora": longa["REGISTRO_OPERADORA"],
            "modalidade": motor.sem_vazio(longa["MODALIDADE"]),
            "indice": longa["indice"],
            "ano_avaliacao": longa["ano_avaliacao"],
            "ano_base": longa["ano_base"],
            "valor": pd.to_numeric(
                longa["nota"].where(e_numero).str.replace(",", ".", regex=False)
            ),
            "faixa": longa["nota"].where(~e_numero, None),
        }
    )
    repetido = pronta["id_na_fonte"].duplicated(keep="first")
    contagem["nota_repetida"] = int(repetido.sum())
    return pronta[~repetido].astype(TIPOS).reset_index(drop=True), contagem


def disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do retrato: o arquivo não diz quando cada nota foi publicada."""
    return pd.Series(dia, index=novos.index)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_primeiro)


def achar_pelo_prefixo(
    conexao: sa.Connection, prefixo: str
) -> tuple[list[motor.Retrato], int]:
    """Os retratos do arquivo cujo endereço tem `prefixo` (o do endereço mais novo; o arquivo de 2016 em
    diante muda de nome a cada ano) e quantos endereços ficaram de fora."""
    achados = [
        r
        for r in motor.retratos(conexao, FONTE)
        if prefixo in r.url and r.url.endswith(EXTENSAO)
    ]
    return cadastros_em_retrato._do_endereco_mais_novo(achados)


CADASTROS = tuple(
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome=nome,
        fonte=FONTE,
        ler=lambda retrato: ler_retrato(motor.original(retrato.caminho)),
        juntar=juntar_retratos,
        colunas=COLUNAS,
        datas=(),
        achar=partial(achar_pelo_prefixo, prefixo=prefixo),
    )
    for nome, prefixo in PREFIXOS.items()
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/ans_idss/{de_2009,de_2012,de_2016}.parquet` (um retrato por baixada, só CNPJ)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
