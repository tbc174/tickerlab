"""O formato das respostas da API de leitura (src/api_v1/esquemas.py)."""

import inspect
import json
import math
from datetime import date

import pandas as pd
import pytest
from pydantic import BaseModel

from src import analises
from src import indicadores as ind
from src.api_v1 import esquemas
from src.backtest import executar_backtest
from src.exemplos import carregar_exemplo
from src.metricas import resumir_desempenho

TAXA = 0.10

# nomes de campo que entregariam o preço bruto (ADR 0048, item 6: só números e base 100)
CAMPOS_DE_PRECO = {
    "preco",
    "precos",
    "close",
    "open",
    "high",
    "low",
    "abertura",
    "fechamento",
    "fechamentos",
    "maxima",
    "minima",
    "volume",
    "cotacao",
    "cotacoes",
}


@pytest.fixture(scope="module")
def petr4():
    fechamento = carregar_exemplo("PETR4.SA", "5y")["Close"]
    return fechamento, ind.calcular_retorno_diario(fechamento)


def _ida_e_volta(modelo: BaseModel) -> dict:
    """Vira JSON de verdade (NaN quebraria aqui) e volta."""
    texto = modelo.model_dump_json()
    assert "NaN" not in texto and "Infinity" not in texto
    return json.loads(texto)


def test_painel_vira_json_com_datas_em_iso(petr4):
    painel = analises.painel_de_numeros(*petr4, TAXA, 95)
    dados = _ida_e_volta(esquemas.de_painel(painel))
    assert dados["retorno_total"] == pytest.approx(painel.retorno_total)
    assert dados["data_do_melhor_dia"] == painel.data_do_melhor_dia.date().isoformat()
    assert dados["confianca_do_var"] == 95


def test_numero_que_nao_existe_vira_null():
    assert esquemas.numero(float("nan")) is None
    assert esquemas.numero(math.inf) is None
    assert esquemas.numero(0.25) == 0.25


def test_risco_tem_as_curvas_e_a_pior_queda(petr4):
    fechamento, retorno = petr4
    risco = analises.risco_ao_longo_do_tempo(fechamento, retorno, 63)
    dados = _ida_e_volta(esquemas.de_risco(risco))
    assert len(dados["drawdown"]["datas"]) == len(risco.drawdown)
    assert max(v for v in dados["drawdown"]["valores"] if v is not None) <= 0
    assert (
        dados["volatilidade_movel"]["valores"][0] is None
    )  # a janela ainda não encheu
    assert dados["pior_queda"]["queda"] == pytest.approx(risco.pior_drawdown.queda)
    assert dados["janela"] == 63


def test_retorno_mensal_com_os_meses_e_a_tabela(petr4):
    mensal = analises.retorno_mensal(petr4[1])
    dados = _ida_e_volta(esquemas.de_retorno_mensal(mensal))
    assert len(dados["meses"]) == len(mensal.retornos)
    primeiro = mensal.retornos.index[0]
    assert dados["meses"][0]["mes"] == f"{primeiro.year:04d}-{primeiro.month:02d}"
    assert dados["melhor"]["retorno"] == pytest.approx(mensal.melhor)
    assert [linha["ano"] for linha in dados["tabela"]] == list(mensal.tabela.index)
    assert all(len(linha["meses"]) == 12 for linha in dados["tabela"])


def test_comparacao_com_curvas_em_base_100():
    fechamentos = {
        t: carregar_exemplo(t, "2y")["Close"] for t in ("PETR4.SA", "VALE3.SA")
    }
    comparacao = analises.comparacao_de_ativos(fechamentos, TAXA)
    dados = _ida_e_volta(esquemas.de_comparacao(comparacao))
    assert set(dados["curvas"]) == {"PETR4.SA", "VALE3.SA"}
    for curva in dados["curvas"].values():
        assert curva["valores"][0] == pytest.approx(100)
    assert [linha["ticker"] for linha in dados["tabela"]] == ["PETR4.SA", "VALE3.SA"]


def test_comparacao_curta_volta_so_as_contagens():
    curta = analises.Comparacao(10, 2, None, None)
    dados = _ida_e_volta(esquemas.de_comparacao(curta))
    assert dados == {
        "dias_em_comum": 10,
        "dias_descartados": 2,
        "curvas": None,
        "tabela": None,
    }


def test_backtest_com_metricas_e_curva_em_base_100(petr4):
    fechamento, _ = petr4
    posicao = pd.Series(1.0, index=fechamento.index)
    resultado = executar_backtest(fechamento, posicao, 0.001)
    metricas = resumir_desempenho(resultado.retorno, resultado.posicao, None, TAXA)
    dados = _ida_e_volta(esquemas.de_backtest(resultado, metricas))
    assert dados["curva_de_capital"]["valores"][0] == pytest.approx(100)
    assert dados["curva_de_capital"]["valores"][-1] == pytest.approx(
        resultado.curva_de_capital.iloc[-1] * 100
    )
    assert dados["metricas"]["Retorno total"] == pytest.approx(
        metricas["Retorno total"]
    )
    assert dados["operacoes"] == len(resultado.operacoes)


def _nomes_dos_campos(esquema: dict) -> set[str]:
    nomes = set()
    for definicao in [esquema, *esquema.get("$defs", {}).values()]:
        nomes |= set(definicao.get("properties", {}))
    return nomes


def test_nenhum_esquema_entrega_preco_bruto():
    """Licença dos preços (ADR 0008): pela API, só números calculados e curvas normalizadas."""
    modelos = [
        m
        for _, m in inspect.getmembers(esquemas, inspect.isclass)
        if issubclass(m, BaseModel) and m is not BaseModel
    ]
    assert len(modelos) >= 6
    for modelo in modelos:
        nomes = {n.lower() for n in _nomes_dos_campos(modelo.model_json_schema())}
        assert not nomes & CAMPOS_DE_PRECO, (modelo.__name__, nomes & CAMPOS_DE_PRECO)


def test_curva_guarda_as_datas_como_data():
    serie = pd.Series(
        [1.0, float("nan")], index=pd.to_datetime(["2024-01-02", "2024-01-03"])
    )
    curva = esquemas.curva(serie)
    assert curva.datas == [date(2024, 1, 2), date(2024, 1, 3)]
    assert curva.valores == [1.0, None]
