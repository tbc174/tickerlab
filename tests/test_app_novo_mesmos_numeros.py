r"""O app em React mostra os mesmos números da visão geral do Streamlit (série 3 da ADR 0048).

A tela do Streamlit é aberta de verdade (AppTest, dados de exemplo, taxa livre de risco zero) e o
que ela mostra (rótulo → valor) vai, junto com a resposta da API para os mesmos dados, para
`web/testes/app/exemplos/visao_geral.json`. O teste do React (`web/testes/app/visao_geral.test.tsx`)
desenha essa resposta e exige cada rótulo com o mesmo valor. Este teste confere que o arquivo está em
dia. Mudou a tela, a API ou os dados de exemplo? Regrave:

    .venv\Scripts\python -m tests.test_app_novo_mesmos_numeros
"""

import json
import re
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import analises, comparacao, ficha, pulse
from src import indicadores as ind
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.api_v1 import esquemas
from src.api_v1.contexto import ContextoDoAtivo
from src.api_v1.rotas import (
    CAPITAL_PADRAO,
    montar_acontecimentos,
    montar_backtest,
    montar_ficha_do_backtest,
    montar_linha_do_tempo,
    montar_variacoes,
    montar_visao_geral,
)
from src.backtest import CUSTO_PADRAO_POR_OPERACAO
from src.banco.eventos import Evento
from src.commodities import painel_de_precos as pdp
from src.commodities.cafe import pacote_do_mapa
from src.dados import baixar_dados
from src.validacao import parametros_numericos
from tests.ajudantes_da_conta import ir_para
from tests.test_commodities_cafe_pacote_do_mapa import pacote_de_exemplo

PASTA = Path(__file__).resolve().parent.parent / "web" / "testes" / "app" / "exemplos"
ARQUIVO = PASTA / "visao_geral.json"
CONFIANCA_DO_VAR = 95  # o padrão da tela e da API


def _tela_da_visao_geral() -> tuple[str, str, dict[str, str]]:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["taxa"] = "Zero"
    app.run()
    ir_para(app, "visao_geral")
    assert not app.exception, [e.value for e in app.exception]
    metricas = {m.label: m.value for m in app.metric}
    return app.session_state["ticker"], app.session_state["periodo"], metricas


def exemplo_da_visao_geral() -> dict:
    """{"resposta": a API com os dados de exemplo, "na_tela": o que o Streamlit mostra}."""
    ticker, periodo, na_tela = _tela_da_visao_geral()
    contexto = _contexto_de_exemplo(ticker, periodo)
    resposta = montar_visao_geral(contexto, CONFIANCA_DO_VAR).model_dump(mode="json")
    return {"resposta": resposta, "na_tela": na_tela}


def _contexto_de_exemplo(ticker: str, periodo: str) -> ContextoDoAtivo:
    dados = baixar_dados(ticker, periodo, forcar_exemplo=True)
    fechamento = dados["Close"]
    retorno = ind.calcular_retorno_diario(fechamento)
    return ContextoDoAtivo(ticker, periodo, dados, fechamento, retorno, 0.0, False)


def exemplo_de_juros() -> dict:
    """O painel de juros com séries feitas à mão (a tela mostra `texto` e `legenda` da API)."""
    hoje = date(2026, 10, 13)
    meses = pd.date_range(end="2026-09-01", periods=24, freq="MS")
    lidas = {
        ji.SELIC_META: ji.SerieLida(
            pd.Series([10.5, 15.0], index=pd.to_datetime(["2025-01-02", "2026-10-10"])),
            date(2026, 10, 10),
        ),
        ji.IPCA: ji.SerieLida(pd.Series([0.4] * 24, index=meses), date(2026, 10, 10)),
        ji.FOCUS_IPCA: ji.SerieLida(
            pd.Series([4.8, 4.2], index=pd.to_datetime(["2026-12-31", "2027-12-31"])),
            date(2026, 10, 9),
        ),
        ji.FOCUS_SELIC: ji.SerieLida(
            pd.Series([15.0, 12.5], index=pd.to_datetime(["2026-12-31", "2027-12-31"])),
            date(2026, 10, 9),
        ),
    }  # sem o dólar: a tela mostra o traço e o aviso
    cdi = pd.Series(0.0005, index=pd.bdate_range(end=hoje, periods=300))
    painel = ji.montar_painel(lidas, cdi, hoje)
    resposta = esquemas.de_juros_e_inflacao(painel, hoje).model_dump(mode="json")
    na_tela = {n.nome: ji.formatar_valor(n) for n in painel.numeros}
    return {"resposta": resposta, "na_tela": na_tela}


