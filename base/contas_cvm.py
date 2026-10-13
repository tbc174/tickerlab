"""Todas as contas das demonstrações da CVM, como vieram nos CSVs originais (série 1, PR 1).

O leitor do app (`src/demonstracoes.py`) guarda só as contas que as telas usam e, na DFP, descarta a
coluna do ano anterior. As regras de qualidade (`base/regras.py`) precisam do plano de contas
inteiro e das duas colunas ("último" e "penúltimo" exercício), por isso leem daqui. Regras:

- **Valor em reais:** a CVM informa a escala de cada linha (`MIL` ou `UNIDADE`); escala desconhecida
  é recusada, porque um valor mil vezes errado é o pior erro possível na base.
- **Linhas repetidas idênticas** (1,7% da DFP 2022 e 2,9% da DFP 2023, medido em 13/10/2026) saem,
  mas são contadas por documento: viram a regra R9 do selo.
- **Nada é escolhido aqui:** todas as versões que o arquivo trouxer ficam; escolher a versão é
  trabalho de quem chama.
"""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

import pandas as pd

CODIFICACAO_DA_CVM = "latin-1"
ESCALAS = {"MIL": 1000.0, "UNIDADE": 1.0}
# dfp_cia_aberta_DRE_con_2022.csv, itr_cia_aberta_BPP_ind_2026.csv...
ARQUIVO_DE_DEMONSTRACAO = re.compile(
    r"_(BPA|BPP|DRE|DFC_MD|DFC_MI)_(con|ind)_\d{4}\.csv$"
)
COLUNAS = (
    "cnpj",
    "empresa",
    "documento",
    "referencia",
    "versao",
    "demonstracao",
    "grupo",
    "ordem",
    "inicio",
    "fim",
    "conta",
    "descricao",
    "conta_fixa",
    "valor",
)
CHAVE_DO_DOCUMENTO = ["cnpj", "referencia", "demonstracao", "grupo"]


@dataclass(frozen=True)
class LeituraDeContas:
    contas: pd.DataFrame  # colunas em COLUNAS
    repetidas: pd.DataFrame  # CHAVE_DO_DOCUMENTO + "linhas" (quantas repetidas saíram)


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


def _ler_csv(arquivo: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    return pd.read_csv(
        arquivo.open(nome),
        sep=";",
        encoding=CODIFICACAO_DA_CVM,
        encoding_errors="replace",
        dtype=str,
        keep_default_na=False,
    )


def _normalizar(
    bruto: pd.DataFrame, documento: str, demonstracao: str, grupo: str
) -> pd.DataFrame:
    escalas = bruto["ESCALA_MOEDA"].str.upper().str.strip()
    desconhecidas = sorted(set(escalas) - set(ESCALAS))
    if desconhecidas:
        raise ValueError(f"escala desconhecida na CVM: {', '.join(desconhecidas)}")
    inicio = (
        bruto["DT_INI_EXERC"]
        if "DT_INI_EXERC" in bruto
        else pd.Series("", index=bruto.index)
    )
    return pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_CIA"],
            "empresa": bruto["DENOM_CIA"],
            "documento": documento,
            "referencia": pd.to_datetime(bruto["DT_REFER"], errors="coerce"),
            "versao": pd.to_numeric(bruto["VERSAO"], errors="coerce").astype("Int64"),
            "demonstracao": demonstracao,
            "grupo": grupo,
            "ordem": bruto["ORDEM_EXERC"].map(_sem_acento),
            "inicio": pd.to_datetime(inicio, errors="coerce"),
            "fim": pd.to_datetime(bruto["DT_FIM_EXERC"], errors="coerce"),
            "conta": bruto["CD_CONTA"],
            "descricao": bruto["DS_CONTA"],
            "conta_fixa": bruto["ST_CONTA_FIXA"].eq("S"),
            "valor": pd.to_numeric(bruto["VL_CONTA"], errors="coerce")
            * escalas.map(ESCALAS),
        },
        columns=list(COLUNAS),
    )


def ler_contas(zip_bytes: bytes, documento: str) -> LeituraDeContas:
    """Todas as contas de BPA, BPP, DRE e DFC (individual e consolidado) de um zip da CVM.

    `documento` é "DFP" ou "ITR". As linhas repetidas idênticas saem e são contadas por documento.
    """
    partes: list[pd.DataFrame] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as arquivo:
        for nome in sorted(arquivo.namelist()):
            achado = ARQUIVO_DE_DEMONSTRACAO.search(nome)
            if achado:
                bruto = _ler_csv(arquivo, nome)
                partes.append(_normalizar(bruto, documento, *achado.groups()))
    if not partes:
        vazio = pd.DataFrame(columns=list(COLUNAS))
        return LeituraDeContas(
            vazio, pd.DataFrame(columns=[*CHAVE_DO_DOCUMENTO, "linhas"])
        )
    contas = pd.concat(partes, ignore_index=True)
    repetida = contas.duplicated(keep="first")
    repetidas = (
        contas[repetida]
        .groupby(CHAVE_DO_DOCUMENTO)
        .size()
        .rename("linhas")
        .reset_index()
    )
    return LeituraDeContas(contas[~repetida].reset_index(drop=True), repetidas)
