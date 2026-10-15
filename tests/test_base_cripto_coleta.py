"""Coleta da base de cripto: só o que falta, sem duplicar, respeitando os limites das fontes
(série 1, PR 6). O `baixar` é falso: responde pelo endereço, sem rede, e guarda os pedidos."""

import json
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import requests

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


def _gdelt_do_periodo(url: str) -> bytes:
    """Um ponto por dia de `startdatetime` até antes de `enddatetime` (resolução "day")."""
    pedido = parse_qs(urlparse(url).query)
    dia = date.fromisoformat(pedido["startdatetime"][0][:8])
    fim = date.fromisoformat(pedido["enddatetime"][0][:8])
    pontos = []
    while dia < fim:
        momento = f"{dia:%Y%m%d}T000000Z"
        if pedido["mode"][0] == "timelinevolraw":
            pontos.append({"date": momento, "value": 4, "norm": 100})
        else:
            pontos.append({"date": momento, "value": -1.0})
        dia += timedelta(days=1)
    return json.dumps({"timeline": [{"data": pontos}]}).encode()


def _so_desde(monkeypatch, dia: date, dias_por_pedido: int = 5) -> None:
    """Começa o GDELT perto de AGORA (o último dia que vale é 12/10/2026)."""
    monkeypatch.setattr(coleta, "INICIO_DO_GDELT", dia)
    monkeypatch.setattr(coleta, "DIAS_POR_PEDIDO_AO_GDELT", dias_por_pedido)


def test_gdelt_pede_varios_dias_de_uma_vez_e_depois_so_o_que_falta(
    tmp_path, monkeypatch
):
    _so_desde(monkeypatch, date(2026, 10, 1))
    pausas: list[float] = []
    fonte = Fonte(_gdelt_do_periodo)

    coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=pausas.append)
    primeira = len(fonte.pedidos)
    coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=pausas.append)

    noticias = ler_tabela(tmp_path / "gdelt", "dia")
    assert noticias["dia"].tolist() == [date(2026, 10, d) for d in range(1, 13)]
    assert primeira == 6  # 1–5, 6–10 e 11–12: contagem e tom de cada bloco
    assert len(fonte.pedidos) == primeira  # a 2ª rodada não tinha o que pedir
    assert (
        "enddatetime=20261013000000" in fonte.pedidos[-1]
    )  # o último bloco para no 12/10
    assert pausas == [coleta.PAUSA_DO_GDELT_EM_SEGUNDOS] * primeira


def test_gdelt_pede_de_novo_o_ultimo_dia_guardado_quando_ha_dias_novos(
    tmp_path, monkeypatch
):
    # Até 14/10/2026 o pedido de um dia trazia também o 1º quarto de hora do dia seguinte, que
    # ficava guardado como se fosse o dia inteiro: a rodada seguinte refaz o último dia.
    _so_desde(monkeypatch, date(2026, 10, 1))
    fonte = Fonte(_gdelt_do_periodo)
    coleta.coletar_gdelt(
        tmp_path, datetime(2026, 10, 6, 12, tzinfo=UTC), fonte, lambda _: None
    )
    fonte.pedidos.clear()

    coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=lambda _: None)

    assert "startdatetime=20261005000000" in fonte.pedidos[0]
    dias = ler_tabela(tmp_path / "gdelt", "dia")["dia"]
    assert dias.tolist() == [
        date(2026, 10, d) for d in range(1, 13)
    ]  # sem repetir o dia 5


def test_gdelt_para_de_comecar_blocos_quando_acaba_o_tempo(tmp_path, monkeypatch):
    _so_desde(monkeypatch, date(2026, 10, 1))
    relogio = iter([0.0, 0.0, coleta.MINUTOS_DO_GDELT_POR_RODADA * 60 + 1])
    fonte = Fonte(_gdelt_do_periodo)

    novas = coleta.coletar_gdelt(
        tmp_path, AGORA, fonte, esperar=lambda _: None, relogio=lambda: next(relogio)
    )

    assert novas == 5  # só o 1º bloco; o resto fica para a noite seguinte
    assert len(fonte.pedidos) == 2


# --- GDELT limitando (14/10/2026: a coleta falhou com 429 Too Many Requests) ------------------------
def _erro_http(codigo: int, espere: str | None = None) -> requests.HTTPError:
    resposta = requests.Response()
    resposta.status_code = codigo
    if espere is not None:
        resposta.headers["Retry-After"] = espere
    return requests.HTTPError(f"{codigo} Client Error", response=resposta)


class GdeltLimitando(Fonte):
    """Responde 429 nos pedidos de número `limitados` (contando de 1) e os dias certos nos outros."""

    def __init__(self, limitados, espere: str | None = None):
        super().__init__(_gdelt_do_periodo)
        self.limitados = limitados
        self.espere = espere

    def __call__(self, url: str) -> bytes:
        self.pedidos.append(url)
        if len(self.pedidos) in self.limitados:
            raise _erro_http(429, self.espere)
        return self.responder(url)


def test_gdelt_espera_e_tenta_de_novo_quando_responde_429(tmp_path, monkeypatch):
    _so_desde(monkeypatch, date(2026, 10, 12))
    pausas: list[float] = []
    fonte = GdeltLimitando(limitados={2, 3})  # o tom leva dois 429

    coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=pausas.append)

    assert ler_tabela(tmp_path / "gdelt", "dia")["dia"].tolist() == [date(2026, 10, 12)]
    assert len(fonte.pedidos) == 4
    esperas_do_429 = [p for p in pausas if p != coleta.PAUSA_DO_GDELT_EM_SEGUNDOS]
    assert esperas_do_429 == list(coleta.ESPERAS_DO_GDELT_EM_SEGUNDOS[:2])


def test_gdelt_respeita_o_retry_after_da_resposta(tmp_path, monkeypatch):
    _so_desde(monkeypatch, date(2026, 10, 12))
    pausas: list[float] = []
    fonte = GdeltLimitando(limitados={1}, espere="90")

    coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=pausas.append)

    assert pausas[0] == 90


def test_gdelt_sempre_limitando_sem_nenhum_dia_novo_falha(tmp_path):
    fonte = GdeltLimitando(limitados=range(1, 1000))

    with pytest.raises(requests.HTTPError):
        coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=lambda _: None)

    assert len(fonte.pedidos) == len(coleta.ESPERAS_DO_GDELT_EM_SEGUNDOS) + 1
    assert not (tmp_path / "gdelt").exists()


def test_gdelt_limitando_depois_de_dias_novos_guarda_o_que_veio_e_para(
    tmp_path, monkeypatch
):
    # 1º bloco inteiro (2 pedidos); do 3º pedido em diante, só 429: termina bem, o resto amanhã.
    _so_desde(monkeypatch, date(2026, 10, 1))
    fonte = GdeltLimitando(limitados=range(3, 1000))

    novas = coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=lambda _: None)

    assert novas == 5
    assert ler_tabela(tmp_path / "gdelt", "dia")["dia"].tolist() == [
        date(2026, 10, d) for d in range(1, 6)
    ]


def test_gdelt_outro_erro_nao_e_tentado_de_novo(tmp_path):
    def quebrado(url: str) -> bytes:
        raise _erro_http(500)

    fonte = Fonte(quebrado)
    with pytest.raises(requests.HTTPError):
        coleta.coletar_gdelt(tmp_path, AGORA, fonte, esperar=lambda _: None)
    assert len(fonte.pedidos) == 1


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
