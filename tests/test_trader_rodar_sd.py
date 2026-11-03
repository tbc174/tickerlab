"""Ficha P0-7: a rodada do estudo com caminhos pequenos, séries sintéticas e um registro temporário."""

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.estrategias import rodar_sd as rodar
from trader.estrategias import sd_simulador as sd
from trader.holdout import FIM_DO_DESENVOLVIMENTO, HoldoutVazandoError

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("rodar_sd")
CAMINHOS, ANOS = 6, 1


def _serie(datas, semente, sigma):
    sorteio = np.random.default_rng(semente)
    log = sorteio.normal(0.0003, sigma, len(datas))
    return pd.Series(100 * np.exp(np.cumsum(log)), index=datas)


def _series():
    dias = pd.date_range("2018-01-01", periods=1_000, freq="D")
    pregoes = pd.bdate_range("2018-01-01", periods=700)
    return {
        "BTC em reais": (_serie(dias, 1, 0.04), pd.Series(0.0004, dias), "cripto", 365),
        "BOVA11": (_serie(pregoes, 2, 0.015), pd.Series(0.0005, pregoes), "etf", 252),
    }


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("p0_7") / "registro.db")
    saida = rodar.executar(_series(), registro, caminhos=CAMINHOS, anos=ANOS)
    return registro, saida


def test_registra_uma_tentativa_da_familia_p0_7(rodada):
    registro, saida = rodada
    assert registro.contar() == 1
    tentativa = registro.obter(saida["id"])
    assert tentativa["familia"] == "P0-7" and tentativa["nome"] == rodar.NOME
    assert tentativa["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert tentativa["spec"]["caminhos"] == CAMINHOS
    assert tentativa["spec"]["historico"]["BOVA11"]["classe"] == "etf"
    assert set(tentativa["resultado"]) >= {"monte_carlo", "day_trade", "historico"}


def test_monte_carlo_tem_os_quatro_cenarios_e_os_testes_do_brasil(rodada):
    monte_carlo = rodada[1]["monte_carlo"]
    assert list(monte_carlo) == [c.nome for c in rodar.CENARIOS]
    for nome, cenario in monte_carlo.items():
        assert list(cenario["base"]) == list(sd.REGRAS)
        assert set(cenario["caixa_a_zero"]) == set(sd.REGRAS)
        assert set(cenario["relatorio"]) == {"comprar_e_segurar", "full"}
        assert cenario["base"]["full"]["caminhos"] == CAMINHOS
        # teto só onde há isenção (o ETF não tem); "como ações" só no ETF
        assert ("teto" in cenario) == ("Ibovespa" not in nome)
        assert ("como_acoes" in cenario) == ("Ibovespa" in nome)


def test_day_trade_so_nos_cenarios_da_b3(rodada):
    day_trade = rodada[1]["day_trade"]
    assert list(day_trade) == list(rodar.CENARIOS_DO_DAY_TRADE)
    for cenario in day_trade.values():
        assert cenario["bloqueado"]["full"]["dias_de_day_trade"] == 0
        assert set(cenario["livre"]) == {"comprar_e_segurar", *rodar.REGRAS_COM_VENDA}


def test_historico_em_janelas_e_cambio_so_no_btc(rodada):
    historico = rodada[1]["historico"]
    assert historico["BTC em reais"]["janelas"] > 1
    assert "com_cambio" in historico["BTC em reais"]
    assert "com_cambio" not in historico["BOVA11"]
    assert "como_acoes" in historico["BOVA11"] and "teto" not in historico["BOVA11"]
    assert (
        historico["BOVA11"]["primeiro_comeco"] > historico["BOVA11"]["primeiro_preco"]
    )


def test_reexecucao_identica(rodada):
    assert rodada[1]["reexecucao_identica"] is True


def test_relatorio_tem_as_tabelas_e_os_limites(rodada, tmp_path):
    texto = rodar.escrever_relatorio(rodada[1], tmp_path).read_text("utf-8")
    for trecho in (
        "## 1. Monte Carlo",
        "## 2. A versão do relatório",
        "## 3. Histórico",
        "## 4. Testes do Brasil",
        "(c) Ordens limitadas",
        "## Limites e cuidados",
        "Nada aqui é recomendação de investimento",
        "Estudo, não candidata",
    ):
        assert trecho in texto
    assert (
        texto.count("| Comprar e segurar |") >= 4 + 3
    )  # os 4 cenários e 3 tabelas do histórico


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(_series(), registro, caminhos=CAMINHOS, anos=ANOS)
    assert registro.contar() == 0


def _carregar_com(monkeypatch, fim_do_btc):
    dias = pd.date_range("2018-01-01", fim_do_btc, freq="D")
    pregoes = pd.bdate_range("2018-01-01", "2024-06-28")
    barras = pd.DataFrame(
        {"abertura": 10.0, "fechamento": 10.0, "volume": 1.0}, index=pregoes
    )
    monkeypatch.setattr(
        rodar.rodar_tendencia_cripto,
        "carregar_tabelas",
        lambda *_: (pd.DataFrame({"BTC": 1.0}, index=dias), pd.Series(0.0, dias), None),
    )
    monkeypatch.setattr(rodar.dados_b3, "barras_do_yahoo", lambda _: barras)
    monkeypatch.setattr(
        rodar.dados_p0_3, "carregar_cdi", lambda *_: pd.Series(0.0005, pregoes)
    )
    return rodar.carregar_historico()


def test_historico_corta_o_bova11_no_fim_do_desenvolvimento(monkeypatch):
    series = _carregar_com(monkeypatch, FIM_DO_DESENVOLVIMENTO)
    fechamento, caixa, classe, dias_por_ano = series["BOVA11"]
    assert fechamento.index.max() <= FIM_DO_DESENVOLVIMENTO
    assert caixa.index.equals(fechamento.index) and caixa.notna().all()
    assert (classe, dias_por_ano) == ("etf", 252)
    assert series["BTC em reais"][2:] == ("cripto", 365)


def test_historico_recusa_dado_do_holdout(monkeypatch):
    with pytest.raises(HoldoutVazandoError):
        _carregar_com(monkeypatch, "2024-01-31")
