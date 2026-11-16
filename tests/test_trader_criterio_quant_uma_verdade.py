"""Os números do pré-registro quant têm uma verdade só: as conferências leem `criterio_quant.py`.

Antes (linha 710 da fila), `VARIACAO_DO_PLATO`, `CONFIANCA_CONTRA_A_REGUA`,
`FRACAO_MINIMA_DO_SHARPE_NO_HOLDOUT` e `QUEDA_MAXIMA_RELATIVA_NO_HOLDOUT` só serviam ao teste do
texto; o ±20%, o 90% e o B1/B2 viviam soltos em outros arquivos. Aqui, cada teste muda a constante
e confere que o resultado acompanha, e confere que, com os valores aprovados, nada mudou.
"""

import numpy as np
import pandas as pd

from trader import criterio, criterio_quant, validacao
from trader.estrategias import (
    combinada,
    rodar_p0_1b,
    rodar_tendencia_b3,
    rodar_tendencia_cripto,
    tendencia_b3,
    tendencia_cripto,
)

DATAS = pd.bdate_range("2015-01-02", "2020-12-30")
CDI = pd.Series(0.0003, index=DATAS)
HOLD = pd.bdate_range("2023-10-10", "2026-10-09")


def _ruido(media: float, semente: int, desvio: float = 0.01) -> pd.Series:
    gerador = np.random.default_rng(semente)
    return pd.Series(gerador.normal(media, desvio, len(DATAS)), index=DATAS)


def _holdout() -> pd.Series:
    gerador = np.random.default_rng(5)
    return pd.Series(gerador.normal(0.0002, 0.01, len(HOLD)), index=HOLD)


def _limite(indice: int, desenvolvimento: float, queda: float) -> str:
    r = _holdout()
    veredito = criterio_quant.avaliar_holdout(r, r, r * 0, desenvolvimento, queda)
    return veredito.itens[indice].limite


# --- A3: o platô ---------------------------------------------------------------------------


def test_fatores_do_plato_saem_da_variacao_e_valem_08_e_12_exatos():
    assert criterio_quant.FATOR_DO_PLATO_ABAIXO == 1 - criterio_quant.VARIACAO_DO_PLATO
    assert criterio_quant.FATOR_DO_PLATO_ACIMA == 1 + criterio_quant.VARIACAO_DO_PLATO
    # igualdade exata: o resultado das rodadas já feitas não pode mudar na última casa
    assert criterio_quant.FATOR_DO_PLATO_ABAIXO == 0.8
    assert criterio_quant.FATOR_DO_PLATO_ACIMA == 1.2


def test_vizinhas_da_c1_seguem_a_variacao_do_criterio(monkeypatch):
    base = combinada.ParametrosC1()
    monkeypatch.setattr(combinada, "FATOR_DO_PLATO_ABAIXO", 0.5)
    monkeypatch.setattr(combinada, "FATOR_DO_PLATO_ACIMA", 1.5)
    vizinhas = combinada.variacoes_do_plato()
    assert {v.janela for v in vizinhas} == {
        round(base.janela * 0.5),
        round(base.janela * 1.5),
        base.janela,
    }
    assert {v.teto for v in vizinhas} >= {base.teto * 0.5, base.teto * 1.5}
    assert {v.banda for v in vizinhas} >= {base.banda * 0.5, base.banda * 1.5}


def test_vizinhos_das_tendencias_valem_os_de_sempre():
    for rodar, estrategia in (
        (rodar_tendencia_b3, tendencia_b3),
        (rodar_tendencia_cripto, tendencia_cripto),
    ):
        janelas = estrategia.JANELAS
        assert rodar.VIZINHOS["janelas_x0.8"]["janelas"] == tuple(
            max(2, round(j * 0.8)) for j in janelas
        )
        assert rodar.VIZINHOS["janelas_x1.2"]["janelas"] == tuple(
            max(2, round(j * 1.2)) for j in janelas
        )


def test_vizinhos_da_banda_da_p0_1b_valem_os_pre_registrados():
    assert rodar_p0_1b.VIZINHOS["banda_0.16"] == {"banda": 0.16}
    assert rodar_p0_1b.VIZINHOS["banda_0.24"] == {"banda": 0.24}


# --- A7: o intervalo do bootstrap --------------------------------------------------------------


def test_percentis_do_intervalo_sem_ruido_de_ponto_flutuante():
    assert validacao._percentis_do_intervalo(0.90) == (5.0, 95.0)
    assert validacao._percentis_do_intervalo(0.95) == (2.5, 97.5)


