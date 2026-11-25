"""Mapa tabela -> fontes de coleta (linha 1 do foco "base em dia", 25/11/2026).

O frescor de cada tabela do conector sai da última coleta "ok" das fontes que a alimentam. Estes
testes trancam o mapa: toda tabela consultável tem fontes (ou um motivo escrito para não ter), toda
fonte citada existe de verdade e nenhuma entrada sobra para tabela que não existe mais.
"""

import ast
from functools import lru_cache
from pathlib import Path

import pytest

from base import dossie as regras
from base.arquivo import destinos
from base.arquivo.fontes import FONTES
from base.dicionario import TABELAS
from src import fontes_das_tabelas
from src.fontes_das_tabelas import (
    COLETAS_PROPRIAS,
    DERIVADAS,
    SEM_COLETA_PROPRIA,
    fontes_da_tabela,
)

RAIZ = Path(__file__).resolve().parent.parent
PASTAS_DO_CODIGO = ("base", "scripts", "src")


def _consultaveis() -> list[str]:
    return sorted(nome for nome in TABELAS if regras.pode_consultar(nome))


@lru_cache(maxsize=1)
def _textos_do_codigo() -> frozenset[str]:
    """Todo texto literal dos arquivos de `base/`, `scripts/` e `src/` (onde um id de fonte nasce)."""
    textos: set[str] = set()
    for pasta in PASTAS_DO_CODIGO:
        for arquivo in (RAIZ / pasta).rglob("*.py"):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            textos.update(
                no.value
                for no in ast.walk(arvore)
                if isinstance(no, ast.Constant) and isinstance(no.value, str)
            )
    return frozenset(textos)


def test_toda_tabela_consultavel_tem_fonte_ou_motivo_para_nao_ter():
    sem_nada = [
        nome
        for nome in _consultaveis()
        if not fontes_da_tabela(nome) and nome not in SEM_COLETA_PROPRIA
    ]
    assert sem_nada == [], (
        "tabela do conector sem fonte de coleta no mapa (ponha em `COLETAS_PROPRIAS`, `DERIVADAS` "
        f"ou, com o motivo, em `SEM_COLETA_PROPRIA`): {sem_nada}"
    )


def test_toda_fonte_citada_existe():
    ids_do_arquivista = {fonte.id for fonte in FONTES}
    textos = _textos_do_codigo()
    inexistentes = sorted(
        {
            fonte
            for nome in TABELAS
            for fonte in fontes_da_tabela(nome)
            if fonte not in ids_do_arquivista and fonte not in textos
        }
    )
    assert inexistentes == [], (
        f"fonte citada no mapa que nenhum coletor registra: {inexistentes}"
    )


def test_nao_ha_entrada_para_tabela_que_nao_existe():
    entradas = {*COLETAS_PROPRIAS, *DERIVADAS, *SEM_COLETA_PROPRIA}
    assert sorted(entradas - set(TABELAS)) == []
    # a tabela de um destino do arquivista tampouco pode sumir do dicionário
    do_arquivista = {t for d in destinos.DESTINOS.values() for t in d.tabelas}
    assert sorted(do_arquivista - set(TABELAS)) == []


def test_cada_tabela_tem_uma_origem_so():
    # coleta própria pode somar-se à do arquivista (o coletor diário e o histórico); derivada e
    # "sem coleta própria" não: ou herdam da origem, ou não têm fonte
    do_arquivista = {t for d in destinos.DESTINOS.values() for t in d.tabelas}
    repetidas = sorted(
        {
            *(set(DERIVADAS) & (do_arquivista | set(COLETAS_PROPRIAS))),
            *(
                set(SEM_COLETA_PROPRIA)
                & (do_arquivista | set(COLETAS_PROPRIAS) | set(DERIVADAS))
            ),
        }
    )
    assert repetidas == [], f"tabela em mais de um lugar do mapa: {repetidas}"


def test_o_motivo_de_nao_ter_coleta_propria_e_escrito():
    assert SEM_COLETA_PROPRIA, "a lista não pode ficar vazia sem aviso"
    sem_motivo = [
        nome for nome, motivo in SEM_COLETA_PROPRIA.items() if not motivo.strip()
    ]
    assert sem_motivo == []


def test_tabela_derivada_herda_as_fontes_da_tabela_de_origem():
    # `fre_remuneracao_extremos` sai da `fre_remuneracao`: o frescor dela é o da origem
    assert fontes_da_tabela("fre_remuneracao_extremos") == fontes_da_tabela(
        "fre_remuneracao"
    )
    assert fontes_da_tabela("fre_remuneracao")  # e a origem tem fonte de verdade


def test_derivada_nunca_aponta_para_derivada_nem_para_tabela_sem_fonte():
    for nome, origens in DERIVADAS.items():
        for origem in origens:
            assert origem in TABELAS, f"{nome}: origem {origem} não existe"
            assert origem not in DERIVADAS, f"{nome}: origem {origem} é derivada também"
            assert fontes_da_tabela(origem), f"{nome}: origem {origem} sem fonte"


def test_fonte_do_arquivista_aparece_nas_tabelas_do_destino():
    # `demonstracoes_como_era` é alimentada pelas fontes da CVM de DFP/ITR: o mapa vem do `destinos`
    assert "cvm-hist-dfp" in fontes_da_tabela("demonstracoes_como_era")
    assert "cvm-dfp-itr" in fontes_da_tabela("demonstracoes_como_era")


def test_tabela_desconhecida_nao_tem_fonte():
    assert fontes_da_tabela("tabela_que_nao_existe") == ()


def test_modulo_nao_importa_o_streamlit():
    assert "streamlit" not in Path(fontes_das_tabelas.__file__).read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("nome", sorted(SEM_COLETA_PROPRIA))
def test_tabela_sem_coleta_propria_nao_tem_fonte_no_mapa(nome):
    assert fontes_da_tabela(nome) == ()
