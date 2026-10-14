"""As rotas de leitura da API v1: os mesmos números que a tela, com os dados de exemplo."""

import re
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import analises, api, cobranca, compartilhamentos, ficha, paginas, planos
from src import indicadores as ind
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, contexto, esquemas, rotas
from src.backtest import executar_backtest
from src.banco import compartilhamentos as links
from src.banco import series as acervo
from src.banco import tentativas
from src.banco.dados_do_usuario import (
    TIPOS_DE_SIMULACAO,
    carregar_preferencias,
    salvar_favoritos,
    salvar_preferencias,
    salvar_simulacao,
)
from src.banco.eventos import Evento
from src.banco.modelo import PLANOS, assinaturas
from src.banco.usuarios import buscar_por_google_sub, entrar, mudar_plano
from src.conformidade import exportar_meus_dados, registrar_aceite
from src.dados import DadosIndisponiveisError, baixar_dados
from src.estrategias import gerar_posicao
from src.exemplos import carregar_exemplo
from src.metricas import resumir_desempenho
from src.tentativas import TETO_POR_PESSOA
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    chaves_publicas,
    com_token,
    gerar_chave,
    token,
)
from tests.test_compartilhamentos import _congelada

TAXA = 0.10


@pytest.fixture(scope="module")
def chave():
    return gerar_chave()


@pytest.fixture
def cliente(banco, monkeypatch, chave):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    monkeypatch.setattr(
        contexto,
        "carregar_dados",
        lambda ticker, periodo: baixar_dados(ticker, periodo, forcar_exemplo=True),
    )
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    app.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas(chave)
    acesso.LIMITE.zerar()
    with banco.begin() as conexao:
        ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
        registrar_aceite(conexao, ana.id)
    cliente = TestClient(app, headers=com_token(token(chave)))
    yield cliente


def _fechamento(ticker="PETR4.SA", periodo="2y"):
    return carregar_exemplo(ticker, periodo)["Close"]


def _json(modelo):
    return modelo.model_dump(mode="json")


