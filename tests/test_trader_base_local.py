"""Base local do trader: a série é servida inteira ou recusada, e o balanço só vale depois de público."""

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base.ponto_no_tempo import montar_base
from trader import base_local as bl
from trader.dados import LACUNA_MAXIMA_DIARIA, salvar

A = "11.111.111/0001-11"
B = "22.222.222/0001-22"


def _candles(inicio="2010-01-04", periodos=300):
    indice = pd.bdate_range(inicio, periods=periodos)
    fechamento = 100 + np.arange(periodos, dtype=float)
    return pd.DataFrame(
        {
            "Open": fechamento,
            "High": fechamento + 1,
            "Low": fechamento - 1,
            "Close": fechamento,
            "Volume": 1000.0,
            "Spread": 2.0,
        },
        index=indice,
    )


@pytest.fixture
def pasta(tmp_path):
    salvar(_candles(), "PETR4", "D1", tmp_path)
    return tmp_path


def test_simbolo_ausente_recusa(pasta):
    with pytest.raises(bl.DadoAusenteError, match="VALE3"):
        bl.ler_serie(pasta, "VALE3", "2010-02-01", "2010-06-01")


def test_periodo_fora_recusa(pasta):
    with pytest.raises(bl.DadoAusenteError, match="2005-01-03.*2010-01-04"):
        bl.ler_serie(pasta, "PETR4", "2005-01-03", "2010-06-01")
    with pytest.raises(bl.DadoAusenteError, match="termina"):
        bl.ler_serie(pasta, "PETR4", "2010-02-01", "2030-01-01")


def test_feriado_na_ponta_nao_recusa(pasta):
    """Pedir a partir de 1º de janeiro numa série que começa no primeiro pregão (dia 4) é normal."""
    serie = bl.ler_serie(pasta, "PETR4", "2010-01-01", "2010-03-01")
    assert serie.index[0] == pd.Timestamp("2010-01-04")


def test_lacuna_maior_que_o_limite_recusa(tmp_path):
    candles = _candles()
    corte = candles.index[50]
    sem_buraco = candles[
        (candles.index < corte) | (candles.index > corte + LACUNA_MAXIMA_DIARIA)
    ]
    salvar(sem_buraco, "PETR4", "D1", tmp_path)
    with pytest.raises(bl.DadoAusenteError, match="lacuna"):
        bl.ler_serie(tmp_path, "PETR4", "2010-01-04", "2010-12-01")
    # fora do pedaço com o buraco, a série é servida
    assert not bl.ler_serie(tmp_path, "PETR4", "2010-06-01", "2010-12-01").empty


def test_preco_vazio_recusa(tmp_path):
    candles = _candles()
    candles.iloc[10, candles.columns.get_loc("Close")] = np.nan
    salvar(candles, "PETR4", "D1", tmp_path)
    with pytest.raises(bl.DadoAusenteError, match="vazio"):
        bl.ler_serie(tmp_path, "PETR4", "2010-01-04", "2010-12-01")


def test_serie_completa_e_servida_sem_mudar(pasta):
    serie = bl.ler_serie(pasta, "PETR4", "2010-02-01", "2010-06-01")
    original = _candles()
    esperado = original.loc["2010-02-01":"2010-06-01"]
    pd.testing.assert_frame_equal(serie, esperado, check_freq=False)


def test_inicio_depois_do_fim_e_erro(pasta):
    with pytest.raises(ValueError, match="depois"):
        bl.ler_serie(pasta, "PETR4", "2010-06-01", "2010-02-01")


# ---- balanço na véspera da decisão ----


def _publicada(
    valor, divulgado_em, fim="2022-12-31", versao=1, cnpj=A, conta="3.11", meses=12
):
    fim = pd.Timestamp(fim)
    inicio = fim - pd.DateOffset(months=meses) + pd.Timedelta(days=1)
    return {
        "cnpj": cnpj,
        "empresa": "EMPRESA",
        "grupo": "con",
        "demonstracao": "DRE",
        "conta": conta,
        "descricao": "Lucro",
        "inicio": inicio,
        "fim": fim,
        "valor": valor,
        "documento": "DFP" if meses == 12 else "ITR",
        "referencia": fim,
        "versao": versao,
        "ordem": "ultimo",
        "origem": "dados_abertos",
        "divulgado_em": pd.Timestamp(divulgado_em),
    }


def _base(*linhas):
    return montar_base(pd.DataFrame(list(linhas)))


