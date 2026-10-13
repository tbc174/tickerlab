r"""O app em React mostra os mesmos números da visão geral do Streamlit (série 3 da ADR 0048).

A tela do Streamlit é aberta de verdade (AppTest, dados de exemplo, taxa livre de risco zero) e o
que ela mostra (rótulo → valor) vai, junto com a resposta da API para os mesmos dados, para
`web/testes/app/exemplos/visao_geral.json`. O teste do React (`web/testes/app/visao_geral.test.tsx`)
desenha essa resposta e exige cada rótulo com o mesmo valor. Este teste confere que o arquivo está em
dia. Mudou a tela, a API ou os dados de exemplo? Regrave:

    .venv\Scripts\python -m tests.test_app_novo_mesmos_numeros
"""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import indicadores as ind
from src.api_v1.contexto import ContextoDoAtivo
from src.api_v1.rotas import montar_visao_geral
from src.dados import baixar_dados
from tests.ajudantes_da_conta import ir_para

ARQUIVO = (
    Path(__file__).resolve().parent.parent
    / "web"
    / "testes"
    / "app"
    / "exemplos"
    / "visao_geral.json"
)
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
    dados = baixar_dados(ticker, periodo, forcar_exemplo=True)
    fechamento = dados["Close"]
    contexto = ContextoDoAtivo(
        ticker,
        periodo,
        dados,
        fechamento,
        ind.calcular_retorno_diario(fechamento),
        0.0,
        False,
    )
    resposta = montar_visao_geral(contexto, CONFIANCA_DO_VAR).model_dump(mode="json")
    return {"resposta": resposta, "na_tela": na_tela}


def _em_json(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def test_o_exemplo_do_react_esta_em_dia():
    assert ARQUIVO.exists(), "rode: python -m tests.test_app_novo_mesmos_numeros"
    gravado = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    assert gravado == json.loads(_em_json(exemplo_da_visao_geral())), (
        "o exemplo do React está velho: python -m tests.test_app_novo_mesmos_numeros"
    )


def test_o_exemplo_tem_os_numeros_do_painel():
    gravado = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    rotulos = set(gravado["na_tela"])
    assert {"Retorno total", "Índice de Sharpe", "Dias de alta"} <= rotulos
    assert gravado["resposta"]["curva"]["valores"][0] == 100.0


if __name__ == "__main__":
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(_em_json(exemplo_da_visao_geral()), encoding="utf-8")
    print(f"Gravado: {ARQUIVO}")
