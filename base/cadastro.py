"""Cadastro histórico das companhias abertas e dos tickers (série 1 da base de ML, PR 8).

ADR 0027, exigência 4: **sem viés de sobrevivência**. Uma base só com as empresas de hoje esconde
as que quebraram, foram compradas ou fecharam o capital, e qualquer modelo treinado nela parece
melhor do que é. Aqui ficam as que saíram, com a data e o motivo, e cada ticker com o período em
que existiu:

- `ler_cadastro`: cada registro do `cad_cia_aberta.csv` da CVM (uma empresa pode ter mais de um),
  com registro, cancelamento, motivo, situação e setor.
- `tickers_no_tempo`: cada código de negociação da B3 (bolsa) com a empresa, o primeiro e o último
  FCA em que apareceu e as datas de início e fim de negociação que a empresa informou. Junta todos
  os anos do FCA, sem ficar só com o mais recente: um código que sumiu continua aqui.
- `cobertura_das_canceladas`: das que saíram num período, quais a base tem (a prova da exigência 4).
"""

import io
import zipfile
from collections.abc import Iterable

import pandas as pd

CODIFICACAO_DA_CVM = "latin-1"
CODIGO_DE_ACAO = (
    r"[A-Z][A-Z0-9]{3}\d{1,2}"  # PETR4, TAEE11, B3SA3 (o emissor pode ter número)
)
COLUNAS_DOS_TICKERS = (
    "codigo",
    "cnpj",
    "empresa",
    "valor_mobiliario",
    "primeiro_visto",
    "ultimo_visto",
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
    setor. Sem as colunas de data (arquivo antigo ou recortado), vale a situação: cancelada conta
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


def _valores_mobiliarios(conteudo_do_zip: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nomes = [n for n in arquivo.namelist() if "valor_mobiliario" in n]
        if not nomes:
            return pd.DataFrame()
        return _ler_csv(io.BytesIO(arquivo.read(nomes[0])))


def tickers_no_tempo(conteudos_dos_zips: Iterable[bytes]) -> pd.DataFrame:
    """Cada código de ação da B3 (bolsa) com a empresa e o período em que existiu.

    Uma linha por (código, CNPJ): o mesmo código pode ter passado de uma empresa para outra.
    """
    partes = [_valores_mobiliarios(c) for c in conteudos_dos_zips]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_DOS_TICKERS))
    bruto = pd.concat(partes, ignore_index=True)
    bruto = bruto[
        bruto["Sigla_Entidade_Administradora"].str.upper().eq("B3")
        & bruto["Mercado"].str.lower().eq("bolsa")
        & bruto["Codigo_Negociacao"].str.fullmatch(CODIGO_DE_ACAO)
    ]
    tabela = pd.DataFrame(
        {
            "codigo": bruto["Codigo_Negociacao"],
            "cnpj": bruto["CNPJ_Companhia"].str.strip(),
            "empresa": bruto["Nome_Empresarial"].str.strip(),
            "valor_mobiliario": bruto["Valor_Mobiliario"].str.strip(),
            "referencia": pd.to_datetime(bruto["Data_Referencia"], errors="coerce"),
            "inicio": pd.to_datetime(bruto["Data_Inicio_Negociacao"], errors="coerce"),
            "fim": pd.to_datetime(bruto["Data_Fim_Negociacao"], errors="coerce"),
        }
    ).sort_values("referencia")
    grupos = tabela.groupby(["codigo", "cnpj"], sort=True)
    return (
        grupos.agg(
            empresa=("empresa", "last"),
            valor_mobiliario=("valor_mobiliario", "last"),
            primeiro_visto=("referencia", "min"),
            ultimo_visto=("referencia", "max"),
            inicio_negociacao=("inicio", "min"),
            fim_negociacao=("fim", "max"),
        )
        .reset_index()
        .reindex(columns=list(COLUNAS_DOS_TICKERS))
    )