def exemplo_da_linha_do_tempo() -> dict:
    """A linha do tempo de PETR4 (dados de exemplo) com três documentos feitos à mão; um deles com
    um link perigoso, que a tela não pode transformar em link."""
    contexto = _contexto_de_exemplo("PETR4.SA", "2y")
    dias = contexto.fechamento.index
    documentos = (
        (40, 90, "Fato relevante", "Aquisição da Refinaria Exemplo", "https://www.rad.cvm.gov.br/exemplo-1"),
        (300, 60, "Comunicado ao mercado", "Produção do trimestre", "javascript:alert(1)"),
        (450, 20, "Aviso aos acionistas", "Data do pagamento", "https://www.rad.cvm.gov.br/exemplo-3"),
    )  # fmt: skip
    eventos = [
        Evento(
            ticker="PETR4.SA",
            empresa="Petrobras",
            rotulo=rotulo,
            tema="eventos",
            materialidade=materialidade,
            assunto=assunto,
            referencia=None,
            publicado_em=dias[posicao].date(),
            link=link,
            fonte="cvm_ipe",
            protocolo=f"exemplo-{posicao}",
            versao=1,
        )
        for posicao, materialidade, rotulo, assunto, link in documentos
    ]
    resposta = montar_linha_do_tempo(contexto, eventos, ldt.MATERIALIDADE_PADRAO)
    return {"resposta": resposta.model_dump(mode="json")}


def _tela(pagina: str) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["taxa"] = "Zero"
    app.run()
    ir_para(app, pagina)
    assert not app.exception, [e.value for e in app.exception]
    return app


def exemplo_do_risco() -> dict:
    """O risco de PETR4 (janela de 20 dias) e um período curto demais para a janela de 252."""
    contexto = _contexto_de_exemplo("PETR4.SA", "2y")
    resposta = analises.risco_ao_longo_do_tempo(
        contexto.fechamento, contexto.retorno, 20
    )
    curto = _contexto_de_exemplo("PETR4.SA", "6mo")
    risco_curto = analises.risco_ao_longo_do_tempo(curto.fechamento, curto.retorno, 252)
    return {
        "resposta": {
            "ativo": esquemas.de_ativo(contexto).model_dump(mode="json"),
            "risco": esquemas.de_risco(resposta).model_dump(mode="json"),
        },
        "curto": {
            "ativo": esquemas.de_ativo(curto).model_dump(mode="json"),
            "risco": esquemas.de_risco(risco_curto).model_dump(mode="json"),
        },
    }


def exemplo_do_retorno_mensal() -> dict:
    """A resposta para os dados de exemplo e os cartões que a tela do Streamlit mostra."""
    app = _tela("retorno_mensal")
    ticker, periodo = app.session_state["ticker"], app.session_state["periodo"]
    contexto = _contexto_de_exemplo(ticker, periodo)
    mensal = analises.retorno_mensal(contexto.retorno)
    return {
        "resposta": {
            "ativo": esquemas.de_ativo(contexto).model_dump(mode="json"),
            "retorno_mensal": esquemas.de_retorno_mensal(mensal).model_dump(
                mode="json"
            ),
        },
        "na_tela": {m.label: m.value for m in app.metric},
    }


def exemplo_da_comparacao() -> dict:
    """O ativo do topo contra os atalhos padrão (Ibovespa e S&P 500) e a tabela que a tela mostra."""
    app = _tela("comparar")
    ticker, periodo = app.session_state["ticker"], app.session_state["periodo"]
    outros = [comparacao.ATALHOS[n] for n in comparacao.ATALHOS_PADRAO]
    contexto = _contexto_de_exemplo(ticker, periodo)
    fechamentos = {ticker: contexto.fechamento} | {
        t: _contexto_de_exemplo(t, periodo).fechamento for t in outros
    }
    resultado = analises.comparacao_de_ativos(fechamentos, 0.0)
    tabela = app.dataframe[0].value
    return {
        "resposta": {
            "ativo": esquemas.de_ativo(contexto).model_dump(mode="json"),
            "comparacao": esquemas.de_comparacao(resultado).model_dump(mode="json"),
            "sem_dados": [],
        },
        "com": outros,
        "na_tela": {
            str(nome): {str(c): str(v) for c, v in linha.items()}
            for nome, linha in tabela.iterrows()
        },
    }


