"""O PDF diz o mesmo que a tela: cada número do relatório confere com o que o app mostra.

O erro mais grave de um relatório é dizer uma coisa e o app outra. Aqui a tela é aberta de verdade
(AppTest, dados de exemplo, taxa livre de risco zero), os números dela são lidos e comparados com
os do PDF dos mesmos dados. A tela mostra 2 casas e o PDF 1, então a diferença aceita é só a do
arredondamento. Comparação e carteira são conferidas contra as funções que as telas chamam.
"""

import re
from io import BytesIO

import pandas as pd
import pytest
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from src import relatorios
from src.backtest import CUSTO_PADRAO_POR_OPERACAO
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA, numeros_da_carteira, simular_carteira
from src.comparacao import alinhar_fechamentos, montar_tabela_comparativa
from src.dados import baixar_dados
from src.exemplos import carregar_exemplo
from tests.ajudantes_da_conta import ir_para

NUMERO = re.compile(r"[+−-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?|—")


def _texto(pdf: bytes) -> str:
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    return " ".join(texto.split())


def _secao(texto: str, titulo: str) -> str:
    """O corpo de uma seção numerada do PDF (a última ocorrência: a primeira é o sumário da capa)."""
    inicios = [m.end() for m in re.finditer(rf"\d+\. {re.escape(titulo)} ", texto)]
    assert inicios, f"seção {titulo!r} não encontrada"
    resto = texto[inicios[-1] :]
    fim = re.search(r" \d+\. [A-ZÁÉÍÓÚ]", resto)
    return resto[: fim.start()] if fim else resto


def _numero(texto: str) -> tuple[float | None, int]:
    """'+1.234,56%' → (1234.56, 2 casas); '—' → (None, 0)."""
    if texto == "—":
        return None, 0
    limpo = texto.replace("−", "-").replace(".", "")
    casas = len(limpo.split(",")[1]) if "," in limpo else 0
    return float(limpo.replace(",", ".")), casas


def _depois(
    trecho: str, rotulo: str, quantos: int = 1
) -> list[tuple[float | None, int]]:
    """Os `quantos` primeiros números logo depois do rótulo."""
    posicao = trecho.find(rotulo)
    assert posicao >= 0, f"{rotulo!r} não está no PDF"
    resto = trecho[posicao + len(rotulo) :]
    return [_numero(n) for n in NUMERO.findall(resto)[:quantos]]


def _bate(
    tela: tuple[float | None, int], pdf: tuple[float | None, int], nome: str
) -> None:
    """Iguais a menos do arredondamento de cada um (meia unidade da última casa)."""
    (a, casas_a), (b, casas_b) = tela, pdf
    if a is None or b is None:
        assert a is b, f"{nome}: tela {a}, PDF {b}"
        return
    folga = 0.5 * 10**-casas_a + 0.5 * 10**-casas_b + 1e-9
    assert abs(a - b) <= folga, f"{nome}: tela {a}, PDF {b}"


def _abrir(pagina: str) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.session_state["taxa"] = "Zero"
    app.run()
    ir_para(app, pagina)
    assert not app.exception, [e.value for e in app.exception]
    return app


def _metricas(app: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in app.metric}


# --- telas abertas de verdade ------------------------------------------------------------------
def test_visao_geral_e_o_pdf_do_ativo_mostram_os_mesmos_numeros():
    app = _abrir("visao_geral")
    ticker, periodo = app.session_state["ticker"], app.session_state["periodo"]
    tela = _metricas(app)
    dados = baixar_dados(ticker, periodo, forcar_exemplo=True)
    pdf = _secao(_texto(relatorios.relatorio_do_ativo(ticker, dados)), "Números-chave")
    pares = {
        "Retorno total": "Retorno total",
        "Retorno anualizado": "Retorno anualizado",
        "Volatilidade anual": "Volatilidade anual",
        "Maior queda (drawdown)": "Maior queda",
        "Índice de Sharpe": "Índice de Sharpe",
    }
    pares |= {r: r for r in tela if r.startswith(("Melhor dia", "Pior dia"))}
    assert len(pares) == 7
    for rotulo_da_tela, rotulo_do_pdf in pares.items():
        (na_tela,) = [_numero(n) for n in NUMERO.findall(tela[rotulo_da_tela])[:1]]
        (no_pdf,) = _depois(pdf, rotulo_do_pdf)
        _bate(na_tela, no_pdf, rotulo_do_pdf)


