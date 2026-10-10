"""Testes de src/cdi.py (sem internet: a consulta ao Banco Central é simulada)."""

import pandas as pd
import pytest

from src import cdi


def _cdi(dias=300, taxa=0.0005, inicio="2025-01-02"):
    return pd.Series(taxa, index=pd.bdate_range(inicio, periods=dias), name="CDI")


def test_serie_do_banco_central_vira_fracao_diaria():
    registros = [
        {"data": "02/01/2026", "valor": "0.055131"},
        {"data": "05/01/2026", "valor": "0.055131"},
    ]
    serie = cdi.montar_serie_do_cdi(registros)
    assert serie.iloc[0] == pytest.approx(0.00055131)
    assert list(serie.index) == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-05")]


def test_serie_ordena_e_tira_datas_repetidas():
    registros = [
        {"data": "05/01/2026", "valor": "0.05"},
        {"data": "02/01/2026", "valor": "0.04"},
        {"data": "02/01/2026", "valor": "0.04"},
    ]
    assert len(cdi.montar_serie_do_cdi(registros)) == 2


@pytest.mark.parametrize(
    "registros", [[], [{"data": "x", "valor": "1"}], [{"outra": 1}]]
)
def test_resposta_ruim_vira_erro_claro(registros):
    with pytest.raises(cdi.CDIIndisponivelError):
        cdi.montar_serie_do_cdi(registros)


def test_curva_comeca_em_um_e_cresce_com_o_cdi():
    serie = _cdi(dias=100)
    curva = cdi.curva_do_cdi(serie, serie.index)
    assert curva.iloc[0] == 1
    assert curva.iloc[-1] == pytest.approx(1.0005**99)


def test_curva_repete_o_valor_nos_dias_sem_cdi():
    serie = _cdi(dias=10)
    indice = pd.date_range(
        serie.index[0], serie.index[-1], freq="D"
    )  # inclui fins de semana
    curva = cdi.curva_do_cdi(serie, indice)
    sabado, sexta = pd.Timestamp("2025-01-04"), pd.Timestamp("2025-01-03")
    assert curva[sabado] == curva[sexta]


def test_taxa_anual_do_cdi_usa_os_dias_corridos():
    serie = _cdi(dias=300)
    taxa = cdi.calcular_taxa_anual_do_cdi(serie, serie.index)
    assert taxa == pytest.approx(1.0005**261 - 1, rel=0.01)


def test_taxa_anual_com_periodo_de_um_dia_da_erro():
    serie = _cdi(dias=3)
    with pytest.raises(ValueError, match="curto"):
        cdi.calcular_taxa_anual_do_cdi(serie, serie.index[:1])


def test_baixar_cdi_divide_periodos_longos_e_junta_tudo(monkeypatch):
    chamadas = []

    def falso(inicio, fim):
        chamadas.append((inicio, fim))
        dias = pd.bdate_range(inicio, fim)
        return [{"data": d.strftime("%d/%m/%Y"), "valor": "0.05"} for d in dias]

    monkeypatch.setattr(cdi, "_consultar", falso)
    serie = cdi.baixar_cdi(pd.Timestamp("2005-01-03"), pd.Timestamp("2026-01-02"))
    assert len(chamadas) >= 3
    assert all((fim - inicio).days <= 365 * 9 + 3 for inicio, fim in chamadas)
    assert serie.index.is_unique and serie.index.is_monotonic_increasing
    assert serie.index[0] == pd.Timestamp("2005-01-03")


def test_baixar_cdi_recusa_datas_invertidas():
    with pytest.raises(ValueError, match="final"):
        cdi.baixar_cdi(pd.Timestamp("2026-01-02"), pd.Timestamp("2025-01-02"))


def test_falha_de_rede_vira_erro_do_app(monkeypatch):
    import requests

    def quebra(*a, **k):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(cdi.requests, "get", quebra)
    with pytest.raises(cdi.CDIIndisponivelError):
        cdi.baixar_cdi(pd.Timestamp("2026-01-02"), pd.Timestamp("2026-02-02"))
