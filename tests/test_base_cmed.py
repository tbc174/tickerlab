"""Preços máximos da CMED (base/cmed.py e a fonte `anvisa-cmed`).

As fixtures em `tests/arquivos/cmed/` são recortes reais de 09/10/2026 (1.195 apresentações dos
produtos registrados de uma coorte de CNPJs), com o nome do laboratório trocado. Elas não provam o
universo inteiro (26.635 apresentações de 262 CNPJs): isso só a carga sobre os arquivos completos confere.
"""

import csv
import gzip
import io
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from base import cmed
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


# ---- a leitura de um retrato (base/cmed.py) --------------------------------------------------
ORENCIA = (
    "1018003900019"  # controle da pesquisa: PF 0% 2123,68; PMVG 0% 1703,40; PMC vazio
)
EVRYSDI = {
    "CNPJ": "33.009.945/0001-23",
    "CÓDIGO GGREM": "529226090029607",
    "REGISTRO": "    -     ",
}


def _linhas(lista: str) -> tuple[list[str], list[dict[str, str]]]:
    texto = _bruto(lista).decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    return list(leitor.fieldnames or []), list(leitor)


def _gravar(tmp_path: Path, cabecalho: list[str], linhas: list[dict[str, str]]) -> Path:
    """Um CSV como a coleta grava (";", UTF-8 sem BOM)."""
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, cabecalho, delimiter=";", extrasaction="ignore")
    escritor.writeheader()
    escritor.writerows(linhas)
    caminho = tmp_path / "cmed.csv"
    caminho.write_text(saida.getvalue(), encoding="utf-8")
    return caminho


def _uma(lista: str, tmp_path: Path, **trocas: str) -> pd.Series:
    """A linha do ORENCIA lida, com as células de `trocas` (nome da fonte com "_" no lugar do espaço)."""
    cabecalho, linhas = _linhas(lista)
    linha = next(l for l in linhas if l["REGISTRO"] == ORENCIA)
    linha.update({k.replace("_", " "): v for k, v in trocas.items()})
    tabela, _ = cmed.ler_retrato(_gravar(tmp_path, cabecalho, [linha]), lista)
    (lida,) = tabela.itertuples(index=False)
    return pd.Series(lida._asdict())


@pytest.mark.parametrize("lista", ARQUIVOS)
def test_controle_do_orencia(lista):
    tabela, contagem = cmed.ler_retrato(PASTA / ARQUIVOS[lista], lista)
    (orencia,) = tabela[tabela["registro"] == ORENCIA].itertuples(index=False)
    assert orencia.pf_0 == Decimal("2123.68")
    assert orencia.pmc_0 is None  # vazio é nulo, nunca zero
    assert orencia.pmvg_0 == (Decimal("1703.40") if lista == "governo" else None)
    assert orencia.registro_produto == ORENCIA[:9]
    assert orencia.id_na_fonte == "56998982000107|505107701157215"
    assert orencia.cnpj == "56.998.982/0001-07"
    assert contagem["linhas"] == APRESENTACOES_NA_FIXTURE
    assert len(tabela) == tabela["id_na_fonte"].nunique() == APRESENTACOES_NA_FIXTURE


def test_pmc_vazio_e_nulo_e_a_contagem_e_de_apresentacoes():
    tabela, contagem = cmed.ler_retrato(PASTA / ARQUIVOS["consumidor"], "consumidor")
    sem_pmc = (
        tabela[[c for c in cmed.PRECOS if c.startswith("pmc_")]].isna().all(axis=1)
    )
    # 94 apresentações sem PMC são 2.444 células vazias: a conta é de apresentações
    assert contagem["sem_pmc"] == int(sem_pmc.sum()) == 94
    assert tabela.loc[sem_pmc, "pf_0"].notna().all()