# os números do backtest que a tela do Streamlit e a API mostram do mesmo jeito
METRICAS_DO_BACKTEST = (
    "Retorno total",
    "Índice de Sharpe",
    "Maior queda",
    "Volatilidade anual",
)


def exemplo_do_backtest() -> dict:
    """O backtest padrão da tela (estratégia, parâmetros e custo de lá) e os números que ela mostra."""
    app = _tela("backtest")
    ticker, periodo = app.session_state["ticker"], app.session_state["periodo"]
    estrategia = app.session_state["backtest_estrategia"]
    contexto = _contexto_de_exemplo(ticker, periodo)
    resposta = montar_backtest(contexto, estrategia, {}, CUSTO_PADRAO_POR_OPERACAO)
    metricas = {m.label: m.value for m in app.metric}
    return {
        "resposta": resposta.model_dump(mode="json"),
        "na_tela": {
            nome: metricas[nome] for nome in METRICAS_DO_BACKTEST if nome in metricas
        },
    }


# com números para variar: as cinco checagens contam
ESTRATEGIA_DA_FICHA = "Cruzamento de médias"
# a tela abre com a estratégia padrão (1ª tentativa no ativo) e troca para esta (2ª), sem login
TENTATIVAS_NA_TELA = 2
CHECAGEM_NA_TELA = re.compile(
    r"^:material/\w+: \*\*(.+?)\*\* \((.+?)\)  \n(.*)$", re.DOTALL
)
TITULO_NA_TELA = re.compile(r"^#### :material/\w+: (.+)$")


def _ficha_na_tela(app: AppTest) -> dict:
    """O veredito, as cinco checagens, o texto das tentativas e a nota, como o Streamlit escreve."""
    textos = [m.value for m in app.markdown]
    inicio = next(i for i, t in enumerate(textos) if TITULO_NA_TELA.match(t))
    checagens = [CHECAGEM_NA_TELA.match(t) for t in textos[inicio + 2 : inicio + 7]]
    assert all(checagens), textos[inicio : inicio + 8]
    return {
        "titulo": TITULO_NA_TELA.match(textos[inicio]).group(1),  # type: ignore[union-attr]
        "texto": textos[inicio + 1],
        "checagens": [
            {"pergunta": c.group(1), "situacao": c.group(2), "explicacao": c.group(3)}
            for c in checagens
            if c is not None
        ],
        "texto_das_tentativas": textos[inicio + 7],
        "nota": next(c.value for c in app.caption if c.value.startswith("Tentativas")),
    }


def exemplo_da_ficha() -> dict:
    """A ficha da tela do backtest (sem login, tolerância e capital padrão) e a da API."""
    app = _tela("backtest")
    app.session_state["backtest_estrategia"] = ESTRATEGIA_DA_FICHA
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    ticker, periodo = app.session_state["ticker"], app.session_state["periodo"]
    contexto = _contexto_de_exemplo(ticker, periodo)
    livres = tuple(p.nome for p in parametros_numericos(ESTRATEGIA_DA_FICHA))[:2]
    custo = app.session_state["backtest_custo"] / 100
    resposta = montar_backtest(contexto, ESTRATEGIA_DA_FICHA, {}, custo)
    resposta.ficha = montar_ficha_do_backtest(
        contexto,
        ESTRATEGIA_DA_FICHA,
        resposta.parametros,
        custo,
        CAPITAL_PADRAO,
        livres,
        ficha.TOLERANCIA_PADRAO_DE_QUEDA,
        TENTATIVAS_NA_TELA,
    )
    return {
        "resposta": resposta.model_dump(mode="json"),
        "na_tela": _ficha_na_tela(app),
    }


