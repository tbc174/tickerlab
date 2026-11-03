"""Ficha P0-2: a rodada completa com dados sintéticos e um registro temporário."""

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.estrategias import dados_tendencia_b3 as dados
from trader.estrategias import rodar_tendencia_b3 as rodar
from trader.estrategias import tendencia_b3 as tb

# A rodada do fixture de módulo demora; num processo só ela roda uma vez (CI com --dist loadgroup).
pytestmark = pytest.mark.xdist_group("tendencia_b3")
PREGOES = pd.bdate_range("2012-01-02", periods=900)
CDI = pd.Series(0.0004, index=PREGOES)


def _fechamento(semente):
    gerador = np.random.default_rng(semente)
    fase = (np.arange(len(PREGOES)) // 150) % 2
    media = np.where(fase == 0, 0.002, -0.0015)
    retornos = gerador.normal(media, 0.015, size=len(PREGOES))
    return pd.Series(100 * np.cumprod(1 + retornos), index=PREGOES)


def _versoes():
    fechamento = _fechamento(3)
    abertura = fechamento.shift(1).fillna(fechamento.iloc[0]) * 1.0005
    bova11 = tb.a_vista(
        "BOVA11", abertura, fechamento, pd.Series(5e8, index=PREGOES), CDI
    )
    curva = pd.DataFrame(
        {
            "data_base": PREGOES,
            "curva": "nominal",
            "prazo_anos": 2.0,
            "taxa": 0.11 + 0.01 * np.sin(np.arange(len(PREGOES)) / 60),
        }
    )
    fechamentos = pd.DataFrame({f"P{k}": _fechamento(10 + k) for k in range(3)})
    aberturas = fechamentos.shift(1).fillna(fechamentos.iloc[0])
    volumes = pd.DataFrame(1e8, index=PREGOES, columns=fechamentos.columns)
    return {
        "BOVA11": bova11,
        "WIN": tb.win_sintetico(bova11, CDI),
        "DI1": tb.di1_sintetico(curva, CDI, bova11),
        "cesta": tb.cesta(aberturas, fechamentos, volumes, CDI),
    }


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("p0_2") / "registro.db")
    versoes = _versoes()
    saida = rodar.executar(versoes, CDI, registro)
    return versoes, registro, saida


def test_registra_uma_tentativa_da_familia_p0_2_com_o_bova11(rodada):
    _, registro, saida = rodada
    assert registro.contar() == 1
    tentativa = registro.obter(saida["id"])
    assert tentativa["familia"] == "P0-2" and tentativa["nome"] == rodar.NOME
    assert tentativa["spec"]["candidato"] == criterio_quant.CANDIDATOS["P0-2"]
    assert tentativa["spec"]["pre_registro"] == criterio_quant.HASH_DO_CRITERIO
    assert tentativa["spec"]["execucao"] == "leilão de abertura de D+1"
    assert tentativa["spec"]["custos"]["emolumentos_no_leilao"] == pytest.approx(
        0.00032
    )
    assert tentativa["resultado"]["veredito"]["itens"]
    assert set(tentativa["resultado"]["versoes"]) == set(tb.VERSOES)


def test_rodar_de_novo_nao_conta_configuracao_nova(rodada):
    versoes, registro, _ = rodada
    rodar.executar(versoes, CDI, registro)
    assert registro.contar() == 1
    assert registro.execucoes() == 2  # mas toda execução conta no DSR


def test_dsr_conta_as_21_series_testadas(rodada):
    saida = rodada[2]
    assert saida["series_testadas"] == len(tb.VERSOES) * (1 + len(rodar.VIZINHOS))
    assert saida["tentativas_totais"] >= saida["series_testadas"]


