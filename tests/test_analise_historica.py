"""Texto aprovado usa sua entrada original, mesmo depois de o cadastro mudar."""

import dataclasses
import json
from datetime import UTC, datetime

import pytest

from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from src.analise_escrita.exibicao import com_analise
from tests.ajudantes_da_analise import entradas_da_cpfl
from tests.test_analise_graficos_na_tela import (
    CONSUMIDORES,
    MARGEM,
    _guardar,
    _publicada,
)
from tests.test_analise_na_tela import entrada_do_lote


def preparar(pasta):
    _guardar(pasta, _publicada([MARGEM, CONSUMIDORES]))
    caminho = next(pasta.glob("*.json"))
    registro = json.loads(caminho.read_text(encoding="utf-8"))
    registro["entrada_aprovada"] = entrada_do_lote()
    registro["linhagem"] = {"porta3": {"veredito": "aprovado"}}
    return caminho, registro


def gravar(caminho, registro):
    caminho.write_text(json.dumps(registro, ensure_ascii=False), encoding="utf-8")


def entradas_atualizadas():
    entradas = entradas_da_cpfl()
    tickers = entradas.tickers.copy()
    tickers["atualizado_em"] = datetime(2026, 10, 26, tzinfo=UTC)
    return dataclasses.replace(entradas, tickers=tickers)


@pytest.mark.parametrize("plano", ["pro", "gratuito"])
def test_cadastro_novo_preserva_texto_notas_e_graficos_da_entrada_aprovada(
    tmp_path, plano
):
    caminho, registro = preparar(tmp_path)
    gravar(caminho, registro)
    anteriores = entradas_da_cpfl()
    antes = com_analise(re_.montar(anteriores, plano), anteriores, plano, tmp_path)
    atuais = entradas_atualizadas()
    base = re_.montar(atuais, plano)
    depois = com_analise(base, atuais, plano, tmp_path)
    assert depois.analise is not None
    assert depois.analise == antes.analise
    assert dataclasses.replace(depois, analise=None) == base
    assert depois.analise.motivo is None
    assert depois.analise.aviso.startswith(
        "Análise histórica com dados até 17/10/2026."
    )
    assert "dados atuais" in depois.analise.aviso
    assert any(p.origem == "modelo" for p in depois.analise.partes)
    if plano == "pro":
        assert any(
            g.titulo == MARGEM["titulo"] and g.origem == "modelo"
            for g in depois.analise.graficos
        )
    if plano == "gratuito":
        proibidas = {
            li["id"] for li in registro["entrada_aprovada"]["linhas"] if li["so_pro"]
        }
        proibidas -= set(registro["entrada_aprovada"]["obrigatorias"])
        assert not proibidas.intersection(n.id for n in depois.analise.notas)
        assert not any(
            g.titulo == CONSUMIDORES["titulo"] for g in depois.analise.graficos
        )


@pytest.mark.parametrize(
    "defeito",
    ["hash", "cnpj", "corte", "futuro", "pessoa", "reprovada", "formato", "duplicada"],
)
def test_entrada_historica_invalida_nao_mostra_texto_nem_derruba_relatorio(
    tmp_path, defeito
):
    caminho, registro = preparar(tmp_path)
    entrada = registro["entrada_aprovada"]
    if defeito == "hash":
        entrada["empresa"] = "OUTRA EMPRESA"
    elif defeito == "cnpj":
        entrada["cnpj"] = "12.345.678/0001-90"
    elif defeito == "corte":
        entrada["corte"] = "2026-10-18"
    elif defeito == "futuro":
        entrada["linhas"][0]["texto"] = "Cadastro em 26/10/2026"
    elif defeito == "pessoa":
        entrada["linhas"][0]["texto"] = "CFO Maria Souza"
    elif defeito == "reprovada":
        registro["linhagem"]["porta3"]["veredito"] = "reprovado"
    elif defeito == "formato":
        entrada["linhas"] = [None]
    elif defeito == "duplicada":
        entrada["linhas"].append(entrada["linhas"][0])
    if defeito != "hash":
        registro["hash_da_entrada_atual"] = en.hash_da_entrada(entrada)
    gravar(caminho, registro)
    entradas = entradas_da_cpfl()
    base = re_.montar(entradas, "pro")
    assert com_analise(base, entradas, "pro", tmp_path) is base


def test_aviso_da_data_chega_a_api_e_ao_pdf(tmp_path):
    from src.api_v1.esquemas import de_relatorio_da_empresa
    from src.relatorio_empresa_pdf import relatorio_da_empresa
    from tests.test_analise_na_tela import _texto_do_pdf

    caminho, registro = preparar(tmp_path)
    gravar(caminho, registro)
    entradas = entradas_atualizadas()
    relatorio = com_analise(re_.montar(entradas, "pro"), entradas, "pro", tmp_path)
    api = de_relatorio_da_empresa(relatorio)
    assert api.analise is not None
    assert "17/10/2026" in api.analise.aviso
    assert "Análisehistóricacomdadosaté17/10/2026." in _texto_do_pdf(
        relatorio_da_empresa(relatorio)
    )


def test_sem_entrada_original_nao_contorna_trava_de_datas(tmp_path):
    _guardar(tmp_path)
    entradas = entradas_atualizadas()
    base = re_.montar(entradas, "pro")
    assert com_analise(base, entradas, "pro", tmp_path) is base
