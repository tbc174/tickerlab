"""Café verde por país e ano no FAOSTAT (FAO): produção, área colhida e rendimento (PR 14 do plano de commodities).

O arquivo é o `Production_Crops_Livestock_E_All_Data_(Normalized)` (zip com um CSV longo: uma linha por
país, produto, elemento e ano, desde 1961). A tabela guarda só o "Coffee, green" dos países (os
agregados da FAO, como "World" e "Africa", saem) e os três elementos que o balanço do café usa. A
FAO não diz quando revisou cada número; cada baixada do arquivista é uma "fotografia", e `divulgado_em`
é o dia da baixada (conservador: o número nunca aparece antes de ser guardado). Licença CC BY 4.0, com
crédito no formato da FAO (`licencas-por-fonte.md`).

O FAOSTAT não separa arábica de robusta: o `tipo` é sempre `total`. A separação por tipo vem do USDA PSD.
"""

import io
import zipfile
from datetime import date

import pandas as pd

FONTE = "faostat-cafe"
PRODUTO = "Coffee, green"
TIPO = "total"
# elemento da fonte → (elemento da base, unidade da base, fator por unidade da fonte)
ELEMENTOS = {
    "Production": ("producao", "t", {"t": 1.0}),
    "Area harvested": ("area_colhida", "ha", {"ha": 1.0}),
    "Yield": ("rendimento", "kg/ha", {"kg/ha": 1.0, "hg/ha": 0.1}),
}  # fmt: skip
COLUNAS = (
    "codigo_do_pais", "pais", "ano", "elemento", "tipo", "valor", "unidade", "sinalizador", "divulgado_em",
)  # fmt: skip
CHAVE = ["codigo_do_pais", "ano", "elemento"]
PRIMEIRO_CODIGO_DE_AGREGADO = (
    5000  # na numeração da FAO, a partir daqui são grupos de países
)


def _csv_do_zip(conteudo: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
        nomes = [n for n in arquivo.namelist() if n.lower().endswith(".csv")]
        if len(nomes) != 1:
            raise ValueError(f"FAOSTAT: esperava 1 CSV no zip, achei {len(nomes)}")
        return arquivo.read(nomes[0])


def _fator(elemento: str, unidade_da_fonte: str) -> float:
    fatores = ELEMENTOS[elemento][2]
    if unidade_da_fonte not in fatores:
        raise ValueError(
            f"FAOSTAT: unidade {unidade_da_fonte!r} no elemento {elemento!r}; conferir antes de gravar"
        )
    return fatores[unidade_da_fonte]


def ler(conteudo: bytes, disponivel_em: date) -> pd.DataFrame:
    """O café verde dos países de um zip baixado em `disponivel_em`."""
    bruto = pd.read_csv(
        io.BytesIO(_csv_do_zip(conteudo)),
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    bruto = bruto[(bruto["Item"] == PRODUTO) & bruto["Element"].isin(ELEMENTOS)]
    bruto = bruto[pd.to_numeric(bruto["Area Code"]) < PRIMEIRO_CODIGO_DE_AGREGADO]
    fatores = [
        _fator(e, u) for e, u in zip(bruto["Element"], bruto["Unit"], strict=True)
    ]
    valor = pd.to_numeric(bruto["Value"], errors="coerce") * fatores
    tabela = pd.DataFrame(
        {
            "codigo_do_pais": bruto["Area Code (M49)"].str.replace("'", "").str.strip(),
            "pais": bruto["Area"].str.strip(),
            "ano": bruto["Year"].astype(int),
            "elemento": bruto["Element"].map(lambda e: ELEMENTOS[e][0]),
            "tipo": TIPO,
            "valor": valor,
            "unidade": bruto["Element"].map(lambda e: ELEMENTOS[e][1]),
            "sinalizador": bruto["Flag"].str.strip(),
            "divulgado_em": pd.Timestamp(disponivel_em),
        }
    )
    return tabela.dropna(subset=["valor"]).reset_index(drop=True)[list(COLUNAS)]


def como_estava_em(tabela: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Para cada país, ano e elemento, a versão mais recente que `dia` já conhecia."""
    conhecidas = tabela[tabela["divulgado_em"] <= pd.Timestamp(dia)]
    ordenadas = conhecidas.sort_values("divulgado_em", kind="stable")
    return ordenadas.drop_duplicates(CHAVE, keep="last").reset_index(drop=True)
