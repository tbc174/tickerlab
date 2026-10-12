"""Quem tem cada ação dos EUA entre os grandes gestores: o Form 13F da SEC (Research R3).

Todo gestor com mais de US$ 100 milhões em ações dos EUA entrega à SEC, por trimestre, o 13F com
as posições do fim do trimestre (até 45 dias depois). A SEC publica tudo junto em bases
trimestrais (`form13f.zip`): `SUBMISSION` (quem entregou e o trimestre), `COVERPAGE` (nome do
gestor, se é retificação) e `INFOTABLE` (cada posição: CUSIP do papel, quantidade e valor).

O 13F identifica o papel pelo **CUSIP**, não pelo ticker. A ligação vem dos arquivos de "falhas
de entrega" da SEC (`cnsfails`), que trazem os dois; juntando alguns meses, cobre quase todo o
S&P 500. Um papel sem ligação fica de fora (e a tela diz isso).

Limites: só posições **compradas** (o 13F não mostra vendas a descoberto); opções (PUT/CALL) e
títulos de dívida ficam de fora; retificações (13F-HR/A) não entram; o atraso é de até 45 dias.
O nome é o do gestor (pessoa jurídica), como na SEC.
"""

import io
import re
import zipfile
from collections.abc import Iterable

import pandas as pd

from src.detentores import COLUNAS_DO_RESUMO, COLUNAS_DOS_MAIORES, COMPRADO, MAIORES

FONTE_13F = "sec_13f"
URL_DA_PAGINA_DO_13F = (
    "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
)
URL_DA_PAGINA_DAS_FALHAS = (
    "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
)
URL_DA_SEC = "https://www.sec.gov"
PEDACO = 200_000  # linhas lidas por vez da INFOTABLE (~400 MB descompactada): cabe no contêiner
COLUNAS_DA_TABELA = [
    "ACCESSION_NUMBER",
    "CUSIP",
    "VALUE",
    "SSHPRNAMT",
    "SSHPRNAMTTYPE",
    "PUTCALL",
]


def ler_mapa_de_cusips(
    arquivos_zip: Iterable[bytes], tickers: set[str]
) -> dict[str, str]:
    """CUSIP → ticker (no formato do Yahoo: BRK.B vira BRK-B) só para os tickers pedidos."""
    mapa: dict[str, str] = {}
    for conteudo in arquivos_zip:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
            tabela = pd.read_csv(
                arquivo.open(arquivo.namelist()[0]),
                sep="|",
                dtype=str,
                usecols=["CUSIP", "SYMBOL"],
                encoding_errors="replace",
                keep_default_na=False,
            )
        tabela["ticker"] = (
            tabela["SYMBOL"].str.strip().str.replace(".", "-", regex=False)
        )
        tabela = tabela[tabela["ticker"].isin(tickers)]
        mapa.update(zip(tabela["CUSIP"].str.strip(), tabela["ticker"], strict=True))
    return mapa


def _gestores(arquivo: zipfile.ZipFile, competencia: pd.Timestamp) -> pd.DataFrame:
    """Os 13F originais (não retificações) do trimestre: protocolo → CIK e nome do gestor."""
    envios = pd.read_csv(
        arquivo.open("SUBMISSION.tsv"), sep="\t", dtype=str, keep_default_na=False
    )
    capas = pd.read_csv(
        arquivo.open("COVERPAGE.tsv"),
        sep="\t",
        dtype=str,
        keep_default_na=False,
        usecols=["ACCESSION_NUMBER", "ISAMENDMENT", "FILINGMANAGER_NAME"],
    )
    envios["periodo"] = pd.to_datetime(
        envios["PERIODOFREPORT"], format="%d-%b-%Y", errors="coerce"
    )
    juntos = envios.merge(capas, on="ACCESSION_NUMBER")
    juntos = juntos[
        (juntos["SUBMISSIONTYPE"] == "13F-HR")
        & (juntos["ISAMENDMENT"] != "Y")
        & (juntos["periodo"] == competencia)
    ]
    return juntos.rename(
        columns={
            "ACCESSION_NUMBER": "protocolo",
            "CIK": "cik",
            "FILINGMANAGER_NAME": "nome",
        }
    )[["protocolo", "cik", "nome"]]


