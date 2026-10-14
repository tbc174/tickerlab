"""Testes de src/diario_de_teses.py: as regras do Diário de Teses, sem banco e sem tela."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src import diario_de_teses as diario

QUANDO = datetime(2026, 10, 13, 22, 0, tzinfo=UTC)


@dataclass
class _Simulacao:
    tipo: str
    parametros: object
    nome: str = "estratégia"
    id: uuid.UUID = field(default_factory=uuid.uuid4)


def _anotacao(ticker: str, dia: int, texto: str = "tese") -> diario.Anotacao:
    return diario.Anotacao(uuid.uuid4(), ticker, texto, QUANDO.replace(day=dia), ())


# --- o texto -------------------------------------------------------------------------------


def test_texto_e_limpo_mas_mantem_as_quebras_de_linha():
    assert diario.limpar_texto(
        "  Comprei pelo dividendo.\r\n\r\nVendo se cortar.  "
    ) == ("Comprei pelo dividendo.\n\nVendo se cortar.")


def test_caracteres_de_controle_saem_do_texto():
    assert diario.limpar_texto("a\x00b\x1bc\u200bd\te") == "abcd\te"


@pytest.mark.parametrize("texto", ["", "   ", "\n\n", "\x00\x01"])
def test_texto_vazio_e_recusado(texto):
    with pytest.raises(diario.TeseInvalidaError, match="Escreva"):
        diario.limpar_texto(texto)


def test_texto_no_limite_passa_e_um_a_mais_e_recusado():
    assert (
        len(diario.limpar_texto("x" * diario.TAMANHO_MAXIMO)) == diario.TAMANHO_MAXIMO
    )
    with pytest.raises(diario.TeseInvalidaError, match="2000"):
        diario.limpar_texto("x" * (diario.TAMANHO_MAXIMO + 1))


def test_texto_que_nao_e_texto_e_recusado():
    with pytest.raises(diario.TeseInvalidaError):
        diario.limpar_texto(None)  # type: ignore[arg-type]


@given(st.text(max_size=3000))
def test_texto_limpo_cabe_no_banco_e_limpar_de_novo_nao_muda(texto):
    """Qualquer texto: ou é recusado, ou sai com 1 a 2000 caracteres sem controle."""
    try:
        limpo = diario.limpar_texto(texto)
    except diario.TeseInvalidaError:
        return
    assert 1 <= len(limpo) <= diario.TAMANHO_MAXIMO
    assert "\x00" not in limpo and "\r" not in limpo
    assert diario.limpar_texto(limpo) == limpo


# --- o ativo -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("petr4", "PETR4.SA"),
        (" PETR4.SA ", "PETR4.SA"),
        ("aapl", "AAPL"),
        ("^BVSP", "^BVSP"),
    ],
)
def test_ticker_da_tese_e_normalizado(bruto, esperado):
    assert diario.ticker_da_tese(bruto) == esperado


@pytest.mark.parametrize("bruto", ["", "PETR 4", "<script>", "X" * 21, None])
def test_ticker_invalido_e_recusado(bruto):
    with pytest.raises(diario.TeseInvalidaError, match="ativo"):
        diario.ticker_da_tese(bruto)  # type: ignore[arg-type]


# --- a ligação com os backtests salvos -------------------------------------------------------


def test_so_liga_backtest_do_mesmo_ativo():
    petr_sem_sufixo = _Simulacao("backtest", {"ticker": "petr4"})
    petr = _Simulacao("backtest", {"ticker": "PETR4.SA"})
    vale = _Simulacao("backtest", {"ticker": "VALE3.SA"})
    carteira = _Simulacao("carteira", {"ticker": "PETR4.SA"})
    estranha = _Simulacao("backtest", ["PETR4.SA"])
    sem_ticker = _Simulacao("backtest", {"ticker": 3})
    podem = diario.backtests_que_podem_ser_ligados(
        "PETR4.SA", [petr_sem_sufixo, petr, vale, carteira, estranha, sem_ticker]
    )
    assert podem == [petr_sem_sufixo, petr]


def test_ticker_do_backtest_le_o_retrato_guardado():
    assert diario.ticker_do_backtest({"ticker": " vale3 "}) == "VALE3.SA"
    assert diario.ticker_do_backtest({"ticker": "X" * 50}) is None
    assert diario.ticker_do_backtest({}) is None


# --- a lista --------------------------------------------------------------------------------


def test_agrupa_por_ativo_com_o_mais_recente_primeiro():
    antiga_petr = _anotacao("PETR4.SA", 1)
    vale = _anotacao("VALE3.SA", 5)
    nova_petr = _anotacao("PETR4.SA", 10)
    grupos = diario.agrupar_por_ativo([antiga_petr, vale, nova_petr])
    assert grupos == [
        ("PETR4.SA", [nova_petr, antiga_petr]),
        ("VALE3.SA", [vale]),
    ]


def test_trecho_corta_no_limite_sem_quebrar_palavra_e_marca_o_corte():
    texto = "palavra " * 60
    trecho = diario.trecho(texto, 50)
    assert len(trecho) <= 50 and trecho.endswith("…")
    assert not trecho.removesuffix("…").endswith("palavr")
    assert diario.trecho("curto", 50) == "curto"
    assert diario.trecho("linha 1\nlinha 2", 50) == "linha 1 linha 2"


def test_data_da_anotacao_no_horario_de_brasilia():
    assert diario.texto_da_data(QUANDO) == "13/10/2026 às 19h00"


def test_limites_citam_os_tetos():
    texto = " ".join(diario.LIMITES)
    assert "2000" in texto and "500" in texto and "10 backtests" in texto
