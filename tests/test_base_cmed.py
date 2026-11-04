"""Preços máximos da CMED (base/cmed.py e a fonte `anvisa-cmed`).

As fixtures em `tests/arquivos/cmed/` são recortes reais de 09/10/2026 (1.195 apresentações dos
produtos registrados de uma coorte de CNPJs), com o nome do laboratório trocado. Elas não provam o
universo inteiro (26.635 apresentações de 262 CNPJs): isso só a carga sobre os arquivos completos confere.
"""

import csv
import gzip
import io
from pathlib import Path

import pytest

from base.arquivo import destinos, fontes
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)
from tests.test_base_arquivo_obter import ServidorComTrechos

PASTA = Path(__file__).parent / "arquivos" / "cmed"
ARQUIVOS = {"consumidor": "consumidor.csv.gz", "governo": "governo.csv.gz"}
APRESENTACOES_NA_FIXTURE = 1195


def _bruto(lista: str) -> bytes:
    return gzip.decompress((PASTA / ARQUIVOS[lista]).read_bytes())


def _cabecalho(lista: str) -> list[str]:
    return next(
        csv.reader(io.StringIO(_bruto(lista).decode("utf-8-sig")), delimiter=";")
    )


def _cadastro(lista: str) -> fontes.CsvDeCadastro:
    url = fontes.PRECOS_DA_CMED + fontes.ARQUIVOS_DA_CMED[lista]
    (cadastro,) = [c for c in fontes.CADASTROS_DE_PRECOS_DA_CMED if c.url == url]
    return cadastro


# ---- a fonte no arquivista -------------------------------------------------------------------
def test_a_fonte_pega_as_duas_listas_e_nao_repete_a_consulta_de_medicamentos():
    (fonte,) = [f for f in fontes.FONTES if f.id == "anvisa-cmed"]
    alvos = fonte.descobrir(None, None)  # type: ignore[arg-type]
    assert [a.url for a in alvos] == [
        "https://dados.anvisa.gov.br/dados/TA_PRECO_MEDICAMENTO.csv",
        "https://dados.anvisa.gov.br/dados/TA_PRECO_MEDICAMENTO_GOV.csv",
    ]
    # a consulta de medicamentos já é da `anvisa-produtos`: uma fonte só a coleta
    consultas = [
        f.id
        for f in fontes.FONTES
        if f.id.startswith("anvisa-")
        for a in f.descobrir(None, None)  # type: ignore[arg-type]
        if a.url.endswith("TA_CONSULTA_MEDICAMENTOS.CSV")
    ]
    assert consultas == ["anvisa-produtos"]


def test_a_fonte_tem_licenca_da_anvisa_e_destino_nos_precos():
    assert licenca_da_fonte("anvisa-cmed") != SEM_LICENCA_CONHECIDA
    assert marca_da_fonte("anvisa-cmed") == Marca.VENDAVEL
    assert "cmed_precos" in destinos.DESTINOS["anvisa-cmed"].porque


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_toda_coluna_pedida_existe_no_cabecalho_real(lista):
    # a coleta guarda a interseção: uma coluna renomeada sumiria calada, então o teste pega antes
    cabecalho = _cabecalho(lista)
    faltam = [c for c in _cadastro(lista).colunas if c not in cabecalho]
    assert faltam == []


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_a_lista_tem_o_pf_e_so_o_preco_maximo_dela(lista):
    colunas = _cadastro(lista).colunas
    maximo = fontes.LISTAS_DA_CMED[lista]
    outro = "PMVG" if maximo == "PMC" else "PMC"
    assert set(fontes.colunas_de_preco_da_cmed("PF")) <= set(colunas)
    assert set(fontes.colunas_de_preco_da_cmed(maximo)) <= set(colunas)
    assert not [c for c in colunas if c.startswith(outro)]
    assert len(fontes.colunas_de_preco_da_cmed("PF")) == 26


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_a_coleta_tira_o_laboratorio_e_o_bom_e_guarda_toda_apresentacao(
    lista, tmp_path
):
    cadastro = _cadastro(lista)
    destino = tmp_path / "cmed.csv"
    obter = cadastro.alvo().obter
    assert obter is not None
    obter(ServidorComTrechos({cadastro.url: _bruto(lista)}), destino)
    texto = destino.read_text(encoding="utf-8")
    assert not texto.startswith("﻿")
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    assert len(linhas) == APRESENTACOES_NA_FIXTURE  # todo CNPJ da lista é inteiro
    assert set(linhas[0]) == set(cadastro.colunas)
    assert "LABORATÓRIO" not in linhas[0]
    assert "LABORATORIO DE MENTIRA" not in texto
    # os anos e a coluna vazia de nome instável ficam de fora
    assert not [c for c in linhas[0] if "COMERCIALIZAÇÃO" in c or "DESTINAÇÃO" in c]
