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
- `conferir_canceladas`: a conferência medida (critério de pronto do modelo 8): cada cancelada ×
  cada tabela, separando o que a fonte nunca publicou do que a montagem perdeu.
- `cadastro_do_acervo`: o `cad_cia_aberta.csv` mais recente guardado pelo arquivista, com a origem.
"""

import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import pandas as pd
import sqlalchemy as sa

from base import fca
from src import acervo
from src.banco.coletas import originais_mais_recentes

CODIFICACAO_DA_CVM = "latin-1"
FONTE_DO_CADASTRO = "cvm-cadastros"
ARQUIVO_DO_CADASTRO = "cad_cia_aberta.csv"
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


def cadastro_do_acervo(
    conexao: sa.Connection,
) -> tuple[pd.DataFrame, dict[str, str]] | None:
    """O cadastro mais recente do acervo (`ler_cadastro`) e a origem (`url`, `sha256`) para o
    manifesto; None se o arquivista ainda não o guardou."""
    for original in originais_mais_recentes(conexao, FONTE_DO_CADASTRO):
        if original.url.rsplit("/", 1)[-1] != ARQUIVO_DO_CADASTRO:
            continue
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is not None:
            return ler_cadastro(conteudo), {
                "url": original.url,
                "sha256": original.sha256,
            }
    return None


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


NA_TABELA = "na_tabela"
ANTES_DA_TABELA = "saiu_antes_da_tabela"
SEM_DOCUMENTO_NA_FONTE = "sem_documento_na_fonte"
EXPLICADA = "explicada_a_mao"
PERDIDA = "perdida_na_montagem"


@dataclass(frozen=True)
class FonteETabela:
    """Os CNPJs com algum documento no original da CVM e os que estão na tabela da base."""

    na_fonte: set[str]
    na_tabela: set[str]
    comeca_em: object  # o primeiro prazo (ou documento) que a fonte cobre


def _situacao(
    cnpj: str, cancelamento: pd.Timestamp, conferir: FonteETabela, explicada: bool
) -> str:
    if cnpj in conferir.na_tabela:
        return NA_TABELA
    if cancelamento <= pd.Timestamp(conferir.comeca_em):  # type: ignore[arg-type]
        return ANTES_DA_TABELA
    if cnpj not in conferir.na_fonte:
        return SEM_DOCUMENTO_NA_FONTE
    return EXPLICADA if explicada else PERDIDA


def conferir_canceladas(
    cadastro: pd.DataFrame,
    tabelas: Mapping[str, FonteETabela],
    desde: object,
    explicadas: Mapping[tuple[str, str], str] | None = None,
) -> pd.DataFrame:
    """Cada empresa cancelada desde `desde` (sem registro ativo) × cada tabela, com a situação.

    Situações: `na_tabela`; `saiu_antes_da_tabela` (cancelada até o começo da fonte);
    `sem_documento_na_fonte` (a CVM não publica nada dela: limite da fonte, contado e declarado);
    `explicada_a_mao` (a fonte tem e a tabela não, com o motivo em `explicadas`, chave
    (tabela, cnpj)); `perdida_na_montagem` (a fonte tem e a tabela não, sem motivo: é erro).
    `attrs["perdidas"]` conta as perdidas.
    """
    explicadas = explicadas or {}
    ativas = set(cadastro.loc[cadastro["cancelamento"].isna(), "cnpj"])
    saidas = (
        canceladas(cadastro, desde)
        .loc[lambda c: ~c["cnpj"].isin(ativas)]
        .sort_values("cancelamento")
        .drop_duplicates("cnpj", keep="last")
    )
    linhas = [
        {
            "tabela": nome,
            "cnpj": saida.cnpj,
            "empresa": saida.empresa,
            "cancelamento": saida.cancelamento,
            "motivo_cancelamento": saida.motivo_cancelamento,
            "situacao": _situacao(
                saida.cnpj,
                saida.cancelamento,
                conferir,
                (nome, saida.cnpj) in explicadas,
            ),
            "explicacao": explicadas.get((nome, saida.cnpj), ""),
        }
        for nome, conferir in tabelas.items()
        for saida in saidas.itertuples(index=False)
    ]
    conferencia = pd.DataFrame(
        linhas,
        columns=[
            "tabela",
            "cnpj",
            "empresa",
            "cancelamento",
            "motivo_cancelamento",
            "situacao",
            "explicacao",
        ],
    )
    conferencia.loc[conferencia["situacao"] != EXPLICADA, "explicacao"] = ""
    conferencia.attrs["perdidas"] = int((conferencia["situacao"] == PERDIDA).sum())
    return conferencia


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
    return tickers_dos_valores(pd.concat(partes, ignore_index=True))


def tickers_dos_valores(valores: pd.DataFrame) -> pd.DataFrame:
    """O mesmo que `tickers_no_tempo`, a partir dos valores mobiliários já lidos (os dos dados
    abertos mais as versões antigas do RAD, por `fca.juntar_versoes`)."""
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
