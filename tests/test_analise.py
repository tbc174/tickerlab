"""A fachada de análise do Research (`src/analise.py`): mesmos números do site, proveniência
completa, "indisponível com motivo" e reprodutibilidade."""

import json
import math
from datetime import datetime
from pathlib import Path

import pytest

from scripts import gerar_golden_analise as golden
from src import analise, metricas
from src import indicadores as ind
from src.comparacao import alinhar_fechamentos
from src.correlacao import calcular_retornos, resumir_betas
from src.presets import Preset, resolver

ARQUIVO_GOLDEN = Path(__file__).parent / "arquivos" / "golden_analise.json"


@pytest.fixture(scope="module")
def petr4():
    return golden.dados("PETR4.SA")


@pytest.fixture(scope="module")
def ibov():
    return golden.dados("^BVSP")["Close"]


# --- mesmos números do site ---------------------------------------------------------------------
def test_com_os_padroes_bate_exatamente_com_as_funcoes_do_site(petr4, ibov):
    a = analise.analisar_ativo("PETR4.SA", petr4, benchmark=ibov)
    fechamento = petr4["Close"].dropna()
    retorno = ind.calcular_retorno_diario(fechamento)
    esperado = {
        "retorno_total": ind.calcular_retorno_acumulado(retorno).iloc[-1],
        "retorno_anualizado": ind.calcular_retorno_anualizado(retorno),
        "volatilidade_anual": ind.calcular_volatilidade_anual(retorno),
        "maior_queda": ind.calcular_drawdown(fechamento).min(),
        "sharpe": ind.calcular_indice_sharpe(retorno, 0.0),
        "sortino": metricas.calcular_sortino(retorno, 0.0),
        "var": ind.calcular_var_historico(retorno),  # o "VaR 95%" da Visão geral
        "dias_de_alta": ind.calcular_percentual_dias_positivos(retorno),
        "rsi": ind.calcular_rsi(fechamento, 14).iloc[-1],
        "media_rapida": ind.calcular_media_movel(fechamento, 50).iloc[-1],
        "media_lenta": ind.calcular_media_movel(fechamento, 200).iloc[-1],
        "atr": ind.calcular_atr(petr4, 14).iloc[-1],
    }
    for chave, valor in esperado.items():
        assert a[chave].valor == float(valor), chave
    # o beta da página Correlação e beta (preços alinhados antes dos retornos)
    alinhado, _ = alinhar_fechamentos({"PETR4.SA": fechamento, "^BVSP": ibov})
    beta_da_pagina = resumir_betas(calcular_retornos(alinhado), "^BVSP").loc[
        "PETR4.SA", "Beta"
    ]
    assert a["beta"].valor == pytest.approx(beta_da_pagina, rel=1e-15)


def test_valores_golden_so_mudam_com_versao_nova():
    """Se um número mudou, a fórmula mudou: suba a versão dela em VERSOES_DAS_FORMULAS e rode
    `python -m scripts.gerar_golden_analise`. Mudança silenciosa de cálculo é recusada."""
    guardado = json.loads(ARQUIVO_GOLDEN.read_text(encoding="utf-8"))
    atuais = golden.cenarios()
    assert set(guardado["cenarios"]) == set(atuais)
    for nome, a in atuais.items():
        for chave, metrica in a.metricas.items():
            antes = guardado["cenarios"][nome].get(chave)
            versao_antes = guardado["versoes"].get(chave)
            if versao_antes != metrica.versao_da_formula:
                continue  # fórmula nova de propósito: o golden precisa ser regravado
            if antes is None or metrica.valor is None:
                assert antes == metrica.valor, (nome, chave)
            else:
                assert metrica.valor == pytest.approx(antes, rel=1e-12, abs=1e-15), (
                    f"{nome}/{chave} mudou de {antes} para {metrica.valor} sem mudar a versão"
                )
    assert set(guardado["versoes"]) == set(analise.VERSOES_DAS_FORMULAS)


# --- parâmetros mudam a leitura, nunca os dados (US-03) -------------------------------------------
def test_trocar_o_rsi_recalcula_sem_mexer_nos_precos(petr4):
    antes = petr4.copy(deep=True)
    padrao = analise.analisar_ativo("PETR4.SA", petr4)
    rsi21 = analise.analisar_ativo(
        "PETR4.SA",
        petr4,
        resolver([Preset(escopo="ativo", alvo="PETR4.SA", parametros={"tecnica.rsi_periodo": 21})],
                 ticker="PETR4.SA"),
    )  # fmt: skip
    assert rsi21["rsi"].valor == float(ind.calcular_rsi(petr4["Close"], 21).iloc[-1])
    assert rsi21["rsi"].valor != padrao["rsi"].valor
    assert rsi21["rsi"].parametros["tecnica.rsi_periodo"] == 21
    assert (
        rsi21["retorno_total"].valor == padrao["retorno_total"].valor
    )  # o resto não muda
    assert petr4.equals(antes)  # os preços não foram alterados
    assert rsi21.resolucao.origem("tecnica.rsi_periodo") == "ativo"