def exemplo_do_pulse() -> dict:
    """A parte 2 do Pulse (acontecimentos e variação) com os preços de exemplo: a visita em
    05/10/2026 às 19h e o "agora" logo depois do último pregão de exemplo (09/10). Os documentos
    são feitos à mão; um tem um link perigoso, que a tela não pode transformar em link."""
    visita = datetime(2026, 10, 5, 22, 0, tzinfo=UTC)
    janela = pulse.Janela(visita, datetime(2026, 10, 9, 23, 0, tzinfo=UTC), False)
    ativos, _ = pulse.ativos_da_pessoa(
        ["PETR4.SA", "VALE3.SA"],
        ["ITUB4.SA"],
        [("Bancos", ["BBDC4.SA"])],
        ["WEGE3.SA", "ZZZZ3.SA"],
    )
    documentos = (
        ("PETR4.SA", "Petrobras", "Fato Relevante", "Aquisição da Refinaria Exemplo", "cvm_ipe",
         "https://www.rad.cvm.gov.br/exemplo-1", date(2026, 10, 8)),
        ("VALE3.SA", "Vale", "Comunicado ao Mercado", "Produção do trimestre", "cvm_ipe",
         "javascript:alert(1)", date(2026, 10, 7)),
        ("PETR4.SA", "Petrobras", "Aviso aos Acionistas", "", "cvm_ipe",
         "https://www.rad.cvm.gov.br/exemplo-3", date(2026, 9, 20)),
    )  # fmt: skip
    eventos = [
        Evento(
            ticker=ticker,
            empresa=empresa,
            rotulo=rotulo,
            tema="eventos",
            materialidade=60,
            assunto=assunto,
            referencia=None,
            publicado_em=publicado_em,
            link=link,
            fonte=fonte,
            protocolo=f"exemplo-{n}",
            versao=1,
        )
        for n, (
            ticker,
            empresa,
            rotulo,
            assunto,
            fonte,
            link,
            publicado_em,
        ) in enumerate(documentos)
    ]
    variacoes, sem_variacao = montar_variacoes(
        ativos,
        janela,
        lambda ticker, periodo: baixar_dados(ticker, periodo, forcar_exemplo=True),
    )
    return {
        "resposta": {
            "acontecimentos": [
                a.model_dump(mode="json")
                for a in montar_acontecimentos(eventos, ativos, janela, [])
            ],
            "variacoes": [v.model_dump(mode="json") for v in variacoes],
            "sem_variacao": sem_variacao,
            "avisos_dos_ativos": [pulse.aviso_dos_ativos_de_fora(3)],
            "sem_ativos": pulse.SEM_ATIVOS,
            "nota_da_variacao": pulse.NOTA_DA_VARIACAO,
        }
    }


def _preco_de_exemplo(
    chave: str, nome: str, inicio: float, com_fmi: bool
) -> pdp.PrecoDeReferencia:
    meses = pd.date_range("2025-08-01", "2026-09-01", freq="MS")
    historico = tuple(
        pdp.PontoMensal(
            m.date(), inicio + i / 10, inicio + i / 10 + 0.02 if com_fmi else None
        )
        for i, m in enumerate(meses)
    )
    ultimo = historico[-1].bm or 0.0
    um_ano_antes = historico[-1 - pdp.MESES_NO_ANO].bm or 1.0
    return pdp.PrecoDeReferencia(
        chave=chave,
        nome=nome,
        unidade="US$/kg",
        ultimo_mes=historico[-1].mes,
        ultimo_valor=ultimo,
        variacao_12_meses=(ultimo / um_ano_antes - 1) * 100,
        historico=historico,
        com_fmi=com_fmi,
        nota_das_fontes=None if com_fmi else pdp.NOTA_FONTES_DIFEREM,
    )


def exemplo_de_precos_de_referencia() -> dict:
    """O painel de preços com séries feitas à mão; `na_tela` é o rótulo do `st.metric` e o texto."""
    hoje = date(2026, 10, 18)
    itens = (
        _preco_de_exemplo(pdp.ARABICA, "Café arábica", 7.0, com_fmi=True),
        _preco_de_exemplo(pdp.ROBUSTA, "Café robusta", 3.5, com_fmi=True),
        _preco_de_exemplo("ureia", "Ureia", 0.4, com_fmi=False),
    )
    spread = tuple(
        pdp.PontoDoSpread(a.mes, (a.bm or 0.0) - (r.bm or 0.0))
        for a, r in zip(itens[0].historico, itens[1].historico, strict=True)
    )
    painel = pdp.PainelDePrecos(itens=itens, spread=spread)
    resposta = esquemas.de_precos_de_referencia(painel, hoje).model_dump(mode="json")
    na_tela = {
        f"{i.nome} ({i.unidade})": pdp.formatar_valor(i.ultimo_valor) for i in itens
    }
    return {"resposta": resposta, "na_tela": na_tela}


