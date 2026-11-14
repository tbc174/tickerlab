"""Os avisos de falha de salvar e apagar uma simulação da conta (`telas/dados_da_conta.py`).

O caminho feliz e o isolamento entre contas estão em `test_conta_no_app.py`. Aqui o banco falha, ou o
plano está no limite, e o callback deve mostrar o aviso certo sem gravar nem apagar nada.
"""

import pytest
import streamlit as st

from src.banco import dados_do_usuario as repo
from src.banco.usuarios import entrar
from src.planos import LIMITES_DOS_PLANOS
from telas import dados_da_conta

AVISO_AO_SALVAR = "Não consegui salvar a simulação agora. Tente de novo em instantes."
AVISO_AO_APAGAR = "Não consegui apagar agora. Tente de novo em instantes."


@pytest.fixture
def ana(banco):
    with banco.begin() as conexao:
        return entrar(conexao, "g-ana-simulacoes", "ana-sim@exemplo.com", "Ana")[0]


@pytest.fixture
def avisos(monkeypatch, ana):
    """A sessão de uma conta válida e a lista dos `st.toast` mostrados."""
    sessao = {"usuario": ana, "usuario_em": 123.0}
    monkeypatch.setattr(st, "session_state", sessao)
    mostrados: list[str] = []
    monkeypatch.setattr(st, "toast", mostrados.append)
    return mostrados


def _simulacoes_da_conta(banco, ana) -> list:
    with banco.connect() as conexao:
        return repo.listar_simulacoes(conexao, ana.id)


def _guardar(banco, ana, nome="Guardada"):
    with banco.begin() as conexao:
        return repo.salvar_simulacao(conexao, ana.id, "backtest", nome, {}, {})


def test_falha_inesperada_ao_salvar_avisa_e_nao_grava(banco, ana, avisos, monkeypatch):
    def quebrar(*_args, **_kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(dados_da_conta, "salvar_simulacao", quebrar)
    st.session_state["salvar_nome_backtest"] = "Meu teste"

    dados_da_conta._salvar_simulacao(ana, "backtest", "Sugerida", {})

    assert avisos == [AVISO_AO_SALVAR]
    assert st.session_state["salvar_nome_backtest"] == "Meu teste"  # o nome fica
    assert _simulacoes_da_conta(banco, ana) == []


def test_plano_no_limite_avisa_o_limite_e_nao_grava(banco, ana, avisos):
    maximo = LIMITES_DOS_PLANOS[ana.plano].simulacoes
    assert maximo is not None, "o plano do teste precisa ter limite"
    for i in range(maximo):
        _guardar(banco, ana, f"Antiga {i}")

    dados_da_conta._salvar_simulacao(ana, "backtest", "Uma a mais", {})

    assert len(avisos) == 1
    assert f"guarda até {maximo} simulações" in avisos[0]
    assert len(_simulacoes_da_conta(banco, ana)) == maximo


def test_nome_vazio_avisa_o_erro_do_dado_e_nao_grava(banco, ana, avisos):
    dados_da_conta._salvar_simulacao(ana, "backtest", "", {})

    assert avisos == ["Dê um nome para a simulação."]
    assert _simulacoes_da_conta(banco, ana) == []


def test_falha_ao_apagar_avisa_e_a_simulacao_continua(banco, ana, avisos, monkeypatch):
    guardada = _guardar(banco, ana)

    def quebrar(*_args, **_kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(dados_da_conta, "apagar_simulacao", quebrar)

    dados_da_conta._apagar_simulacao(ana, guardada)

    assert avisos == [AVISO_AO_APAGAR]
    assert [s.id for s in _simulacoes_da_conta(banco, ana)] == [guardada.id]


def test_apagar_com_sucesso_avisa_o_nome(banco, ana, avisos):
    """Contraponto das falhas: o mesmo callback, sem defeito, apaga e avisa."""
    guardada = _guardar(banco, ana, "Para sair")

    dados_da_conta._apagar_simulacao(ana, guardada)

    assert avisos == ["Simulação apagada: Para sair."]
    assert _simulacoes_da_conta(banco, ana) == []