def test_cada_metrica_diz_os_parametros_que_usou(petr4):
    a = analise.analisar_ativo("PETR4.SA", petr4)
    assert a["var"].parametros == {"quant.var_confianca": 95}
    assert a["volatilidade_recente"].parametros == {"quant.janela_volatilidade": 252}
    assert a["retorno_total"].parametros == {}
    assert set(a.metricas) == set(analise.VERSOES_DAS_FORMULAS)


# --- indisponível com motivo (US-12) --------------------------------------------------------------
def test_sem_indice_de_referencia_beta_fica_indisponivel_com_motivo(petr4):
    a = analise.analisar_ativo("PETR4.SA", petr4)
    assert a["beta"].valor is None and not a["beta"].disponivel
    assert "^BVSP" in a["beta"].motivo


def test_sem_cdi_sharpe_fica_indisponivel_e_nunca_vira_zero(petr4):
    com_cdi = resolver([], simulacao={"quant.taxa_livre_de_risco": "cdi"})
    sem = analise.analisar_ativo("PETR4.SA", petr4, com_cdi)
    assert sem["sharpe"].valor is None and "CDI" in sem["sharpe"].motivo
    com = analise.analisar_ativo("PETR4.SA", petr4, com_cdi, taxa_cdi_anual=0.1)
    retorno = ind.calcular_retorno_diario(petr4["Close"])
    assert com["sharpe"].valor == ind.calcular_indice_sharpe(retorno, 0.1)


def test_periodo_curto_para_a_janela_explica_o_que_fazer(petr4):
    curto = petr4.iloc[-120:]
    a = analise.analisar_ativo("PETR4.SA", curto)
    assert a["media_lenta"].valor is None
    assert "120 pregões" in a["media_lenta"].motivo and "200" in a["media_lenta"].motivo
    assert a["volatilidade_recente"].valor is None
    assert a["media_rapida"].valor is not None  # 50 cabe em 120


def test_sem_maxima_e_minima_o_atr_fica_indisponivel(petr4):
    a = analise.analisar_ativo("PETR4.SA", petr4[["Close"]])
    assert a["atr"].valor is None and "máxima e mínima" in a["atr"].motivo


def test_nan_e_infinito_viram_indisponivel_nunca_numero():
    assert analise._numero(math.nan) is None
    assert analise._numero(math.inf) is None
    assert analise._numero("abc") is None
    assert analise._numero(0.0) == 0.0


def test_menos_de_dois_pregoes_e_recusado(petr4):
    with pytest.raises(ValueError, match="dois pregões"):
        analise.analisar_ativo("PETR4.SA", petr4.iloc[:1])


# --- proveniência e reprodutibilidade --------------------------------------------------------------
@pytest.mark.parametrize(
    ("origem", "fonte"),
    [
        (None, "Yahoo Finance"),
        ("exemplo", "exemplo"),
        ("cache_antigo", "histórico guardado"),
    ],
)
def test_proveniencia_diz_a_fonte_o_periodo_e_a_moeda(petr4, origem, fonte):
    dados = petr4.copy()
    dados.attrs = {} if origem is None else {"origem": origem}
    p = analise.analisar_ativo("PETR4.SA", dados).proveniencia
    assert fonte in p.fonte
    assert (p.inicio, p.fim, p.pregoes) == (dados.index[0], dados.index[-1], len(dados))
    assert p.moeda == "BRL" and "dividendos" in p.ajuste
    assert len(p.assinatura_dos_dados) == 16


def test_moeda_dos_eua_e_a_convertida():
    aapl = golden.dados("AAPL")
    assert analise.analisar_ativo("AAPL", aapl).proveniencia.moeda == "USD"
    aapl.attrs["moeda"] = "BRL"  # "Converter para reais" ligado no site
    assert analise.analisar_ativo("AAPL", aapl).proveniencia.moeda == "BRL"


def test_mesma_entrada_mesmo_id_em_qualquer_hora(petr4):
    a = analise.analisar_ativo(
        "PETR4.SA", petr4, agora=datetime(2026, 1, 1, tzinfo=analise.FUSO)
    )
    b = analise.analisar_ativo(
        "PETR4.SA", petr4, agora=datetime(2027, 1, 1, tzinfo=analise.FUSO)
    )
    assert a.id_da_execucao == b.id_da_execucao


def test_id_muda_com_dados_ou_parametros(petr4):
    base = analise.analisar_ativo("PETR4.SA", petr4).id_da_execucao
    outros_dados = analise.analisar_ativo("PETR4.SA", petr4.iloc[:-1]).id_da_execucao
    outro_parametro = analise.analisar_ativo(
        "PETR4.SA", petr4, resolver([], simulacao={"tecnica.rsi_periodo": 15})
    ).id_da_execucao
    assert len({base, outros_dados, outro_parametro}) == 3
