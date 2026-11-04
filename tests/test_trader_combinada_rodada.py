"""Rodada da ficha C-1 (`rodar_c1`) com camadas artificiais e um registro temporário.

Confere a ordem da seção 9 (as duas tentativas registradas antes de carregar as camadas), a parada
com defeito quando uma camada não reproduz o registro, a evidência completa das duas carteiras e os
testes do Brasil (sem cripto, correlação e imposto compensado).
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader import calendario, criterio_quant
from trader.estrategias import camadas_da_combinada as cdc
from trader.estrategias import combinada, rodar_c1

PREGOES = pd.DatetimeIndex(calendario.pregoes(date(2015, 1, 2), date(2018, 12, 28)))
CORRIDOS = pd.date_range(PREGOES[0], PREGOES[-1])
CDI_DIA = 0.0004


def _serie(indice: pd.DatetimeIndex, semente: int, escala: float) -> pd.Series:
    gerador = np.random.default_rng(semente)
    return pd.Series(
        CDI_DIA + 0.0002 + escala * gerador.standard_normal(len(indice)), index=indice
    )


def _camada(nome: str, semente: int, sharpe: float | None = None) -> cdc.Camada:
    indice = CORRIDOS if nome in combinada.CAMADAS_DE_CRIPTO else PREGOES
    base = _serie(indice, semente, 0.01)
    return cdc.Camada(
        nome=nome,
        base=base,
        estresse=base - 0.0001,
        bruto=base + 0.0001,
        cdi=pd.Series(CDI_DIA, index=indice),
        sharpe=cdc.REGISTRADO[nome].sharpe if sharpe is None else sharpe,
    )


def _camadas(sharpe_da_p0_4: float | None = None) -> cdc.Camadas:
    camadas = {
        nome: _camada(nome, semente, sharpe_da_p0_4 if nome == "P0-4" else None)
        for semente, nome in enumerate(cdc.REGISTRADO)
    }
    return cdc.Camadas(camadas=camadas, regua_60_40=_serie(PREGOES, 99, 0.006))


def _cdi() -> pd.Series:
    return pd.Series(CDI_DIA, index=PREGOES)


@pytest.fixture
def registro(tmp_path):
    return criterio_quant.abrir_registro(tmp_path / "registro.db")


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = criterio_quant.abrir_registro(
        tmp_path_factory.mktemp("c1") / "registro.db"
    )
    return registro, rodar_c1.executar(lambda: (_camadas(), _cdi()), registro)


def test_registra_as_duas_tentativas_antes_de_carregar(registro):
    vistas = []

    def carregar():
        vistas.append([t["nome"] for t in registro.listar()])
        return _camadas(sharpe_da_p0_4=9.0), _cdi()

    rodar_c1.executar(carregar, registro)
    assert vistas == [[rodar_c1.CANDIDATA, rodar_c1.COMPARACAO]]
    assert {t["familia"] for t in registro.listar()} == {rodar_c1.FICHA}


def test_camada_que_nao_reproduz_para_a_rodada_como_defeito(registro):
    saida = rodar_c1.executar(lambda: (_camadas(sharpe_da_p0_4=9.0), _cdi()), registro)
    assert "carteiras" not in saida
    assert not saida["reproducao"]["P0-4"]["reproduz"]
    for tentativa in saida["ids"].values():
        assert "defeito" in registro.obter(tentativa)["resultado"]


def test_mesma_rodada_de_novo_soma_execucao_na_mesma_linha(registro):
    um = rodar_c1.executar(lambda: (_camadas(sharpe_da_p0_4=9.0), _cdi()), registro)
    dois = rodar_c1.executar(lambda: (_camadas(sharpe_da_p0_4=9.0), _cdi()), registro)
    assert um["ids"] == dois["ids"]
    assert registro.total_para_o_dsr() == 4


def test_as_duas_carteiras_tem_veredito_completo_e_gravado(rodada):
    registro, saida = rodada
    codigos = {"A1", "A3", "A4", "A5", "A6", "A7", "A8", "F1", "V"}
    for nome, tentativa in saida["ids"].items():
        carteira = saida["carteiras"][nome]
        assert codigos <= {i.codigo for i in carteira["veredito"].itens}
        assert carteira["camadas"] == list(rodar_c1.CARTEIRAS[nome])
        gravado = registro.obter(tentativa)["resultado"]
        assert gravado["veredito"]["itens"]
        assert gravado["hash"] == carteira["hash"]


def test_verificacoes_passam_com_o_codigo_honesto(rodada):
    _, saida = rodada
    for carteira in saida["carteiras"].values():
        v = next(i for i in carteira["veredito"].itens if i.codigo == "V")
        assert v.passou, v


def test_comparacao_usa_so_as_tres_camadas_dela(rodada):
    _, saida = rodada
    pesos = saida["carteiras"][rodar_c1.COMPARACAO]["resumo"]["pesos_medios"]
    assert set(pesos) == set(combinada.CAMADAS_DA_COMPARACAO)


def test_sem_cripto_tira_a_p0_1(rodada):
    _, saida = rodada
    candidata = saida["carteiras"][rodar_c1.CANDIDATA]
    assert "P0-1" in candidata["resumo"]["pesos_medios"]
    assert "P0-1" not in candidata["brasil"]["sem_cripto"]["pesos_medios"]


def test_correlacao_mensal_e_ganho_por_ano(rodada):
    _, saida = rodada
    correlacao = saida["carteiras"][rodar_c1.CANDIDATA]["brasil"]["correlacao"]
    assert correlacao["correlacao_mensal"]["P0-3"]["P0-3"] == pytest.approx(1.0)
    for ano in correlacao["por_ano"].values():
        assert ano["ganho"] == pytest.approx(
            ano["sharpe_da_c1"] - ano["sharpe_medio_das_camadas"]
        )


def test_compensar_entre_camadas_nunca_paga_mais_no_total(rodada):
    _, saida = rodada
    por_ano = saida["carteiras"][rodar_c1.CANDIDATA]["brasil"]["imposto"]
    assert (
        sum(a["compensando"] for a in por_ano.values())
        <= sum(a["sem_compensar"] for a in por_ano.values()) + 1e-12
    )


def test_imposto_compensado_leva_o_prejuizo_adiante():
    dias = PREGOES[:60]
    tabela = pd.DataFrame({"a": 0.0, "b": 0.0}, index=dias)
    tabela.loc[dias[0], "a"] = -0.10  # janeiro: prejuízo de 10% numa camada
    tabela.loc[dias[30], "b"] = 0.15  # fevereiro: lucro de 15% na outra
    pesos = pd.DataFrame(1.0, index=dias, columns=["a", "b"])
    zero = pd.Series(0.0, index=dias)
    resultado = combinada.ResultadoC1(
        retorno=zero,
        bruto=zero,
        pesos=pesos,
        custo=zero,
        imposto=zero,
        decisoes=(),
        parametros=combinada.ParametrosC1(),
    )
    ano = rodar_c1.imposto_compensado(tabela, resultado, ("a", "b"))[2015]
    assert ano["sem_compensar"] == pytest.approx(0.15 * rodar_c1.IR_DA_BOLSA)
    assert ano["compensando"] == pytest.approx(0.05 * rodar_c1.IR_DA_BOLSA)


def test_relatorio_tem_o_veredito_das_duas(rodada, tmp_path):
    _, saida = rodada
    texto = rodar_c1.escrever_relatorio(saida, tmp_path).read_text(encoding="utf-8")
    assert "candidata" in texto and "comparação" in texto
    assert "| A1 |" in texto