def test_balanco_entregue_em_d_vale_para_decisao_de_d_mais_1():
    base = _base(_publicada(512.0, "2023-03-17"))
    datas = pd.to_datetime(["2023-03-16", "2023-03-17", "2023-03-18"])
    serie = bl.balanco_na_vespera(base, datas, A, "3.11", aceitar_vazio=True)
    # no dia 17 a CVM recebeu, mas não diz a hora: quem decide no dia 17 só vê o dia 16
    assert serie.isna().tolist() == [True, True, False]
    assert serie.iloc[2] == 512.0


def test_reapresentacao_so_vale_depois_de_divulgada():
    base = _base(
        _publicada(512.0, "2023-03-17"), _publicada(12.0, "2023-05-02", versao=2)
    )
    datas = pd.to_datetime(["2023-04-01", "2023-05-02", "2023-05-03"])
    assert bl.balanco_na_vespera(base, datas, A, "3.11").tolist() == [
        512.0,
        512.0,
        12.0,
    ]


def test_periodo_mais_recente_publicado_e_o_usado():
    base = _base(
        _publicada(100.0, "2023-03-17", fim="2022-12-31"),
        _publicada(30.0, "2023-05-10", fim="2023-03-31", meses=3),
        _publicada(
            500.0, "2023-05-10", fim="2023-03-31", cnpj=B
        ),  # outra empresa: não entra
    )
    datas = pd.to_datetime(["2023-05-01", "2023-05-20"])
    assert bl.balanco_na_vespera(base, datas, A, "3.11").tolist() == [100.0, 30.0]
    so_anual = bl.balanco_na_vespera(base, datas, A, "3.11", meses=12)
    assert so_anual.tolist() == [100.0, 100.0]


def test_dois_periodos_na_mesma_data_pedem_meses():
    base = _base(
        _publicada(30.0, "2023-08-10", fim="2023-06-30", meses=3),
        _publicada(55.0, "2023-08-10", fim="2023-06-30", meses=6),
    )
    datas = pd.to_datetime(["2023-08-20"])
    with pytest.raises(ValueError, match="meses"):
        bl.balanco_na_vespera(base, datas, A, "3.11")
    assert bl.balanco_na_vespera(base, datas, A, "3.11", meses=6).tolist() == [55.0]


def test_sem_balanco_divulgado_recusa_ou_vazio_declarado():
    base = _base(_publicada(512.0, "2023-03-17"))
    datas = pd.to_datetime(["2023-01-10", "2023-04-01"])
    with pytest.raises(bl.DadoAusenteError, match="2023-01-10"):
        bl.balanco_na_vespera(base, datas, A, "3.11")
    serie = bl.balanco_na_vespera(base, datas, A, "3.11", aceitar_vazio=True)
    assert np.isnan(serie.iloc[0])
    assert serie.iloc[1] == 512.0


PRIMEIRO_DIA = pd.Timestamp("2023-03-01")


@st.composite
def _publicacoes(desenho):
    """Até 8 publicações de 3 períodos da mesma conta em 30 dias, com reapresentações e brancos."""
    quantas = desenho(st.integers(min_value=1, max_value=8))
    linhas = []
    for versao in range(1, quantas + 1):
        fim = desenho(st.sampled_from(["2022-06-30", "2022-09-30", "2022-12-31"]))
        valor = desenho(st.sampled_from([1.0, 2.0, 3.0, float("nan")]))
        dia = PRIMEIRO_DIA + pd.Timedelta(days=desenho(st.integers(0, 30)))
        linhas.append(_publicada(valor, dia, fim=fim, versao=versao))
    return pd.DataFrame(linhas)


@settings(max_examples=60, deadline=None)
@given(publicadas=_publicacoes(), dias=st.integers(0, 32))
def test_cortar_o_futuro_nao_muda_o_passado(publicadas, dias):
    """O valor de cada decisão até o corte é o mesmo com ou sem as publicações depois do corte."""
    corte = PRIMEIRO_DIA + pd.Timedelta(days=dias)
    datas = pd.date_range(PRIMEIRO_DIA, corte + pd.Timedelta(days=1))
    inteira = bl.balanco_na_vespera(
        montar_base(publicadas), datas, A, "3.11", aceitar_vazio=True
    )
    so_o_passado = publicadas[publicadas["divulgado_em"] <= corte]
    if so_o_passado.empty:
        assert inteira.isna().all()
        return
    cortada = bl.balanco_na_vespera(
        montar_base(so_o_passado), datas, A, "3.11", aceitar_vazio=True
    )
    # quem decide no dia seguinte ao corte ainda olha só até o corte
    pd.testing.assert_series_equal(inteira, cortada)