def exemplo_do_mapa_do_cafe() -> dict:
    """O mapa do arábica em novembro com o pacote dos 5 municípios de exemplo (só Linhares tem
    contorno na malha pequena)."""
    vista = pacote_do_mapa.montar_vista(pacote_de_exemplo(), "arabica", 11)
    resposta = esquemas.MapaDoCafeV1.model_validate(asdict(vista)).model_dump(
        mode="json"
    )
    return {"resposta": resposta}


EXEMPLOS = {
    "visao_geral": exemplo_da_visao_geral,
    "juros_e_inflacao": exemplo_de_juros,
    "precos_de_referencia": exemplo_de_precos_de_referencia,
    "linha_do_tempo": exemplo_da_linha_do_tempo,
    "risco": exemplo_do_risco,
    "retorno_mensal": exemplo_do_retorno_mensal,
    "comparacao": exemplo_da_comparacao,
    "backtest": exemplo_do_backtest,
    "ficha": exemplo_da_ficha,
    "pulse": exemplo_do_pulse,
    "mapa_do_cafe": exemplo_do_mapa_do_cafe,
}


def _em_json(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


@pytest.mark.parametrize("nome", list(EXEMPLOS))
def test_o_exemplo_do_react_esta_em_dia(nome):
    arquivo = PASTA / f"{nome}.json"
    assert arquivo.exists(), "rode: python -m tests.test_app_novo_mesmos_numeros"
    gravado = json.loads(arquivo.read_text(encoding="utf-8"))
    assert gravado == json.loads(_em_json(EXEMPLOS[nome]())), (
        "o exemplo do React está velho: python -m tests.test_app_novo_mesmos_numeros"
    )


def test_o_exemplo_tem_os_numeros_do_painel():
    gravado = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    rotulos = set(gravado["na_tela"])
    assert {"Retorno total", "Índice de Sharpe", "Dias de alta"} <= rotulos
    assert gravado["resposta"]["curva"]["valores"][0] == 100.0


if __name__ == "__main__":
    PASTA.mkdir(parents=True, exist_ok=True)
    for nome, exemplo in EXEMPLOS.items():
        arquivo = PASTA / f"{nome}.json"
        arquivo.write_text(_em_json(exemplo()), encoding="utf-8")
        print(f"Gravado: {arquivo}")


def test_o_exemplo_do_pulse_tem_o_numero_de_pulse_variacao():
    """Cada variação do exemplo é a de `pulse.variacao` com os preços de exemplo; a maior
    mudança vem primeiro; o link perigoso não chega à tela."""
    gravado = json.loads((PASTA / "pulse.json").read_text(encoding="utf-8"))["resposta"]
    visita = datetime(2026, 10, 5, 22, 0, tzinfo=UTC)
    for v in gravado["variacoes"]:
        precos = baixar_dados(f"{v['ticker']}.SA", "6mo", forcar_exemplo=True)["Close"]
        esperada = pulse.variacao(f"{v['ticker']}.SA", precos, visita)
        assert esperada is not None and v["variacao"] == esperada.retorno
    tamanhos = [abs(v["variacao"]) for v in gravado["variacoes"]]
    assert tamanhos == sorted(tamanhos, reverse=True)
    assert gravado["sem_variacao"] == ["ZZZZ3"]
    links = {a["titulo"]: a["link_do_original"] for a in gravado["acontecimentos"]}
    assert links["Produção do trimestre"] is None


def test_a_ficha_da_api_e_a_da_tela():
    """A mesma ficha nos dois apps: veredito, as cinco checagens, as tentativas e a nota."""
    gravado = json.loads((PASTA / "ficha.json").read_text(encoding="utf-8"))
    da_api, na_tela = gravado["resposta"]["ficha"], gravado["na_tela"]
    assert da_api["veredito"]["titulo"] == na_tela["titulo"]
    assert da_api["veredito"]["texto"] == na_tela["texto"]
    assert da_api["checagens"] == na_tela["checagens"]
    assert da_api["texto_das_tentativas"] == na_tela["texto_das_tentativas"]
    assert da_api["nota"] == na_tela["nota"]
