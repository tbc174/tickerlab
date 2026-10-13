"""Coleta da base de cripto: só o que falta, sem duplicar, respeitando os limites das fontes
(série 1, PR 6). O `baixar` é falso: responde pelo endereço, sem rede, e guarda os pedidos."""

import json
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from base.cripto import coleta
from base.cripto.arquivos import ler_tabela
from base.cripto.receita import abrir_planilha
from tests.test_base_cripto_cftc import _zip_da_amostra
from tests.test_base_cripto_leitura import NoFalso, _cadeia
from tests.test_base_cripto_precos import KRAKEN_REST
from tests.test_base_cripto_receita import _relatorio_1, _relatorio_4

AGORA = datetime(2026, 10, 13, 12, tzinfo=UTC)


class Fonte:
    """Um `baixar` falso: cada pedido fica em `pedidos`; a resposta vem de `responder(url)`."""

    def __init__(self, responder):
        self.responder = responder
        self.pedidos: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.pedidos.append(url)
        return self.responder(url)


def _candles_mb(url: str) -> bytes:
    """Um candle por dia entre `from` e `to` do pedido, com fechamento = dia do mês."""
    pedido = parse_qs(urlparse(url).query)
    inicio, fim = int(pedido["from"][0]), int(pedido["to"][0])
    horas = list(range(inicio, fim + 1, 86_400))
    preco = [str(datetime.fromtimestamp(h, UTC).day) for h in horas]
    return json.dumps(
        {
            "t": horas,
            "o": preco,
            "h": preco,
            "l": preco,
            "c": preco,
            "v": ["1"] * len(horas),
        }
    ).encode()


def test_mercado_bitcoin_primeira_vez_desde_2014_e_depois_so_o_que_falta(tmp_path):
    fonte = Fonte(_candles_mb)

    coleta.coletar_mercado_bitcoin(tmp_path, AGORA, fonte)
    primeira = len(fonte.pedidos)
    coleta.coletar_mercado_bitcoin(tmp_path, AGORA + timedelta(days=3), fonte)

    precos = ler_tabela(tmp_path / "precos" / "mb", "dia")
    assert precos["dia"].min() == date(2014, 1, 1)
    assert precos["dia"].max() == date(2026, 10, 15)  # o dia 16 ainda está aberto
    assert precos["dia"].is_unique
    # a segunda vez pede só a partir do dia seguinte ao último guardado
    segunda = parse_qs(urlparse(fonte.pedidos[primeira]).query)
    assert int(segunda["from"][0]) == int(
        datetime(2026, 10, 13, tzinfo=UTC).timestamp()
    )


def test_kraken_pela_api_nao_duplica(tmp_path):
    fonte = Fonte(lambda _: KRAKEN_REST)

    primeira = coleta.coletar_kraken(tmp_path, AGORA, fonte)
    segunda = coleta.coletar_kraken(tmp_path, AGORA, fonte)

    # a segunda vez regrava os mesmos dias: nenhuma linha nova
    assert (primeira, segunda) == (2, 0)

    precos = ler_tabela(tmp_path / "precos" / "kraken", "dia")
    assert precos["dia"].tolist() == [date(2026, 10, 11), date(2026, 10, 12)]


def test_kraken_arquivo_historico_entra_na_mesma_tabela(tmp_path):
    coleta.carregar_arquivo_kraken(
        tmp_path, AGORA, b"1381017600,122.0,122.0,122.0,122.0,0.1,1\n"
    )
    coleta.coletar_kraken(tmp_path, AGORA, Fonte(lambda _: KRAKEN_REST))

    assert len(ler_tabela(tmp_path / "precos" / "kraken", "dia")) == 3


def test_cftc_primeira_vez_desde_2017_e_depois_o_ano_anterior_e_o_atual(tmp_path):
    fonte = Fonte(lambda _: _zip_da_amostra())

    coleta.coletar_cftc(tmp_path, AGORA, fonte)
    anos_da_primeira = [url[-8:-4] for url in fonte.pedidos]
    fonte.pedidos.clear()
    coleta.coletar_cftc(tmp_path, AGORA, fonte)

    assert anos_da_primeira == [str(ano) for ano in range(2017, 2027)]
    assert [url[-8:-4] for url in fonte.pedidos] == ["2025", "2026"]
    cot = ler_tabela(tmp_path / "cftc", ["relatorio", "contrato"])
    assert not cot.duplicated(["relatorio", "contrato"]).any()


def _acessos_wikipedia(url: str) -> bytes:
    inicio, fim = (
        pd.to_datetime(p, format="%Y%m%d") for p in url.rstrip("/").split("/")[-2:]
    )
    dias = pd.date_range(inicio, fim, freq="D")
    itens = [
        {
            "project": url.split("/per-article/")[1].split("/")[0],
            "article": "Bitcoin",
            "timestamp": d.strftime("%Y%m%d00"),
            "views": 10,
        }
        for d in dias
    ]
    return json.dumps({"items": itens}).encode()


def test_wikipedia_so_os_dias_que_ja_valem(tmp_path):
    fonte = Fonte(_acessos_wikipedia)

    coleta.coletar_wikipedia(tmp_path, AGORA, fonte)

    acessos = ler_tabela(tmp_path / "wikipedia", ["projeto", "dia"])
    assert set(acessos["projeto"]) == {"en.wikipedia", "pt.wikipedia"}
    for _, do_projeto in acessos.groupby("projeto"):
        assert do_projeto["dia"].min() == date(2015, 7, 1)
        # o dia 11 vale no fim do dia 12 (antes de agora); o dia 12 só no fim do dia 13
        assert do_projeto["dia"].max() == date(2026, 10, 11)
        assert do_projeto["dia"].is_unique


