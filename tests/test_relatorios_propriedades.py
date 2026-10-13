"""Relatórios em PDF com qualquer série de preços: abrem, trazem os limites e não inventam número.

Duas partes:
- **Propriedades (Hypothesis):** o gerador cria séries de preços (curtas, longas, constantes, com
  buracos, com saltos) e confere as mesmas regras em todas. Com poucos pregões, o relatório recusa
  com `DadosInsuficientesError` e uma mensagem em português, o mesmo mínimo que a tela usa; com
  pregões suficientes, o PDF abre, tem "Limites e cuidados" e nenhum "nan" ou "inf".
- **Matriz:** cada tipo de relatório em cada estilo, com ação da B3, ação dos EUA, cripto e índice.
"""

import re
from datetime import UTC, datetime
from io import BytesIO

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, event, example, given, settings
from hypothesis import strategies as st
from pypdf import PdfReader

from src import relatorios
from src.analises import MIN_DIAS_PARA_ANALISE
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA, MIN_DIAS_NA_CARTEIRA
from src.comparacao import alinhar_fechamentos
from src.estilos_pdf import ESTILOS, PADRAO
from src.estrategias import ESTRATEGIAS
from src.relatorio_newsletter import relatorio_da_newsletter
from src.relatorio_pdf import RelatorioPDF
from tests.test_carteira_b3 import _carteira
from tests.test_newsletter import EVENTOS, _edicao

