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
- **Só as contas das regras** (`so_as_das_regras=True`, PR 3): BPA e BPP inteiros e o primeiro nível
  da DRE (receita, lucro); a DFC e o detalhe da DRE ficam de fora. O ITR inteiro ocupava 741 MB
  na leitura, mais que o contêiner do VPS (768 MB, dividido com o app). As repetidas continuam
  contadas em todas as demonstrações.
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
# as colunas do CSV que a leitura usa (o resto, como CD_CVM e MOEDA, nem entra na memória)
COLUNAS_DO_CSV = {
    "CNPJ_CIA",
    "DENOM_CIA",
    "DT_REFER",
    "VERSAO",
    "ESCALA_MOEDA",
    "ORDEM_EXERC",
    "DT_INI_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
    "ST_CONTA_FIXA",
}
BALANCO = ("BPA", "BPP")
DRE = "DRE"


@dataclass(frozen=True)
class LeituraDeContas:
    contas: pd.DataFrame  # colunas em COLUNAS
    repetidas: pd.DataFrame  # CHAVE_DO_DOCUMENTO + "linhas" (quantas repetidas saíram)


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


def _ler_csv(
    arquivo: zipfile.ZipFile, nome: str, colunas: set[str] | None = COLUNAS_DO_CSV
) -> pd.DataFrame:
    return pd.read_csv(
        arquivo.open(nome),
        sep=";",
        encoding=CODIFICACAO_DA_CVM,
        encoding_errors="replace",
        dtype=str,
        keep_default_na=False,
        usecols=None if colunas is None else lambda coluna: coluna in colunas,
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


def so_as_contas_das_regras(contas: pd.DataFrame) -> pd.DataFrame:
    """BPA e BPP inteiros (subtotais da R2 e da R11) e o primeiro nível da DRE.

    Vale para contas de qualquer fonte (os CSVs ou o ENET): a base "como era na data" precisa do
    mesmo recorte em todas, senão uma conta que só uma fonte traz nunca seria substituída.
    """
    demonstracao = contas["demonstracao"]
    primeiro_nivel = contas["conta"].str.count(r"\.") <= 1
    return contas[demonstracao.isin(BALANCO) | ((demonstracao == DRE) & primeiro_nivel)]


def _contar_repetidas(contas: pd.DataFrame) -> pd.DataFrame:
    return contas.groupby(CHAVE_DO_DOCUMENTO).size().rename("linhas").reset_index()


def ler_contas(
    zip_bytes: bytes, documento: str, so_as_das_regras: bool = False
) -> LeituraDeContas:
    """Todas as contas de BPA, BPP, DRE e DFC (individual e consolidado) de um zip da CVM.

    `documento` é "DFP" ou "ITR". As linhas repetidas idênticas saem e são contadas por documento
    (cada CSV é uma demonstração, então as repetidas são procuradas dentro dele).
    `so_as_das_regras`: só as contas que `base/regras.py` usa, para caber na memória do VPS.
    """
    partes: list[pd.DataFrame] = []
    repetidas: list[pd.DataFrame] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as arquivo:
        for nome in sorted(arquivo.namelist()):
            achado = ARQUIVO_DE_DEMONSTRACAO.search(nome)
            if not achado:
                continue
            parte = _normalizar(_ler_csv(arquivo, nome), documento, *achado.groups())
            repetida = parte.duplicated(keep="first")
            repetidas.append(_contar_repetidas(parte[repetida]))
            parte = parte[~repetida]
            if so_as_das_regras:
                parte = so_as_contas_das_regras(parte)
            partes.append(parte)
    if not partes:
        vazio = pd.DataFrame(columns=list(COLUNAS))
        return LeituraDeContas(vazio, _contar_repetidas(vazio))
    contas = pd.concat(partes, ignore_index=True)
    return LeituraDeContas(contas, pd.concat(repetidas, ignore_index=True))


def ler_indice(zip_bytes: bytes, documento: str) -> pd.DataFrame:
    """Todas as entregas (versões) do índice de um zip de DFP ou ITR, com a data de entrega.

    Colunas: cnpj, empresa, documento, referencia, versao, recebido_em, link (o pacote no ENET).
    """
    colunas = [
        "cnpj",
        "empresa",
        "documento",
        "referencia",
        "versao",
        "recebido_em",
        "link",
    ]
    nome_do_indice = re.compile(rf"^{documento.lower()}_cia_aberta_\d{{4}}\.csv$")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as arquivo:
        nomes = [n for n in arquivo.namelist() if nome_do_indice.match(n)]
        if not nomes:
            return pd.DataFrame(columns=colunas)
        bruto = _ler_csv(arquivo, nomes[0], colunas=None)
    return pd.DataFrame(
        {
            "cnpj": bruto["CNPJ_CIA"],
            "empresa": bruto["DENOM_CIA"],
            "documento": documento,
            "referencia": pd.to_datetime(bruto["DT_REFER"], errors="coerce"),
            "versao": pd.to_numeric(bruto["VERSAO"], errors="coerce").astype("Int64"),
            "recebido_em": pd.to_datetime(bruto["DT_RECEB"], errors="coerce"),
            "link": bruto["LINK_DOC"],
        },
        columns=colunas,
    )
