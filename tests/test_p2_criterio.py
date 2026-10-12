"""Pesquisa 2, P5 parte 4: o critério (dados sintéticos; nenhum dado real)."""

import numpy as np
import pandas as pd

from trader.p2 import criterio

DATAS = pd.bdate_range("1980-01-01", "2023-09-08")
GRUPOS = {
    f"m{i}": ("moedas", "indices", "metais", "energia", "titulos")[i % 5]
    for i in range(10)
}


def _ruido(semente, media=0.0, desvio=0.001):
    return np.random.default_rng(semente).normal(media, desvio, len(DATAS))


def _evidencia(media_diaria, **mudancas):
    por_mercado = pd.DataFrame(
        {m: _ruido(i, media_diaria / 10, 0.002) for i, m in enumerate(GRUPOS)},
        index=DATAS,
    )
    candidato = por_mercado.sum(axis=1)
    b1 = pd.Series(_ruido(99, 0.0004, 0.0063), index=DATAS)
    candidatos = pd.DataFrame(
        {
            "K1": candidato + pd.Series(_ruido(7, 0.0, 0.002), index=DATAS),
            "K2": candidato,
            "B0": pd.Series(_ruido(8, 0.00045, 0.0063), index=DATAS),
            "B1": b1,
        }
    )
    base = {
        "candidato": candidato,
        "por_mercado": por_mercado,
        "grupo_do_mercado": GRUPOS,
        "b1": b1,
        "candidatos": candidatos,
        "candidatos_a": candidatos,
        "candidatos_b": candidatos,
        "tentativas_totais": 105,
        "p_valor_do_acaso": 0.01,
        "sharpe_olhando_o_futuro": 9.0,
        "reexecucao_identica": True,
    }
    base.update(mudancas)
    return criterio.Evidencia(**base)


def test_estrategia_forte_e_aprovada():
    """K1 parecido com K2 (como na pesquisa real); se só o K2 fosse bom, o DSR exigiria mais."""
    veredito = criterio.avaliar(_evidencia(0.0005))
    assert veredito.reprovados == [] and veredito.aprovado


def test_estrategia_sem_vantagem_reprova_em_varios_itens():
    veredito = criterio.avaliar(_evidencia(0.0))
    assert {"A1", "A3", "A5"} <= set(veredito.reprovados)


def test_a2_exige_a_ultima_decada_positiva():
    e = _evidencia(0.0005)
    ruim = e.candidato.copy()
    ultima = ruim.index >= "2010-01-01"
    ruim[ultima] = -ruim[ultima].abs()
    veredito = criterio.avaliar(_evidencia(0.0005, candidato=ruim))
    assert "A2" in veredito.reprovados


def test_a7_reprova_quando_um_mercado_carrega_tudo():
    e = _evidencia(0.0)
    por_mercado = e.por_mercado.copy()
    por_mercado["m0"] += 0.001
    veredito = criterio.avaliar(
        _evidencia(0.0, por_mercado=por_mercado, candidato=por_mercado.sum(axis=1))
    )
    assert "A7" in veredito.reprovados


def test_v_reprova_se_olhar_o_futuro_nao_inflar_ou_a_reexecucao_mudar():
    assert (
        "V"
        in criterio.avaliar(_evidencia(0.0005, sharpe_olhando_o_futuro=1.0)).reprovados
    )
    assert (
        "V"
        in criterio.avaliar(_evidencia(0.0005, reexecucao_identica=False)).reprovados
    )


def test_a10_usa_o_p_valor_informado():
    assert (
        "A10" in criterio.avaliar(_evidencia(0.0005, p_valor_do_acaso=0.2)).reprovados
    )


def test_limiares_sao_os_do_pre_registro():
    assert criterio.DSR_MINIMO == 0.95
    assert criterio.T_MINIMO == 3.0
    assert criterio.FRACAO_DE_ANOS_POSITIVOS_MINIMA == 0.60
    assert criterio.PARTICIPACAO_MAXIMA_DO_MERCADO == 0.25
    assert criterio.PARTICIPACAO_MAXIMA_DO_GRUPO == 0.50
    assert criterio.DSR_MINIMO_NO_ESTRESSE == 0.90
    assert criterio.P_VALOR_MAXIMO_DO_ACASO == 0.05
    assert criterio.INICIO_DA_AVALIACAO == pd.Timestamp("1980-01-01")


# --- A10 --------------------------------------------------------------------------------------
def _caso_do_acaso(com_habilidade):
    n = 3000
    datas = pd.bdate_range("2000-01-03", periods=n)
    rng = np.random.default_rng(5)
    retornos = pd.DataFrame(
        rng.normal(0, 0.01, (n, 3)), index=datas, columns=list("abc")
    )
    if com_habilidade:
        posicoes = (
            np.sign(retornos.shift(-1)).fillna(0) * 0.3
        )  # sabe o amanhã: habilidade máxima
    else:
        posicoes = pd.DataFrame(
            rng.choice([-0.3, 0.3], (n, 3)), index=datas, columns=list("abc")
        )
    zeros = pd.Series(0.0, index=list("abc"))
    return criterio.p_valor_do_acaso(
        posicoes, retornos, zeros, zeros, pd.Series(1.0, index=datas), sorteios=200
    )


def test_acaso_separa_habilidade_de_sorte():
    assert _caso_do_acaso(True)["p_valor"] < 0.05
    assert _caso_do_acaso(False)["p_valor"] > 0.05