# Cada PDF leva ~0,4 s: 20 exemplos por propriedade cabem na suíte. Sem prazo por exemplo (pandas
# e matplotlib variam muito de uma máquina para outra e o prazo viraria teste instável no CI).
POUCOS_EXEMPLOS = settings(
    max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
# texto que nenhum leitor decifra (no papel, quadradinhos no lugar das letras)
ILEGIVEL = re.compile(r"[\x00-\x08\x0b-\x1f]")
SUSPEITOS = re.compile(r"\b(?:nan|NaN|inf|None)\b|∞")
PROIBIDAS = re.compile(r"\b(?:compre|venda agora|recomendamos|vai subir|vai cair)\b")
ESTRATEGIAS_DE_BACKTEST = [n for n in ESTRATEGIAS if n != "Comprar e segurar"]


def _texto(pdf: bytes) -> str:
    assert pdf.startswith(b"%PDF")
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    return " ".join(texto.split())


def _conferir(pdf: bytes) -> str:
    """O que vale para todo relatório, com quaisquer dados."""
    texto = _texto(pdf)
    assert not ILEGIVEL.search(texto), repr(
        texto[ILEGIVEL.search(texto).start() - 40 :][:80]
    )
    assert "Limites e cuidados" in texto
    assert "nada aqui é recomendação de investimento" in texto.lower()
    assert not SUSPEITOS.findall(texto), SUSPEITOS.findall(texto)
    assert not PROIBIDAS.findall(texto.lower())
    assert "**" not in texto
    return texto


def test_depois_de_uma_seta_os_numeros_da_mesma_linha_continuam_legiveis():
    """A seta vem da fonte reserva (JetBrains Mono); o fpdf2 2.8.9 ficava preso nela e as
    colunas seguintes saíam em quadradinhos (tabela "Cada ativo sozinho" da carteira)."""
    pdf = RelatorioPDF("t", "s", datetime(2026, 1, 1, tzinfo=UTC), PADRAO)
    pdf.add_page()
    pdf.tabela(
        ["Ativo", "Retorno", "Volatilidade", "Maior queda"],
        [["PETR4.SA", "▲ +5,0%", "39,7%", "−49,2%"]],
        tickers=True,
    )
    assert "PETR4.SA ▲ +5,0% 39,7% −49,2%" in _texto(bytes(pdf.output()))


# --- geradores ---------------------------------------------------------------------------------
def _dos_dois_lados(minimo: int, maximo: int = 150) -> st.SearchStrategy[int]:
    """Tamanhos abaixo e acima do mínimo: testa a recusa e também o PDF.

    O ramo de cima aparece duas vezes porque o Hypothesis prefere números pequenos.
    """
    acima = st.integers(minimo, maximo)
    return st.one_of(st.integers(1, minimo - 1), acima, acima)


@st.composite
def fechamentos(draw, n=None, buracos=True, inicio="2024-01-01"):
    """Preços a partir de retornos diários entre −30% e +50%, às vezes parados, às vezes com buracos."""
    if n is None:
        n = draw(_dos_dois_lados(MIN_DIAS_PARA_ANALISE + 1))
    retorno = st.one_of(st.just(0.0), st.floats(-0.3, 0.5, allow_nan=False))
    retornos = draw(st.lists(retorno, min_size=n - 1, max_size=n - 1))
    precos = 10 * np.cumprod([1.0, *(1 + r for r in retornos)])
    serie = pd.Series(precos, index=pd.bdate_range(inicio, periods=n), name="Close")
    if buracos and n > 2:
        sem_preco = draw(st.lists(st.integers(1, n - 1), max_size=n // 5))
        serie.iloc[sem_preco] = np.nan
    return serie


@st.composite
def par_para_comparar(draw):
    """Dois ativos; o segundo começa depois (como uma ação recém-listada)."""
    atraso = draw(st.integers(0, 60))
    n_b = draw(_dos_dois_lados(MIN_DIAS_PARA_ANALISE + 1))
    inicio = pd.Timestamp("2024-01-01") + pd.offsets.BDay(atraso)
    b = draw(fechamentos(n=n_b, inicio=inicio))
    a = draw(fechamentos(n=atraso + n_b + draw(st.integers(0, 30)), buracos=False))
    return a, b


@st.composite
def tabela_da_carteira(draw):
    """Três ativos nos mesmos dias, com tamanhos dos dois lados do mínimo da carteira."""
    n = draw(_dos_dois_lados(MIN_DIAS_NA_CARTEIRA))
    return pd.DataFrame(
        {c: draw(fechamentos(n=n, buracos=False)) for c in "ABC"}
    ).dropna()


def _recusa_ou_pdf(pregoes: int, minimo: int) -> bool:
    """Diz se o PDF deve sair e registra o ramo (pytest --hypothesis-show-statistics)."""
    sai = pregoes >= minimo
    event("PDF gerado" if sai else "recusado por poucos pregões")
    return sai


def _ohlcv(fechamento: pd.Series, volume: bool = True) -> pd.DataFrame:
    dados = pd.DataFrame(
        {c: fechamento for c in ("Open", "High", "Low", "Close")},
        index=fechamento.index,
    )
    if volume:
        dados["Volume"] = 1_000_000.0
    return dados


def _serie_de_pregoes(n: int) -> pd.Series:
    return pd.Series(
        10 + np.sin(np.arange(n)), index=pd.bdate_range("2024-01-01", periods=n)
    )


# --- propriedades ------------------------------------------------------------------------------
@POUCOS_EXEMPLOS
@given(fechamento=fechamentos(), volume=st.booleans())
@example(fechamento=_serie_de_pregoes(1), volume=True)
@example(fechamento=_serie_de_pregoes(2), volume=True)
@example(fechamento=_serie_de_pregoes(MIN_DIAS_PARA_ANALISE + 1), volume=False)
@example(
    fechamento=pd.Series(10.0, index=pd.bdate_range("2024-01-01", periods=60)),
    volume=True,
)
def test_relatorio_do_ativo_com_qualquer_serie(fechamento, volume):
    dados = _ohlcv(fechamento, volume)
    if not _recusa_ou_pdf(fechamento.dropna().size, MIN_DIAS_PARA_ANALISE + 1):
        with pytest.raises(
            relatorios.DadosInsuficientesError, match="período mais longo"
        ):
            relatorios.relatorio_do_ativo("X", dados)
    else:
        _conferir(relatorios.relatorio_do_ativo("X", dados))


@POUCOS_EXEMPLOS
@given(
    fechamento=fechamentos(buracos=False),
    estrategia=st.sampled_from(ESTRATEGIAS_DE_BACKTEST),
)
@example(fechamento=_serie_de_pregoes(2), estrategia=ESTRATEGIAS_DE_BACKTEST[0])
def test_relatorio_de_backtest_com_qualquer_serie(fechamento, estrategia):
    dados = _ohlcv(fechamento)
    if not _recusa_ou_pdf(fechamento.size, MIN_DIAS_PARA_ANALISE + 1):
        with pytest.raises(relatorios.DadosInsuficientesError):
            relatorios.relatorio_de_backtest("X", dados, estrategia)
    else:
        texto = _conferir(relatorios.relatorio_de_backtest("X", dados, estrategia))
        assert "pode ser sorte" in texto


@POUCOS_EXEMPLOS
@given(par=par_para_comparar())
def test_relatorio_de_comparacao_com_poucos_dias_em_comum(par):
    """Só os dias em que os dois têm preço contam."""
    alinhado, _ = alinhar_fechamentos(dict(zip("AB", par, strict=True)))
    if not _recusa_ou_pdf(len(alinhado), MIN_DIAS_PARA_ANALISE + 1):
        with pytest.raises(relatorios.DadosInsuficientesError, match="em comum"):
            relatorios.relatorio_de_comparacao(alinhado)
    else:
        _conferir(relatorios.relatorio_de_comparacao(alinhado))


@POUCOS_EXEMPLOS
@given(
    tabela=tabela_da_carteira(),
    estrategia=st.sampled_from(list(ESTRATEGIAS_DE_CARTEIRA)),
)
def test_relatorio_de_carteira_com_poucos_dias_em_comum(tabela, estrategia):
    if not _recusa_ou_pdf(len(tabela), MIN_DIAS_NA_CARTEIRA):
        with pytest.raises(relatorios.DadosInsuficientesError, match="em comum"):
            relatorios.relatorio_de_carteira(tabela, estrategia)
    else:
        _conferir(relatorios.relatorio_de_carteira(tabela, estrategia))


def test_dados_insuficientes_e_um_valueerror_que_a_tela_ja_mostra():
    """A tela do estúdio trata ValueError com uma mensagem e sem contar no limite do plano."""
    assert issubclass(relatorios.DadosInsuficientesError, ValueError)
    with pytest.raises(relatorios.DadosInsuficientesError) as erro:
        relatorios.relatorio_do_ativo("X", _ohlcv(_serie_de_pregoes(2)))
    assert "2 pregões" in str(erro.value)
    assert str(MIN_DIAS_PARA_ANALISE + 1) in str(erro.value)


def test_minha_carteira_com_poucos_pregoes_recusa():
    carteira = _carteira()
    tabela = pd.DataFrame(
        {t: _serie_de_pregoes(5) for t in carteira.posicoes["ticker"]}
    )
    with pytest.raises(relatorios.DadosInsuficientesError, match="5 pregões"):
        relatorios.relatorio_da_minha_carteira(carteira, tabela)


# --- matriz: tipos × estilos × ativos ----------------------------------------------------------
def _dados(ticker: str) -> pd.DataFrame:
    return pd.read_csv(f"dados_de_exemplo/{ticker}.csv", index_col=0, parse_dates=True)


ATIVOS = {
    "PETR4.SA": "ação da B3",
    "AAPL": "ação dos EUA",
    "BTC-USD": "cripto",
    "_BVSP": "índice",
}


@pytest.mark.parametrize("estilo", list(ESTILOS))
@pytest.mark.parametrize("ticker", list(ATIVOS))
def test_matriz_do_ativo(ticker, estilo):
    config = relatorios.Configuracao(estilo=estilo)
    texto = _conferir(
        relatorios.relatorio_do_ativo(ticker, _dados(ticker), config=config)
    )
    assert ticker in texto


@pytest.mark.parametrize("estilo", list(ESTILOS))
@pytest.mark.parametrize("ticker", list(ATIVOS))
def test_matriz_do_backtest(ticker, estilo):
    config = relatorios.Configuracao(estilo=estilo)
    pdf = relatorios.relatorio_de_backtest(
        ticker, _dados(ticker), "Cruzamento de médias", config=config
    )
    assert "pode ser sorte" in _conferir(pdf)


@pytest.mark.parametrize("estilo", list(ESTILOS))
def test_matriz_da_comparacao_com_moedas_diferentes_avisa(estilo):
    alinhado, _ = alinhar_fechamentos({t: _dados(t)["Close"] for t in ATIVOS})
    config = relatorios.Configuracao(estilo=estilo)
    texto = _conferir(relatorios.relatorio_de_comparacao(alinhado, config=config))
    assert "moedas diferentes" in texto


@pytest.mark.parametrize("estilo", list(ESTILOS))
def test_matriz_da_carteira(estilo):
    tabela = pd.DataFrame(
        {t: _dados(t)["Close"] for t in ("PETR4.SA", "VALE3.SA", "ITUB4.SA")}
    ).dropna()
    nome = list(ESTRATEGIAS_DE_CARTEIRA)[1]
    config = relatorios.Configuracao(estilo=estilo)
    _conferir(relatorios.relatorio_de_carteira(tabela, nome, config=config))


@pytest.mark.parametrize("estilo", list(ESTILOS))
def test_matriz_da_minha_carteira(estilo):
    carteira = _carteira()
    tabela = pd.DataFrame({t: _dados(t)["Close"] for t in carteira.posicoes["ticker"]})
    config = relatorios.Configuracao(estilo=estilo)
    pdf = relatorios.relatorio_da_minha_carteira(
        carteira, tabela, _dados("_BVSP")["Close"], config=config
    )
    assert "Não é o seu resultado real" in _conferir(pdf)


@pytest.mark.parametrize("estilo", list(ESTILOS))
def test_matriz_da_newsletter(estilo):
    config = relatorios.Configuracao(estilo=estilo)
    _conferir(relatorio_da_newsletter(_edicao(EVENTOS), config=config))