def test_zero_e_zero_e_o_asterisco_sai_do_numero(tmp_path):
    lida = _uma("governo", tmp_path, **{"PF_0%": "0,00", "PMVG_0_%": "25614,71*"})
    assert lida["pf_0"] == Decimal("0.00")
    assert lida["pmvg_0"] == Decimal("25614.71")
    assert "pmvg_0" in lida["precos_com_asterisco"].split(" / ")
    assert "pf_0" not in lida["precos_com_asterisco"].split(" / ")


def test_texto_que_nao_e_preco_fica_nulo_com_o_texto_guardado(tmp_path):
    lida = _uma("consumidor", tmp_path, **{"PF_0%": "1.234,56", "PF_12_%": "12,345"})
    assert (
        lida["pf_0"] is None and lida["pf_12"] is None
    )  # nunca arredondado nem adivinhado
    assert lida["precos_ilegiveis"] == "pf_0=1.234,56 / pf_12=12,345"


def test_marcas_sim_nao_e_o_resto_nulo(tmp_path):
    lida = _uma("consumidor", tmp_path, CAP="Não", CONFAZ_87="Sim", **{"ICMS_0%": "?"})
    assert lida["cap"] is False and lida["confaz_87"] is True
    assert lida["icms_0"] is None


def test_o_marcador_do_evrysdi_nao_vira_registro(tmp_path):
    cabecalho, linhas = _linhas("consumidor")
    linha = {**linhas[0], **EVRYSDI, "PF 0%": "58405,53", "PMC 0 %": "78348,94"}
    tabela, contagem = cmed.ler_retrato(
        _gravar(tmp_path, cabecalho, [linha]), "consumidor"
    )
    (lida,) = tabela.itertuples(index=False)
    assert lida.registro is None and lida.registro_produto is None
    assert lida.pmc_0 == Decimal("78348.94")
    assert contagem["registro_fora_do_padrao"] == 1


def test_uma_linha_por_apresentacao_qualquer_que_seja_a_ordem(tmp_path):
    cabecalho, linhas = _linhas("consumidor")
    repetida = {**linhas[0], "PF 0%": "1,00"}
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a, _ = cmed.ler_retrato(
        _gravar(tmp_path / "a", cabecalho, [linhas[0], repetida]), "consumidor"
    )
    b, contagem = cmed.ler_retrato(
        _gravar(tmp_path / "b", cabecalho, [repetida, linhas[0]]), "consumidor"
    )
    assert contagem["id_repetido"] == 1
    pd.testing.assert_frame_equal(a, b)


def test_cnpj_que_nao_e_inteiro_nao_entra(tmp_path):
    cabecalho, linhas = _linhas("consumidor")
    mascarado = {**linhas[1], "CNPJ": "***.456.789-**"}
    tabela, contagem = cmed.ler_retrato(
        _gravar(tmp_path, cabecalho, [linhas[0], mascarado]), "consumidor"
    )
    assert len(tabela) == 1 and contagem["cnpj_invalido"] == 1


def test_o_laboratorio_nao_e_lido_e_cada_preco_tem_coluna_propria():
    tabela, _ = cmed.ler_retrato(PASTA / ARQUIVOS["consumidor"], "consumidor")
    assert list(tabela.columns) == [c for c in cmed.COLUNAS if c in tabela.columns]
    assert not [c for c in tabela.columns if "laborat" in c]
    assert (
        len(cmed.PRECOS) == 78
    )  # PF, PMC e PMVG: sem imposto, 0% e 12 alíquotas com e sem ALC
    assert {"pf_17_5_alc", "pmc_sem_impostos", "pmvg_0", "pf_0"} <= set(cmed.PRECOS)


def test_layout_novo_e_avisado(tmp_path):
    cabecalho, linhas = _linhas("governo")
    sem_pmvg = [c for c in cabecalho if not c.startswith("PMVG")]
    with pytest.raises(cmed.LayoutNovo, match="PMVG0"):
        cmed.ler_retrato(_gravar(tmp_path, sem_pmvg, linhas[:3]), "governo")