def trimestre_da_base(conteudo_do_zip: bytes) -> str:
    """O trimestre (AAAA-MM-DD) da maioria dos 13F originais de uma base: cada base junta os
    entregues em três meses, quase todos sobre o mesmo trimestre."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        envios = pd.read_csv(
            arquivo.open("SUBMISSION.tsv"), sep="	", dtype=str, keep_default_na=False
        )
    originais = envios[envios["SUBMISSIONTYPE"] == "13F-HR"]
    periodos = pd.to_datetime(
        originais["PERIODOFREPORT"], format="%d-%b-%Y", errors="coerce"
    )
    if periodos.dropna().empty:
        raise ValueError("Base do 13F sem trimestre reconhecível.")
    return f"{periodos.mode().iloc[0]:%Y-%m-%d}"


def ler_posicoes(
    conteudo_do_zip: bytes, competencia: str, mapa: dict[str, str]
) -> pd.DataFrame:
    """As posições dos gestores nas ações do mapa, no fim do trimestre `competencia` (AAAA-MM-DD).

    Colunas: competencia, cnpj_fundo (o CIK do gestor), fundo (o nome), codigo, tipo, quantidade,
    valor, compras, vendas (as duas últimas zeradas: o 13F não informa o que foi negociado).
    """
    data = pd.Timestamp(competencia)
    partes = []
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        gestores = _gestores(arquivo, data).set_index("protocolo")
        leitor = pd.read_csv(
            arquivo.open("INFOTABLE.tsv"),
            sep="\t",
            dtype=str,
            keep_default_na=False,
            usecols=COLUNAS_DA_TABELA,
            chunksize=PEDACO,
        )
        for pedaco in leitor:
            escolhidas = pedaco[
                pedaco["CUSIP"].isin(mapa)
                & (pedaco["SSHPRNAMTTYPE"] == "SH")
                & (pedaco["PUTCALL"] == "")
                & pedaco["ACCESSION_NUMBER"].isin(gestores.index)
            ]
            # só o necessário, em formato compacto: o pedaço bruto é descartado a cada volta
            partes.append(
                pd.DataFrame(
                    {
                        "protocolo": escolhidas["ACCESSION_NUMBER"].astype("category"),
                        "codigo": escolhidas["CUSIP"].map(mapa).astype("category"),
                        "quantidade": pd.to_numeric(
                            escolhidas["SSHPRNAMT"], errors="coerce"
                        ),
                        "valor": pd.to_numeric(escolhidas["VALUE"], errors="coerce"),
                    }
                )
            )
    tabela = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if tabela.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "competencia": data.date(),
            "cnpj_fundo": tabela["protocolo"].map(gestores["cik"]),
            "fundo": tabela["protocolo"].map(gestores["nome"].str.strip().str[:200]),
            "codigo": tabela["codigo"],
            "tipo": COMPRADO,
            "quantidade": tabela["quantidade"].fillna(0.0),
            "valor": tabela["valor"].fillna(0.0),
            "compras": 0.0,
            "vendas": 0.0,
        }
    )


def resumir(posicoes: pd.DataFrame) -> pd.DataFrame:
    """Por trimestre e ação: quantos gestores têm e quanto (sem vendidos nem emprestados)."""
    if posicoes.empty:
        return pd.DataFrame(columns=COLUNAS_DO_RESUMO)
    por_gestor = posicoes.groupby(
        ["competencia", "codigo", "cnpj_fundo"], as_index=False
    )[["quantidade", "valor"]].sum()
    resumo = por_gestor.groupby(["competencia", "codigo"], as_index=False).agg(
        detentores=("cnpj_fundo", "nunique"),
        valor=("valor", "sum"),
        quantidade=("quantidade", "sum"),
    )
    resumo = resumo.assign(
        fonte=FONTE_13F, vendidos=0, valor_vendido=0.0, valor_emprestado=0.0,
        compras_no_mes=0.0, vendas_no_mes=0.0,
    )  # fmt: skip
    return resumo[COLUNAS_DO_RESUMO]


def maiores(posicoes: pd.DataFrame, quantos: int = MAIORES) -> pd.DataFrame:
    """Os maiores gestores de cada ação no trimestre (posição 1 = o maior)."""
    if posicoes.empty:
        return pd.DataFrame(columns=COLUNAS_DOS_MAIORES)
    por_gestor = posicoes.groupby(
        ["competencia", "codigo", "cnpj_fundo", "fundo"], as_index=False
    )[["quantidade", "valor"]].sum()
    por_gestor = por_gestor.sort_values("valor", ascending=False)
    por_gestor["posicao"] = por_gestor.groupby(["competencia", "codigo"]).cumcount() + 1
    por_gestor = por_gestor[por_gestor["posicao"] <= quantos]
    tabela = por_gestor.rename(
        columns={"fundo": "nome", "cnpj_fundo": "documento"}
    ).assign(fonte=FONTE_13F, tipo=COMPRADO)
    return tabela[COLUNAS_DOS_MAIORES].reset_index(drop=True)


def links_da_pagina(html: str, contem: str) -> list[str]:
    """Os links (absolutos) de uma página da SEC que contêm `contem`, na ordem da página."""
    caminhos = re.findall(r'href="([^"]*' + re.escape(contem) + r'[^"]*\.zip)"', html)
    return [
        c if c.startswith("http") else URL_DA_SEC + c for c in dict.fromkeys(caminhos)
    ]
