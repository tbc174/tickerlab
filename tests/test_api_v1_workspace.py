"""O Workspace pelo app novo (plano de 17/10; ADR 0062, tela 3).

PR 1: o que o Streamlit faz em "Minhas simulações" passa a existir na API v1: listar, salvar (com a
ficha "Foi sorte?", para o Pulse recalcular depois) e apagar. O limite de simulações do plano vira um
403 com o motivo "plano", que o app novo já sabe mostrar.

PR 2: o Pulse pela API, parte 1: as estratégias acompanhadas (o veredito da ficha com os dados de
hoje) e a janela da visita, que o F5 não zera.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src import api, ficha, planos, pulse
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, contexto
from src.banco import pulse as repo_pulse
from src.banco import teses as repo_teses
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


# --- Tarefa 2.1: o Pulse pela API, parte 1 (estratégias acompanhadas e a janela da visita) ----
# os preços de exemplo vão até 09/10/2026: o "agora" do Pulse fica logo depois (como no Streamlit)
AGORA_DO_PULSE = datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
UMA_HORA_DEPOIS = AGORA_DO_PULSE + timedelta(hours=1)


@pytest.fixture
def relogio(monkeypatch):
    """O relógio do Pulse: começa em AGORA_DO_PULSE e o teste o adianta com `relogio.append`."""
    horas = [AGORA_DO_PULSE]
    monkeypatch.setattr(pulse, "agora", lambda: horas[-1])
    return horas


def _pulse(cliente, desde=None):
    params = {} if desde is None else {"desde": desde}
    resposta = cliente.get("/api/v1/pulse", params=params)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _hora(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def _visita(banco, usuario_id):
    with banco.connect() as conexao:
        return repo_pulse.ultima_visita(conexao, usuario_id)


def _veredito_de_hoje_da_petrobras():
    """O veredito da ficha do PEDIDO com os preços de exemplo de hoje (calculado à parte)."""
    pedido = ficha.PedidoDaFicha(
        dados=baixar_dados("PETR4.SA", "2y", forcar_exemplo=True),
        estrategia="Cruzamento de médias",
        parametros={"curta": 10, "longa": 40},
        custo_por_operacao=0.001,
        capital_inicial=20_000,
        livres=("curta", "longa"),
        taxa_livre_de_risco=0.1,
        tentativas_da_pessoa=1,
    )
    return ficha.montar_ficha(pedido).veredito.resultado.value


def _outro(veredito):
    return next(r.value for r in ficha.Resultado if r.value != veredito)


def test_pulse_marca_a_visita_e_devolve_a_janela(cliente, banco, relogio):
    """1ª visita: os últimos 7 dias; a visita fica marcada e a 2ª começa nela."""
    primeira = _pulse(cliente)["janela"]
    assert _hora(primeira["inicio"]) == AGORA_DO_PULSE - timedelta(days=7)
    assert _hora(primeira["fim"]) == AGORA_DO_PULSE
    assert primeira["primeira_vez"] is True
    assert "Primeira visita" in primeira["texto"]
    assert _visita(banco, _conta(banco).id) == AGORA_DO_PULSE
    relogio.append(UMA_HORA_DEPOIS)
    segunda = _pulse(cliente)["janela"]
    assert _hora(segunda["inicio"]) == AGORA_DO_PULSE
    assert segunda["primeira_vez"] is False
    assert "Desde a sua última visita" in segunda["texto"]


def test_desde_mantem_a_janela_no_f5(cliente, relogio):
    """O F5 reenvia o início que a aba já mostrava: a janela não encolhe para a última hora."""
    inicio = _pulse(cliente)["janela"]["inicio"]
    relogio.append(UMA_HORA_DEPOIS)
    janela = _pulse(cliente, desde=inicio)["janela"]
    assert _hora(janela["inicio"]) == _hora(inicio)
    assert _hora(janela["fim"]) == UMA_HORA_DEPOIS
    assert "Primeira visita" not in janela["texto"]


def test_desde_alem_de_30_dias_e_cortado(cliente, banco, relogio):
    """`desde` só amplia a janela até 30 dias atrás; nunca a encurta; sem fuso é recusado."""
    janela = _pulse(cliente, desde=(AGORA_DO_PULSE - timedelta(days=90)).isoformat())
    assert _hora(janela["janela"]["inicio"]) == AGORA_DO_PULSE - timedelta(days=30)
    with banco.begin() as conexao:
        repo_pulse.marcar_visita(
            conexao, _conta(banco).id, UMA_HORA_DEPOIS - timedelta(minutes=30)
        )
    relogio.append(UMA_HORA_DEPOIS)
    mais_tarde = (UMA_HORA_DEPOIS - timedelta(minutes=5)).isoformat()
    janela = _pulse(cliente, desde=mais_tarde)["janela"]
    assert _hora(janela["inicio"]) == UMA_HORA_DEPOIS - timedelta(minutes=30)
    sem_fuso = cliente.get("/api/v1/pulse", params={"desde": "2026-10-08T10:00:00"})
    assert sem_fuso.status_code == 422


def test_pulse_veredito_que_mudou_vem_com_antes_agora_e_data(cliente, banco, relogio):
    """Salvo com um veredito; com os dados de hoje, outro: o selo vem com a data, a tese ligada
    e o endereço do backtest; o F5 (com `desde`) mantém o selo; a visita seguinte, não."""
    hoje = _veredito_de_hoje_da_petrobras()
    antes = _outro(hoje)
    assert _salvar(cliente, veredito=antes).status_code == 200
    ana = _conta(banco)
    [salva] = _simulacoes_no_banco(banco, ana.id)
    with banco.begin() as conexao:
        repo_teses.escrever(conexao, ana.id, "PETR4", "Tese <b>da Ana</b>", [salva.id])
    dados = _pulse(cliente)
    [estrategia] = dados["estrategias"]
    assert estrategia["id"] == str(salva.id)
    assert estrategia["nome"] == PEDIDO["nome"]
    assert estrategia["ticker"] == "PETR4.SA"
    assert (estrategia["antes"], estrategia["agora"]) == (antes, hoje)
    assert estrategia["mudou"] is True
    assert _hora(estrategia["conferido_em"]) == AGORA_DO_PULSE
    assert estrategia["tese_ligada"].endswith("“Tese <b>da Ana</b>”")
    assert urlsplit(estrategia["endereco"]).path == "/backtest"
    assert dados["limites"] == {
        "sem_ficha": 0,
        "alem_do_maximo": 0,
        "nao_conferidas": 0,
    }
    # o F5: a aba reenvia o início; a mudança vista há pouco continua com o selo e a data
    relogio.append(UMA_HORA_DEPOIS)
    [no_f5] = _pulse(cliente, desde=dados["janela"]["inicio"])["estrategias"]
    assert (no_f5["antes"], no_f5["agora"], no_f5["mudou"]) == (antes, hoje, True)
    assert _hora(no_f5["conferido_em"]) == AGORA_DO_PULSE
    # a visita seguinte (sem `desde`) começa depois da mudança: o veredito está igual
    relogio.append(UMA_HORA_DEPOIS + timedelta(hours=1))
    [depois] = _pulse(cliente)["estrategias"]
    assert (depois["antes"], depois["agora"], depois["mudou"]) == (hoje, hoje, False)
    assert _hora(depois["conferido_em"]) == UMA_HORA_DEPOIS + timedelta(hours=1)


def test_pulse_grava_os_vereditos_vistos(cliente, banco, relogio):
    hoje = _veredito_de_hoje_da_petrobras()
    assert _salvar(cliente, veredito=hoje).status_code == 200
    ana = _conta(banco)
    [salva] = _simulacoes_no_banco(banco, ana.id)
    [estrategia] = _pulse(cliente)["estrategias"]
    assert (estrategia["antes"], estrategia["agora"], estrategia["mudou"]) == (
        hoje,
        hoje,
        False,
    )
    with banco.connect() as conexao:
        assert repo_pulse.vereditos_vistos(conexao, ana.id) == {str(salva.id): hoje}


def _salvar_com_ficha(banco, usuario_id, nome, veredito="passou"):
    resumo = {"numeros": {}, "ficha": {"pedido": {"versao": 1}, "veredito": veredito}}
    with banco.begin() as conexao:
        return salvar_simulacao(
            conexao, usuario_id, "backtest", nome, RETRATO_DO_STREAMLIT, resumo
        )


def test_pulse_confere_no_maximo_10_fichas(cliente, banco, relogio, monkeypatch):
    """Cada ficha refaz a validação inteira: só as 10 mais novas são conferidas; as outras
    aparecem como não conferidas agora."""
    ana = _conta(banco)
    for n in range(12):
        _salvar_com_ficha(banco, ana.id, f"Estratégia {n:02d}")
    conferidas = []

    def conferir(estrategia, _carregar, _cdi):
        conferidas.append(estrategia.nome)
        return "passou"

    monkeypatch.setattr(pulse, "veredito_de_hoje", conferir)
    dados = _pulse(cliente)
    assert len(conferidas) == pulse.MAXIMO_DE_FICHAS
    assert "Estratégia 00" not in conferidas and "Estratégia 01" not in conferidas
    assert len(dados["estrategias"]) == 12
    assert [e["agora"] for e in dados["estrategias"][-2:]] == [None, None]
    assert dados["limites"] == {
        "sem_ficha": 0,
        "alem_do_maximo": 2,
        "nao_conferidas": 0,
    }
    assert any("ficaram para depois" in aviso for aviso in dados["avisos"])


def test_pulse_ordem_mudou_iguais_e_nao_conferidas(
    cliente, banco, relogio, monkeypatch
):
    """Primeiro o que mudou, depois as iguais, por último as que não deu para conferir; a do
    app atual (retrato do Streamlit) traz o ticker, mas só reabre lá (endereço nulo)."""
    ana = _conta(banco)
    _salvar_com_ficha(banco, ana.id, "Não deu")
    _salvar_com_ficha(banco, ana.id, "Igual")
    _salvar_com_ficha(banco, ana.id, "Mudou")
    with banco.begin() as conexao:
        salvar_simulacao(conexao, ana.id, "backtest", "Velha", {}, {})  # sem ficha
    hoje = {"Igual": "passou", "Mudou": _outro("passou"), "Não deu": None}
    monkeypatch.setattr(
        pulse, "veredito_de_hoje", lambda e, _carregar, _cdi: hoje[e.nome]
    )
    dados = _pulse(cliente)
    assert [e["nome"] for e in dados["estrategias"]] == ["Mudou", "Igual", "Não deu"]
    assert [e["mudou"] for e in dados["estrategias"]] == [True, False, False]
    assert dados["estrategias"][2]["conferido_em"] is None
    assert {e["ticker"] for e in dados["estrategias"]} == {"VALE3.SA"}
    assert {e["endereco"] for e in dados["estrategias"]} == {None}
    assert dados["limites"] == {
        "sem_ficha": 1,
        "alem_do_maximo": 0,
        "nao_conferidas": 1,
    }
    assert any("Não deu para conferir agora: Não deu." in a for a in dados["avisos"])
    assert any("salve de novo" in a for a in dados["avisos"])


def test_pulse_de_quem_nao_salvou_nada(cliente, banco, relogio):
    dados = _pulse(cliente)
    assert dados["estrategias"] == []
    assert "salve um backtest" in dados["sem_estrategias"].lower()
    assert dados["notas"]  # os limites do Pulse que valem para esta parte
    assert _visita(banco, _conta(banco).id) == AGORA_DO_PULSE


def test_pulse_so_mostra_o_da_propria_conta(cliente, banco, relogio, monkeypatch):
    """O Pulse lê e marca pela conta do token: a estratégia e a visita da Bia não aparecem."""
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia", "bia@exemplo.com")[0]
        repo_pulse.marcar_visita(conexao, bia.id, AGORA_DO_PULSE - timedelta(days=1))
    _salvar_com_ficha(banco, bia.id, "Da Bia")
    monkeypatch.setattr(pulse, "veredito_de_hoje", lambda *_: "passou")
    dados = _pulse(cliente)
    assert dados["estrategias"] == []
    assert dados["janela"]["primeira_vez"] is True
    assert _visita(banco, bia.id) == AGORA_DO_PULSE - timedelta(days=1)


PALAVRAS_DE_RECOMENDACAO = ("compre", "venda", "oportunidade", "preço-alvo", "recomend")


def test_textos_do_pulse_nao_recomendam(cliente, banco, relogio):
    """O Pulse mostra o que mudou, não o que fazer: nenhum texto fixo sugere compra ou venda
    (a nota "nada aqui é recomendação" é a única que pode usar a palavra)."""
    ana = _conta(banco)
    _salvar_com_ficha(banco, ana.id, "X")
    with banco.begin() as conexao:
        salvar_simulacao(conexao, ana.id, "backtest", "Velha", {}, {})
    dados = _pulse(cliente)
    textos = [dados["janela"]["texto"], dados["sem_estrategias"], *dados["avisos"]]
    textos += [n for n in dados["notas"] if "é recomendação" not in n]
    for texto in textos:
        for palavra in PALAVRAS_DE_RECOMENDACAO:
            assert palavra not in texto.lower(), texto
