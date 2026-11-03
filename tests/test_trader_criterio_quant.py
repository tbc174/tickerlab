"""O pré-registro das estratégias quant P0 está travado pelo hash e bate com os números do código."""

import pytest

from trader import criterio_quant


def test_texto_vigente_e_o_aprovado():
    criterio_quant.conferir()  # não pode levantar erro


def test_texto_alterado_e_recusado(tmp_path):
    copia = tmp_path / "pre-registro.md"
    copia.write_text(
        criterio_quant.ARQUIVO.read_text(encoding="utf-8") + "\nmudança\n",
        encoding="utf-8",
    )
    with pytest.raises(criterio_quant.PreRegistroAlteradoError, match="versão nova"):
        criterio_quant.conferir(copia)


def test_orcamento_das_fichas_soma_o_total_da_versao():
    assert sum(criterio_quant.ORCAMENTO_POR_FICHA.values()) == (
        criterio_quant.ORCAMENTO_DE_TENTATIVAS
    )
    assert set(criterio_quant.FICHAS_SEM_CRITERIO) <= set(
        criterio_quant.ORCAMENTO_POR_FICHA
    )
    assert set(criterio_quant.CANDIDATOS) <= set(criterio_quant.ORCAMENTO_POR_FICHA)


def test_alavancagem_do_nucleo_so_tem_as_duas_versoes():
    assert criterio_quant.ALAVANCAGENS_DO_NUCLEO == (1.0, 1.3)
    assert criterio_quant.QUEDA_MAXIMA == criterio_quant.FREIO_GLOBAL == 0.35
    assert criterio_quant.FREIO_POR_CAMADA > criterio_quant.FREIO_GLOBAL


def test_numeros_do_codigo_aparecem_no_texto():
    texto = criterio_quant.ARQUIVO.read_text(encoding="utf-8")
    assert "**Status: APROVADO, versão 0.1, em 03/11/2026" in texto
    assert "DSR ≥ 0,95" in texto
    assert "≤ 0,30" in texto
    assert "±20% em cada parâmetro mantém ≥ 70% do Sharpe" in texto
    assert "no máximo ⅓ do Sharpe bruto" in texto
    assert "≥ 3,0" in texto
    assert "percentil 95 de 1.000 sinais deslocados" in texto
    assert "limite inferior de 90% (bootstrap em blocos de 21 dias)" in texto
    assert "DSR ≥ 0,90" in texto
    assert "| ≤ 35% |" in texto
    assert "queda de 35% do pico da carteira inteira" in texto
    assert "queda de 40% do pico da própria camada" in texto
    assert "volta no primeiro pregão 12 meses depois do disparo" in texto
    assert "**1,0x** e **1,3x**" in texto
    assert "≥ R$ 5 milhões nos 60 pregões anteriores" in texto
    assert "**Orçamento total desta versão: 60\ntentativas**" in texto
    assert "**+25 tentativas**" in texto
    for ficha, orcamento in criterio_quant.ORCAMENTO_POR_FICHA.items():
        assert f"### Ficha {ficha}." in texto
        assert f"**Orçamento:** {orcamento} tentativas" in texto


# --- a avaliação contra o critério (Evidencia e avaliar) ---------------------------------------

import numpy as np
import pandas as pd

from trader import avaliacao

DATAS = pd.bdate_range("2009-01-02", "2020-12-30")
CDI = pd.Series(0.0003, index=DATAS)


def _ruido(media, semente, desvio=0.01):
    gerador = np.random.default_rng(semente)
    return pd.Series(gerador.normal(media, desvio, len(DATAS)), index=DATAS)


def _excesso(serie):
    return avaliacao.sharpe(serie - CDI)


