"""Atenção do público ao Bitcoin: acessos à Wikipedia e notícias no GDELT (base de cripto, PR 4).

As respostas seguem o formato real das duas APIs (conferido em 13/10/2026): a Wikipedia começa em
01/07/2015 e o GDELT (DOC 2.0) em 01/01/2017.
"""

import json
from datetime import UTC, date, datetime

import pytest

from base.cripto.atencao import (
    endereco_gdelt,
    endereco_wikipedia,
    juntar_gdelt,
    ler_gdelt,
    ler_wikipedia,
)

WIKIPEDIA = json.dumps(
    {
        "items": [
            {"article": "Bitcoin", "timestamp": "2015070100", "views": 12957},
            {"article": "Bitcoin", "timestamp": "2015070200", "views": 9802},
        ]
    }
).encode()


def _gdelt(serie: str, pontos: list[tuple[str, float, int | None]]) -> bytes:
    dados = []
    for quando, valor, norma in pontos:
        ponto = {"date": quando, "value": valor}
        if norma is not None:
            ponto["norm"] = norma
        dados.append(ponto)
    return json.dumps({"timeline": [{"series": serie, "data": dados}]}).encode()


# três intervalos de 15 min no dia 01 e um no dia 02
VOLUME = _gdelt(
    "Article Count",
    [
        ("20170101T000000Z", 5, 4000),
        ("20170101T001500Z", 0, 3600),
        ("20170101T234500Z", 3, 3400),
        ("20170102T000000Z", 2, 1000),
    ],
)
TOM = _gdelt(
    "Average Tone",
    [
        ("20170101T000000Z", -2.0, None),
        ("20170101T001500Z", 0.0, None),
        ("20170101T234500Z", 2.0, None),
        ("20170102T000000Z", 1.5, None),
    ],
)


def test_wikipedia_acessos_por_dia():
    tabela = ler_wikipedia(WIKIPEDIA)

    assert tabela["dia"].tolist() == [date(2015, 7, 1), date(2015, 7, 2)]
    assert tabela["acessos"].tolist() == [12_957, 9_802]
    assert (tabela["artigo"] == "Bitcoin").all()


def test_wikipedia_dia_so_vale_no_fim_do_dia_seguinte():
    # a Wikimedia publica o dia depois que ele termina; o dia seguinte inteiro é a margem
    assert ler_wikipedia(WIKIPEDIA).iloc[0]["divulgado_em"] == datetime(
        2015, 7, 3, tzinfo=UTC
    )


def test_endereco_wikipedia():
    assert endereco_wikipedia("Bitcoin", date(2015, 7, 1), date(2015, 7, 31)) == (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
        "all-access/user/Bitcoin/daily/20150701/20150731"
    )


def test_gdelt_soma_por_dia_utc():
    volume = ler_gdelt(VOLUME)

    por_dia = volume.groupby("dia")["valor"].sum()
    assert por_dia.loc[date(2017, 1, 1)] == 8
    assert por_dia.loc[date(2017, 1, 2)] == 2


def test_gdelt_junta_contagem_fracao_e_tom_ponderado():
    dias = juntar_gdelt(ler_gdelt(VOLUME), ler_gdelt(TOM)).set_index("dia")

    dia = dias.loc[date(2017, 1, 1)]
    assert dia["noticias"] == 8
    assert dia["fracao_das_noticias"] == pytest.approx(8 / 11_000)
    # tom ponderado pelas notícias de cada intervalo: (5 × -2 + 3 × 2) / 8 = -0,5
    assert dia["tom"] == pytest.approx(-0.5)


def test_gdelt_dia_so_vale_uma_hora_depois_da_meia_noite():
    dias = juntar_gdelt(ler_gdelt(VOLUME), ler_gdelt(TOM)).set_index("dia")

    assert dias.loc[date(2017, 1, 1), "divulgado_em"] == datetime(
        2017, 1, 2, 1, tzinfo=UTC
    )


def test_dia_sem_noticia_tem_tom_vazio():
    volume = _gdelt("Article Count", [("20170105T000000Z", 0, 100)])
    tom = _gdelt("Average Tone", [("20170105T000000Z", 0.0, None)])

    dia = juntar_gdelt(ler_gdelt(volume), ler_gdelt(tom)).iloc[0]

    assert dia["noticias"] == 0
    assert dia["tom"] != dia["tom"]  # NaN: sem notícia, não há tom


def test_endereco_gdelt_de_um_dia():
    assert endereco_gdelt("bitcoin", "timelinevolraw", date(2017, 1, 1)) == (
        "https://api.gdeltproject.org/api/v2/doc/doc?query=bitcoin&mode=timelinevolraw"
        "&format=json&timelinesmooth=0&startdatetime=20170101000000&enddatetime=20170102000000"
    )