def test_cada_projeto_da_wikipedia_pede_so_o_que_falta(tmp_path):
    fonte = Fonte(_acessos_wikipedia)
    coleta.coletar_wikipedia(tmp_path, AGORA, fonte)
    fonte.pedidos.clear()

    coleta.coletar_wikipedia(tmp_path, AGORA + timedelta(days=1), fonte)

    # cada projeto pede só o dia que falta dele
    assert [url.rsplit("/", 2)[-2:] for url in fonte.pedidos] == [
        ["20261012", "20261012"]
    ] * 2


def _gdelt_do_dia(url: str) -> bytes:
    pedido = parse_qs(urlparse(url).query)
    inicio = pedido["startdatetime"][0][:8]
    if pedido["mode"][0] == "timelinevolraw":
        ponto = {"date": f"{inicio}T000000Z", "value": 4, "norm": 100}
    else:
        ponto = {"date": f"{inicio}T000000Z", "value": -1.0}
    return json.dumps({"timeline": [{"data": [ponto]}]}).encode()


def test_gdelt_um_dia_por_vez_com_pausa_e_limite_por_rodada(tmp_path, monkeypatch):
    monkeypatch.setattr(coleta, "DIAS_DO_GDELT_POR_RODADA", 3)
    pausas: list[float] = []
    fonte = Fonte(_gdelt_do_dia)

    coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=pausas.append)
    coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=pausas.append)

    noticias = ler_tabela(tmp_path / "gdelt", "dia")
    assert noticias["dia"].tolist() == [date(2017, 1, d) for d in range(1, 7)]
    assert len(fonte.pedidos) == 12  # 6 dias, contagem e tom
    assert all(pausa >= coleta.PAUSA_DO_GDELT_EM_SEGUNDOS for pausa in pausas)
    assert len(pausas) == len(fonte.pedidos)


PAGINA_DA_RECEITA = (
    b'<a href="https://www.gov.br/receitafederal/arquivos/criptoativos_dados_abertos_20260826.pdf">'
    b'<a href="https://www.gov.br/receitafederal/arquivos/criptoativos_dados_abertos_20260826.xls">'
)


@pytest.fixture
def planilha_da_receita(monkeypatch):
    abas = {"Relatorio1": _relatorio_1(), "Relatorio4": _relatorio_4()}
    monkeypatch.setattr(coleta, "abrir_planilha", lambda _: abas)
    return abas


def test_receita_acha_a_planilha_na_pagina_e_guarda_cada_versao(
    tmp_path, planilha_da_receita
):
    fonte = Fonte(
        lambda url: PAGINA_DA_RECEITA if url == coleta.PAGINA_DA_RECEITA else b"xls"
    )

    coleta.coletar_receita(tmp_path, AGORA, fonte)
    coleta.coletar_receita(tmp_path, AGORA, fonte)  # mesma planilha: não baixa de novo

    assert fonte.pedidos.count(coleta.PAGINA_DA_RECEITA) == 2
    assert sum(url.endswith(".xls") for url in fonte.pedidos) == 1
    totais = ler_tabela(tmp_path / "receita" / "totais", ["mes", "divulgado_em"])
    assert len(totais) == 2
    por_criptoativo = ler_tabela(
        tmp_path / "receita" / "criptoativo", ["mes", "divulgado_em"]
    )
    # a amostra tem AAVE e BTC; só os da lista entram
    assert set(por_criptoativo["criptoativo"]) == {"BTC"}
    assert set(coleta.CRIPTOATIVOS_DA_RECEITA) == {"BTC", "ETH", "USDT", "USDC", "BRZ"}


def test_abrir_planilha_e_a_da_receita():
    assert coleta.abrir_planilha is abrir_planilha


def test_no_le_os_blocos_e_grava_o_resumo_diario(tmp_path):
    no = NoFalso(_cadeia(30))

    lidos = coleta.coletar_no(tmp_path, AGORA, no)
    de_novo = coleta.coletar_no(tmp_path, AGORA, no)

    assert (lidos, de_novo) == (25, 0)
    diario = ler_tabela(tmp_path / "rede_diaria", "dia")
    assert not diario.empty
    assert diario["dia"].is_unique


def test_no_confere_a_oferta_ao_fim_da_leitura(tmp_path):
    no = NoFalso(_cadeia(30))
    no.ajuste_do_total = 1  # o nó diz 1 satoshi a mais do que a base somou

    with pytest.raises(ValueError, match="C7"):
        coleta.coletar_no(tmp_path, AGORA, no)


def test_no_com_indice_sincronizando_deixa_a_conferencia_para_depois(tmp_path):
    from base.cripto.no_bitcoin import ErroDoNo

    class NoSincronizando(NoFalso):
        def total_nao_gasto(self, altura):
            raise ErroDoNo(
                "gettxoutsetinfo: Unable to get data because coinstatsindex is still syncing."
            )

    assert coleta.coletar_no(tmp_path, AGORA, NoSincronizando(_cadeia(30))) == 25
