"""Ficha P0-1: a rodada completa com dados sintéticos e um registro temporário."""

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.estrategias import rodar_tendencia_cripto as rodar
from trader.estrategias import tendencia_cripto as tc

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("tendencia_cripto")
DIAS = pd.date_range("2018-01-01", periods=1500, freq="D")
CDI = pd.Series(0.0003, index=DIAS)
VOLUMES = pd.DataFrame(1e9, index=DIAS, columns=list(tc.ATIVOS))


def _precos(semente=11):
    """Tendências longas alternadas: a regra tem o que seguir e olhar o futuro infla o Sharpe."""
    gerador = np.random.default_rng(semente)
    fase = (np.arange(len(DIAS)) // 200) % 2
    media = np.where(fase == 0, 0.003, -0.002)
    retornos = gerador.normal(media[:, None], 0.03, size=(len(DIAS), 2))
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=DIAS, columns=list(tc.ATIVOS)
    )


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("p0_1") / "registro.db")
    precos = _precos()
    saida = rodar.executar(precos, CDI, VOLUMES, registro)
    return precos, registro, saida


def test_registra_uma_tentativa_da_familia_p0_1(rodada):
    _, registro, saida = rodada
    assert registro.contar() == 1
    tentativa = registro.obter(saida["id"])
    assert tentativa["familia"] == "P0-1" and tentativa["nome"] == rodar.NOME
    assert tentativa["spec"]["candidato"] == criterio_quant.CANDIDATOS["P0-1"]
    assert tentativa["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert tentativa["spec"]["janelas"] == list(tc.JANELAS)
    assert tentativa["spec"]["execucao"] == "fechamento de D+1"
    assert tentativa["resultado"]["veredito"]["itens"]
    assert tentativa["resultado"]["brasil"]["meses_simulados"] > 0


def test_rodar_de_novo_nao_conta_configuracao_nova(rodada):
    precos, registro, _ = rodada
    rodar.executar(precos, CDI, VOLUMES, registro)
    assert registro.contar() == 1
    assert registro.execucoes() == 2  # mas toda execução conta no DSR


def test_veredito_completo_sem_pbo(rodada):
    veredito = rodada[2]["veredito"]
    itens = {i.codigo: i for i in veredito.itens}
    assert list(itens) == ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "F1", "V"]
    assert itens["A2"].valor is None and itens["A2"].passou
    assert itens["V"].passou


def test_resumo_e_teste_do_brasil(rodada):
    saida = rodada[2]
    assert {
        "sharpe_do_excesso",
        "sharpe_365",
        "queda_com_freio",
        "exposicao_media",
        "giro",
        "meses_acima_da_isencao",
        "caixa_minimo",
    } <= set(saida["resumo"])
    brasil = saida["brasil"]
    assert brasil["retorno_anual_caixa_a_cdi"] > brasil["retorno_anual_caixa_a_zero"]
    assert 0 <= brasil["meses_acima_da_isencao"] <= brasil["meses_simulados"]
    assert brasil["cambio_total"] > 0
    assert saida["estresse"]["custos"] > saida["resumo"]["custos"]
    assert set(saida["vizinhos"]) == set(rodar.VIZINHOS)
    assert set(saida["reguas"]) == {"BTC comprar e segurar", "CDI"}
    assert saida["inicio_das_series"] == {"BTC": "2018-01-01", "ETH": "2018-01-01"}
    assert saida["primeiro_dia_simulado"] == "2019-01-01"


def test_anos_para_t_segue_a_regua_do_pre_registro():
    assert rodar.anos_para_t(1.0) == 9.0
    assert rodar.anos_para_t(0.5) == 36.0
    assert rodar.anos_para_t(0.0) == float("inf")


def test_relatorio_tem_as_tabelas_e_os_limites(rodada, tmp_path):
    texto = rodar.escrever_relatorio(rodada[2], tmp_path).read_text(encoding="utf-8")
    assert "### BTC e ETH 50/50" in texto
    assert "## Teste do Brasil" in texto and "R$ 35 mil" in texto
    assert "Primeiro preço de cada série" in texto and "(t ÷ SR)²" in texto
    assert "## Limites e cuidados" in texto
    assert "recomendação de investimento" in texto


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(_precos(), CDI, VOLUMES, registro)
    assert registro.contar() == 0


def test_vizinhos_sao_os_do_plato_de_20_por_cento():
    assert rodar.VIZINHOS["janelas_x1.2"]["janelas"] == tc.escalar_janelas(
        tc.JANELAS, 1.2
    )
    assert rodar.VIZINHOS["vol_alvo_0.20"]["vol_alvo"] == pytest.approx(0.25 * 0.8)
    assert rodar.VIZINHOS["janela_da_vol_108"]["janela_da_vol"] == 90 * 1.2