def test_bootstrap_padrao_continua_com_as_chaves_ic90():
    r = validacao.bootstrap_do_sharpe(_ruido(0.001, 1), bloco=21)
    d = validacao.bootstrap_diferenca_de_sharpe(
        _ruido(0.001, 1), _ruido(0, 2), bloco=21
    )
    assert {"ic90_inferior", "ic90_superior"} <= set(r)
    assert {"ic90_inferior", "ic90_superior"} <= set(d)


def test_bootstrap_com_outra_confianca_muda_o_intervalo_e_o_nome():
    serie = _ruido(0.001, 1)
    p90 = validacao.bootstrap_do_sharpe(serie, bloco=21, confianca=0.90)
    p95 = validacao.bootstrap_do_sharpe(serie, bloco=21, confianca=0.95)
    assert p95["ic95_inferior"] < p90["ic90_inferior"]
    assert p95["ic95_superior"] > p90["ic90_superior"]
    assert "ic90_inferior" not in p95


def test_conferencia_contra_a_regua_usa_a_confianca_do_criterio(monkeypatch):
    excesso = _ruido(0.0008, 1)
    regua = CDI + _ruido(0.0001, 2)
    direto = validacao.bootstrap_diferenca_de_sharpe(
        excesso, regua - CDI, bloco=criterio_quant.BLOCO_DO_BOOTSTRAP_EM_DIAS
    )["ic90_inferior"]
    assert criterio_quant._contra_a_regua(excesso, regua, CDI) == direto

    monkeypatch.setattr(criterio_quant, "CONFIANCA_CONTRA_A_REGUA", 0.95)
    assert criterio_quant._contra_a_regua(excesso, regua, CDI) < direto


def test_conferencia_contra_a_regua_sem_risco_usa_a_mesma_confianca(monkeypatch):
    excesso = _ruido(0.0008, 1)
    aprovado = criterio_quant._contra_a_regua(excesso, CDI, CDI)
    assert (
        aprovado
        == validacao.bootstrap_do_sharpe(
            excesso, bloco=criterio_quant.BLOCO_DO_BOOTSTRAP_EM_DIAS
        )["ic90_inferior"]
    )
    monkeypatch.setattr(criterio_quant, "CONFIANCA_CONTRA_A_REGUA", 0.95)
    assert criterio_quant._contra_a_regua(excesso, CDI, CDI) < aprovado


# --- B1 e B2: o holdout --------------------------------------------------------------------


def test_holdout_quant_com_os_numeros_aprovados_e_igual_ao_da_m2():
    r = _holdout()
    b1 = r.shift(1).fillna(
        0.0
    )  # uma série com variação (Sharpe finito: NaN != NaN no ==)
    quant = criterio_quant.avaliar_holdout(r, r, b1, 2.0, -0.5)
    m2 = criterio.avaliar_holdout(r, r, b1, 2.0, -0.5)
    assert [(i.codigo, i.valor, i.limite, i.passou) for i in quant.itens] == [
        (i.codigo, i.valor, i.limite, i.passou) for i in m2.itens
    ]


def test_b1_do_holdout_quant_segue_a_fracao_do_criterio(monkeypatch):
    assert ">= 1.000" in _limite(0, 2.0, -0.5)
    monkeypatch.setattr(criterio_quant, "FRACAO_MINIMA_DO_SHARPE_NO_HOLDOUT", 0.75)
    assert ">= 1.500" in _limite(0, 2.0, -0.5)


def test_b1_do_holdout_quant_segue_o_piso_do_criterio(monkeypatch):
    assert ">= 0.300" in _limite(0, 0.2, -0.5)
    monkeypatch.setattr(criterio_quant, "SHARPE_MINIMO_NO_HOLDOUT", 0.45)
    assert ">= 0.450" in _limite(0, 0.2, -0.5)


def test_b2_do_holdout_quant_segue_a_queda_relativa_do_criterio(monkeypatch):
    assert ">= -0.150" in _limite(1, 1.0, -0.10)
    monkeypatch.setattr(criterio_quant, "QUEDA_MAXIMA_RELATIVA_NO_HOLDOUT", 3.0)
    assert ">= -0.300" in _limite(1, 1.0, -0.10)


def test_holdout_da_m2_nao_muda_com_as_constantes_do_quant(monkeypatch):
    monkeypatch.setattr(criterio_quant, "FRACAO_MINIMA_DO_SHARPE_NO_HOLDOUT", 0.9)
    r = _holdout()
    assert (
        ">= 1.000" in criterio.avaliar_holdout(r, r, r * 0, 2.0, -0.5).itens[0].limite
    )
