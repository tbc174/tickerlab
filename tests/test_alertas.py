"""Alertas compostos do Research (etapa 6): regras, avaliação sem olhar o futuro, gravação por
usuário (limites do plano, LGPD) e a página."""

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import alertas as al
from src.banco import dados_do_usuario as repo
from src.banco import usuarios as contas
from src.banco.dados_do_usuario import DadosInvalidosError
from src.conformidade import apagar_conta, exportar_meus_dados
from src.planos import LimiteDoPlanoError
from tests.ajudantes_da_conta import ir_para


@pytest.fixture(scope="module")
def petr4():
    return pd.read_csv("dados_de_exemplo/PETR4.SA.csv", index_col=0, parse_dates=True)


def _barras(precos, inicio="2026-01-05"):
    indice = pd.bdate_range(inicio, periods=len(precos))
    fechamento = pd.Series(precos, index=indice, dtype=float)
    return pd.DataFrame(
        {"Open": fechamento, "High": fechamento * 1.01, "Low": fechamento * 0.99,
         "Close": fechamento, "Volume": 1_000}
    )  # fmt: skip


# --- regras -------------------------------------------------------------------------------------
def test_validar_completa_os_padroes_e_recusa_o_que_nao_faz_sentido():
    regra = al.validar(al.Regra("  Meu   alerta ", (al.Condicao("rsi_abaixo"),)))
    assert regra.nome == "Meu alerta"
    assert (regra.condicoes[0].janela, regra.condicoes[0].limiar) == (14, 30.0)
    with pytest.raises(al.RegraInvalidaError, match="nome"):
        al.validar(al.Regra(" ", (al.Condicao("rsi_abaixo"),)))
    with pytest.raises(al.RegraInvalidaError, match="1 a 4"):
        al.validar(al.Regra("x", ()))
    with pytest.raises(al.RegraInvalidaError, match="desconhecida"):
        al.validar(al.Regra("x", (al.Condicao("adivinhar"),)))
    with pytest.raises(al.RegraInvalidaError, match="janela"):
        al.validar(al.Regra("x", (al.Condicao("rsi_abaixo", janela=1),)))


def test_guardar_e_ler_de_novo_da_a_mesma_regra():
    regra = al.validar(
        al.Regra("a", (al.Condicao("media_de_alta", al.SEMANAL),), al.QUALQUER)
    )
    assert al.Regra.de_guardada("a", regra.para_guardar()) == regra


# --- avaliação ----------------------------------------------------------------------------------
def test_regra_do_prd_media_semanal_de_alta_e_preco_diario_abaixo(petr4):
    regra = al.validar(
        al.Regra(
            "PRD 7.1",
            (
                al.Condicao("media_de_alta", al.SEMANAL, 10, 30),
                al.Condicao("preco_abaixo_de", al.DIARIO, limiar=1_000),
            ),
        )
    )
    resultado = al.avaliar(regra, petr4)
    assert resultado.disparou is (resultado.avaliacoes[0].satisfeita is True)
    assert resultado.avaliacoes[1].satisfeita is True  # preço abaixo de 1.000
    assert (
        resultado.avaliacoes[0].barra <= petr4.index[-1].date()
    )  # nunca depois dos dados
    assert "pregão seguinte" in resultado.atraso


def test_sem_dados_nao_dispara_e_explica():
    regra = al.validar(al.Regra("x", (al.Condicao("rsi_acima", janela=200, limiar=0),)))
    resultado = al.avaliar(regra, _barras(np.linspace(10, 20, 50)))
    assert resultado.disparou is None
    assert "precisa de 201" in resultado.avaliacoes[0].motivo


def test_todas_e_qualquer():
    subida = _barras(np.linspace(10, 20, 80))
    verdade = al.Condicao("preco_acima_da_media", janela=20)
    mentira = al.Condicao("preco_abaixo_da_media", janela=20)
    sem_dados = al.Condicao("preco_acima_da_media", janela=300)
    avaliar = lambda modo, *cs: (
        al.avaliar(al.validar(al.Regra("x", cs, modo)), subida).disparou
    )
    assert avaliar(al.TODAS, verdade) is True
    assert avaliar(al.TODAS, verdade, mentira) is False
    assert avaliar(al.TODAS, verdade, sem_dados) is None  # não vira "sim" sem dados
    assert avaliar(al.QUALQUER, mentira, verdade) is True
    assert avaliar(al.QUALQUER, mentira, sem_dados) is None


