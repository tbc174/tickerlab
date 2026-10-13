"""Atenção do público ao Bitcoin: acessos à Wikipedia e notícias no GDELT (base de cripto, PR 4).

- **Wikipedia** (Wikimedia, CC0): acessos diários de pessoas (sem robôs) a um artigo, desde
  01/07/2015. Mede curiosidade do público sem depender de rede social.
- **GDELT** (DOC 2.0, uso livre com citação): quantas notícias do mundo citaram o termo e o tom
  médio delas, desde 01/01/2017. Só contagem e tom; nenhum texto de notícia é guardado (ADR 0029).
  O GDELT pede **um pedido a cada 5 segundos**: a coleta pede um dia por vez, devagar.

**Quando o dia passa a valer:** a Wikimedia publica os acessos depois que o dia termina, com algumas
horas de atraso, então o dia vale no fim do dia seguinte. O GDELT atualiza a cada 15 minutos: o dia
vale uma hora depois da meia-noite UTC que o encerra.
"""

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

ENDERECO_WIKIPEDIA = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{projeto}/"
    "all-access/user/{artigo}/daily/{inicio:%Y%m%d}/{fim:%Y%m%d}"
)
ENDERECO_GDELT = (
    "https://api.gdeltproject.org/api/v2/doc/doc?query={termo}&mode={modo}"
    "&format=json&timelinesmooth=0&startdatetime={inicio:%Y%m%d}000000"
    "&enddatetime={fim:%Y%m%d}000000"
)
MARGEM_DA_WIKIPEDIA = pd.Timedelta(days=2)  # o dia inteiro e mais o seguinte
MARGEM_DO_GDELT = pd.Timedelta(days=1, hours=1)  # o dia inteiro e mais uma hora


def endereco_wikipedia(
    artigo: str, inicio: date, fim: date, projeto: str = "en.wikipedia"
) -> str:
    """Pedido dos acessos diários de um artigo de `inicio` a `fim` (`pt.wikipedia` = português)."""
    return ENDERECO_WIKIPEDIA.format(
        projeto=projeto, artigo=artigo, inicio=inicio, fim=fim
    )


def endereco_gdelt(termo: str, modo: str, dia: date) -> str:
    """Pedido de um dia UTC ao GDELT (`timelinevolraw` para contagem, `timelinetone` para tom)."""
    return ENDERECO_GDELT.format(
        termo=termo, modo=modo, inicio=dia, fim=dia + timedelta(days=1)
    )


def ler_wikipedia(conteudo: bytes) -> pd.DataFrame:
    """Uma linha por dia: `dia`, `projeto`, `artigo`, `acessos` e `divulgado_em`."""
    itens = pd.DataFrame(json.loads(conteudo)["items"])
    inicio_do_dia = pd.to_datetime(itens["timestamp"], format="%Y%m%d%H", utc=True)
    return pd.DataFrame(
        {
            "dia": inicio_do_dia.dt.date,
            "projeto": itens["project"],
            "artigo": itens["article"],
            "acessos": itens["views"].astype(int),
            "divulgado_em": inicio_do_dia + MARGEM_DA_WIKIPEDIA,
        }
    )


def ler_gdelt(conteudo: bytes) -> pd.DataFrame:
    """Os intervalos de uma série do GDELT: `momento` (UTC), `dia`, `valor` e `norma` (o total de
    notícias que o GDELT viu no intervalo; só na série de contagem)."""
    serie = json.loads(conteudo)["timeline"][0]["data"]
    tabela = pd.DataFrame(serie).rename(
        columns={"date": "momento", "value": "valor", "norm": "norma"}
    )
    tabela["momento"] = pd.to_datetime(
        tabela["momento"], format="%Y%m%dT%H%M%SZ", utc=True
    )
    tabela["dia"] = tabela["momento"].dt.date
    return tabela


def juntar_gdelt(volume: pd.DataFrame, tom: pd.DataFrame) -> pd.DataFrame:
    """Por dia: `noticias`, `fracao_das_noticias` (do total que o GDELT viu), `tom` médio
    ponderado pelas notícias de cada intervalo (vazio se não houve notícia) e `divulgado_em`."""
    juntos = volume.merge(
        tom[["momento", "valor"]].rename(columns={"valor": "tom"}),
        on="momento",
        how="left",
    )
    juntos["tom_vezes_noticias"] = juntos["tom"] * juntos["valor"]
    dias = juntos.groupby("dia").agg(
        noticias=("valor", "sum"),
        norma=("norma", "sum"),
        tom_vezes_noticias=("tom_vezes_noticias", "sum"),
    )
    dias["fracao_das_noticias"] = dias["noticias"] / dias["norma"]
    dias["tom"] = dias["tom_vezes_noticias"] / dias["noticias"].replace(0, np.nan)
    dias = dias.drop(columns=["norma", "tom_vezes_noticias"]).reset_index()
    dias["divulgado_em"] = (
        pd.to_datetime(dias["dia"]).dt.tz_localize("UTC") + MARGEM_DO_GDELT
    )
    return dias