def test_visao_geral_igual_a_tela(cliente):
    resposta = cliente.get(
        "/api/v1/visao-geral", params={"ticker": "petr4", "periodo": "2y", "taxa": TAXA}
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    fechamento = _fechamento()
    painel = analises.painel_de_numeros(
        fechamento, ind.calcular_retorno_diario(fechamento), TAXA, 95
    )
    assert dados["painel"] == _json(esquemas.de_painel(painel))
    assert dados["ativo"]["ticker"] == "PETR4.SA"  # "petr4" normalizado como na tela
    assert dados["ativo"]["origem"] == "exemplo"
    assert dados["ativo"]["taxa_livre_de_risco"] == TAXA
    assert dados["ativo"]["taxa_do_cdi"] is False


def test_visao_geral_com_outra_confianca(cliente):
    dados = cliente.get(
        "/api/v1/visao-geral",
        params={"ticker": "PETR4.SA", "taxa": TAXA, "confianca_do_var": 99},
    ).json()
    assert dados["painel"]["confianca_do_var"] == 99


def test_sem_taxa_usa_o_cdi_e_cai_para_zero_se_o_bc_falhar(cliente, monkeypatch):
    def falhar(*_):
        raise contexto.CDIIndisponivelError("Banco Central fora do ar.")

    monkeypatch.setattr(contexto, "baixar_cdi", falhar)
    monkeypatch.setattr(contexto, "_cdi_em_cache", {})
    dados = cliente.get("/api/v1/visao-geral", params={"ticker": "PETR4.SA"}).json()
    assert dados["ativo"]["taxa_livre_de_risco"] == 0.0
    assert dados["ativo"]["taxa_do_cdi"] is False


def test_risco_igual_a_tela(cliente):
    dados = cliente.get(
        "/api/v1/risco", params={"ticker": "PETR4.SA", "janela": 60, "taxa": TAXA}
    ).json()
    fechamento = _fechamento()
    risco = analises.risco_ao_longo_do_tempo(
        fechamento, ind.calcular_retorno_diario(fechamento), 60
    )
    assert dados["risco"] == _json(esquemas.de_risco(risco))


def test_retorno_mensal_igual_a_tela(cliente):
    dados = cliente.get(
        "/api/v1/retorno-mensal", params={"ticker": "PETR4.SA", "taxa": TAXA}
    ).json()
    fechamento = _fechamento()
    mensal = analises.retorno_mensal(ind.calcular_retorno_diario(fechamento))
    assert dados["retorno_mensal"] == _json(esquemas.de_retorno_mensal(mensal))


def test_comparacao_igual_a_tela_e_avisa_quem_ficou_de_fora(cliente):
    resposta = cliente.get(
        "/api/v1/comparacao",
        params={"ticker": "PETR4.SA", "com": ["VALE3", "XXXX9"], "taxa": TAXA},
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    fechamentos = {t: _fechamento(t) for t in ("PETR4.SA", "VALE3.SA")}
    comparacao = analises.comparacao_de_ativos(fechamentos, TAXA)
    assert dados["comparacao"] == _json(esquemas.de_comparacao(comparacao))
    assert dados["sem_dados"] == ["XXXX9.SA"]


def test_comparacao_com_ativos_demais_422(cliente):
    resposta = cliente.get(
        "/api/v1/comparacao",
        params={
            "ticker": "PETR4.SA",
            "com": ["VALE3", "ITUB4", "BBAS3", "ABEV3", "AAPL"],
        },
    )
    assert resposta.status_code == 422


def test_backtest_igual_ao_executar_backtest(cliente):
    pedido = {
        "ticker": "PETR4.SA",
        "periodo": "2y",
        "estrategia": "Cruzamento de médias",
        "parametros": {"curta": 10, "longa": 40},
        "custo_por_operacao": 0.001,
        "taxa": TAXA,
    }
    resposta = cliente.post("/api/v1/backtest", json=pedido)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    precos = carregar_exemplo("PETR4.SA", "2y")
    posicao = gerar_posicao("Cruzamento de médias", precos, curta=10, longa=40)
    resultado = executar_backtest(precos["Close"], posicao, 0.001)
    metricas = resumir_desempenho(resultado.retorno, resultado.posicao, None, TAXA)
    assert dados["backtest"] == _json(esquemas.de_backtest(resultado, metricas))
    assert dados["parametros"] == {"curta": 10, "longa": 40, "tipo": "Simples"}


@pytest.mark.parametrize(
    "mudanca",
    [
        {"estrategia": "Estratégia que não existe"},
        {"parametros": {"curta": 1}},  # abaixo do mínimo da tela
        {"parametros": {"inventado": 3}},
        {"parametros": {"curta": "abc"}},  # texto no lugar de número
        {"parametros": {"tipo": 3}},  # número no lugar de uma opção
        {"custo_por_operacao": 0.5},
        {"periodo": "50y"},
    ],
)
def test_backtest_recusa_pedido_fora_dos_limites(cliente, mudanca):
    pedido = {"ticker": "PETR4.SA", "estrategia": "Cruzamento de médias", "taxa": TAXA}
    resposta = cliente.post("/api/v1/backtest", json={**pedido, **mudanca})
    assert resposta.status_code == 422


def test_ativo_sem_dados_404(cliente):
    resposta = cliente.get(
        "/api/v1/visao-geral", params={"ticker": "XXXX9", "taxa": TAXA}
    )
    assert resposta.status_code == 404


@pytest.mark.parametrize("ticker", ["", "PETR4;DROP", "A" * 30, "../etc"])
def test_ticker_malformado_422(cliente, ticker):
    resposta = cliente.get("/api/v1/visao-geral", params={"ticker": ticker})
    assert resposta.status_code == 422


def test_periodo_curto_demais_422(cliente, monkeypatch):
    curto = carregar_exemplo("PETR4.SA", "2y").iloc[-10:]
    monkeypatch.setattr(contexto, "carregar_dados", lambda *_: curto)
    resposta = cliente.get(
        "/api/v1/visao-geral", params={"ticker": "PETR4.SA", "taxa": TAXA}
    )
    assert resposta.status_code == 422


def test_dados_fora_do_ar_404_com_a_mensagem(cliente, monkeypatch):
    def falhar(*_):
        raise DadosIndisponiveisError("O Yahoo não respondeu.")

    monkeypatch.setattr(contexto, "carregar_dados", falhar)
    resposta = cliente.get(
        "/api/v1/visao-geral", params={"ticker": "PETR4.SA", "taxa": TAXA}
    )
    assert resposta.status_code == 404
    assert "Yahoo" in resposta.json()["detail"]


@pytest.mark.parametrize(
    "rota",
    [
        "/api/v1/visao-geral",
        "/api/v1/risco",
        "/api/v1/retorno-mensal",
        "/api/v1/comparacao",
    ],
)
def test_toda_rota_exige_login(banco, rota, monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    assert (
        TestClient(api.criar_app({VARIAVEL_DA_CHAVE: "1"}))
        .get(rota, params={"ticker": "PETR4.SA"})
        .status_code
        == 401
    )


def test_nenhuma_resposta_traz_a_serie_de_precos(cliente):
    """Licença dos preços (ADR 0008): nenhum fechamento do ativo aparece na resposta."""
    fechamento = _fechamento()
    texto = (
        cliente.get(
            "/api/v1/visao-geral", params={"ticker": "PETR4.SA", "taxa": TAXA}
        ).text
        + cliente.get("/api/v1/risco", params={"ticker": "PETR4.SA", "taxa": TAXA}).text
    )
    precos = {f"{v}" for v in fechamento.iloc[-20:]} | {
        f"{v:.2f}" for v in fechamento.iloc[-20:]
    }
    # número inteiro da resposta, não pedaço: "48.0" dentro de "148.09" (base 100) não é preço
    numeros = set(re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", texto))
    assert not precos & numeros


def test_posicao_e_numeros_simples_no_backtest(cliente):
    dados = cliente.post(
        "/api/v1/backtest",
        json={"ticker": "PETR4.SA", "estrategia": "Comprar e segurar", "taxa": TAXA},
    ).json()
    assert dados["backtest"]["curva_de_capital"]["valores"][0] == pytest.approx(100)
    assert isinstance(dados["backtest"]["operacoes"], int)
    assert pd.Timestamp(dados["ativo"]["fim"]) == _fechamento().index[-1]


# --- Juros e inflação e Linha do tempo (pedido da sessão "Funcionalidades", onda 2) ---------

HOJE = date(2026, 10, 13)


def _cdi_de_exemplo(*_):
    return pd.Series(0.0005, index=pd.bdate_range(end=HOJE, periods=300))


def _gravar_series_de_juros(banco):
    with banco.begin() as conexao:
        for codigo, nome, unidade, valores in (
            (ji.SELIC_META, "Selic", "% ao ano", pd.Series([15.0], index=pd.to_datetime(["2026-10-10"]))),
            (ji.IPCA, "IPCA", "% no mês", pd.Series([0.4] * 12, index=pd.date_range(end="2026-09-01", periods=12, freq="MS"))),
        ):  # fmt: skip
            acervo.garantir_serie(
                conexao, acervo.SerieDoAcervo(codigo, nome, unidade, "mensal")
            )
            acervo.gravar(conexao, codigo, valores, date(2026, 10, 10))


@pytest.fixture
def no_dia(monkeypatch):
    monkeypatch.setattr(rotas, "hoje_no_brasil", lambda: HOJE)
    monkeypatch.setattr(contexto, "baixar_cdi", _cdi_de_exemplo)
    monkeypatch.setattr(contexto, "_cdi_em_cache", {})


def test_juros_e_inflacao_igual_a_tela(cliente, banco, no_dia):
    _gravar_series_de_juros(banco)
    resposta = cliente.get("/api/v1/juros-e-inflacao")
    assert resposta.status_code == 200, resposta.text
    with banco.connect() as conexao:
        lidas = ji.ler_series(conexao, HOJE)
    painel = ji.montar_painel(lidas, _cdi_de_exemplo(), HOJE)
    assert resposta.json() == _json(esquemas.de_juros_e_inflacao(painel, HOJE))
    numeros = {n["nome"]: n for n in resposta.json()["numeros"]}
    assert numeros[ji.NOME_SELIC]["texto"] == "15,00% ao ano"
    assert numeros[ji.NOME_SELIC]["fonte"].startswith("Banco Central")


def test_juros_e_inflacao_sem_cdi_avisa_e_nao_quebra(
    cliente, banco, no_dia, monkeypatch
):
    def falhar(*_):
        raise contexto.CDIIndisponivelError("Banco Central fora do ar.")

    monkeypatch.setattr(contexto, "baixar_cdi", falhar)
    _gravar_series_de_juros(banco)
    dados = cliente.get("/api/v1/juros-e-inflacao").json()
    numeros = {n["nome"]: n for n in dados["numeros"]}
    assert numeros[ji.NOME_JURO_REAL]["valor"] is None
    assert any("CDI" in aviso for aviso in dados["avisos"])


def test_juros_e_inflacao_sem_series_coletadas_503(cliente, no_dia):
    resposta = cliente.get("/api/v1/juros-e-inflacao")
    assert resposta.status_code == 503
    assert "coletadas" in resposta.json()["detail"]


def _eventos_no_periodo(fechamento):
    dias = fechamento.index
    return [
        Evento(
            ticker="PETR4.SA",
            empresa="Petrobras",
            rotulo="Fato relevante",
            tema="eventos",
            materialidade=materialidade,
            assunto=f"Assunto {posicao}",
            referencia=None,
            publicado_em=dias[posicao].date(),
            link="https://www.rad.cvm.gov.br/doc",
            fonte="cvm_ipe",
            protocolo=f"p-{posicao}",
            versao=1,
        )
        for posicao, materialidade in ((10, 90), (200, 60), (300, 20))
    ]


def test_linha_do_tempo_igual_a_tela(cliente, monkeypatch):
    fechamento = _fechamento()
    eventos = _eventos_no_periodo(fechamento)
    pedidos = []

    def ler(_conexao, tickers, desde, limite):
        pedidos.append((tickers, desde, limite))
        return eventos

    monkeypatch.setattr(rotas, "eventos_dos_tickers", ler)
    resposta = cliente.get(
        "/api/v1/linha-do-tempo", params={"ticker": "petr4", "materialidade_minima": 50}
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()["linha_do_tempo"]
    linha = ldt.montar_linha_do_tempo(fechamento, eventos, 50)
    assert dados == _json(esquemas.de_linha_do_tempo(linha))
    assert resposta.json()["ativo"]["ticker"] == "PETR4.SA"
    assert pedidos == [
        (["PETR4.SA"], fechamento.index[0].date(), ldt.LIMITE_DE_EVENTOS)
    ]
    assert len(dados["marcos"]) == 2 and dados["fora_do_grafico"] == 1
    assert dados["aviso"] == ldt.AVISO_DA_LINHA
    assert dados["texto_fora_do_grafico"] == ldt.texto_fora_do_grafico(1)


def test_linha_do_tempo_so_em_base_100(cliente, monkeypatch):
    """Nada de preço bruto pela API (ADR 0048, item 6): a curva começa em 100."""
    monkeypatch.setattr(rotas, "eventos_dos_tickers", lambda *_a, **_k: [])
    resposta = cliente.get("/api/v1/linha-do-tempo", params={"ticker": "PETR4.SA"})
    dados = resposta.json()["linha_do_tempo"]
    assert dados["curva"]["valores"][0] == pytest.approx(100.0)
    fechamento = _fechamento()
    assert dados["curva"]["valores"][-1] == pytest.approx(
        fechamento.iloc[-1] / fechamento.iloc[0] * 100
    )


def test_linha_do_tempo_com_o_banco_sem_acontecimentos(cliente):
    resposta = cliente.get("/api/v1/linha-do-tempo", params={"ticker": "PETR4.SA"})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()["linha_do_tempo"]
    assert dados["marcos"] == [] and dados["fora_do_grafico"] == 0
    assert dados["sem_acontecimentos"] == ldt.SEM_ACONTECIMENTOS


def test_linha_do_tempo_com_relevancia_fora_da_faixa_422(cliente):
    resposta = cliente.get(
        "/api/v1/linha-do-tempo",
        params={"ticker": "PETR4.SA", "materialidade_minima": 101},
    )
    assert resposta.status_code == 422


# --- visão geral para o app em React (série 3, PR 3) ---


def test_visao_geral_traz_a_curva_em_base_100_e_os_avisos(cliente):
    dados = cliente.get(
        "/api/v1/visao-geral",
        params={"ticker": "PETR4.SA", "taxa": TAXA, "periodo": "6mo"},
    ).json()
    fechamento = _fechamento(periodo="6mo")
    curva = dados["curva"]
    assert curva["valores"][0] == pytest.approx(100.0)
    assert curva["valores"][-1] == pytest.approx(
        fechamento.iloc[-1] / fechamento.iloc[0] * 100
    )
    assert len(curva["datas"]) == len(fechamento)
    # 6 meses: menos de 1 ano, o retorno não é anualizado e a API diz por quê
    assert dados["painel"]["retorno_anualizado"] is None
    assert dados["motivo_sem_anualizar"] == ind.MOTIVO_SEM_ANUALIZAR
    # dados de exemplo: o mesmo aviso que a tela mostra
    assert dados["ativo"]["aviso_da_origem"] == analises.aviso_da_origem(
        "exemplo", fechamento.index[-1].strftime("%d/%m/%Y")
    )


def test_visao_geral_de_2_anos_sem_motivo(cliente):
    dados = cliente.get(
        "/api/v1/visao-geral", params={"ticker": "PETR4.SA", "taxa": TAXA}
    ).json()
    assert dados["painel"]["retorno_anualizado"] is not None
    assert dados["motivo_sem_anualizar"] is None


# --- textos prontos de Risco, Retorno mensal e Comparar (série 3, PR 5) ---


def test_risco_traz_a_frase_da_pior_queda_e_o_aviso_da_janela(cliente):
    from src.conteudo import descrever_pior_drawdown

    dados = cliente.get(
        "/api/v1/risco", params={"ticker": "PETR4.SA", "taxa": TAXA}
    ).json()
    fechamento = _fechamento()
    risco = analises.risco_ao_longo_do_tempo(
        fechamento, ind.calcular_retorno_diario(fechamento), 20
    )
    assert dados["risco"]["frase_da_pior_queda"] == descrever_pior_drawdown(
        risco.pior_drawdown, negrito=False
    )
    assert dados["risco"]["aviso_da_janela"] is None
    curto = cliente.get(
        "/api/v1/risco",
        params={"ticker": "PETR4.SA", "taxa": TAXA, "periodo": "6mo", "janela": 252},
    ).json()
    assert curto["risco"]["aviso_da_janela"] == analises.aviso_janela_curta(252)


def test_retorno_mensal_traz_a_media_de_cada_mes(cliente):
    dados = cliente.get(
        "/api/v1/retorno-mensal", params={"ticker": "PETR4.SA", "taxa": TAXA}
    ).json()["retorno_mensal"]
    mensal = analises.retorno_mensal(ind.calcular_retorno_diario(_fechamento()))
    media = ind.calcular_media_por_mes(mensal.tabela)
    assert dados["media_por_mes"] == pytest.approx(list(media.to_numpy()), nan_ok=True)
    assert len(dados["media_por_mes"]) == 12


def test_comparacao_traz_a_nota_e_avisa_poucos_dias():
    curta = analises.Comparacao(
        dias_em_comum=8, dias_descartados=0, base_100=None, tabela=None
    )
    assert esquemas.de_comparacao(curta).aviso == analises.aviso_poucos_dias_em_comum(8)
    assert esquemas.de_comparacao(curta).nota is None


def test_comparacao_com_dados_traz_a_nota(cliente):
    dados = cliente.get(
        "/api/v1/comparacao",
        params={"ticker": "PETR4.SA", "com": ["^BVSP"], "taxa": TAXA},
    ).json()["comparacao"]
    assert dados["aviso"] is None
    assert dados["nota"] == analises.nota_da_comparacao(
        dados["dias_em_comum"], dados["dias_descartados"]
    )


def test_a_resposta_traz_o_codigo_para_mostrar(cliente):
    """Índice sem o ^ do Yahoo na tela (ADR 0065); `ticker` continua o símbolo dos dados."""
    ativo = cliente.get(
        "/api/v1/visao-geral", params={"ticker": "^BVSP", "taxa": TAXA}
    ).json()["ativo"]
    assert (ativo["ticker"], ativo["codigo"]) == ("^BVSP", "IBOV")
    tabela = cliente.get(
        "/api/v1/comparacao",
        params={"ticker": "PETR4.SA", "com": ["^BVSP"], "taxa": TAXA},
    ).json()["comparacao"]["tabela"]
    assert {(linha["ticker"], linha["codigo"]) for linha in tabela} == {
        ("PETR4.SA", "PETR4"),
        ("^BVSP", "IBOV"),
    }


# --- Plano de cada rota (ADR 0062) ----------------------------------------------------------

ROTAS_PUBLICAS = frozenset({"/v1/configuracao"})  # sem login (o client ID do Google)


def test_toda_rota_da_v1_tem_contrato_ou_e_da_conta():
    """Rota nova precisa de contrato de página (que diz o plano) ou entrar em ROTAS_DA_CONTA."""
    for rota in rotas.router.routes:
        caminho = rota.path  # type: ignore[attr-defined]
        if caminho in ROTAS_PUBLICAS:
            continue
        assert caminho in paginas.POR_ROTA or caminho in acesso.ROTAS_DA_CONTA, caminho
        dependencias = {d.call for d in rota.dependant.dependencies}  # type: ignore[attr-defined]
        assert acesso.conta_com_acesso in dependencias, caminho


@pytest.mark.parametrize("plano", PLANOS)
def test_rotas_reais_seguem_o_contrato(cliente, banco, plano):
    """403 de plano se e só se a página da rota não abre no plano (hoje, nenhuma é paga).

    Sem os campos da rota: a conferência do plano vem antes, então a página fechada responde 403 e
    a aberta passa dela (e para no 422 dos campos que faltam, sem calcular nada).
    """
    with banco.begin() as conexao:
        ana = buscar_por_google_sub(conexao, "ana")
        assert ana is not None
        mudar_plano(conexao, ana.id, plano)
    for rota, pagina in paginas.POR_ROTA.items():
        metodo = pagina.contrato.metodo  # type: ignore[union-attr]
        resposta = cliente.request(metodo, "/api" + rota)
        fechada = paginas.motivo_da_pagina(plano, pagina.chave) is not None
        recusou = resposta.headers.get(acesso.CABECALHO_DO_MOTIVO) == "plano"
        assert recusou == fechada, (rota, resposta.status_code)
        assert (resposta.status_code == 403) == fechada, (rota, resposta.status_code)


# --- A ficha "Foi sorte?" na resposta do backtest (ADR 0062, tela 1) -------------------------

PEDIDO_DA_FICHA = {
    "ticker": "PETR4.SA",
    "periodo": "2y",
    "estrategia": "Cruzamento de médias",
    "parametros": {"curta": 10, "longa": 40},
    "custo_por_operacao": 0.001,
    "taxa": TAXA,
}


def _ficha(cliente, **mudancas):
    resposta = cliente.post("/api/v1/backtest", json={**PEDIDO_DA_FICHA, **mudancas})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _id_da_ana(banco):
    with banco.connect() as conexao:
        return buscar_por_google_sub(conexao, "ana").id


def test_a_ficha_do_backtest_e_a_mesma_de_src_ficha(cliente):
    dados = _ficha(cliente)
    precos = carregar_exemplo("PETR4.SA", "2y")
    esperada = ficha.montar_ficha(
        ficha.PedidoDaFicha(
            dados=precos,
            estrategia="Cruzamento de médias",
            parametros={"curta": 10, "longa": 40, "tipo": "Simples"},
            custo_por_operacao=0.001,
            capital_inicial=rotas.CAPITAL_PADRAO,
            livres=("curta", "longa"),  # os dois primeiros numéricos, como no Streamlit
            taxa_livre_de_risco=TAXA,
            tentativas_da_pessoa=1,
        )
    )
    recebida = dados["ficha"]
    assert dados["motivo_sem_ficha"] is None
    assert recebida["veredito"] == {
        "resultado": esperada.veredito.resultado.value,
        "titulo": esperada.veredito.titulo,
        "texto": esperada.veredito.texto,
    }
    assert recebida["checagens"] == [
        {
            "pergunta": c.pergunta,
            "situacao": c.situacao.value,
            "explicacao": c.explicacao,
        }
        for c in esperada.checagens
    ]
    assert recebida["tentativas"] == esperada.tentativas
    assert recebida["tentativas_da_pessoa"] == 1
    # o texto leva o código da tela (PETR4), não o símbolo do Yahoo
    assert recebida["texto_das_tentativas"] == ficha.texto_das_tentativas(
        1, "PETR4", TETO_POR_PESSOA
    )
    assert recebida["tolerancia_de_queda"] == ficha.TOLERANCIA_PADRAO_DE_QUEDA
    assert recebida["livres"] == ["curta", "longa"]
    assert recebida["capital_inicial"] == rotas.CAPITAL_PADRAO
    assert recebida["nota"] == ficha.nota_das_tentativas(esperada.tentativas)


def test_a_mesma_configuracao_conta_uma_vez_so(cliente, banco):
    assert _ficha(cliente)["ficha"]["tentativas_da_pessoa"] == 1
    assert _ficha(cliente)["ficha"]["tentativas_da_pessoa"] == 1  # recarregar não conta
    outra = _ficha(cliente, parametros={"curta": 12, "longa": 40})
    assert outra["ficha"]["tentativas_da_pessoa"] == 2
    with banco.connect() as conexao:
        assert tentativas.contar_tentativas(conexao, _id_da_ana(banco), "PETR4.SA") == 2


def test_as_tentativas_de_uma_conta_nao_contam_na_outra(cliente, banco, chave):
    _ficha(cliente)
    _ficha(cliente, parametros={"curta": 12, "longa": 40})
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia", "bia@exemplo.com")[0]
        registrar_aceite(conexao, bia.id)
    da_bia = cliente.post(
        "/api/v1/backtest",
        json=PEDIDO_DA_FICHA,
        headers=com_token(token(chave, sub="bia", email="bia@exemplo.com")),
    )
    assert da_bia.status_code == 200, da_bia.text
    assert da_bia.json()["ficha"]["tentativas_da_pessoa"] == 1


def test_a_tolerancia_informada_fica_guardada_na_conta(cliente, banco):
    assert (
        _ficha(cliente, tolerancia_de_queda=0.5)["ficha"]["tolerancia_de_queda"] == 0.5
    )
    with banco.connect() as conexao:
        guardadas = carregar_preferencias(conexao, _id_da_ana(banco))
    assert guardadas[ficha.PREFERENCIA_DA_TOLERANCIA] == 0.5
    # sem o campo: a guardada
    assert _ficha(cliente)["ficha"]["tolerancia_de_queda"] == 0.5


def test_guardar_a_tolerancia_mantem_as_outras_preferencias(cliente, banco):
    with banco.begin() as conexao:
        salvar_preferencias(conexao, _id_da_ana(banco), {"tema": "escuro"})
    _ficha(cliente, tolerancia_de_queda=0.4)
    with banco.connect() as conexao:
        guardadas = carregar_preferencias(conexao, _id_da_ana(banco))
    assert guardadas == {"tema": "escuro", ficha.PREFERENCIA_DA_TOLERANCIA: 0.4}


def test_os_parametros_que_variam_vem_do_pedido(cliente):
    dados = _ficha(cliente, livres=["longa"])
    assert dados["ficha"]["livres"] == ["longa"]


@pytest.mark.parametrize(
    "mudanca",
    [
        {"livres": ["inventado"]},
        {"livres": ["tipo"]},  # opção, não número: não varia na grade
        {"livres": ["curta", "curta"]},
        {"livres": ["curta", "longa", "curta"]},
        {"tolerancia_de_queda": 0.01},
        {"tolerancia_de_queda": 0.95},
        {"capital_inicial": 0},
        {"capital_inicial": 1e13},
    ],
)
def test_a_ficha_recusa_pedido_fora_dos_limites(cliente, mudanca):
    resposta = cliente.post("/api/v1/backtest", json={**PEDIDO_DA_FICHA, **mudanca})
    assert resposta.status_code == 422


def test_sem_o_banco_para_contar_nao_sai_ficha(cliente, monkeypatch):
    """Contar "1" por engano deixaria a checagem do acaso mais branda: melhor não mostrar."""

    def falhar(*_):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(tentativas, "registrar_tentativa", falhar)
    dados = _ficha(cliente)
    assert dados["ficha"] is None
    assert "tentativas" in dados["motivo_sem_ficha"]
    assert dados["backtest"]["operacoes"] > 0  # o backtest sai do mesmo jeito


def test_erro_do_calculo_da_ficha_vira_o_motivo(cliente, monkeypatch):
    def falhar(_pedido):
        raise ValueError("Histórico curto demais para a ficha.")

    monkeypatch.setattr(ficha, "montar_ficha", falhar)
    dados = _ficha(cliente)
    assert dados["ficha"] is None
    assert dados["motivo_sem_ficha"] == "Histórico curto demais para a ficha."


def test_com_o_cdi_a_ficha_compara_com_o_cdi(cliente, no_dia):
    dados = _ficha(cliente, taxa=None)
    custos = dados["ficha"]["checagens"][1]
    assert custos["pergunta"] == ficha.PERGUNTA_CUSTOS
    assert "o CDI rendeu" in custos["explicacao"]


def test_com_taxa_informada_a_ficha_nao_usa_o_cdi(cliente):
    custos = _ficha(cliente)["ficha"]["checagens"][1]
    assert "sem o CDI" in custos["explicacao"]


def test_se_o_cdi_sumir_a_ficha_compara_com_zero(cliente, no_dia, monkeypatch):
    def falhar(*_):
        raise contexto.CDIIndisponivelError("Banco Central fora do ar.")

    monkeypatch.setattr(
        rotas, "cdi_entre", falhar
    )  # a taxa já veio do CDI; a ficha não acha
    custos = _ficha(cliente, taxa=None)["ficha"]["checagens"][1]
    assert "sem o CDI" in custos["explicacao"]


# --- Planos e assinatura no app novo (conta e planos, PR 3) -----------------------------------


def _id_da_ana_no(banco):
    with banco.connect() as conexao:
        ana = buscar_por_google_sub(conexao, "ana")
    assert ana is not None
    return ana.id


def test_meu_plano_mostra_o_plano_e_o_uso(cliente, banco):
    ana = _id_da_ana_no(banco)
    with banco.begin() as conexao:
        salvar_favoritos(conexao, ana, ["PETR4.SA", "VALE3.SA"])
        salvar_simulacao(conexao, ana, TIPOS_DE_SIMULACAO[0], "minha", {}, {})
    resposta = cliente.get("/api/v1/meu-plano")
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["plano"] == "gratuito"
    assert dados["nome_do_plano"] == "Gratuito"
    assert dados["simulacoes"] == "1 de 5"  # como as métricas do Streamlit
    assert dados["favoritos"] == "2 de 3"
    assert dados["frase_da_assinatura"] is None
    assert dados["aviso"] == planos.AVISO_DO_MODO_DE_TESTE
    assert dados["tabela"] == planos.tabela_de_planos()


def test_meu_plano_pro_sem_limite_de_simulacoes(cliente, banco):
    with banco.begin() as conexao:
        mudar_plano(conexao, _id_da_ana_no(banco), "pro")
    assert cliente.get("/api/v1/meu-plano").json()["simulacoes"] == "0 de ilimitadas"


@pytest.mark.parametrize(("cancela", "verbo"), [(False, "renova"), (True, "termina")])
def test_meu_plano_diz_quando_a_assinatura_renova(cliente, banco, cancela, verbo):
    with banco.begin() as conexao:
        conexao.execute(
            sa.insert(assinaturas).values(
                usuario_id=_id_da_ana_no(banco),
                stripe_customer_id="cus_teste",
                status="active",
                periodo_fim=datetime(2026, 11, 14, 12, tzinfo=UTC),
                cancela_no_fim=cancela,
            )
        )
    dados = cliente.get("/api/v1/meu-plano").json()
    assert dados["frase_da_assinatura"] == f"Sua assinatura {verbo} em 14/11/2026."
    assert "cus_teste" not in str(dados)  # nada do Stripe na resposta


def test_meu_plano_e_so_da_conta_do_token(cliente, banco):
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia2", "bia2@exemplo.com")[0]
        salvar_favoritos(conexao, bia.id, ["PETR4.SA", "VALE3.SA", "ITUB4.SA"])
    assert cliente.get("/api/v1/meu-plano").json()["favoritos"] == "0 de 3"


# --- Meus dados no app novo (conta e planos, PR 5) --------------------------------------------


def _link_da_ana(banco):
    with banco.begin() as conexao:
        links.criar_link_da_ficha(
            conexao, _id_da_ana_no(banco), "gratuito", _congelada(), 30
        )
        return links.listar_links(conexao, _id_da_ana_no(banco))[0]


def test_meus_links_lista_os_links_da_conta(cliente, banco):
    link = _link_da_ana(banco)
    dados = cliente.get("/api/v1/links-compartilhados").json()
    assert dados["explicacao"] == compartilhamentos.EXPLICACAO_DOS_LINKS
    assert dados["sem_links"] == compartilhamentos.SEM_LINKS
    [recebido] = dados["links"]
    assert recebido["id"] == str(link.id)
    assert recebido["titulo"] == link.titulo
    assert recebido["situacao"] == "ativo"
    assert recebido["descricao"] == compartilhamentos.descrever_link(
        link.tipo, link.situacao, link.criado_em, link.expira_em, link.visitas
    )
    assert "codigo" not in recebido and "hash" not in str(
        recebido
    )  # o código nunca volta


def test_meus_links_nao_mostra_os_de_outra_conta(cliente, banco):
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia3", "bia3@exemplo.com")[0]
        links.criar_link_da_ficha(conexao, bia.id, "gratuito", _congelada(), 30)
    assert cliente.get("/api/v1/links-compartilhados").json()["links"] == []


def test_revogar_um_link_da_conta(cliente, banco):
    link = _link_da_ana(banco)
    resposta = cliente.post("/api/v1/revogar-link", json={"id": str(link.id)})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["links"][0]["situacao"] == "revogado"


def test_revogar_link_de_outra_conta_404(cliente, banco):
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia4", "bia4@exemplo.com")[0]
        links.criar_link_da_ficha(conexao, bia.id, "gratuito", _congelada(), 30)
        dela = links.listar_links(conexao, bia.id)[0]
    resposta = cliente.post("/api/v1/revogar-link", json={"id": str(dela.id)})
    assert resposta.status_code == 404
    with banco.connect() as conexao:
        assert links.listar_links(conexao, bia.id)[0].situacao == "ativo"


@pytest.mark.parametrize("corpo", [{}, {"id": "nao-e-uuid"}, {"id": 3}])
def test_revogar_sem_id_valido_422(cliente, corpo):
    assert cliente.post("/api/v1/revogar-link", json=corpo).status_code == 422


def test_baixar_meus_dados(cliente, banco):
    resposta = cliente.get("/api/v1/meus-dados")
    assert resposta.status_code == 200, resposta.text
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.headers["cache-control"] == "no-store"
    with banco.begin() as conexao:
        esperado = exportar_meus_dados(conexao, _id_da_ana_no(banco))
    recebido = resposta.json()
    assert recebido.keys() == esperado.keys()
    assert recebido["perfil"]["email"] == "ana@exemplo.com"


# --- Assinar e gerenciar pelo app novo (conta e planos, PR 4; Stripe só em modo de teste) -------

STRIPE_DE_TESTE = {
    "STRIPE_SECRET_KEY": "sk_test_abc",
    "STRIPE_PRICE_ID": "price_123",
    "TICKERLAB_URL_PUBLICA": "https://app.tickerlab.com.br",
}
CHECKOUT = "https://checkout.stripe.com/c/pay/cs_test_1"
PORTAL = "https://billing.stripe.com/p/session/test_1"


@pytest.fixture
def stripe_de_teste(monkeypatch):
    """O Stripe configurado com chaves de teste e as chamadas a ele trocadas por respostas fixas."""
    for nome, valor in STRIPE_DE_TESTE.items():
        monkeypatch.setenv(nome, valor)
    chamadas = []

    def pagina(usuario_id, email, id_do_cliente=None, caminho_de_volta="/", **_):
        chamadas.append(("pagina", usuario_id, email, id_do_cliente, caminho_de_volta))
        return CHECKOUT

    def portal(id_do_cliente, caminho_de_volta="/", **_):
        chamadas.append(("portal", id_do_cliente, caminho_de_volta))
        return PORTAL

    monkeypatch.setattr(cobranca, "criar_pagina_de_pagamento", pagina)
    monkeypatch.setattr(cobranca, "criar_portal_da_assinatura", portal)
    return chamadas


def _ana_admin(banco):
    with banco.begin() as conexao:
        entrar(conexao, "ana", "ana@exemplo.com", emails_de_admin=("ana@exemplo.com",))


def _assinatura_da_ana(banco, cliente="cus_ana"):
    with banco.begin() as conexao:
        conexao.execute(
            sa.insert(assinaturas).values(
                usuario_id=_id_da_ana_no(banco),
                stripe_customer_id=cliente,
                status="active",
            )
        )


def test_meu_plano_diz_qual_botao_mostrar(cliente, banco, stripe_de_teste):
    dados = cliente.get("/api/v1/meu-plano").json()
    assert (dados["acao"], dados["texto_da_acao"]) == (
        None,
        cobranca.AVISO_DE_PLANOS_EM_BREVE,  # conta comum: só admins assinam (ADR 0029)
    )
    _ana_admin(banco)
    dados = cliente.get("/api/v1/meu-plano").json()
    assert dados["acao"] == "assinar"
    assert dados["nota_do_cartao"] == cobranca.NOTA_DO_CARTAO_DE_TESTE


def test_meu_plano_sem_stripe_configurado(cliente, banco, monkeypatch):
    for nome in STRIPE_DE_TESTE:
        monkeypatch.delenv(nome, raising=False)
    dados = cliente.get("/api/v1/meu-plano").json()
    assert (dados["acao"], dados["texto_da_acao"]) == (
        None,
        cobranca.AVISO_SEM_COBRANCA,
    )


def test_admin_assina_e_volta_para_os_planos_do_app_novo(
    cliente, banco, stripe_de_teste
):
    _ana_admin(banco)
    resposta = cliente.post("/api/v1/pagamento-da-assinatura", json={})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"url": CHECKOUT}
    assert stripe_de_teste == [
        ("pagina", _id_da_ana_no(banco), "ana@exemplo.com", None, "/novo/planos")
    ]


def test_quem_ja_e_cliente_reusa_o_cliente_do_stripe(cliente, banco, stripe_de_teste):
    _ana_admin(banco)
    _assinatura_da_ana(banco)
    cliente.post("/api/v1/pagamento-da-assinatura", json={})
    assert stripe_de_teste[0][3] == "cus_ana"


def test_conta_comum_nao_cria_pagamento(cliente, banco, stripe_de_teste):
    """A trava da ADR 0029 vale também se alguém chamar a rota direto, sem o botão."""
    resposta = cliente.post("/api/v1/pagamento-da-assinatura", json={})
    assert resposta.status_code == 409
    assert resposta.json()["detail"] == cobranca.AVISO_DE_PLANOS_EM_BREVE
    assert stripe_de_teste == []


def test_quem_ja_e_pro_nao_assina_de_novo(cliente, banco, stripe_de_teste):
    _ana_admin(banco)
    with banco.begin() as conexao:
        mudar_plano(conexao, _id_da_ana_no(banco), "pro")
    assert cliente.post("/api/v1/pagamento-da-assinatura", json={}).status_code == 409
    assert stripe_de_teste == []


def test_sem_stripe_configurado_503(cliente, banco, monkeypatch):
    for nome in STRIPE_DE_TESTE:
        monkeypatch.delenv(nome, raising=False)
    _ana_admin(banco)
    assert cliente.post("/api/v1/pagamento-da-assinatura", json={}).status_code == 503


def test_assinante_abre_o_portal(cliente, banco, stripe_de_teste):
    with banco.begin() as conexao:
        mudar_plano(conexao, _id_da_ana_no(banco), "pro")
    _assinatura_da_ana(banco)
    resposta = cliente.post("/api/v1/portal-da-assinatura", json={})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"url": PORTAL}
    assert stripe_de_teste == [("portal", "cus_ana", "/novo/planos")]


def test_sem_assinatura_nao_ha_portal(cliente, banco, stripe_de_teste):
    with banco.begin() as conexao:
        mudar_plano(conexao, _id_da_ana_no(banco), "pro")  # Pro dado por administrador
    assert cliente.post("/api/v1/portal-da-assinatura", json={}).status_code == 404
    assert stripe_de_teste == []


def test_o_portal_e_so_da_assinatura_da_conta_do_token(cliente, banco, stripe_de_teste):
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia5", "bia5@exemplo.com")[0]
        conexao.execute(
            sa.insert(assinaturas).values(
                usuario_id=bia.id, stripe_customer_id="cus_bia", status="active"
            )
        )
    assert cliente.post("/api/v1/portal-da-assinatura", json={}).status_code == 404
    assert stripe_de_teste == []
