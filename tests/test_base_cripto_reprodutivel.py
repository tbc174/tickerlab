"""Refazer a base de cripto a partir dos originais do acervo e comparar com a guardada (série 1;
exigências 3 e 9 do critério de pronto). Os originais são as amostras dos testes de cada leitor."""

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.cripto import reprodutivel
from base.cripto.arquivos import acrescentar
from base.cripto.reprodutivel import Original, comparar, nada_depois_de, refazer
from tests.test_base_cripto_atencao import TOM, VOLUME, WIKIPEDIA
from tests.test_base_cripto_cftc import _zip_da_amostra
from tests.test_base_cripto_precos import KRAKEN_REST, MERCADO_BITCOIN
from tests.test_base_cripto_receita import _relatorio_1, _relatorio_4

DIA_DA_COLETA = datetime(2026, 10, 13, 12, tzinfo=UTC)
URL_DO_GDELT = (
    "https://api.gdeltproject.org/api/v2/doc/doc?query=bitcoin&mode={modo}&format=json"
    "&timelinesmooth=0&startdatetime=20170101000000&enddatetime=20170102000000"
)


def _original(
    fonte: str, conteudo: bytes, url: str = "https://x", quando=DIA_DA_COLETA
):
    return Original(fonte=fonte, url=url, baixado_em=quando, conteudo=conteudo)


def test_refaz_cada_tabela_com_o_leitor_da_fonte():
    originais = [
        _original("kraken-ohlc", KRAKEN_REST),
        _original(
            "mb-candles", MERCADO_BITCOIN, quando=datetime(2024, 1, 5, 12, tzinfo=UTC)
        ),
        _original("cftc-tff", _zip_da_amostra()),
        _original("wiki-acessos", WIKIPEDIA),
        _original("gdelt-cripto", VOLUME, URL_DO_GDELT.format(modo="timelinevolraw")),
        _original("gdelt-cripto", TOM, URL_DO_GDELT.format(modo="timelinetone")),
    ]

    tabelas = refazer(originais)

    assert set(tabelas) == {"precos/kraken", "precos/mb", "cftc", "wikipedia", "gdelt"}
    assert len(tabelas["precos/kraken"]) == 2
    assert (
        len(tabelas["precos/mb"]) == 4
    )  # o candle de 05/01 ainda estava aberto na coleta
    assert len(tabelas["cftc"]) == 4
    assert tabelas["gdelt"]["noticias"].tolist() == [8, 2]


def test_cada_original_e_lido_com_a_hora_em_que_foi_baixado():
    # refeito hoje, o arquivo baixado em 05/01/2024 não pode ganhar o candle que estava aberto
    tabela = refazer(
        [
            _original(
                "mb-candles",
                MERCADO_BITCOIN,
                quando=datetime(2024, 1, 5, 12, tzinfo=UTC),
            )
        ]
    )

    assert tabela["precos/mb"]["dia"].max() == date(2024, 1, 4)


def test_a_mesma_chave_em_dois_originais_fica_com_o_mais_novo():
    velho = json.loads(KRAKEN_REST)
    novo = json.loads(KRAKEN_REST)
    novo["result"]["XXBTZUSD"][1][4] = "99999.0"  # fechamento do dia 12 corrigido
    originais = [
        _original(
            "kraken-ohlc",
            json.dumps(novo).encode(),
            quando=datetime(2026, 10, 13, 13, tzinfo=UTC),
        ),
        _original("kraken-ohlc", json.dumps(velho).encode(), quando=DIA_DA_COLETA),
    ]

    kraken = refazer(originais)["precos/kraken"].set_index("dia")

    assert kraken.loc[date(2026, 10, 12), "fechamento"] == 99999.0


def test_receita_le_a_planilha_e_ignora_a_pagina(monkeypatch):
    monkeypatch.setattr(
        reprodutivel,
        "abrir_planilha",
        lambda _: {"Relatorio1": _relatorio_1(), "Relatorio4": _relatorio_4()},
    )
    planilha = reprodutivel.ASSINATURA_DO_XLS + b"resto"
    url = "https://www.gov.br/receitafederal/arquivos/criptoativos_dados_abertos_20260826.xls"

    tabelas = refazer(
        [
            _original("rfb-cripto", b"<html>pagina</html>"),
            _original("rfb-cripto", planilha, url),
        ]
    )

    assert len(tabelas["receita/totais"]) == 2
    assert set(tabelas["receita/criptoativo"]["criptoativo"]) == {"BTC"}


def test_gdelt_sem_o_par_nao_entra():
    # a coleta só grava o dia quando a contagem e o tom vieram; o refazer faz igual
    tabelas = refazer(
        [_original("gdelt-cripto", VOLUME, URL_DO_GDELT.format(modo="timelinevolraw"))]
    )

    assert "gdelt" not in tabelas


def test_fonte_sem_leitor_e_ignorada():
    assert refazer([_original("cvm-dfp-itr", b"zip")]) == {}


def test_comparar_da_igual_com_a_tabela_gravada_pela_coleta(tmp_path):
    originais = [
        _original("kraken-ohlc", KRAKEN_REST),
        _original("cftc-tff", _zip_da_amostra()),
    ]
    tabelas = refazer(originais)
    for nome, chave in (
        ("precos/kraken", ["dia"]),
        ("cftc", ["relatorio", "contrato"]),
    ):
        tabela = tabelas[nome].assign(
            coletado_em=DIA_DA_COLETA
        )  # a coleta grava a hora; não é conteúdo
        ano = tabela[chave[0]].map(lambda d: str(d.year))
        acrescentar(tmp_path / nome, tabela, ano, chave)

    resultado = comparar(tabelas, tmp_path)

    assert resultado == {"precos/kraken": True, "cftc": True}


def test_comparar_acusa_um_numero_mudado(tmp_path):
    tabelas = refazer([_original("kraken-ohlc", KRAKEN_REST)])
    guardada = tabelas["precos/kraken"].copy()
    guardada.loc[0, "fechamento"] += 0.01
    acrescentar(
        tmp_path / "precos/kraken",
        guardada,
        guardada["dia"].map(lambda d: str(d.year)),
        ["dia"],
    )

    assert comparar(tabelas, tmp_path) == {"precos/kraken": False}


def test_nada_depois_de_acusa_linha_divulgada_depois_da_data():
    tabela = pd.DataFrame(
        {"divulgado_em": pd.to_datetime(["2020-12-31", "2021-01-02"], utc=True)}
    )

    assert nada_depois_de({"x": tabela}, datetime(2021, 1, 1, tzinfo=UTC)) == {
        "x": True
    }
    with pytest.raises(ValueError, match="sem fuso"):
        nada_depois_de(
            {
                "x": tabela.assign(
                    divulgado_em=tabela["divulgado_em"].dt.tz_localize(None)
                )
            },
            datetime(2021, 1, 1, tzinfo=UTC),
        )
