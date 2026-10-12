"""Quem tem cada ação da B3 entre os fundos: a carteira mensal dos fundos na CVM (Research R3).

Todo fundo informa à CVM, por mês, o que tem na carteira (CDA, "composição e diversificação das
aplicações"). O arquivo de ações e afins (`cda_fi_BLC_4_AAAAMM.csv`) traz, por fundo e por papel:
a posição no fim do mês (quantidade e valor de mercado) e o que comprou e vendeu no mês.

Três tipos de posição interessam aqui:
- **comprado:** ações (e units) na carteira, inclusive as que o fundo emprestou a outros (continuam
  dele);
- **vendido:** ações tomadas em empréstimo e vendidas ("obrigações por ações recebidas em
  empréstimo"), a aposta na queda. É o equivalente brasileiro do *short interest*, dado pouco
  visto fora do mercado profissional;
- **emprestado:** a parte das ações compradas que está emprestada (sinal de procura por aluguel).

Limites: o arquivo sai cerca de 40 dias depois do mês; um fundo pode manter uma posição em sigilo
por até 90 dias (essas ficam fora daqui); só fundos registrados na CVM (não pessoas físicas nem
estrangeiros diretos). Nomes de fundos são de pessoas jurídicas e aparecem como no cadastro.
"""

import io
import zipfile
from datetime import date

import pandas as pd

from src.detentores import (
    COLUNAS_DO_RESUMO,
    COLUNAS_DOS_MAIORES,
    COMPRADO,
    EMPRESTADO,
    MAIORES,
    VENDIDO,
)

FONTE_CDA = "cvm_cda"
URL_DO_CDA = "https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{ano}{mes:02d}.zip"
CODIFICACAO_DA_CVM = "cp1252"
TIPOS = {
    "Ações": COMPRADO,
    "Certificado ou recibo de depósito de valores mobiliários": COMPRADO,  # units
    "Ações e outros TVM cedidos em empréstimo": EMPRESTADO,
    "Obrigações por ações e outros TVM recebidos em empréstimo": VENDIDO,
}
CODIGO_DA_B3 = r"[A-Z]{4}\d{1,2}"


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0.0)


def ler_posicoes(conteudo_do_zip: bytes) -> pd.DataFrame:
    """As posições em ações da B3 de todos os fundos num arquivo mensal do CDA.

    Colunas: competencia, cnpj_fundo, fundo, codigo, tipo, quantidade, valor, compras, vendas.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nomes = [n for n in arquivo.namelist() if "_BLC_4_" in n]
        if not nomes:
            return pd.DataFrame()
        bruto = pd.read_csv(
            arquivo.open(nomes[0]),
            sep=";",
            encoding=CODIFICACAO_DA_CVM,
            encoding_errors="replace",
            dtype=str,
            keep_default_na=False,
            usecols=[
                "CNPJ_FUNDO_CLASSE", "DENOM_SOCIAL", "DT_COMPTC", "TP_APLIC", "CD_ATIVO",
                "QT_POS_FINAL", "VL_MERC_POS_FINAL", "VL_AQUIS_NEGOC", "VL_VENDA_NEGOC",
            ],
        )  # fmt: skip
    bruto = bruto[
        bruto["TP_APLIC"].isin(TIPOS) & bruto["CD_ATIVO"].str.fullmatch(CODIGO_DA_B3)
    ]
    return pd.DataFrame(
        {
            "competencia": pd.to_datetime(bruto["DT_COMPTC"], errors="coerce").dt.date,
            "cnpj_fundo": bruto["CNPJ_FUNDO_CLASSE"].str.strip(),
            "fundo": bruto["DENOM_SOCIAL"].str.strip().str[:200],
            "codigo": bruto["CD_ATIVO"].str.strip(),
            "tipo": bruto["TP_APLIC"].map(TIPOS),
            "quantidade": _numero(bruto["QT_POS_FINAL"]),
            "valor": _numero(bruto["VL_MERC_POS_FINAL"]),
            "compras": _numero(bruto["VL_AQUIS_NEGOC"]),
            "vendas": _numero(bruto["VL_VENDA_NEGOC"]),
        }
    ).dropna(subset=["competencia"])


def _comprados(posicoes: pd.DataFrame) -> pd.DataFrame:
    """Comprado + emprestado de cada fundo e papel (a ação emprestada continua sendo do fundo)."""
    donos = posicoes[posicoes["tipo"].isin([COMPRADO, EMPRESTADO])]
    return donos.groupby(
        ["competencia", "codigo", "cnpj_fundo", "fundo"], as_index=False
    )[["quantidade", "valor", "compras", "vendas"]].sum()


def resumir(posicoes: pd.DataFrame) -> pd.DataFrame:
    """Por mês e ação: quantos fundos têm, quanto têm, quantos estão vendidos e quanto, quanto
    está emprestado e quanto foi comprado e vendido no mês."""
    if posicoes.empty:
        return pd.DataFrame(columns=COLUNAS_DO_RESUMO)
    chave = ["competencia", "codigo"]
    comprados = _comprados(posicoes)
    resumo = comprados.groupby(chave).agg(
        detentores=("cnpj_fundo", "nunique"),
        valor=("valor", "sum"),
        quantidade=("quantidade", "sum"),
        compras_no_mes=("compras", "sum"),
        vendas_no_mes=("vendas", "sum"),
    )
    vendidos = (
        posicoes[posicoes["tipo"] == VENDIDO]
        .groupby(chave)
        .agg(vendidos=("cnpj_fundo", "nunique"), valor_vendido=("valor", "sum"))
    )
    emprestados = (
        posicoes[posicoes["tipo"] == EMPRESTADO]
        .groupby(chave)["valor"]
        .sum()
        .rename("valor_emprestado")
    )
    resumo = (
        resumo.join(vendidos, how="outer").join(emprestados, how="outer").fillna(0.0)
    )
    resumo["detentores"] = resumo["detentores"].astype(int)
    resumo["vendidos"] = resumo["vendidos"].astype(int)
    resumo = resumo.reset_index().assign(fonte=FONTE_CDA)
    return resumo[COLUNAS_DO_RESUMO]


def maiores(posicoes: pd.DataFrame, quantos: int = MAIORES) -> pd.DataFrame:
    """Os maiores fundos comprados e vendidos de cada ação, por mês (posição 1 = o maior)."""
    if posicoes.empty:
        return pd.DataFrame(columns=COLUNAS_DOS_MAIORES)
    comprados = _comprados(posicoes).assign(tipo=COMPRADO)
    vendidos = posicoes[posicoes["tipo"] == VENDIDO][
        ["competencia", "codigo", "cnpj_fundo", "fundo", "quantidade", "valor"]
    ].assign(tipo=VENDIDO)
    juntos = pd.concat([comprados, vendidos], ignore_index=True)
    juntos = juntos.sort_values("valor", ascending=False)
    juntos["posicao"] = juntos.groupby(["competencia", "codigo", "tipo"]).cumcount() + 1
    juntos = juntos[juntos["posicao"] <= quantos]
    tabela = juntos.rename(columns={"fundo": "nome", "cnpj_fundo": "documento"}).assign(
        fonte=FONTE_CDA
    )
    return tabela[COLUNAS_DOS_MAIORES].reset_index(drop=True)


def meses_recentes(hoje: date, quantos: int) -> list[tuple[int, int]]:
    """(ano, mês) dos `quantos` meses anteriores a `hoje`, do mais recente ao mais antigo."""
    ano, mes = hoje.year, hoje.month
    meses = []
    for _ in range(quantos):
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
        meses.append((ano, mes))
    return meses
