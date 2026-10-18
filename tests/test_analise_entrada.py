"""A entrada da análise escrita (ADR 0100): a ficha da empresa com um id por número.

O modelo só pode citar o que está aqui, e a porta 1 confere cada frase contra estas linhas.
"""

import dataclasses
import json
from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from src.analise_escrita import numeros
from tests.ajudantes_da_analise import CORTE, entrada_da_cpfl, relatorios_da_cpfl


@pytest.fixture(scope="module")
def entrada() -> dict:
    return entrada_da_cpfl()


def _linhas(entrada: dict) -> dict[str, dict]:
    return {linha["id"]: linha for linha in entrada["linhas"]}


def test_todo_numero_da_ficha_vira_uma_linha_com_id(entrada):
    roe = _linhas(entrada)["retorno.roe"]
    assert roe["tipo"] == "numero"
    assert roe["valor"] == pytest.approx(0.2643, abs=1e-4)
    assert roe["texto"] == "26,4%"
    assert roe["medido_em"] and roe["fonte"]
    assert "mediana" in roe["comparacao"]["texto"]
    com, _ = relatorios_da_cpfl()
    for secao in com.secoes:
        if secao.chave in en.SECOES_FORA:
            continue
        for item in secao.itens:
            assert f"{secao.chave}.{item.chave}" in _linhas(entrada)


def test_linhas_de_tabela_paragrafo_e_ponto_tem_id(entrada):
    linhas = _linhas(entrada)
    controlada = linhas["auditor_e_controladas.controladas.18"]
    assert controlada["tipo"] == "linha"
    assert "CPFL TRANSMISS" in json.dumps(controlada["celulas"], ensure_ascii=False)
    assert linhas["historico.paragrafos.0"]["texto"].startswith("Crescimento composto")
    assert linhas["o_que_os_dados_mostram.pontos.0"]["tipo"] == "ponto"
    assert len(linhas) == len(entrada["linhas"])  # nenhum id repetido


def test_entrada_sem_valuation_nem_preco(entrada):
    texto = json.dumps(entrada, ensure_ascii=False)
    assert not any(linha["secao"] == "valuation" for linha in entrada["linhas"])
    assert "Yahoo" not in texto  # o preço do app é de uso interno


def test_lacunas_da_cpfl(entrada):
    linhas = _linhas(entrada)
    assert entrada["obrigatorias"] == [
        "ficha_tecnica.controlador",
        "lacuna.segmentos",
        "lacuna.concessao",
    ]
    assert linhas["ficha_tecnica.controlador"]["motivo"]
    assert "segmento" in linhas["lacuna.segmentos"]["texto"]
    assert "concess" in linhas["lacuna.concessao"]["texto"]
    crescimento = [i for i in linhas if i.startswith("resultado.crescimento")]
    assert crescimento and all(linhas[i]["motivo"] for i in crescimento)


def test_lacuna_da_concessao_so_nos_setores_de_concessao():
    com, sem = relatorios_da_cpfl()
    varejo = dataclasses.replace(com, setor="Comércio (Atacado e Varejo)")
    entrada = en.entrada_da_ficha(varejo, CORTE, sem_dossie=sem)
    assert "lacuna.concessao" not in _linhas(entrada)
    assert "lacuna.concessao" not in entrada["obrigatorias"]


def test_linhas_do_dossie_sao_so_pro(entrada):
    linhas = _linhas(entrada)
    assert linhas["ofertas_e_fundos.fundos_com_a_acao"]["so_pro"]
    assert linhas["auditor_e_controladas.controladas.18"]["so_pro"]
    assert not linhas["retorno.roe"]["so_pro"]
    assert not linhas["historico.paragrafos.0"]["so_pro"]
    assert not linhas["lacuna.segmentos"]["so_pro"]


def test_sem_a_ficha_sem_dossie_tudo_e_so_pro():
    """Sem a versão de comparação não dá para saber o que é aberto: na dúvida, fecha."""
    com, _ = relatorios_da_cpfl()
    entrada = en.entrada_da_ficha(com, CORTE)
    numeros_da_ficha = [li for li in entrada["linhas"] if li["tipo"] != "lacuna"]
    assert all(li["so_pro"] for li in numeros_da_ficha)


def test_entrada_nao_tem_data_depois_do_corte():
    com, sem = relatorios_da_cpfl()
    with pytest.raises(en.DataDepoisDoCorteError, match="17/10/2026"):
        en.entrada_da_ficha(com, CORTE - timedelta(days=1), sem_dossie=sem)


@settings(max_examples=25, deadline=None)
@given(corte=st.dates(min_value=date(2024, 1, 1), max_value=date(2027, 12, 31)))
def test_nenhuma_data_da_entrada_passa_do_corte(corte):
    com, sem = relatorios_da_cpfl()
    try:
        entrada = en.entrada_da_ficha(com, corte, sem_dossie=sem)
    except en.DataDepoisDoCorteError:
        return
    texto = json.dumps(entrada["linhas"], ensure_ascii=False)
    assert not any(data.depois_de(corte) for data in numeros.datas(texto))


def test_entrada_recusa_pessoa():
    com, sem = relatorios_da_cpfl()
    secoes = [
        *com.secoes,
        re_.Secao("extra", "Extra", paragrafos=["CPF 123.456.789-09"]),
    ]
    with pytest.raises(en.PessoaNaEntradaError):
        en.entrada_da_ficha(
            dataclasses.replace(com, secoes=secoes), CORTE, sem_dossie=sem
        )


def test_hash_estavel(entrada):
    assert en.hash_da_entrada(entrada) == en.hash_da_entrada(entrada_da_cpfl())
    mudada = {**entrada, "corte": "2026-10-16"}
    assert en.hash_da_entrada(mudada) != en.hash_da_entrada(entrada)


def test_entrada_cabe_no_pedido(entrada):
    """~25 mil tokens no plano: a entrada não pode crescer sem a gente ver (custo da 0087)."""
    caracteres = len(json.dumps(entrada, ensure_ascii=False, separators=(",", ":")))
    assert caracteres < 90_000
