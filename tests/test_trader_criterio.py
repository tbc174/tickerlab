"""O critério aprovado em código: limiares iguais ao texto, aprova o forte e reprova o fraco."""

import numpy as np
import pandas as pd
import pytest

from trader import criterio as c
from trader.holdout import CAMINHO_DO_CRITERIO

DATAS = pd.bdate_range("2000-01-03", "2023-09-08")


def _ruido(media, vol, seed, datas=DATAS):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(media, vol, len(datas)), index=datas)


def _evidencia(forte=True):
    media = 0.0006 if forte else 0.0
    por_ativo = {f"A{i}": _ruido(media, 0.01, i) for i in range(8)}
    carteira = pd.concat(por_ativo, axis=1).mean(axis=1)
    caminhos = [carteira + _ruido(0, 0.0005, 100 + j) for j in range(9)]
    caminhos_x2 = [cam - 0.00005 for cam in caminhos]
    alternativas = {f"alt{j}": _ruido(0, 0.004, 200 + j) for j in range(9)}
    candidatos = pd.concat({"candidato": caminhos[0], **alternativas}, axis=1)
    return c.EvidenciaDoDesenvolvimento(
        caminhos=caminhos,
        caminhos_x2=caminhos_x2,
        por_ativo=por_ativo,
        b1=_ruido(0, 0.005, 300),
        candidatos=candidatos,
        candidatos_x2=candidatos - 0.00005,
        tentativas_totais=40,
        p_valor_do_acaso=0.01 if forte else 0.4,
        vazamento={
            "futuro_inflou": True,
            "rotulos_embaralhados_zero": True,
            "reprodutivel": True,
        },
    )


def test_limiares_sao_os_do_texto_aprovado():
    texto = CAMINHO_DO_CRITERIO.read_text(encoding="utf-8")
    assert (c.DSR_MINIMO, c.PBO_MAXIMO, c.T_MINIMO) == (0.95, 0.25, 3.0)
    assert c.CAMINHOS_POSITIVOS_MINIMOS == 8
    assert (c.FRACAO_DE_ATIVOS_POSITIVOS_MINIMA, c.PARTICIPACAO_MAXIMA) == (0.60, 0.25)
    assert c.FRACAO_DE_ANOS_POSITIVOS_MINIMA == 0.65
    assert c.DSR_MINIMO_NO_ESTRESSE == 0.90 and c.P_VALOR_MAXIMO_DO_ACASO == 0.05
    assert (c.SHARPE_MINIMO_NO_HOLDOUT, c.DESCONTO_DE_DECAIMENTO) == (0.30, 0.50)
    assert c.QUEDA_MAXIMA_RELATIVA == 1.5
    for trecho in (
        "probabilidade ≥ **0,95**",
        "≤ **0,25**",
        "≥ **3,0**",
        "pelo menos 8 dos 9",
        "≥ **60%**",
        "≤ **25%**",
        "≥ **65%**",
        "DSR ≥ **0,90**",
        "percentil 95",
        "max(0,3; 0,5 × Sharpe do desenvolvimento)",
        "1,5 ×",
    ):
        assert trecho in texto, trecho


def test_candidato_forte_passa_em_tudo():
    v = c.avaliar_desenvolvimento(_evidencia(forte=True))
    assert v.reprovados == [], [
        (i.codigo, i.valor, i.limite) for i in v.itens if not i.passou
    ]
    assert v.aprovado and not v.inconclusivo
    registro = v.para_registro()
    assert registro["aprovado"] is True and len(registro["itens"]) == 11


def test_candidato_sem_sinal_e_reprovado_com_os_motivos():
    v = c.avaliar_desenvolvimento(_evidencia(forte=False))
    assert not v.aprovado
    # A4 pode passar por sorte (os 9 caminhos aqui dividem o mesmo ruído); A1, A3 e A10 não
    for codigo in ("A1", "A3", "A10"):
        assert codigo in v.reprovados


def test_sem_verificacoes_de_vazamento_nao_aprova():
    e = _evidencia(forte=True)
    e.vazamento = {}
    assert "V" in c.avaliar_desenvolvimento(e).reprovados
    e.vazamento = {"futuro_inflou": True, "rotulos_embaralhados_zero": False}
    assert "V" in c.avaliar_desenvolvimento(e).reprovados