def test_semana_em_andamento_e_avisada():
    quarta = _barras(
        np.linspace(10, 20, 33), inicio="2026-01-01"
    )  # termina numa quarta
    assert quarta.index[-1].weekday() < al.SEXTA
    condicao = al.validar(
        al.Regra("x", (al.Condicao("rsi_acima", al.SEMANAL, 3, 0),))
    ).condicoes[0]
    avaliacao = al.avaliar_condicao(condicao, quarta)
    assert "ainda não terminou" in avaliacao.aviso


def test_queda_do_topo_e_volatilidade():
    queda = _barras([10] * 30 + [8] * 5)
    c = al.validar(
        al.Regra("x", (al.Condicao("queda_do_topo", janela=30, limiar=15),))
    ).condicoes[0]
    avaliacao = al.avaliar_condicao(c, queda)
    assert avaliacao.valor == pytest.approx(20) and avaliacao.satisfeita is True


# --- gravação por usuário ------------------------------------------------------------------------
def _usuario(conexao, sub):
    usuario, _ = contas.entrar(conexao, sub, f"{sub}@exemplo.com")
    return usuario.id


def _regra(nome="Meu alerta"):
    return al.Regra(nome, (al.Condicao("rsi_abaixo"),))


def test_salvar_listar_apagar_e_nome_repetido(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        alerta_id = repo.salvar_alerta(c, ana, _regra())
        [salvo] = repo.listar_alertas(c, ana)
        assert salvo.id == alerta_id and salvo.regra.condicoes[0].limiar == 30.0
        with pytest.raises(DadosInvalidosError, match="já tem"):
            repo.salvar_alerta(c, ana, _regra("MEU ALERTA"))
        assert repo.apagar_alerta(c, ana, alerta_id)
        assert repo.listar_alertas(c, ana) == []


def test_limite_do_plano_e_isolamento_entre_usuarios(banco):
    with banco.begin() as c:
        ana, bia = _usuario(c, "ana"), _usuario(c, "bia")
        repo.salvar_alerta(c, ana, _regra("um"), plano="gratuito")
        with pytest.raises(LimiteDoPlanoError, match="1 alerta"):
            repo.salvar_alerta(c, ana, _regra("dois"), plano="gratuito")
        [alerta_da_ana] = repo.listar_alertas(c, ana)
        assert not repo.apagar_alerta(
            c, bia, alerta_da_ana.id
        )  # a outra conta não apaga
        assert repo.listar_alertas(c, bia) == []


def test_alertas_entram_na_exportacao_e_somem_com_a_conta(banco):
    with banco.begin() as c:
        ana = _usuario(c, "ana")
        repo.salvar_alerta(c, ana, _regra())
        exportado = exportar_meus_dados(c, ana)["alertas_do_research"]
        assert (
            exportado[0]["nome"] == "Meu alerta" and exportado[0]["regra"]["condicoes"]
        )
        assert apagar_conta(c, ana)
        assert repo.listar_alertas(c, ana) == []


# --- a página ----------------------------------------------------------------------------------
def test_pagina_monta_salva_e_avalia_um_alerta_no_modo_local(banco):
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app = ir_para(app, "alertas")
    assert not app.exception
    assert any("ainda não tem alertas" in i.value for i in app.info)
    app.text_input(key="alerta_nome").input("Tendência").run()
    app.button(key="alerta_salvar").click().run()
    assert not app.exception and not app.error
    tabela = next(t.value for t in app.dataframe if "Resultado" in t.value.columns)
    assert set(tabela["Resultado"]) <= {"Disparou", "Não", "Sem dados"}
    assert "PETR4" in set(tabela["Ativo"])
    assert any("pregão seguinte" in c.value for c in app.caption)
