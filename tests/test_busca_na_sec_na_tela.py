"""A busca na hora na SEC (R4): quando o botão aparece, os limites e as mensagens de cada desfecho.

Sem internet: a coleta (`coleta_sec.buscar_agora`) e o mapa da SEC são trocados por dublês.
"""

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import coleta_sec
from telas.research import busca_na_sec


@pytest.mark.parametrize(
    ("ticker", "esperado"),
    [
        ("AAPL", True),
        ("BRK-B", True),
        ("BF.B", True),
        ("PETR4.SA", False),  # B3
        ("^GSPC", False),  # índice
        ("BTC-USD", False),  # cripto
        ("aapl", False),  # a tela sempre manda em maiúsculas
        ("", False),
        ("ABCDEFGHIJK", False),  # mais de 10 caracteres
    ],
)
def test_so_acao_dos_eua_pode_ser_buscada_na_sec(ticker, esperado):
    assert busca_na_sec._pode_buscar_na_sec(ticker) is esperado


def _oferecer_aapl() -> None:
    from telas.research.busca_na_sec import oferecer_busca_na_sec

    oferecer_busca_na_sec("AAPL", "Os fundamentos")


def _oferecer_b3() -> None:
    from telas.research.busca_na_sec import oferecer_busca_na_sec

    oferecer_busca_na_sec("PETR4.SA", "Os fundamentos")


def test_acao_dos_eua_ganha_o_botao_de_buscar():
    app = AppTest.from_function(_oferecer_aapl).run()
    assert [b.label for b in app.button] == ["Buscar na SEC agora"]
    assert "AAPL ainda não está na base" in app.info[0].value


def test_ticker_da_b3_nao_ganha_botao_e_diz_o_que_a_busca_cobre():
    app = AppTest.from_function(_oferecer_b3).run()
    assert len(app.button) == 0
    assert "PETR4.SA não tem cadastro na CVM nem na SEC" in app.info[0].value
    assert "Os fundamentos cobrem ações e units da B3" in app.info[0].value


def _buscar() -> None:
    import streamlit as st

    from telas.research import busca_na_sec

    busca_na_sec._buscar_na_sec("AAPL")
    st.session_state["rodou"] = True


@pytest.fixture
def com_contato(monkeypatch):
    monkeypatch.setattr(busca_na_sec, "contato", lambda: "contato@exemplo.test")
    monkeypatch.setattr(busca_na_sec, "obter_engine", lambda: object())
    monkeypatch.setattr(busca_na_sec, "_mapa_da_sec", lambda agente: pd.DataFrame())


def _buscar_com(monkeypatch, **estado) -> AppTest:
    app = AppTest.from_function(_buscar)
    for chave, valor in estado.items():
        app.session_state[chave] = valor
    return app.run()


def test_sem_email_de_contato_a_busca_avisa_e_nao_chama_a_sec(monkeypatch):
    monkeypatch.setattr(busca_na_sec, "contato", lambda: None)

    def nao_deve_chamar(*args, **kwargs):
        raise AssertionError("não devia buscar sem e-mail de contato")

    monkeypatch.setattr(coleta_sec, "buscar_agora", nao_deve_chamar)
    app = _buscar_com(monkeypatch)
    assert "falta o e-mail de contato" in app.session_state["busca_na_sec_aviso"]
    assert "busca_na_sec_feita" not in app.session_state


def test_limite_de_buscas_por_visita_recusa_a_sexta(monkeypatch, com_contato):
    def nao_deve_chamar(*args, **kwargs):
        raise AssertionError("passou do limite e buscou mesmo assim")

    monkeypatch.setattr(coleta_sec, "buscar_agora", nao_deve_chamar)
    limite = busca_na_sec.BUSCAS_NA_SEC_POR_SESSAO
    app = _buscar_com(monkeypatch, buscas_na_sec=limite)
    assert (
        f"Você já fez {limite} buscas novas" in app.session_state["busca_na_sec_aviso"]
    )
    assert app.session_state["buscas_na_sec"] == limite


def test_busca_feita_conta_na_visita_e_guarda_a_mensagem(monkeypatch, com_contato):
    chamadas = []

    def falsa(motor, cliente, ticker, mapa, agora):
        chamadas.append(ticker)
        return "Apple Inc.", 12, 3

    monkeypatch.setattr(coleta_sec, "buscar_agora", falsa)
    app = _buscar_com(monkeypatch, buscas_na_sec=2)
    assert chamadas == ["AAPL"]
    assert app.session_state["buscas_na_sec"] == 3
    mensagem = app.session_state["busca_na_sec_feita"]
    assert "Apple Inc.: 12 eventos e 3 negociações" in mensagem
    assert "entra na coleta diária" in mensagem


def test_busca_recusada_mostra_o_motivo_sem_gastar_uma_busca(monkeypatch, com_contato):
    def recusa(*args, **kwargs):
        raise coleta_sec.BuscaRecusada("Limite da hora atingido.")

    monkeypatch.setattr(coleta_sec, "buscar_agora", recusa)
    app = _buscar_com(monkeypatch)
    assert app.session_state["busca_na_sec_aviso"] == "Limite da hora atingido."
    assert "buscas_na_sec" not in app.session_state


def test_sec_fora_do_ar_avisa_sem_gastar_uma_busca(monkeypatch, com_contato):
    def cai(*args, **kwargs):
        raise coleta_sec.requests.ConnectionError("sem rede")

    monkeypatch.setattr(coleta_sec, "buscar_agora", cai)
    app = _buscar_com(monkeypatch)
    assert "A SEC não respondeu agora" in app.session_state["busca_na_sec_aviso"]
    assert "buscas_na_sec" not in app.session_state


def _mostrar_resultado() -> None:
    from telas.research.busca_na_sec import mostrar_resultado_da_busca_na_sec

    mostrar_resultado_da_busca_na_sec()


def test_resultado_da_busca_aparece_uma_vez_so():
    app = AppTest.from_function(_mostrar_resultado)
    app.session_state["busca_na_sec_feita"] = "Apple Inc.: 1 eventos e 0 negociações"
    app.run()
    assert [s.value for s in app.success] == ["Apple Inc.: 1 eventos e 0 negociações"]
    assert "busca_na_sec_feita" not in app.session_state
    assert len(app.run().success) == 0