def test_backtest_e_o_pdf_do_backtest_mostram_os_mesmos_numeros():
    app = _abrir("backtest")
    ticker, periodo = app.session_state["ticker"], app.session_state["periodo"]
    estrategia = app.session_state["backtest_estrategia"]
    tela = _metricas(app)
    dados = baixar_dados(ticker, periodo, forcar_exemplo=True)
    texto = _texto(
        relatorios.relatorio_de_backtest(
            ticker, dados, estrategia, {}, CUSTO_PADRAO_POR_OPERACAO
        )
    )
    resultado = _secao(texto, "Resultado")
    for rotulo_da_tela, rotulo_do_pdf in {
        "Retorno total": "Retorno total da estratégia",
        "Índice de Sharpe": "Índice de Sharpe",
        "Maior queda": "Maior queda",
        "Operações": "Operações",
    }.items():
        (na_tela,) = [_numero(n) for n in NUMERO.findall(tela[rotulo_da_tela])[:1]]
        (no_pdf,) = _depois(resultado, rotulo_do_pdf)
        _bate(na_tela, no_pdf, rotulo_do_pdf)


# --- contra as funções que as telas chamam -----------------------------------------------------
def _pct(valor: float) -> tuple[float | None, int]:
    return (None, 0) if pd.isna(valor) else (valor * 100, 9)


def _num(valor: float) -> tuple[float | None, int]:
    return (None, 0) if pd.isna(valor) else (valor, 9)


def test_tabela_do_pdf_da_comparacao_e_a_da_pagina_comparar():
    tickers = ("PETR4.SA", "VALE3.SA", "AAPL")
    alinhado, _ = alinhar_fechamentos(
        {t: carregar_exemplo(t, "5y")["Close"] for t in tickers}
    )
    tabela = montar_tabela_comparativa(alinhado)  # o que a página Comparar mostra
    texto = _texto(relatorios.relatorio_de_comparacao(alinhado))
    tabela_do_pdf = texto.split(
        "Ativo Retorno total Ao ano Volatilidade Maior queda Sharpe"
    )[1]
    for ticker, linha in tabela.iterrows():
        numeros = _depois(tabela_do_pdf, f"{ticker} ", 5)
        esperado = [
            _pct(linha["Retorno total"]),
            _pct(linha["Retorno anualizado"]),
            _pct(linha["Volatilidade anual"]),
            _pct(linha["Maior queda"]),
            _num(linha["Índice de Sharpe"]),
        ]
        for nome, tela, pdf in zip(tabela.columns, esperado, numeros, strict=False):
            _bate(tela, pdf, f"{ticker} / {nome}")


@pytest.mark.parametrize("estrategia", list(ESTRATEGIAS_DE_CARTEIRA)[:3])
def test_pdf_da_carteira_e_a_pagina_carteira(estrategia):
    tickers = ("PETR4.SA", "VALE3.SA", "ITUB4.SA")
    alinhado, _ = alinhar_fechamentos(
        {t: carregar_exemplo(t, "5y")["Close"] for t in tickers}
    )
    referencia = next(iter(ESTRATEGIAS_DE_CARTEIRA))
    principal = simular_carteira(estrategia, alinhado, CUSTO_PADRAO_POR_OPERACAO)
    _, numeros = numeros_da_carteira(  # o que a página Carteira mostra
        estrategia,
        principal,
        simular_carteira(referencia, alinhado, CUSTO_PADRAO_POR_OPERACAO),
        alinhado,
        0.0,
        {},
    )
    texto = _texto(relatorios.relatorio_de_carteira(alinhado, estrategia))
    resultado = _secao(texto, "Resultado da carteira")
    da_tela = numeros[estrategia]
    for rotulo_do_pdf, chave, conv in (
        ("Retorno total da carteira", "Retorno total", _pct),
        ("Retorno anualizado", "Retorno anualizado", _pct),
        ("Volatilidade anual", "Volatilidade anual", _pct),
        ("Maior queda", "Maior queda", _pct),
        ("Índice de Sharpe", "Índice de Sharpe", _num),
    ):
        (no_pdf,) = _depois(resultado, rotulo_do_pdf)
        _bate(conv(da_tela[chave]), no_pdf, rotulo_do_pdf)
    sozinhos = _secao(texto, "Cada ativo sozinho")
    for ticker in tickers:
        tela = numeros[f"{ticker} (comprar e segurar)"]
        retorno, vol, queda, sharpe = _depois(sozinhos, f"{ticker} ", 4)
        _bate(_pct(tela["Retorno total"]), retorno, f"{ticker} / retorno")
        _bate(_pct(tela["Volatilidade anual"]), vol, f"{ticker} / volatilidade")
        _bate(_pct(tela["Maior queda"]), queda, f"{ticker} / maior queda")
        _bate(_num(tela["Índice de Sharpe"]), sharpe, f"{ticker} / Sharpe")
