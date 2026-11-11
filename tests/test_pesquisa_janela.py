"""A janela literal em volta do valor provado (linha 830): fatia do original, com o valor, sem texto inventado."""

import pytest

from pesquisa.janela import janela_do_valor
from src.novidades_da_pesquisa import (
    CORTE_NO_FIM,
    CORTE_NO_INICIO,
    CORTE_NOS_DOIS,
    SEM_CORTE,
    TRECHO_MAXIMO,
)

ENCHIMENTO = "palavra "


def _linha(antes: int, depois: int, valor: str = "120 MW") -> str:
    return f"{ENCHIMENTO * antes}{valor} {ENCHIMENTO * depois}".strip()


def test_trecho_curto_sai_igual_e_sem_corte():
    janela = janela_do_valor("Parque: 120 MW", "120 MW", TRECHO_MAXIMO)
    assert janela is not None
    assert (janela.texto, janela.recorte) == ("Parque: 120 MW", SEM_CORTE)


def test_trecho_curto_sai_igual_mesmo_sem_valor_localizavel():
    janela = janela_do_valor("Parque Exemplo", "", TRECHO_MAXIMO)
    assert janela is not None and janela.texto == "Parque Exemplo"


@pytest.mark.parametrize(
    ("antes", "depois", "recorte"),
    [(80, 80, CORTE_NOS_DOIS), (0, 80, CORTE_NO_FIM), (80, 0, CORTE_NO_INICIO)],
)
def test_janela_e_fatia_literal_dentro_do_maximo_com_o_valor(antes, depois, recorte):
    trecho = _linha(antes, depois)
    janela = janela_do_valor(trecho, "120 MW", TRECHO_MAXIMO)
    assert janela is not None
    assert janela.texto in trecho  # literal: fatia contígua do original
    assert "120 MW" in janela.texto  # o valor provado está dentro
    assert len(janela.texto) <= TRECHO_MAXIMO
    assert janela.recorte == recorte
    assert "…" not in janela.texto and "..." not in janela.texto


def test_janela_nao_corta_palavra_no_meio():
    trecho = _linha(80, 80)
    janela = janela_do_valor(trecho, "120 MW", TRECHO_MAXIMO)
    assert janela is not None
    assert all(p in trecho.split() for p in janela.texto.split())


def test_valor_acha_sem_ligar_para_a_caixa():
    trecho = _linha(80, 80, valor="Valor Exato")
    janela = janela_do_valor(trecho, "valor exato", TRECHO_MAXIMO)
    assert janela is not None and "Valor Exato" in janela.texto


@pytest.mark.parametrize("valor", ["", "   ", "999 GW", "x" * (TRECHO_MAXIMO + 1)])
def test_fato_sem_valor_localizavel_fica_de_fora(valor):
    assert janela_do_valor(_linha(80, 80), valor, TRECHO_MAXIMO) is None
