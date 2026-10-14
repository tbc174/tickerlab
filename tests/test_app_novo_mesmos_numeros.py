r"""O app em React mostra os mesmos números da visão geral do Streamlit (série 3 da ADR 0048).

A tela do Streamlit é aberta de verdade (AppTest, dados de exemplo, taxa livre de risco zero) e o
que ela mostra (rótulo → valor) vai, junto com a resposta da API para os mesmos dados, para
`web/testes/app/exemplos/visao_geral.json`. O teste do React (`web/testes/app/visao_geral.test.tsx`)
desenha essa resposta e exige cada rótulo com o mesmo valor. Este teste confere que o arquivo está em
dia. Mudou a tela, a API ou os dados de exemplo? Regrave:

    .venv\Scripts\python -m tests.test_app_novo_mesmos_numeros
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import analises, comparacao
from src import indicadores as ind
from src import juros_e_inflacao as ji
from src import linha_do_tempo as ldt
from src.api_v1 import esquemas
from src.api_v1.contexto import ContextoDoAtivo
from src.api_v1.rotas import montar_linha_do_tempo, montar_visao_geral
from src.banco.eventos import Evento
from src.dados import baixar_dados
from tests.ajudantes_da_conta import ir_para

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
        (40, 90, "Fato relevante", "Plano de investimentos", "https://www.rad.cvm.gov.br/exemplo-1"),
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


EXEMPLOS = {
    "visao_geral": exemplo_da_visao_geral,
    "juros_e_inflacao": exemplo_de_juros,
    "linha_do_tempo": exemplo_da_linha_do_tempo,
    "risco": exemplo_do_risco,
    "retorno_mensal": exemplo_do_retorno_mensal,
    "comparacao": exemplo_da_comparacao,
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
