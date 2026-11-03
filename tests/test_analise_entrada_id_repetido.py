"""Linha 432: `entrada_da_ficha` com a ficha de exemplo do dia (11 seções, 26/10) e o aviso de id repetido."""

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from src import dossie
from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from tests.ajudantes_da_analise import entradas_da_cpfl
from tests.test_relatorio_empresa_v2 import DIA_DA_FICHA

FICHA_DO_DIA = (
    Path(__file__).parent.parent / "dados_de_exemplo" / "dossie" / "02429144000193.json"
)
CORTE_DO_DIA = date(2026, 10, 26)


def _relatorio_do_dia() -> re_.Relatorio:
    ficha = dossie.ler_ficha(FICHA_DO_DIA)
    assert ficha is not None
    entradas = dataclasses.replace(
        entradas_da_cpfl(),
        dossie=dossie.dossie_da_ficha(dossie.cortar(ficha), DIA_DA_FICHA),
    )
    return re_.montar(entradas, plano="pro")


def test_ficha_do_dia_vira_entrada_sem_id_repetido():
    entrada = en.entrada_da_ficha(_relatorio_do_dia(), CORTE_DO_DIA)
    ids = [linha["id"] for linha in entrada["linhas"]]
    assert len(ids) == len(set(ids))


def test_secao_repetida_na_ficha_diz_quais_ids_repetem(monkeypatch):
    """Duas seções com a mesma chave repetem os ids: o erro nomeia o id, não só diz que repetiu."""
    relatorio = _relatorio_do_dia()
    original = en._linhas_da_ficha

    def com_secao_dobrada(ficha):
        linhas = original(ficha)
        return [*linhas, linhas[0]]

    monkeypatch.setattr(en, "_linhas_da_ficha", com_secao_dobrada)
    with pytest.raises(ValueError, match="id repetido na entrada: .+"):
        en.entrada_da_ficha(relatorio, CORTE_DO_DIA)
