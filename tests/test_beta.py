"""O roteiro do beta (src/beta.py): cada passo leva a uma página que existe no app."""

from src import beta, paginas


def test_cada_passo_do_roteiro_leva_a_uma_pagina_do_app():
    enderecos = {p.url for p in paginas.PAGINAS}
    assert {passo.url for passo in beta.ROTEIRO} <= enderecos


def test_o_roteiro_tem_dez_minutos_em_ordem():
    assert [passo.ordem for passo in beta.ROTEIRO] == list(
        range(1, len(beta.ROTEIRO) + 1)
    )
    assert beta.TOTAL_DE_MINUTOS == 10


def test_o_texto_do_beta_nao_promete_nada():
    assert "recomendação de investimento" in beta.SOBRE_O_BETA
    assert "rentabilidade" not in (beta.ABERTURA + beta.SOBRE_O_BETA).lower()
