"""P0-3: a rodada completa com dados sintéticos e um registro temporário (4 tentativas por rodada)."""

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.estrategias import rodar_p0_3 as rodar
from trader.estrategias.carteira_rp import ATIVOS_DE_RISCO

DATAS = pd.bdate_range("2014-01-02", "2020-12-30")
ATIVOS = list(ATIVOS_DE_RISCO)


def _precos_com_regimes(semente=5):
    """Volatilidade que troca de ativo todo mês (a partir do 2º pregão, quando a carteira nova
    já rende), com tendência: olhar o mês seguinte infla."""
    gerador = np.random.default_rng(semente)
    mes_par = pd.Series(DATAS.month).shift(1).bfill().to_numpy() % 2 == 0
    vol_a = np.where(mes_par, 0.03, 0.004)
    vol_b = np.where(mes_par, 0.004, 0.03)
    vols = np.column_stack(
        [vol_a, vol_b, np.full(len(DATAS), 0.01), np.full(len(DATAS), 0.01)]
    )
    retornos = gerador.normal(0.0006, vols)
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=DATAS, columns=ATIVOS
    )


def _precos_aleatorios(semente=6):
    gerador = np.random.default_rng(semente)
    retornos = gerador.normal(0.0, 0.012, size=(len(DATAS), 4))
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=DATAS, columns=ATIVOS
    )


CDI = pd.Series(0.0003, index=DATAS)
VOLUMES = pd.Series(5e7, index=ATIVOS)


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("p0_3") / "registro.db")
    precos = _precos_com_regimes()
    saida = rodar.executar(precos, CDI, VOLUMES, registro)
    return precos, registro, saida


def test_registra_as_quatro_tentativas_na_familia_p0_3(rodada):
    _, registro, saida = rodada
    assert set(saida["ids"]) == {
        "risk_parity",
        "inverso_vol",
        "min_var",
        "risk_parity_aporte",
    }
    assert registro.contar() == 4
    guardado = registro.obter(saida["ids"]["risk_parity"])
    assert guardado["familia"] == "P0-3"
    assert guardado["resultado"]["veredito"]["itens"]
    assert guardado["resultado"][
        "vizinhos"
    ]  # o platô fica dentro da tentativa do candidato
    assert guardado["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO


def test_rodar_de_novo_nao_conta_tentativa_nova(rodada):
    precos, registro, _ = rodada
    rodar.executar(precos, CDI, VOLUMES, registro)
    assert registro.contar() == 4


def test_veredito_tem_os_itens_do_pre_registro_e_as_verificacoes_passam(rodada):
    veredito = rodada[2]["veredito"]
    itens = {i.codigo: i for i in veredito.itens}
    assert list(itens) == ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "F1", "V"]
    assert itens["V"].passou
    assert itens["A2"].passou and itens["A2"].valor is None  # não se aplica à P0-3


def test_teste_do_brasil_compara_vender_com_aporte(rodada):
    brasil = rodada[2]["brasil"]
    assert set(brasil) == {"vender", "aporte"}
    assert all(
        {"sharpe", "retorno_anual", "maior_queda"} <= set(v) for v in brasil.values()
    )


def test_reguas_e_estresse_foram_calculados(rodada):
    saida = rodada[2]
    assert set(saida["reguas"]) == {"60/40", "CDI"}
    assert set(saida["resumos"]) == {"risk_parity", "inverso_vol", "min_var"}
    assert saida["tentativas_totais"] >= criterio_quant.tentativas_anteriores() + 4


def test_dados_aleatorios_nao_passam(tmp_path):
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    saida = rodar.executar(_precos_aleatorios(), CDI, VOLUMES, registro)
    assert not saida["veredito"].aprovado


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(_precos_aleatorios(), CDI, VOLUMES, registro)
    assert registro.contar() == 0


def test_relatorio_e_escrito_com_limites_e_cuidados(rodada, tmp_path):
    caminho = rodar.escrever_relatorio(rodada[2], tmp_path)
    texto = caminho.read_text(encoding="utf-8")
    assert "Veredito do risk parity" in texto
    assert "| F1 |" in texto and "| V |" in texto
    assert "teste do Brasil" in texto
    assert "## Limites e cuidados" in texto
    assert "Primeiro dia de cada série" in texto
