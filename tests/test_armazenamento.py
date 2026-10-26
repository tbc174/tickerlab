"""Testes de src/armazenamento.py e do cache em SQLite dentro de baixar_dados."""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src import armazenamento as ar
from src.armazenamento import VARIAVEL_DO_CAMINHO
from src.dados import DadosIndisponiveisError, baixar_dados
from src.exemplos import DESLOCAMENTO_DO_PERIODO

HOJE = datetime(2026, 10, 9, 12, 0)  # noqa: DTZ001  (horários do banco são UTC sem fuso)


def _precos(inicio, fim, nivel=10.0):
    """Preços de dias úteis, crescendo 1 centavo por dia (fácil de reconhecer)."""
    indice = pd.bdate_range(inicio, fim)
    close = nivel + 0.01 * np.arange(len(indice))
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.1,
            "Low": close - 0.1,
            "Close": close,
            "Volume": 1000.0,
        },
        index=pd.Index(indice, name="Date"),
    )


def _como_o_yahoo(dados, ticker="PETR4.SA"):
    colunas = pd.MultiIndex.from_product(
        [dados.columns, [ticker]], names=["Price", "Ticker"]
    )
    saida = dados.copy()
    saida.columns = colunas
    return saida


class YahooFalso:
    """Imita yf.download: devolve o recorte do histórico pedido e guarda cada pedido."""

    def __init__(self, historico):
        self.historico = historico
        self.pedidos = []
        self.fora_do_ar = False
        self.so_o_pedido_completo_falha = (
            False  # o incremental responde, o completo não
        )

    def __call__(self, ticker, **pedido):
        self.pedidos.append(
            {k: v for k, v in pedido.items() if k in ("period", "start")}
        )
        if self.fora_do_ar or (self.so_o_pedido_completo_falha and "period" in pedido):
            raise ConnectionError("Yahoo fora do ar")
        dados = self.historico
        if "start" in pedido:
            dados = dados.loc[pedido["start"] :]
        if "period" in pedido:
            dados = dados.loc[
                dados.index
                > dados.index[-1] - DESLOCAMENTO_DO_PERIODO[pedido["period"]]
            ]
        return _como_o_yahoo(dados, ticker)


@pytest.fixture
def yahoo(monkeypatch):
    falso = YahooFalso(_precos("2024-10-01", "2026-10-08"))
    monkeypatch.setattr("src.dados.yf.download", falso)
    return falso


# --- armazenamento ------------------------------------------------------------------------


def test_salvar_e_ler_devolve_o_mesmo():
    dados = _precos("2026-01-05", "2026-01-30")
    assert ar.salvar_precos("AAA", dados) == len(dados)
    lido = ar.ler_precos("AAA")
    pd.testing.assert_frame_equal(lido, dados, check_freq=False)
    assert ar.ler_precos("OUTRO").empty


def test_salvar_de_novo_atualiza_em_vez_de_duplicar():
    dados = _precos("2026-01-05", "2026-01-09")
    ar.salvar_precos("AAA", dados)
    ar.salvar_precos("AAA", dados.assign(Close=99.0))
    lido = ar.ler_precos("AAA")
    assert len(lido) == 5 and (lido["Close"] == 99.0).all()


def test_substituir_troca_o_historico_inteiro_de_um_ticker_so():
    ar.salvar_precos("AAA", _precos("2026-01-05", "2026-01-30"))
    ar.salvar_precos("BBB", _precos("2026-01-05", "2026-01-07"))
    novo = _precos("2026-01-19", "2026-02-06", nivel=50.0)
    assert ar.substituir_precos("AAA", novo, HOJE) == len(novo)
    pd.testing.assert_frame_equal(ar.ler_precos("AAA"), novo, check_freq=False)
    assert len(ar.ler_precos("BBB")) == 3
    assert ar.consulta_recente("AAA", HOJE)


