"""Testes de src/cdi.py (sem internet: a consulta ao Banco Central é simulada)."""

import pandas as pd
import pytest
import requests

from src import bcb, cdi


def _cdi(dias=300, taxa=0.0005, inicio="2025-01-02"):
    return pd.Series(taxa, index=pd.bdate_range(inicio, periods=dias), name="CDI")


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


class RespostaFalsa:
    def __init__(self, conteudo: object, status: int = 200) -> None:
        self.conteudo = conteudo
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)  # type: ignore[arg-type]

    def json(self) -> object:
        if isinstance(self.conteudo, Exception):
            raise self.conteudo
        return self.conteudo


def _registros(inicio: str, fim: str, valor: str = "0.05") -> list[dict]:
    dias = pd.bdate_range(_data(inicio), _data(fim))
    return [{"data": d.strftime("%d/%m/%Y"), "valor": valor} for d in dias]


def _data(texto: str) -> pd.Timestamp:
    return pd.to_datetime(texto, format="%d/%m/%Y")


@pytest.fixture
def sem_espera(monkeypatch):
    """As novas tentativas do leitor do Banco Central esperam segundos: nos testes, não."""
    esperas: list = []
    monkeypatch.setattr(bcb, "esperar", esperas.append)
    return esperas


def test_serie_do_banco_central_vira_fracao_diaria(sem_espera):
    registros = [
        {"data": "02/01/2026", "valor": "0.055131"},
        {"data": "05/01/2026", "valor": "0.055131"},
    ]
    serie = cdi.baixar_cdi(
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-05"),
        buscar=lambda *a, **k: RespostaFalsa(registros),
    )
    assert serie.name == "CDI"
    assert serie.iloc[0] == pytest.approx(0.00055131)
    assert list(serie.index) == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-05")]


@pytest.mark.parametrize(
    "registros", [[], [{"data": "x", "valor": "1"}], [{"outra": 1}]]
)
def test_resposta_ruim_vira_erro_claro(registros, sem_espera):
    with pytest.raises(cdi.CDIIndisponivelError):
        cdi.baixar_cdi(
            pd.Timestamp("2026-01-02"),
            pd.Timestamp("2026-01-05"),
            buscar=lambda *a, **k: RespostaFalsa(registros),
        )


def test_baixar_cdi_pede_janelas_curtas_e_junta_tudo(sem_espera):
    """Regressão (13/10/2026): o CDI pedia 9 anos por consulta. Sem cache, o Banco Central passa
    dos ~30 s numa janela longa e devolve uma página "Requisição inválida!" com status 200; um
    backtest longo ficava sem o CDI. Agora são janelas de até 3 anos, como nas séries do SGS."""
    pedidos: list = []

    def buscar(url, params=None, timeout=None):
        pedidos.append(params)
        return RespostaFalsa(_registros(params["dataInicial"], params["dataFinal"]))

    serie = cdi.baixar_cdi(
        pd.Timestamp("2005-01-03"), pd.Timestamp("2026-01-02"), buscar=buscar
    )
    janelas = [(_data(p["dataInicial"]), _data(p["dataFinal"])) for p in pedidos]
    assert len(janelas) >= 7
    assert all((fim - inicio).days <= 365 * 3 + 1 for inicio, fim in janelas)
    assert serie.index.is_unique and serie.index.is_monotonic_increasing
    assert serie.index[0] == pd.Timestamp("2005-01-03")
    assert serie.index[-1] == pd.Timestamp("2026-01-02")


def test_falha_passageira_do_banco_central_tenta_de_novo(sem_espera):
    """Um 502 isolado do Banco Central não pode deixar o backtest sem o CDI."""
    respostas = [
        RespostaFalsa(None, status=502),
        RespostaFalsa([{"data": "02/01/2026", "valor": "0.05"}]),
    ]
    serie = cdi.baixar_cdi(
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-02"),
        buscar=lambda *a, **k: respostas.pop(0),
    )
    assert len(serie) == 1 and len(sem_espera) == 1


def test_pagina_de_erro_do_banco_central_tenta_de_novo(sem_espera):
    """A página "Requisição inválida!" (status 200) some quando a consulta é repetida."""
    respostas = [
        RespostaFalsa(ValueError("Requisição inválida!")),
        RespostaFalsa([{"data": "02/01/2026", "valor": "0.05"}]),
    ]
    serie = cdi.baixar_cdi(
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-02"),
        buscar=lambda *a, **k: respostas.pop(0),
    )
    assert len(serie) == 1 and len(sem_espera) == 1


def test_pagina_de_erro_que_insiste_vira_erro_do_app(sem_espera):
    pagina = RespostaFalsa(ValueError("Requisição inválida!"))
    with pytest.raises(cdi.CDIIndisponivelError):
        cdi.baixar_cdi(
            pd.Timestamp("2026-01-02"),
            pd.Timestamp("2026-02-02"),
            buscar=lambda *a, **k: pagina,
        )
    assert len(sem_espera) == 2


def test_baixar_cdi_recusa_datas_invertidas():
    with pytest.raises(ValueError, match="final"):
        cdi.baixar_cdi(pd.Timestamp("2026-01-02"), pd.Timestamp("2025-01-02"))


def test_falha_de_rede_vira_erro_do_app(monkeypatch, sem_espera):
    def quebra(*a, **k):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(cdi.requests, "get", quebra)
    with pytest.raises(cdi.CDIIndisponivelError):
        cdi.baixar_cdi(pd.Timestamp("2026-01-02"), pd.Timestamp("2026-02-02"))


# --- saiu da tela da carteira (preparação para outra interface, 13/10/2026) ---------------------
def test_retorno_diario_do_caixa_e_o_da_curva_do_cdi():
    serie = _cdi()
    indice = pd.bdate_range("2025-02-03", periods=120)
    esperado = cdi.curva_do_cdi(serie, indice).pct_change().fillna(0.0)
    pd.testing.assert_series_equal(cdi.retorno_diario_do_caixa(serie, indice), esperado)