def _evidencia_boa(**mudancas):
    candidato = CDI + _ruido(0.0010, 1)
    candidatos = pd.DataFrame(
        {
            "risk_parity": candidato,
            "inverso_vol": CDI + _ruido(0.0008, 2),
            "min_var": CDI + _ruido(0.0007, 3),
        }
    )
    sharpe = _excesso(candidato)
    base = {
        "candidato": candidato,
        "cdi": CDI,
        "candidatos": candidatos,
        "candidatos_estresse": candidatos - 0.0001,
        "sharpe_bruto": sharpe * 1.1,
        "sharpes_vizinhos": {
            "janela_202": sharpe * 0.9,
            "janela_302": sharpe * 0.95,
            "banda_0.16": sharpe,
            "banda_0.24": sharpe * 0.85,
        },
        "reguas": {"60/40": CDI + _ruido(0.0001, 4), "CDI": CDI},
        "p_valor_do_acaso": 0.001,
        "sharpe_olhando_o_futuro": sharpe + 0.5,
        "reexecucao_identica": True,
        "cortar_o_futuro_nao_muda": True,
        "tentativas_totais": 107,
    }
    return criterio_quant.Evidencia(**{**base, **mudancas})


def test_evidencia_boa_e_aprovada_com_todos_os_itens():
    veredito = criterio_quant.avaliar(_evidencia_boa())
    assert [i.codigo for i in veredito.itens] == [
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "A7",
        "A8",
        "F1",
        "V",
    ]
    assert veredito.aprovado, veredito.reprovados
    assert not veredito.inconclusivo
    a2 = veredito.itens[1]
    assert a2.passou and a2.valor is None and "não se aplica" in a2.limite


def test_ruido_sem_excesso_sobre_o_cdi_reprova():
    candidato = CDI + _ruido(0.0, 7)
    candidatos = pd.DataFrame(
        {
            "risk_parity": candidato,
            "inverso_vol": CDI + _ruido(0.0, 8),
            "min_var": CDI + _ruido(0.0, 9),
        }
    )
    veredito = criterio_quant.avaliar(
        _evidencia_boa(
            candidato=candidato,
            candidatos=candidatos,
            candidatos_estresse=candidatos - 0.0001,
            sharpe_bruto=0.1,
        )
    )
    assert not veredito.aprovado
    assert {"A1", "A5", "A7"} <= set(veredito.reprovados)


@pytest.mark.parametrize(
    ("mudanca", "item"),
    [
        ({"sharpes_vizinhos": {"janela_202": 0.1}}, "A3"),
        ({"sharpe_bruto": 10.0}, "A4"),
        ({"p_valor_do_acaso": 0.2}, "A6"),
        ({"reexecucao_identica": False}, "V"),
        ({"cortar_o_futuro_nao_muda": False}, "V"),
        ({"dados_conforme": False}, "V"),
        ({"pbo": 0.5}, "A2"),
    ],
)
def test_cada_item_reprova_sozinho(mudanca, item):
    veredito = criterio_quant.avaliar(_evidencia_boa(**mudanca))
    assert veredito.reprovados == [item]


def test_futuro_que_nao_infla_reprova_a_verificacao():
    boa = _evidencia_boa()
    veredito = criterio_quant.avaliar(
        _evidencia_boa(sharpe_olhando_o_futuro=_excesso(boa.candidato))
    )
    assert veredito.reprovados == ["V"]


def test_estresse_e_queda_sao_medidos_no_estresse_e_no_candidato():
    boa = _evidencia_boa()
    piores = boa.candidatos - 0.002
    assert criterio_quant.avaliar(
        _evidencia_boa(candidatos_estresse=piores)
    ).reprovados == ["A8"]
    tombo = boa.candidato.copy()
    tombo.iloc[1000:1010] = -0.05  # queda de ~40% em dez dias
    assert "F1" in criterio_quant.avaliar(_evidencia_boa(candidato=tombo)).reprovados


def test_tentativas_anteriores_somam_m2_scalp_e_o_registro_da_p2(tmp_path):
    assert (
        criterio_quant.TENTATIVAS_DA_M2 == 101
        and criterio_quant.TENTATIVAS_DO_SCALP == 2
    )
    assert criterio_quant.tentativas_anteriores(tmp_path / "nao-existe.db") == 103
    from trader.registro import Registro

    registro = Registro(
        tmp_path / "registro.db", familias=("K", "B"), commit_fn=lambda: "x"
    )
    registro.registrar("K", "k1", {"a": 1})
    assert criterio_quant.tentativas_anteriores(tmp_path / "registro.db") == 104