def test_substituir_com_dados_ruins_nao_apaga_o_guardado():
    guardado = _precos("2026-01-05", "2026-01-30")
    ar.salvar_precos("AAA", guardado)
    sem_datas = guardado.reset_index(drop=True)  # índice de números: não vira data
    with pytest.raises(AttributeError):
        ar.substituir_precos("AAA", sem_datas, HOJE)
    with pytest.raises(ValueError, match="vazio"):
        ar.substituir_precos("AAA", guardado.iloc[:0], HOJE)
    pd.testing.assert_frame_equal(ar.ler_precos("AAA"), guardado, check_freq=False)


def test_volume_vazio_volta_como_vazio_e_dados_vazios_nao_gravam():
    dados = _precos("2026-01-05", "2026-01-07")
    dados["Volume"] = np.nan
    ar.salvar_precos("AAA", dados)
    assert ar.ler_precos("AAA")["Volume"].isna().all()
    assert ar.salvar_precos("AAA", dados.iloc[:0]) == 0


def test_consulta_recente_vale_por_quatro_horas():
    assert not ar.consulta_recente("AAA", HOJE)
    ar.registrar_consulta("AAA", HOJE)
    assert ar.consulta_recente("AAA", HOJE + timedelta(hours=3, minutes=59))
    assert not ar.consulta_recente("AAA", HOJE + timedelta(hours=4, minutes=1))
    assert not ar.consulta_recente("BBB", HOJE)


def test_deteccao_de_precos_reajustados():
    base = _precos("2026-01-05", "2026-01-30")
    assert not ar.precos_foram_reajustados(base, base.iloc[-5:])
    assert ar.precos_foram_reajustados(base, base.iloc[-5:] * 0.95)
    assert not ar.precos_foram_reajustados(
        base.iloc[:5], base.iloc[10:]
    )  # sem dias em comum


def test_banco_fica_no_caminho_da_variavel_de_ambiente(tmp_path, monkeypatch):
    alvo = tmp_path / "pasta_nova" / "meu.sqlite"
    monkeypatch.setenv(VARIAVEL_DO_CAMINHO, str(alvo))
    ar.salvar_precos("AAA", _precos("2026-01-05", "2026-01-07"))
    assert alvo.exists()


# --- baixar_dados com o cache -------------------------------------------------------------


def test_segundo_pedido_do_mesmo_ticker_nao_vai_ao_yahoo(yahoo):
    primeiro = baixar_dados("PETR4", "2y", agora=HOJE)
    segundo = baixar_dados("PETR4", "2y", agora=HOJE + timedelta(minutes=30))
    assert len(yahoo.pedidos) == 1
    assert len(segundo) > 450
    assert segundo["Close"].iloc[-1] == pytest.approx(primeiro["Close"].iloc[-1])


def test_periodo_menor_sai_do_historico_guardado(yahoo):
    baixar_dados("PETR4", "2y", agora=HOJE)
    seis_meses = baixar_dados("PETR4", "6mo", agora=HOJE)
    assert len(yahoo.pedidos) == 1
    assert 110 < len(seis_meses) < 135


def test_periodo_maior_que_o_guardado_baixa_de_novo(monkeypatch):
    falso = YahooFalso(_precos("2021-10-01", "2026-10-08"))
    monkeypatch.setattr("src.dados.yf.download", falso)
    baixar_dados("PETR4", "6mo", agora=HOJE)
    cinco = baixar_dados("PETR4", "5y", agora=HOJE)
    assert len(falso.pedidos) == 2 and falso.pedidos[1] == {"period": "5y"}
    assert len(cinco) > 1200


def test_depois_da_validade_pede_so_os_dias_que_faltam(yahoo):
    baixar_dados("PETR4", "2y", agora=HOJE)
    ultimo = ar.ler_precos("PETR4.SA").index[-1]
    # chegam dias novos no Yahoo
    yahoo.historico = _precos("2024-10-01", "2026-10-14")
    dados = baixar_dados("PETR4", "2y", agora=HOJE + timedelta(hours=5))
    assert len(yahoo.pedidos) == 2
    assert yahoo.pedidos[1] == {
        "start": (ultimo - timedelta(days=7)).strftime("%Y-%m-%d")
    }
    assert dados.index[-1] == pd.Timestamp("2026-10-14")
    assert ar.ler_precos("PETR4.SA").index[-1] == pd.Timestamp("2026-10-14")
    assert dados.index.is_unique


