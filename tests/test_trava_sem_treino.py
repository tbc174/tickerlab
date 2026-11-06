"""Trava das fontes que não treinam modelo (ADR 0122, item 1; linha 698).

O Ministério da Saúde liberou o uso comercial dos dados do DATASUS (CNES, SIH, SIA) com a fonte citada, mas
a resposta não fala de treino de modelos: até haver resposta escrita, a família `ms` mostra, rotula e
exporta, e não treina. A trava passa por `coletas.pode_usar`, como a das fontes só internas, então vale para
os scripts que montam amostra e modelo e para o portão da API externa (finalidade treino).
"""

import pytest

from src.banco import coletas
from src.banco.coletas import (
    FONTES_SEM_TREINO,
    MOSTRAR,
    LicencaNaoPermiteError,
    exigir_licenca,
    pode_usar,
)

DATASUS = ("ms", "ms-cnes", "ms-sih-rd-competencia", "ms-sia-pa-competencia")


def test_o_datasus_e_a_unica_fonte_sem_treino():
    assert frozenset({"ms"}) == FONTES_SEM_TREINO


@pytest.mark.parametrize("fonte", DATASUS)
def test_ms_nao_treina(fonte):
    assert pode_usar("treinar", fonte) is False
    with pytest.raises(LicencaNaoPermiteError, match="sem treino"):
        exigir_licenca("treinar", ["cvm-ipe", fonte], onde="amostra")


@pytest.mark.parametrize("fonte", DATASUS)
@pytest.mark.parametrize("uso", ["rotular", "exportar", MOSTRAR])
def test_ms_entra_nos_outros_usos(fonte, uso):
    assert pode_usar(uso, fonte) is True
    exigir_licenca(uso, [fonte], onde="ficha")


def test_sem_treino_olha_a_familia_e_nao_o_comeco_do_nome():
    """O governo de Mato Grosso do Sul (`msestado`) é outra fonte e continua treinando."""
    assert pode_usar("treinar", "msestado") is True
    assert pode_usar("treinar", "msestado-despesas") is True
    assert coletas.sem_treino("ms-cnes") and not coletas.sem_treino("msestado")