def test_concentracao_num_ativo_reprova_a7():
    e = _evidencia(forte=True)
    e.por_ativo = {
        "A0": _ruido(0.002, 0.01, 1),
        **{f"B{i}": _ruido(0, 0.01, 50 + i) for i in range(4)},
    }
    assert "A7" in c.avaliar_desenvolvimento(e).reprovados


def test_custos_dobrados_que_viram_prejuizo_reprovam_a9():
    e = _evidencia(forte=True)
    e.caminhos_x2 = [cam - 0.003 for cam in e.caminhos]
    assert "A9" in c.avaliar_desenvolvimento(e).reprovados


def test_exige_os_9_caminhos():
    e = _evidencia()
    e.caminhos = e.caminhos[:5]
    with pytest.raises(ValueError, match="9 caminhos"):
        c.avaliar_desenvolvimento(e)


def test_caminho_mediano_e_o_do_meio():
    caminhos = [_ruido(m, 0.01, i) for i, m in enumerate(np.linspace(-0.001, 0.001, 9))]
    assert c.indice_do_caminho_mediano(caminhos) == 4


# --- holdout -------------------------------------------------------------------------------

HOLD = pd.bdate_range("2023-10-10", "2026-10-09")


def test_holdout_aprova_quando_mantem_metade_do_sharpe():
    bom = _ruido(0.001, 0.006, 1, HOLD)  # Sharpe esperado ~2,6 (3 anos variam muito)
    v = c.avaliar_holdout(
        bom,
        bom - 0.00005,
        _ruido(0, 0.006, 2, HOLD),
        sharpe_do_desenvolvimento=1.5,
        queda_mediana_do_desenvolvimento=-0.10,
    )
    assert v.aprovado, v.reprovados


def test_holdout_reprova_decaimento_queda_e_derrota_para_a_b1():
    fraco = _ruido(0.0, 0.01, 3, HOLD)
    v = c.avaliar_holdout(
        fraco,
        fraco - 0.001,
        _ruido(0.001, 0.01, 4, HOLD),
        sharpe_do_desenvolvimento=2.0,
        queda_mediana_do_desenvolvimento=-0.02,
    )
    assert {"B1", "B2", "B3", "B4"} <= set(v.reprovados)


def test_piso_do_holdout_e_o_maior_entre_03_e_metade():
    r = _ruido(0.0002, 0.01, 5, HOLD)
    baixo = c.avaliar_holdout(r, r, r * 0, 0.2, -0.5)
    assert ">= 0.300" in baixo.itens[0].limite
    alto = c.avaliar_holdout(r, r, r * 0, 2.0, -0.5)
    assert ">= 1.000" in alto.itens[0].limite


# --- contra o acaso ------------------------------------------------------------------------


def _mercado(n=3000, k=5, seed=7):
    rng = np.random.default_rng(seed)
    datas = pd.bdate_range("2005-01-03", periods=n)
    return pd.DataFrame(
        rng.normal(0, 0.01, (n, k)), index=datas, columns=list("ABCDE")[:k]
    )


def test_acaso_reconhece_habilidade_de_verdade():
    r = _mercado()
    sabe_o_amanha = np.sign(r.shift(-1)).fillna(
        0.0
    )  # trapaça de propósito: só para o teste
    res = c.p_valor_do_acaso_da_carteira(
        sabe_o_amanha, r, pd.Series(0.0001, index=r.columns), 300
    )
    assert res["p_valor"] <= 0.01 and res["sharpe_real"] > res["percentil_95"]


def test_acaso_nao_ve_habilidade_em_sinal_aleatorio():
    r = _mercado()
    rng = np.random.default_rng(1)
    aleatorio = pd.DataFrame(
        np.sign(rng.normal(size=r.shape)), index=r.index, columns=r.columns
    )
    res = c.p_valor_do_acaso_da_carteira(
        aleatorio, r, pd.Series(0.0, index=r.columns), 300
    )
    assert res["p_valor"] > 0.05


def test_acaso_respeita_ativo_sem_dado_e_valida_formato():
    r = _mercado()
    r.iloc[:500, 0] = np.nan  # ativo A começa depois
    pos = pd.DataFrame(1.0, index=r.index, columns=r.columns)
    res = c.p_valor_do_acaso_da_carteira(pos, r, pd.Series(0.0, index=r.columns), 200)
    assert np.isfinite(res["sharpe_real"])
    with pytest.raises(ValueError, match="mesmas datas"):
        c.p_valor_do_acaso_da_carteira(
            pos.iloc[:10], r, pd.Series(0.0, index=r.columns)
        )
