"""Cadastro histórico das companhias abertas e dos tickers (série 1 da base de ML, PR 8).

ADR 0027, exigência 4: **sem viés de sobrevivência**. Uma base só com as empresas de hoje esconde
as que quebraram, foram compradas ou fecharam o capital, e qualquer modelo treinado nela parece
melhor do que é. Aqui ficam as que saíram, com a data e o motivo, e cada ticker com o período em
que existiu:

- `ler_cadastro`: cada registro do `cad_cia_aberta.csv` da CVM (uma empresa pode ter mais de um),
  com registro, cancelamento, motivo, situação e setor.
- `tickers_no_tempo`: cada código de negociação da B3 (bolsa) com a empresa, de quando a quando
  valeu (pelas datas de entrega do FCA; série 4, PR 1) e as datas de início e fim de negociação que
  a empresa informou. Junta todos os anos do FCA, sem ficar só com o mais recente: um código que
  sumiu continua aqui.
- `cobertura_das_canceladas`: das que saíram num período, quais a base tem (a prova da exigência 4).
"""

import io
from collections.abc import Iterable

import pandas as pd

from base import fca

CODIFICACAO_DA_CVM = "latin-1"
COLUNAS_DOS_TICKERS = (
    "codigo",
    "cnpj",
    "empresa",
    "valor_mobiliario",
    "primeiro_visto",
    "ultimo_visto",
    "valido_ate",
    "inicio_negociacao",
    "fim_negociacao",
)


def _ler_csv(arquivo: io.BytesIO | bytes) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(arquivo) if isinstance(arquivo, bytes) else arquivo,
        sep=";",
        encoding=CODIFICACAO_DA_CVM,
        encoding_errors="replace",
        dtype=str,
        keep_default_na=False,
    )


def _texto(bruto: pd.DataFrame, coluna: str) -> pd.Series:
    """A coluna sem espaços nas pontas, ou vazia se o arquivo não a tem (cadastro antigo)."""
    if coluna not in bruto:
        return pd.Series("", index=bruto.index)
    return bruto[coluna].str.strip()


def ler_cadastro(conteudo_csv: bytes) -> pd.DataFrame:
    """Cada registro de companhia aberta, com as datas de registro e de cancelamento.

    Colunas: cnpj, empresa, registro, cancelamento (vazio = ativa), motivo_cancelamento, situacao,
    setor e uf (da sede, em maiúsculas; vazia no arquivo antigo). A UF é a do cadastro de hoje: uma
    mudança de sede não deixa rastro. Sem as colunas de data (arquivo antigo ou recortado), vale a situação: cancelada conta
    como cancelada desde sempre.
    """
    bruto = _ler_csv(conteudo_csv)
    cancelamento = pd.to_datetime(_texto(bruto, "DT_CANCEL"), errors="coerce")
    situacao = _texto(bruto, "SIT").str.upper()
    if "DT_CANCEL" not in bruto:
        cancelamento = cancelamento.mask(situacao.ne("ATIVO"), pd.Timestamp.min)
    return pd.DataFrame(
        {
            "cnpj": _texto(bruto, "CNPJ_CIA"),
            "empresa": _texto(bruto, "DENOM_SOCIAL"),
            "registro": pd.to_datetime(_texto(bruto, "DT_REG"), errors="coerce"),
            "cancelamento": cancelamento,
            "motivo_cancelamento": _texto(bruto, "MOTIVO_CANCEL"),
            "situacao": situacao,
            "setor": _texto(bruto, "SETOR_ATIV"),
            "uf": _texto(bruto, "UF").str.upper(),
        }
    )


def canceladas(
    cadastro: pd.DataFrame, desde: object, ate: object = None
) -> pd.DataFrame:
    """Os registros cancelados no período (`ate` vazio = até hoje)."""
    inicio = pd.Timestamp(desde)  # type: ignore[arg-type]
    fim = pd.Timestamp.max if ate is None else pd.Timestamp(ate)  # type: ignore[arg-type]
    no_periodo = (cadastro["cancelamento"] >= inicio) & (
        cadastro["cancelamento"] <= fim
    )
    return cadastro[no_periodo].reset_index(drop=True)


def cobertura_das_canceladas(
    cnpjs_na_base: Iterable[str],
    cadastro: pd.DataFrame,
    desde: object,
    ate: object = None,
) -> pd.DataFrame:
    """Das empresas que saíram no período, quais estão na base (índice: cnpj; coluna `na_base`).

    `attrs["proporcao_na_base"]` resume: 1,0 = nenhuma que saiu ficou de fora.
    """
    presentes = set(cnpjs_na_base)
    saidas = canceladas(cadastro, desde, ate).drop_duplicates("cnpj").set_index("cnpj")
    cobertura = saidas[["empresa", "cancelamento", "motivo_cancelamento"]].assign(
        na_base=[cnpj in presentes for cnpj in saidas.index]
    )
    cobertura.attrs["proporcao_na_base"] = (
        float(cobertura["na_base"].mean()) if len(cobertura) else 1.0
    )
    return cobertura


def _acoes_da_bolsa(valores: pd.DataFrame) -> pd.DataFrame:
    """As linhas com código de ação da B3 negociada em bolsa (PETR4, TAEE11, B3SA3)."""
    return valores[
        valores["administradora"].str.upper().eq("B3")
        & valores["mercado"].str.lower().eq("bolsa")
        & valores["ticker"].notna()
    ]


def tickers_no_tempo(conteudos_dos_zips: Iterable[bytes]) -> pd.DataFrame:
    """Cada código de ação da B3 (bolsa) com a empresa e de quando a quando valeu.

    Uma linha por período de (código, CNPJ): o mesmo código pode ter passado de uma empresa para
    outra, ou sumido e voltado. `primeiro_visto` e `ultimo_visto` são as entregas do primeiro e do
    último formulário vigente com o código; `valido_ate`, a do formulário que passou a valer sem ele
    (vazio: ainda no mais recente). Qual formulário vale em cada data: `fca.formularios_vigentes`.
    """
    partes = [fca.ler_valores_mobiliarios(c) for c in conteudos_dos_zips]
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DOS_TICKERS))
    valores = pd.concat(partes, ignore_index=True)
    acoes = _acoes_da_bolsa(valores).merge(
        fca.formularios_vigentes(valores), on=["cnpj", "id_documento", "recebido_em"]
    )
    if acoes.empty:
        return pd.DataFrame(columns=list(COLUNAS_DOS_TICKERS))
    acoes = acoes.sort_values(["ticker", "cnpj", "ordem"])
    # um período segue enquanto o código está em formulários vigentes seguidos (0: duas linhas
    # do mesmo formulário)
    salto = acoes.groupby(["ticker", "cnpj"])["ordem"].diff()
    acoes["periodo"] = (~salto.isin([0, 1])).cumsum()
    return (
        acoes.groupby(["ticker", "cnpj", "periodo"], sort=True)
        .agg(
            empresa=("empresa", "last"),
            valor_mobiliario=("valor_mobiliario", "last"),
            primeiro_visto=("recebido_em", "min"),
            ultimo_visto=("recebido_em", "max"),
            # o do último formulário, vazio inclusive ("last" pularia o vazio)
            valido_ate=("ate", lambda ate: ate.iloc[-1]),
            inicio_negociacao=("inicio_negociacao", "min"),
            fim_negociacao=("fim_negociacao", "max"),
        )
        .reset_index()
        .rename(columns={"ticker": "codigo"})
        .reindex(columns=list(COLUNAS_DOS_TICKERS))
    )