def test_preco_reajustado_apaga_o_guardado_e_baixa_tudo_de_novo(yahoo):
    baixar_dados("PETR4", "2y", agora=HOJE)
    yahoo.historico = yahoo.historico * 0.9  # dividendo: o passado inteiro mudou
    dados = baixar_dados("PETR4", "2y", agora=HOJE + timedelta(hours=5))
    assert yahoo.pedidos[-1] == {"period": "2y"}
    guardado = ar.ler_precos("PETR4.SA")
    assert guardado["Close"].iloc[0] == pytest.approx(dados["Close"].iloc[0])
    assert guardado["Close"].iloc[-1] == pytest.approx(
        yahoo.historico["Close"].iloc[-1]
    )


def test_reajuste_com_o_yahoo_caindo_no_meio_nao_apaga_o_guardado(yahoo, caplog):
    # regressão do achado A-01 (Master v3): o guardado era apagado antes do download completo
    baixar_dados("PETR4", "2y", agora=HOJE)
    antes = ar.ler_precos("PETR4.SA")
    yahoo.historico = yahoo.historico * 0.9  # dividendo: o passado inteiro mudou
    yahoo.so_o_pedido_completo_falha = True
    with caplog.at_level(logging.WARNING):
        dados = baixar_dados("PETR4", "2y", agora=HOJE + timedelta(hours=5))
    assert yahoo.pedidos[-1] == {"period": "2y"}  # tentou baixar de novo
    pd.testing.assert_frame_equal(ar.ler_precos("PETR4.SA"), antes)  # nada misturado
    assert dados.attrs["origem"] == "cache_antigo"
    assert dados["Close"].iloc[-1] == pytest.approx(antes["Close"].iloc[-1])
    assert "mantendo o guardado" in caplog.text
    # a consulta não conta como feita: o próximo pedido tenta de novo e, com o Yahoo de volta,
    # troca o histórico inteiro pelo reajustado
    yahoo.so_o_pedido_completo_falha = False
    dados = baixar_dados("PETR4", "2y", agora=HOJE + timedelta(hours=5, minutes=1))
    assert "origem" not in dados.attrs
    assert ar.ler_precos("PETR4.SA")["Close"].iloc[0] == pytest.approx(
        dados["Close"].iloc[0]
    )


def test_reajuste_com_resposta_curta_nao_troca_o_guardado(yahoo):
    baixar_dados("PETR4", "2y", agora=HOJE)
    antes = ar.ler_precos("PETR4.SA")
    yahoo.historico = (yahoo.historico * 0.9).iloc[-30:]  # o Yahoo só devolveu 30 dias
    dados = baixar_dados("PETR4", "2y", agora=HOJE + timedelta(hours=5))
    pd.testing.assert_frame_equal(ar.ler_precos("PETR4.SA"), antes)
    assert dados.attrs["origem"] == "cache_antigo" and len(dados) > 450


def test_yahoo_fora_do_ar_usa_o_historico_guardado_e_avisa(yahoo, caplog):
    baixar_dados("PETR4", "2y", agora=HOJE)
    yahoo.fora_do_ar = True
    with caplog.at_level(logging.WARNING):
        dados = baixar_dados("PETR4", "2y", agora=HOJE + timedelta(hours=5))
    assert dados.attrs["origem"] == "cache_antigo"
    assert dados.attrs["ate"] == "08/10/2026"
    assert "histórico guardado" in caplog.text
    assert len(dados) > 450


def test_yahoo_fora_do_ar_sem_nada_guardado_usa_o_exemplo(yahoo):
    yahoo.fora_do_ar = True
    assert baixar_dados("PETR4", "1y").attrs["origem"] == "exemplo"
    with pytest.raises(DadosIndisponiveisError, match="XXXX9"):
        baixar_dados("XXXX9")