def test_veredito_completo_sem_pbo_nas_tres_versoes(rodada):
    for nome in tb.VERSOES:
        veredito = rodada[2]["versoes"][nome]["veredito"]
        itens = {i.codigo: i for i in veredito.itens}
        assert list(itens) == [
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
        assert itens["A2"].valor is None and itens["A2"].passou
    assert rodada[2]["veredito"] is rodada[2]["versoes"]["BOVA11"]["veredito"]


def test_teste_do_brasil(rodada):
    saida = rodada[2]
    brasil = saida["brasil"]
    assert brasil["day_trades"] == {n: 0 for n in tb.VERSOES}
    assert set(brasil["imposto"]) == {"BOVA11", "WIN", "cesta", "cesta_sem_isencao"}
    assert (
        brasil["imposto"]["cesta_sem_isencao"]["imposto"]
        >= brasil["imposto"]["cesta"]["imposto"]
    )
    assert brasil["imposto"]["BOVA11"]["meses_acima_da_isencao"] == 0
    assert brasil["rolagem_do_win"]["total"] > 0
    assert (
        brasil["rolagem_do_win"]["rolagens_com_posicao"]
        <= (brasil["rolagem_do_win"]["rolagens_no_periodo"])
    )
    assert set(saida["reguas"]) == {rodar.REGUA, "CDI"}
    assert (
        saida["primeiro_dia_simulado"]
        == PREGOES[tb.AQUECIMENTO_EM_PREGOES].date().isoformat()
    )


def test_relatorio_tem_as_tabelas_e_os_limites(rodada, tmp_path):
    texto = rodar.escrever_relatorio(rodada[2], tmp_path).read_text(encoding="utf-8")
    for nome in tb.VERSOES:
        assert f"### {nome}:" in texto
    assert "## Teste do Brasil" in texto and "R$ 20 mil" in texto
    assert "day trade" in texto and "Rolagem do WIN" in texto
    assert "(t ÷ SR)²" in texto
    assert "## Limites e cuidados" in texto
    assert "recomendação de investimento" in texto


def test_pre_registro_alterado_nao_roda_nem_registra(tmp_path, monkeypatch):
    def recusar(*_, **__):
        raise criterio_quant.PreRegistroAlteradoError("mudou")

    monkeypatch.setattr(rodar.criterio_quant, "conferir", recusar)
    registro = rodar.abrir_registro(tmp_path / "registro.db")
    with pytest.raises(criterio_quant.PreRegistroAlteradoError):
        rodar.executar(_versoes(), CDI, registro)
    assert registro.contar() == 0


def test_vizinhos_sao_os_do_plato_de_20_por_cento():
    assert rodar.VIZINHOS["janelas_x1.2"]["janelas"] == tb.escalar_janelas(
        tb.JANELAS, 1.2
    )
    assert rodar.VIZINHOS["vol_alvo_0.20"]["vol_alvo"] == pytest.approx(0.25 * 0.8)
    assert rodar.VIZINHOS["janela_da_vol_108"]["janela_da_vol"] == 90 * 1.2


# --- os dados ------------------------------------------------------------------------------------


def _parquet(caminho, datas, fechamento, volume, abertura=None):
    pd.DataFrame(
        {
            "Open": fechamento if abertura is None else abertura,
            "High": fechamento,
            "Low": fechamento,
            "Close": fechamento,
            "Volume": volume,
        },
        index=pd.DatetimeIndex(datas, name="Date"),
    ).to_parquet(caminho)


def test_barras_tiram_o_feriado_e_guardam_a_abertura(tmp_path):
    datas = pd.bdate_range("2020-01-01", periods=5)
    arquivo = tmp_path / "X.SA_D1.parquet"
    _parquet(
        arquivo,
        datas,
        [10.0, 11.0, 11.0, 12.0, 13.0],
        [5, 6, 0, 7, 8],
        abertura=[9.5, 10.5, 11.0, 11.5, 12.5],
    )
    barras = dados.barras_do_yahoo(arquivo)
    assert list(barras.index) == [datas[0], datas[1], datas[3], datas[4]]
    assert barras["abertura"].tolist() == [9.5, 10.5, 11.5, 12.5]


def test_serie_comeca_no_primeiro_pregao_com_volume():
    datas = pd.bdate_range("2008-12-29", periods=4)
    barras = pd.DataFrame(
        {
            "abertura": [1.0, 2, 3, 4],
            "fechamento": [1.0, 2, 3, 4],
            "volume": [0, 0, 5, 6],
        },
        index=datas,
    )
    assert dados.so_com_negocio_desde_o_inicio(barras).index[0] == datas[2]


def test_papel_entra_na_cesta_so_depois_do_primeiro_preco(tmp_path):
    pregoes = pd.bdate_range("2020-01-01", periods=6)
    _parquet(tmp_path / "A.SA_D1.parquet", pregoes, [10.0] * 6, [1] * 6)
    _parquet(
        tmp_path / "B.SA_D1.parquet",
        pregoes[[2, 3, 5]],
        [20.0, 21.0, 22.0],
        [1, 1, 1],
    )
    aberturas, fechamentos, volumes = dados.carregar_cesta(
        pregoes, tmp_path, papeis=("A", "B")
    )
    assert fechamentos["B"].iloc[:2].isna().all()
    assert fechamentos["B"].iloc[4] == 21.0  # pregão sem barra repete o fechamento
    assert volumes["B"].iloc[4] == 0.0
    assert aberturas["B"].iloc[4] == 21.0
