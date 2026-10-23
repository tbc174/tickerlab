"""O relatório de setor da semana no site (ADR 0109, item 10; fila 210): os números saem do retrato por
conta, o texto cita fonte e data, e o que a base não tem aparece dito."""

import json
import re

from src import relatorio_semanal as semanal


def _retrato() -> dict:
    return semanal.ler_retrato()


def test_o_retrato_tem_as_nove_companhias_e_o_que_ficou_de_fora():
    retrato = _retrato()
    assert len(retrato["grupos"]) == 9
    assert {d["nome"] for d in retrato["de_fora"]} == {
        "AXIA Energia",
        "AES Elpa",
        "CEB",
    }


def test_a_participacao_de_cada_grupo_e_consumidores_sobre_o_total_do_pais():
    pagina = semanal.para_o_site()
    tabela = next(t for t in pagina["tabelas"] if t["chave"] == "consumidores")
    retrato = _retrato()
    maior = max(retrato["grupos"], key=lambda g: g["consumidores"])
    esperado = f"{maior['consumidores'] / retrato['total_do_pais'] * 100:.1f}".replace(
        ".", ","
    )
    assert tabela["linhas"][0][2] == f"{esperado}%"


def test_a_tabela_vem_ordenada_do_maior_para_o_menor():
    tabela = next(
        t for t in semanal.para_o_site()["tabelas"] if t["chave"] == "consumidores"
    )
    numeros = [int(linha[1].replace(".", "")) for linha in tabela["linhas"]]
    assert numeros == sorted(numeros, reverse=True)


def test_o_destaque_das_quatro_maiores_soma_as_quatro_primeiras_linhas():
    retrato = _retrato()
    quatro = sorted(g["consumidores"] for g in retrato["grupos"])[-4:]
    esperado = (
        f"{sum(quatro) / retrato['total_do_pais'] * 100:.1f}".replace(".", ",") + "%"
    )
    assert esperado in semanal.para_o_site()["destaques"][1]["titulo"]


def test_todo_destaque_tem_fonte_e_data():
    for d in semanal.para_o_site()["destaques"]:
        assert d["fonte"] and d["data"]
        assert "ODbL" in d["fonte"]


def test_auditor_com_data_futura_fica_fora_do_peso_mas_aparece_avisado():
    pagina = semanal.para_o_site()
    retrato = _retrato()
    futuras = [g for g in retrato["grupos"] if g["auditor_desde"] > retrato["dados_de"]]
    assert futuras, "o retrato da semana 1 tem a Neoenergia com data futura"
    por_auditor = next(t for t in pagina["tabelas"] if t["chave"] == "peso_por_auditor")
    assert sum(int(linha[1]) for linha in por_auditor["linhas"]) == 9 - len(futuras)
    de_cada = next(t for t in pagina["tabelas"] if t["chave"] == "auditor_de_cada")
    assert sum("data futura" in linha[2] for linha in de_cada["linhas"]) == len(futuras)


def test_o_que_falta_nao_leva_jargao_de_planejamento():
    texto = json.dumps(semanal.para_o_site()["nao_temos"], ensure_ascii=False)
    assert "mesa" not in texto and "série" not in texto and "tabela " not in texto
    assert semanal.para_o_site()["nao_temos"]


def test_a_pagina_nao_recomenda_nem_promete_nada():
    texto = json.dumps(semanal.para_o_site(), ensure_ascii=False).lower()
    assert "não é recomendação" in texto or "nada aqui é recomendação" in texto
    for proibida in ("compre", "venda", "recomendamos", "vai subir", "oportunidade"):
        assert not re.search(rf"\b{proibida}\b", texto)


def test_a_pagina_nao_cita_pessoa_nem_cpf():
    texto = json.dumps(semanal.para_o_site(), ensure_ascii=False)
    assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto)


def test_os_limites_dizem_o_que_ficou_de_fora():
    limites = " ".join(semanal.para_o_site()["limites"])
    for nome in ("AXIA Energia", "AES Elpa", "CEB"):
        assert nome in limites
