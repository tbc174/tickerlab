"""Fontes tiradas da coleta pelos termos (ADR 0102, Emenda 1, 21/10/2026): não podem voltar sem nova emenda."""

import pytest

from base.arquivo import destinos, fontes

RETIRADAS = (
    "b3-emprestimo-posicoes",
    "b3-derivativos-posicoes",
    "b3-emprestimo-resumo",
    "fnc-estadisticas",
    "cecafe-relatorio-mensal",
)
VIGIAS_QUE_FICAM = (
    "termos-b3-coleta-automatizada",
    "termos-fnc-colombia",
    "termos-cecafe-robots",
)


@pytest.mark.parametrize("id_", RETIRADAS)
def test_fonte_retirada_nao_esta_nas_fontes_nem_nos_destinos(id_):
    assert id_ not in fontes.POR_ID
    assert id_ not in destinos.DESTINOS


@pytest.mark.parametrize("id_", VIGIAS_QUE_FICAM)
def test_as_vigias_de_termos_das_fontes_retiradas_continuam(id_):
    assert fontes.POR_ID[id_].vigia
    assert destinos.DESTINOS[id_].tipo == destinos.VIGIA
