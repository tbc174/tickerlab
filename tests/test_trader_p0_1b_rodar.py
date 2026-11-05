"""Ficha P0-1b: a rodada completa com dados sintéticos e um registro temporário."""

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.estrategias import rodar_p0_1b as rodar
from trader.estrategias import rodar_tendencia_cripto as rodar_p0_1
from trader.estrategias import tendencia_cripto as tc
from trader.estrategias import tendencia_cripto_brl as brl

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("p0_1b")
DIAS_P0_1 = pd.date_range("2018-01-01", periods=1500, freq="D")
DIAS = DIAS_P0_1[700:]  # o par em reais começa depois
CDI = pd.Series(0.0003, index=DIAS_P0_1)
VOLUMES = pd.DataFrame(1e9, index=DIAS_P0_1, columns=list(tc.ATIVOS))


def _precos(dias=DIAS_P0_1, semente=11):
    """Tendências longas alternadas: a regra tem o que seguir e olhar o futuro infla o Sharpe."""
    gerador = np.random.default_rng(semente)
    fase = (np.arange(len(dias)) // 200) % 2
    media = np.where(fase == 0, 0.003, -0.002)
    retornos = gerador.normal(media[:, None], 0.03, size=(len(dias), 2))
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=dias, columns=list(tc.ATIVOS)
    )


def _p0_1():
    return _precos(), CDI, VOLUMES


def _brl():
    precos = _precos(DIAS, semente=12)
    precos.loc[precos.index < DIAS[17], "ETH"] = (
        np.nan
    )  # o ETHBRL começou 17 dias depois
    return precos, CDI.reindex(DIAS), VOLUMES.reindex(DIAS)


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("p0_1b") / "registro.db")
    precos, cdi, volumes = _brl()
    saida = rodar.executar(precos, cdi, volumes, registro, _p0_1())
    return registro, saida


def test_registra_uma_tentativa_da_familia_p0_1b(rodada):
    registro, saida = rodada
    tentativa = registro.obter(saida["id"])
    assert tentativa["familia"] == "P0-1b" and tentativa["nome"] == rodar.NOME
    spec = tentativa["spec"]
    assert spec["candidato"] == brl.CANDIDATO
    assert spec["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert spec["banda"] == 0.20 and spec["spread_por_lado"] == 0.003
    assert spec["com_cambio"] is False and spec["janelas"] == list(tc.JANELAS)
    assert spec["primeiro_candle"] == {
        "BTC": DIAS[0].date().isoformat(),
        "ETH": DIAS[17].date().isoformat(),
    }
    assert spec["comparacao_p0_1"]["hash_dos_dados"]
    assert tentativa["resultado"]["veredito"]["itens"]
    assert saida["execucoes_da_ficha"] == 1


def test_veredito_completo_sem_pbo(rodada):
    itens = {i.codigo: i for i in rodada[1]["veredito"].itens}
    assert list(itens) == ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "F1", "V"]
    assert itens["A2"].valor is None and itens["A2"].passou
    assert itens["V"].passou


def test_teste_do_brasil_tem_os_quatro_itens(rodada):
    saida = rodada[1]
    brasil = saida["brasil"]
    assert (
        brasil["retorno_anual_caixa_a_cdi"] > brasil["retorno_anual_caixa_a_zero"]
    )  # (a)
    assert 0 <= brasil["meses_acima_da_isencao"] <= brasil["meses_simulados"]  # (b)
    c = brasil["p0_1_no_periodo"]  # (c)
    assert c["cambio_no_periodo"] > 0
    assert c["sharpe_do_excesso_sem_cambio"] > c["sharpe_do_excesso"]
    assert brasil["sem_banda"]["giro"] > saida["resumo"]["giro"]  # (d)
    assert saida["resumo"]["spread"] > 0
    assert saida["estresse"]["custos"] > saida["resumo"]["custos"]
    assert (
        saida["spread_de_leitura"]["sharpe_do_excesso"]
        > saida["resumo"]["sharpe_do_excesso"]
    )


def test_reguas_vizinhos_e_datas(rodada):
    saida = rodada[1]
    assert set(saida["vizinhos"]) == set(rodar.VIZINHOS)
    assert set(saida["reguas"]) == {"BTCBRL comprar e segurar", "CDI"}
    assert (
        saida["primeiro_dia_simulado"]
        == (DIAS[0] + pd.Timedelta(days=365)).date().isoformat()
    )


def test_vizinhos_sao_os_da_p0_1_mais_a_banda():
    assert {n: m for n, m in rodar.VIZINHOS.items() if not n.startswith("banda")} == (
        rodar_p0_1.VIZINHOS
    )
    assert rodar.VIZINHOS["banda_0.16"]["banda"] == pytest.approx(0.20 * 0.8)
    assert rodar.VIZINHOS["banda_0.24"]["banda"] == pytest.approx(0.20 * 1.2)


def test_relatorio_tem_as_tabelas_e_os_limites(rodada, tmp_path):
    texto = rodar.escrever_relatorio(rodada[1], tmp_path).read_text(encoding="utf-8")
    assert "### BTCBRL e ETHBRL 50/50" in texto
    assert "## Teste do Brasil" in texto and "R$ 35 mil" in texto
    for item in ("- (a)", "- (b)", "- (c)", "- (d)"):
        assert item in texto
    assert "Primeiro candle de cada par" in texto and "(t ÷ SR)²" in texto
    assert "0,1% por lado" in texto
    assert "depois de ver o resultado da P0-1" in texto
    assert "## Limites e cuidados" in texto
    assert "recomendação de investimento" in texto


def test_terceira_execucao_e_recusada_antes_de_registrar(tmp_path):
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    spec = {"pesquisa": "P0-1b"}
    registro.registrar("P0-1b", rodar.NOME, spec)
    registro.registrar("P0-1b", rodar.NOME, spec)
    assert rodar.execucoes_da_ficha(registro) == 2
    precos, cdi, volumes = _brl()
    with pytest.raises(rodar.OrcamentoDaFichaEsgotadoError):
        rodar.executar(precos, cdi, volumes, registro, _p0_1())
    assert rodar.execucoes_da_ficha(registro) == 2


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    precos, cdi, volumes = _brl()
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(precos, cdi, volumes, registro, _p0_1())
    assert registro.contar() == 0


def test_comparacao_recusa_p0_1_que_nao_cobre_o_periodo():
    precos, cdi, volumes = _p0_1()
    curto = (precos.iloc[:900], cdi.iloc[:900], volumes.iloc[:900])
    with pytest.raises(ValueError):
        rodar.comparar_com_a_p0_1(curto, pd.DatetimeIndex(DIAS[400:]))
