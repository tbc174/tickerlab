"""Testes de src/ficha.py: a ficha "Foi sorte?" (ADR 0037, D1 e D2)."""

import pytest

from src import ficha
from src.ficha import Checagem, Situacao

PALAVRAS_PROIBIDAS = (
    "compre",
    "comprar agora",
    "garantid",
    "vai subir",
    "lucro certo",
    "recomendamos",
    "recomendo",
)


def _checagem(situacao, pergunta="Pergunta?"):
    return Checagem(pergunta, situacao, "Explicação.")


def _ficha(*situacoes):
    return ficha.Ficha(
        tuple(_checagem(s, f"Pergunta {i}?") for i, s in enumerate(situacoes)),
        tentativas=1,
    )


# --- Veredito -----------------------------------------------------------------------------


def test_veredito_passou_so_com_tudo_passando():
    v = _ficha(*[Situacao.PASSOU] * 5).veredito
    assert v.resultado is ficha.Resultado.PASSOU
    assert v.titulo == "Passou no teste contra a sorte"


def test_uma_falha_da_nao_passou_e_diz_qual():
    v = _ficha(
        Situacao.PASSOU,
        Situacao.NAO_PASSOU,
        Situacao.PASSOU,
        Situacao.SEM_MEDIDA,
        Situacao.PASSOU,
    ).veredito
    assert v.resultado is ficha.Resultado.NAO_PASSOU
    assert v.titulo == "Não passou no teste contra a sorte"
    assert "Pergunta 1?" in v.texto
    assert "Pergunta 3?" not in v.texto


def test_sem_medida_e_sem_falha_da_inconclusivo():
    v = _ficha(
        Situacao.PASSOU, Situacao.SEM_MEDIDA, Situacao.PASSOU, Situacao.PASSOU
    ).veredito
    assert v.resultado is ficha.Resultado.INCONCLUSIVO
    assert "Pergunta 1?" in v.texto


def test_nao_se_aplica_nao_pesa():
    v = _ficha(
        Situacao.NAO_SE_APLICA,
        Situacao.PASSOU,
        Situacao.PASSOU,
        Situacao.NAO_SE_APLICA,
        Situacao.PASSOU,
    ).veredito
    assert v.resultado is ficha.Resultado.PASSOU


def test_sem_nenhuma_checagem_que_passou_e_inconclusivo():
    v = _ficha(Situacao.NAO_SE_APLICA, Situacao.NAO_SE_APLICA).veredito
    assert v.resultado is ficha.Resultado.INCONCLUSIVO


@pytest.mark.parametrize(
    "situacoes",
    [
        [Situacao.PASSOU] * 5,
        [Situacao.NAO_PASSOU] * 5,
        [Situacao.PASSOU, Situacao.SEM_MEDIDA],
    ],
)
def test_todo_veredito_tem_o_aviso(situacoes):
    assert ficha.AVISO in _ficha(*situacoes).veredito.texto


@pytest.mark.parametrize(
    "situacoes",
    [
        [Situacao.PASSOU] * 5,
        [Situacao.NAO_PASSOU] * 5,
        [Situacao.PASSOU, Situacao.SEM_MEDIDA],
    ],
)
def test_veredito_nao_usa_palavras_proibidas(situacoes):
    v = _ficha(*situacoes).veredito
    texto = f"{v.titulo} {v.texto}".lower()
    assert not [p for p in PALAVRAS_PROIBIDAS if p in texto]
