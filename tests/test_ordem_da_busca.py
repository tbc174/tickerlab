"""Ordem dos candidatos da busca pública: a companhia com ação na bolsa vem antes da filial."""

import pytest

from src.ordem_da_busca import Candidata, ordenar

EQUATORIAL = "03.220.438/0001-73"
EQUATORIAL_PARA = "04.895.728/0001-80"
OUTRA_FILIAL = "12.345.678/0001-95"


def test_equatorial_poe_a_listada_antes_da_filial_mesmo_fora_da_ordem_alfabetica():
    linhas = [
        (EQUATORIAL_PARA, "EQUATORIAL PARÁ DISTRIBUIDORA S.A.", "Debêntures"),
        (EQUATORIAL, "EQUATORIAL S.A.", "Ações Ordinárias"),
    ]
    assert [c.cnpj for c in ordenar(linhas)] == [EQUATORIAL, EQUATORIAL_PARA]


def test_sem_companhia_listada_fica_a_ordem_alfabetica_e_nenhuma_e_listada():
    linhas = [
        (OUTRA_FILIAL, "EQUATORIAL MARANHÃO S.A.", "Debêntures"),
        (EQUATORIAL_PARA, "EQUATORIAL PARÁ DISTRIBUIDORA S.A.", "Debêntures"),
    ]
    resultado = ordenar(linhas)
    assert [c.cnpj for c in resultado] == [OUTRA_FILIAL, EQUATORIAL_PARA]
    assert not any(c.listada for c in resultado)


def test_uma_companhia_com_varios_papeis_vira_um_candidato_listado():
    linhas = [
        (EQUATORIAL, "EQUATORIAL S.A.", "Debêntures"),
        (EQUATORIAL, "EQUATORIAL S.A.", "Ações Ordinárias"),
    ]
    assert ordenar(linhas) == [Candidata(EQUATORIAL, "EQUATORIAL S.A.", True)]


@pytest.mark.parametrize("papel", ["Units", "Ações Preferenciais", "BDR Nível 1", ""])
def test_papeis_de_participacao_ou_sem_tipo_contam_como_listada(papel):
    assert ordenar([(EQUATORIAL, "X S.A.", papel)])[0].listada


def test_sem_linhas_nao_ha_candidatos():
    assert ordenar([]) == []