def test_sem_banco_nao_cria_arquivo_e_sempre_pergunta_ao_yahoo(yahoo, tmp_path):
    baixar_dados("PETR4", "2y", usar_banco=False)
    baixar_dados("PETR4", "2y", usar_banco=False)
    assert len(yahoo.pedidos) == 2
    assert not (tmp_path / "precos_de_teste.sqlite").exists()


def test_banco_com_problema_nao_derruba_o_app(yahoo, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(VARIAVEL_DO_CAMINHO, str(tmp_path))  # uma pasta, não um arquivo
    with caplog.at_level(logging.ERROR):
        dados = baixar_dados("PETR4", "2y")
    assert len(dados) > 450
    assert "SQLite indisponível" in caplog.text


def test_exemplo_forcado_nao_toca_no_banco(yahoo, tmp_path):
    baixar_dados("VALE3", "1y", forcar_exemplo=True)
    assert yahoo.pedidos == []
    assert not (tmp_path / "precos_de_teste.sqlite").exists()


def test_reajuste_pequeno_tambem_e_reajuste():
    """Achado 5c do Codex: um dividendo de 0,05% reajusta o passado; abaixo da tolerância antiga
    (0,1%) ele passava e o histórico ficava em duas escalas."""
    base = _precos("2026-01-05", "2026-01-30", nivel=100.0)
    novo = base.iloc[-5:].copy()
    novo[["Open", "High", "Low", "Close"]] *= 0.9995
    assert ar.precos_foram_reajustados(base, novo)


def test_ultimo_dia_guardado_pode_ter_sido_parcial():
    """O último dia guardado pode ser o pregão em andamento: só ele mudar não é reajuste."""
    base = _precos("2026-01-05", "2026-01-30", nivel=100.0)
    novo = base.iloc[-5:].copy()
    novo.loc[novo.index[-1], "Close"] *= 1.02  # o fechamento do dia, depois do pregão
    assert not ar.precos_foram_reajustados(base, novo)
    # só o último dia em comum: ainda é o que há para comparar
    assert ar.precos_foram_reajustados(base, novo.iloc[-1:])


# --- prazo do guardado (linha 413, Y3 b: "pode" do Tiago em 25/10/2026) ---------------------------


def test_ticker_que_ninguem_abriu_em_7_dias_sai_do_guardado():
    """O cache não guarda a série de quem ninguém abriu em 7 dias (nem a de quem nunca teve
    consulta registrada); o resto fica como estava."""
    for ticker in ("VELHO", "NOVO", "SEM_CONSULTA"):
        ar.salvar_precos(ticker, _precos("2026-01-05", "2026-01-30"))
    ar.registrar_consulta("VELHO", HOJE - timedelta(days=7, minutes=1))
    ar.registrar_consulta("NOVO", HOJE - timedelta(days=6, hours=23))
    assert ar.apagar_tickers_esquecidos(HOJE) == 2
    assert ar.ler_precos("VELHO").empty and ar.ler_precos("SEM_CONSULTA").empty
    assert len(ar.ler_precos("NOVO")) == 20
    assert not ar.consulta_recente(
        "VELHO", HOJE, horas=24 * 365
    )  # a consulta saiu junto
    assert ar.apagar_tickers_esquecidos(HOJE) == 0


def test_ticker_esquecido_volta_inteiro_do_yahoo(yahoo):
    baixar_dados("PETR4", "2y", agora=HOJE)
    baixar_dados("PETR4", "2y", agora=HOJE + timedelta(days=ar.DIAS_SEM_CONSULTA + 1))
    # sem o prazo, o 2º pedido seria só dos dias que faltam ({"start": ...})
    assert yahoo.pedidos == [{"period": "2y"}, {"period": "2y"}]


def test_ticker_aberto_toda_semana_continua_guardado(yahoo):
    baixar_dados("PETR4", "2y", agora=HOJE)
    baixar_dados("PETR4", "2y", agora=HOJE + timedelta(days=ar.DIAS_SEM_CONSULTA - 1))
    assert yahoo.pedidos[1].keys() == {
        "start"
    }  # o guardado ficou: pediu só o que falta
