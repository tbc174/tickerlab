"""As rotas de leitura da API v1: os mesmos números que a tela, com os dados de exemplo."""

import re
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import analises, api
from src import indicadores as ind
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, contexto, esquemas, rotas
from src.backtest import executar_backtest
from src.banco import series as acervo
from src.banco.eventos import Evento
from src.banco.usuarios import entrar
from src.conformidade import registrar_aceite
from src.dados import DadosIndisponiveisError, baixar_dados
from src.estrategias import gerar_posicao
from src.exemplos import carregar_exemplo
from src.metricas import resumir_desempenho
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    chaves_publicas,
    com_token,
    gerar_chave,
    token,
)

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
