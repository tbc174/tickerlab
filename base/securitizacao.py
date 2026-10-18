"""Informes mensais de CRI, CRA e outros títulos de securitização (OTS) da CVM, sem dado pessoal
(vertical de crédito do produto Base, ADR 0084; plano de 18/10/2026).

- **Um informe por certificado e mês** (`inf_mensal_<produto>_<ano>.zip`), um CSV por quadro (`geral`,
  `ativo_passivo`, `classe`, `cedente_devedor`...). O CRI tem quadros próprios até a Resolução CVM 60
  (`carteira`, `creditos`...); CRA e OTS seguem o modelo novo. Cada quadro vira uma tabela, no
  formato da fonte, com a chave na frente: `competencia` (o 1º dia do mês: o OTS informa o último, CRI
  e CRA o primeiro), `cnpj_securitizadora` (formatado) e `codigo_certificado`.
- **Linhas repetidas:** a CVM guarda só a última versão de cada informe; linha repetida inteira entra
  uma vez. Num certificado e mês, mais de uma linha é normal em `classe` (uma por série) e em
  `cedente_devedor`; o OTS de 2026 tem até um informe entregue duas vezes com conteúdo diferente, e os
  dois ficam (não há como saber qual vale).
"""

import io
import re
import zipfile
from dataclasses import dataclass

import pandas as pd

from base.fidc import CODIFICACAO_DA_CVM, documento_de_empresa

PRODUTOS = ("cri", "cra", "ots")
CHAVE = ("competencia", "cnpj_securitizadora", "codigo_certificado")
COLUNAS_DA_SECURITIZADORA = ("CNPJ_Emissora", "CNPJ_Securitizadora")  # o OTS usa a 2ª
COLUNA_DO_CERTIFICADO = "Codigo_Identificacao_Certificado"
COLUNA_DA_REFERENCIA = "Data_Referencia"


@dataclass(frozen=True)
class Leitura:
    """As tabelas de um arquivo do informe (uma por quadro) e as linhas quebradas de cada quadro."""

    tabelas: dict[str, pd.DataFrame]
    linhas_quebradas: dict[str, int]


def _nome_do_quadro(produto: str) -> re.Pattern[str]:
    if produto not in PRODUTOS:
        raise ValueError(f"produto {produto!r} não é um de {PRODUTOS}")
    return re.compile(rf"inf_mensal_{produto}_([a-z_]+?)_\d{{4,6}}\.csv$")


def quadros_do_arquivo(conteudo_do_zip: bytes, produto: str) -> set[str]:
    """Os quadros (`geral`, `classe`...) que um arquivo do informe traz, sem ler os dados."""
    nome_do_quadro = _nome_do_quadro(produto)
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        return {
            a.group(1) for n in arquivo.namelist() if (a := nome_do_quadro.search(n))
        }


def _ler_csv(arquivo: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    return pd.read_csv(
        arquivo.open(nome), sep=";", encoding=CODIFICACAO_DA_CVM, encoding_errors="replace",
        dtype=str, keep_default_na=False, engine="python", on_bad_lines="skip",
    ).replace("", None)  # fmt: skip


def _com_chave(tabela: pd.DataFrame) -> pd.DataFrame:
    tabela = tabela.drop_duplicates(ignore_index=True)
    securitizadora = next(c for c in COLUNAS_DA_SECURITIZADORA if c in tabela.columns)
    referencia = pd.to_datetime(tabela[COLUNA_DA_REFERENCIA], errors="coerce")
    chave = pd.DataFrame(
        {
            "competencia": referencia.dt.to_period("M").dt.to_timestamp(),
            "cnpj_securitizadora": tabela[securitizadora].map(documento_de_empresa),
            "codigo_certificado": tabela[COLUNA_DO_CERTIFICADO].str.strip(),
        }
    )
    resto = tabela.drop(columns=[securitizadora, COLUNA_DO_CERTIFICADO])
    return pd.concat([chave, resto], axis=1)


def ler_informe(conteudo_do_zip: bytes, produto: str) -> Leitura:
    """Uma tabela por quadro do informe, com a chave na frente."""
    nome_do_quadro = _nome_do_quadro(produto)
    tabelas = {}
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        for nome in sorted(arquivo.namelist()):
            if achado := nome_do_quadro.search(nome):
                tabelas[achado.group(1)] = _com_chave(_ler_csv(arquivo, nome))
    return Leitura(tabelas, {})
