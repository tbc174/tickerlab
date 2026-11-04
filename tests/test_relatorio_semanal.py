"""O relatório de setor da semana no site (ADR 0109, item 10; fila 210): os números saem do retrato por
conta, o texto cita fonte e data, e o que a base não tem aparece dito."""

import json
import re
from io import BytesIO

from pypdf import PdfReader

from src import apresentacao
from src import relatorio_semanal as semanal
from src import relatorio_semanal_arquivos as arquivos
from src.enderecos_das_fontes import enderecos_da_fonte


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


# --- os arquivos para levar: PDF e deck da página pública (fila 600) -----------------------------


def test_a_pagina_aponta_para_os_tres_arquivos():
    pagina = semanal.para_o_site()
    assert set(pagina["arquivos"]) == {"pdf", "apresentacao_pdf", "apresentacao_pptx"}
    assert all(c.startswith("/relatorio/") for c in pagina["arquivos"].values())


def test_o_pdf_e_o_deck_tem_os_numeros_da_pagina_e_os_limites():
    pagina = semanal.para_o_site()
    momento = semanal.gerado_em_do_retrato()
    deck = apresentacao.do_relatorio_semanal(pagina, momento)
    texto = " ".join(deck.textos())
    maior = pagina["tabelas"][0]["linhas"][0]
    assert maior[0] in texto and maior[1] in texto
    assert pagina["destaques"][0]["fonte"] in texto
    assert deck.slides[-1].titulo.startswith("Limites e cuidados")
    assert "Limites e cuidados" in {s.titulo.split(" (")[0] for s in deck.slides}


def test_os_tres_arquivos_abrem_e_o_pdf_tem_limites_e_cuidados():
    pagina = semanal.para_o_site()
    momento = semanal.gerado_em_do_retrato()
    pdf = arquivos.relatorio_em_pdf(pagina, momento)
    deck_pdf = arquivos.apresentacao_em_pdf_do_relatorio(pagina, momento)
    deck_pptx = arquivos.apresentacao_em_pptx_do_relatorio(pagina, momento)
    assert pdf.startswith(b"%PDF") and deck_pdf.startswith(b"%PDF")
    assert deck_pptx.startswith(b"PK")  # o .pptx é um zip
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    assert "Limites e cuidados" in texto
    assert pagina["tabelas"][0]["linhas"][0][0] in texto
    assert "Limites e cuidados" in " ".join(
        p.extract_text() for p in PdfReader(BytesIO(deck_pdf)).pages
    )


def test_os_arquivos_nao_mudam_a_cada_geracao():
    pagina = semanal.para_o_site()
    momento = semanal.gerado_em_do_retrato()
    assert arquivos.relatorio_em_pdf(pagina, momento) == arquivos.relatorio_em_pdf(
        pagina, momento
    )


def test_o_pptx_nao_muda_com_o_relogio():
    import time

    pagina = semanal.para_o_site()
    momento = semanal.gerado_em_do_retrato()
    primeiro = arquivos.apresentacao_em_pptx_do_relatorio(pagina, momento)
    time.sleep(2)
    assert primeiro == arquivos.apresentacao_em_pptx_do_relatorio(pagina, momento)


def test_o_rodape_cita_as_fontes_do_setor_e_nao_o_yahoo():
    """Linha 602: o rodapé padrão do site dizia "Os dados vêm do Yahoo Finance" no relatório do setor,
    cujos dados são da ANEEL e da CVM. O rodapé sai das fontes dos próprios destaques."""
    pagina = semanal.para_o_site()
    rodape = pagina["aviso_rodape"]
    fontes = " ".join(d["fonte"] for d in pagina["destaques"])
    assert "Yahoo" not in fontes
    assert "Yahoo" not in rodape
    assert "Nada aqui é recomendação de investimento" in rodape
    for orgao, endereco in enderecos_da_fonte(fontes):
        assert orgao in rodape and endereco in rodape
    assert "ANEEL" in rodape and "dados.cvm.gov.br" in rodape


def test_o_rodape_cita_o_yahoo_so_se_uma_fonte_usa_dado_dele(monkeypatch):
    monkeypatch.setattr(
        semanal, "FONTES_DOS_DADOS", ("Yahoo Finance, preços de fechamento",)
    )
    assert "Yahoo Finance" in semanal.para_o_site()["aviso_rodape"]
