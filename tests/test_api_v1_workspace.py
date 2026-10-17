"""As simulações pelo app novo (Workspace, PR 1 do plano de 17/10; ADR 0062, tela 3).

O que o Streamlit faz em "Minhas simulações" passa a existir na API v1: listar, salvar (com a ficha
"Foi sorte?", para o Pulse recalcular depois) e apagar. O limite de simulações do plano vira um 403
com o motivo "plano", que o app novo já sabe mostrar.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src import api, ficha, planos, pulse
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, contexto
from src.banco.dados_do_usuario import listar_simulacoes, salvar_simulacao
from src.banco.usuarios import buscar_por_google_sub, entrar
from src.conformidade import registrar_aceite
from src.dados import baixar_dados
from src.exemplos import carregar_exemplo
from src.simulacoes import restaurar_estado
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    chaves_publicas,
    com_token,
    gerar_chave,
    token,
)


@pytest.fixture(scope="module")
def chave():
    return gerar_chave()


@pytest.fixture
def app(banco, monkeypatch, chave):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    monkeypatch.setattr(
        contexto,
        "carregar_dados",
        lambda ticker, periodo: baixar_dados(ticker, periodo, forcar_exemplo=True),
    )
    nova = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    nova.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas(chave)
    acesso.LIMITE.zerar()
    with banco.begin() as conexao:
        ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
        registrar_aceite(conexao, ana.id)
    return nova


@pytest.fixture
def cliente(app, chave):
    return TestClient(app, headers=com_token(token(chave)))


# --- Tarefa 1.1: o limite do plano vira 403 com o motivo "plano" ----------------------------


def test_limite_do_plano_responde_403_com_motivo_plano(app, cliente):
    """Qualquer rota que deixe escapar `LimiteDoPlanoError` responde como a recusa de plano da
    API (403 + `X-TickerLab-Motivo: plano`), com a frase do erro, que já sugere o Pro."""

    def estourar():
        planos.conferir_simulacoes("gratuito", 5)  # a 6ª simulação do Gratuito

    with pytest.raises(planos.LimiteDoPlanoError) as erro:
        estourar()
    app.add_api_route("/v1/estourar-limite", estourar)
    resposta = cliente.get("/v1/estourar-limite")
    assert resposta.status_code == 403, resposta.text
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "plano"
    assert resposta.json() == {"detail": str(erro.value)}


# --- Tarefa 1.2: listar, salvar (com a ficha, para o Pulse) e apagar -------------------------

PEDIDO = {
    "nome": "Médias 10/40 na Petrobras",
    "backtest": {
        "ticker": "PETR4.SA",
        "periodo": "2y",
        "estrategia": "Cruzamento de médias",
        "parametros": {"curta": 10, "longa": 40},
        "custo_por_operacao": 0.001,
        "taxa": 0.1,
        "capital_inicial": 20_000,
    },
    "veredito": "passou",
}
# o que o Streamlit guarda (src/simulacoes.capturar_estado): as chaves do session_state
RETRATO_DO_STREAMLIT = {
    "ticker": "VALE3.SA",
    "periodo": "1y",
    "backtest_estrategia": "RSI",
}
RESUMO_DO_STREAMLIT = {
    "numeros": {"Retorno total": "+12,0%"},
    "dados_ate": "10/10/2026",
}


def _salvar(cliente, **mudancas):
    return cliente.post("/api/v1/salvar-simulacao", json={**PEDIDO, **mudancas})


def _conta(banco, google_sub="ana"):
    with banco.connect() as conexao:
        usuario = buscar_por_google_sub(conexao, google_sub)
    assert usuario is not None
    return usuario


def _simulacoes_no_banco(banco, usuario_id):
    with banco.connect() as conexao:
        return listar_simulacoes(conexao, usuario_id)


def test_salvar_simulacao_guarda_a_ficha_para_o_pulse(cliente, banco):
    """Salvar pelo app novo guarda o que o Streamlit guarda: o retrato dos campos, os números
    formatados, até quando vão os dados e a ficha (pedido + veredito), que o Pulse recalcula."""
    resposta = _salvar(cliente)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert (dados["usadas"], dados["limite"], dados["uso"]) == (1, 5, "1 de 5")
    [salva] = dados["simulacoes"]
    assert salva["nome"] == PEDIDO["nome"]
    assert salva["tipo"] == "backtest"
    assert salva["veredito"] == "passou"
    precos = carregar_exemplo("PETR4.SA", "2y")
    assert precos is not None
    assert salva["dados_ate"] == f"{precos.index[-1]:%d/%m/%Y}"
    assert "Retorno total" in salva["numeros"] and "Operações" in salva["numeros"]
    assert all(isinstance(v, str) for v in salva["numeros"].values())  # como na tela
    # o endereço reabre o backtest no app novo com as mesmas escolhas (fração, como a API)
    endereco = urlsplit(salva["endereco"])
    assert endereco.path == "/backtest"
    assert parse_qs(endereco.query) == {
        "ticker": ["PETR4.SA"],
        "periodo": ["2y"],
        "estrategia": ["Cruzamento de médias"],
        "custo_por_operacao": ["0.001"],
        "taxa": ["0.1"],
        "capital_inicial": ["20000.0"],
        "tolerancia_de_queda": [str(ficha.TOLERANCIA_PADRAO_DE_QUEDA)],
        "livres": ["curta", "longa"],
        "p.curta": ["10"],
        "p.longa": ["40"],
        "p.tipo": ["Simples"],
    }
    # o Pulse (src/pulse.py) lê a simulação como lê as do Streamlit
    salvas, sem_ficha, fora = pulse.estrategias_salvas(
        _simulacoes_no_banco(banco, _conta(banco).id)
    )
    assert (len(salvas), sem_ficha, fora) == (1, 0, 0)
    estrategia = salvas[0]
    assert estrategia.veredito_ao_salvar == "passou"
    campos = restaurar_estado(estrategia.retrato, "backtest")
    assert (campos["ticker"], campos["periodo"]) == ("PETR4.SA", "2y")
    pedido = ficha.pedido_guardado(
        estrategia.pedido, precos
    )  # não levanta: dá para recalcular
    assert pedido.estrategia == "Cruzamento de médias"
    assert pedido.parametros == {"curta": 10, "longa": 40, "tipo": "Simples"}
    assert (pedido.custo_por_operacao, pedido.capital_inicial) == (0.001, 20_000)
    assert (pedido.taxa_livre_de_risco, pedido.cdi_diario) == (0.1, None)
    assert pedido.livres == ("curta", "longa")


def test_salvar_sem_veredito_fica_sem_ficha(cliente, banco):
    """Quando a tela não conseguiu montar a ficha, a simulação é salva sem ela (o Pulse conta
    como "salva antes da ficha") e o veredito volta nulo."""
    resposta = _salvar(cliente, veredito=None)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["simulacoes"][0]["veredito"] is None
    salvas, sem_ficha, _ = pulse.estrategias_salvas(
        _simulacoes_no_banco(banco, _conta(banco).id)
    )
    assert (len(salvas), sem_ficha) == (0, 1)


def test_salvar_recusa_veredito_e_estrategia_que_nao_existem(cliente):
    assert _salvar(cliente, veredito="talvez").status_code == 422
    backtest = {**PEDIDO["backtest"], "estrategia": "Bola de cristal"}
    assert _salvar(cliente, backtest=backtest).status_code == 422


def test_salvar_alem_do_limite_responde_403_plano(cliente, banco):
    """A 6ª simulação do Gratuito: a recusa de plano, que o app novo mostra com o caminho do Pro."""
    ana = _conta(banco)
    with banco.begin() as conexao:
        for n in range(5):
            salvar_simulacao(
                conexao, ana.id, "backtest", f"Simulação {n}", {}, {}, plano="gratuito"
            )
    resposta = _salvar(cliente)
    assert resposta.status_code == 403, resposta.text
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "plano"
    assert "plano Pro" in resposta.json()["detail"]
    assert len(_simulacoes_no_banco(banco, ana.id)) == 5


def test_listar_traz_as_do_streamlit_sem_endereco_do_app_novo(cliente, banco):
    """As simulações salvas no app atual aparecem na lista, mas só reabrem lá: o retrato delas
    são campos do Streamlit, que a tela nova não entende (endereço nulo)."""
    ana = _conta(banco)
    with banco.begin() as conexao:
        salvar_simulacao(
            conexao,
            ana.id,
            "backtest",
            "Do app atual",
            RETRATO_DO_STREAMLIT,
            RESUMO_DO_STREAMLIT,
        )
        salvar_simulacao(
            conexao, ana.id, "carteira", "Carteira", {"carteira_pesos": "1"}, {}
        )
    resposta = cliente.get("/api/v1/simulacoes")
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert [s["nome"] for s in dados["simulacoes"]] == ["Carteira", "Do app atual"]
    assert [s["endereco"] for s in dados["simulacoes"]] == [None, None]
    do_app_atual = dados["simulacoes"][1]
    assert do_app_atual["numeros"] == RESUMO_DO_STREAMLIT["numeros"]
    assert do_app_atual["dados_ate"] == "10/10/2026"
    assert do_app_atual["veredito"] is None
    assert (dados["usadas"], dados["limite"]) == (2, 5)


def test_listar_sem_simulacoes(cliente):
    dados = cliente.get("/api/v1/simulacoes").json()
    assert dados["simulacoes"] == []
    assert (dados["usadas"], dados["uso"]) == (0, "0 de 5")
    assert dados["sem_simulacoes"]  # a frase da lista vazia vem da API, como nos links


def test_apagar_simulacao_so_a_propria(cliente, banco):
    """Apagar a de outra conta dá 404 (sem dizer que existe); a própria some e a lista volta."""
    ana = _conta(banco)
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia", "bia@exemplo.com")[0]
        da_bia = salvar_simulacao(conexao, bia.id, "backtest", "Da Bia", {}, {})
        da_ana = salvar_simulacao(conexao, ana.id, "backtest", "Da Ana", {}, {})
    resposta = cliente.post("/api/v1/apagar-simulacao", json={"id": str(da_bia.id)})
    assert resposta.status_code == 404
    assert len(_simulacoes_no_banco(banco, bia.id)) == 1
    resposta = cliente.post("/api/v1/apagar-simulacao", json={"id": str(da_ana.id)})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["simulacoes"] == []
    assert resposta.json()["usadas"] == 0
    assert _simulacoes_no_banco(banco, ana.id) == []
    # apagar de novo: já não existe
    assert (
        cliente.post(
            "/api/v1/apagar-simulacao", json={"id": str(da_ana.id)}
        ).status_code
        == 404
    )
