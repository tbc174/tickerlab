"""A amostra aberta do relatório no site, a CPFL Energia (plano do relatório-modelo, 17/10/2026, PR 1,
tarefas 4 e 5): só dado vendável, nenhuma pessoa, os mesmos números no JSON do site e no PDF."""

import json
from pathlib import Path

import pytest

from base import dossie as dossie_da_base
from src import amostra_do_relatorio as amostra
from src import dossie


def _texto_do_pdf(pdf: bytes) -> str:
    import pypdfium2

    documento = pypdfium2.PdfDocument(pdf)
    try:
        paginas = [p.get_textpage().get_text_range() for p in documento]
    finally:
        documento.close()
    return " ".join(" ".join(paginas).split())


def _ficha_alterada(tmp_path: Path, alterar) -> dossie.Ficha:
    bruta = json.loads(dossie.FICHA_DE_EXEMPLO.read_text(encoding="utf-8"))
    alterar(bruta)
    caminho = tmp_path / "ficha.json"
    caminho.write_text(json.dumps(bruta), encoding="utf-8")
    ficha = dossie.ler_ficha(caminho)
    assert ficha is not None
    return ficha


def test_toda_secao_da_amostra_so_usa_tabela_que_pode_ser_mostrada() -> None:
    registro = {s.chave: s for s in dossie_da_base.SECOES}
    for secao in amostra.montar().ficha.secoes:
        assert all(
            dossie_da_base.pode_mostrar(t) for t in registro[secao.chave].tabelas
        )


def test_secao_fora_do_registro_barra_a_amostra(tmp_path: Path) -> None:
    def com_pgfn(bruta: dict) -> None:
        bruta["secoes"].append(
            {
                "chave": "pgfn_divida",
                "titulo": "Dívida ativa",
                "itens": [],
                "tabelas": {},
            }
        )

    with pytest.raises(dossie_da_base.TabelaProibidaError):
        amostra.montar(_ficha_alterada(tmp_path, com_pgfn))


def test_cpf_na_ficha_barra_a_amostra(tmp_path: Path) -> None:
    def com_cpf(bruta: dict) -> None:
        bruta["secoes"][0]["paragrafos"].append("Conselheiro 123.456.789-09")

    with pytest.raises(dossie_da_base.PessoaNaFichaError):
        amostra.montar(_ficha_alterada(tmp_path, com_cpf))


def test_coluna_de_pessoa_na_ficha_barra_a_amostra(tmp_path: Path) -> None:
    def com_administrador(bruta: dict) -> None:
        bruta["secoes"][0]["tabelas"]["controladas"][0]["administrador"] = "Fulano"

    with pytest.raises(dossie_da_base.PessoaNaFichaError):
        amostra.montar(_ficha_alterada(tmp_path, com_administrador))


def test_json_do_site_tem_destaques_secoes_limites_e_a_data() -> None:
    site = amostra.para_o_site()
    assert site["empresa"] == "CPFL Energia"
    assert site["cnpj"] == "02.429.144/0001-93"
    assert site["dados_de"] == "26/10/2026"
    assert site["pdf"] == "/relatorio/exemplo-CPFE3.pdf"
    assert len(site["destaques"]) == 6
    assert [s["chave"] for s in site["secoes"]] == [
        "auditor_e_controladas",
        "qualidade_do_lucro",
        "geracao_de_caixa",
        "ofertas_e_fundos",
        "capital_e_acionistas",
        "governanca",
        "credito",
        "setor_regulado",
        "negocios",
        "insolvencia",
        "rede",
    ]
    assert "nada aqui é recomendação de investimento" in site["aviso"].lower()
    assert site["limites"][0].startswith("Nada aqui é recomendação")


def test_tabela_do_site_traz_colunas_linhas_e_links() -> None:
    negocios = next(
        s for s in amostra.para_o_site()["secoes"] if s["chave"] == "negocios"
    )
    tabela = next(t for t in negocios["tabelas"] if t["chave"] == "negocios")
    assert tabela["titulo"] == "Últimos documentos de negócios"
    assert tabela["colunas"] == [
        "Data",
        "Documento",
        "Assunto, como a empresa escreveu",
    ]
    assert len(tabela["links"]) == len(tabela["linhas"])
    assert tabela["linhas"][0][0] == "02/02/2026"
    fundos = next(
        s for s in amostra.para_o_site()["secoes"] if s["chave"] == "ofertas_e_fundos"
    )
    assert all(t["links"] == [] for t in fundos["tabelas"])


def test_pdf_tem_os_destaques_as_secoes_os_limites_e_as_fontes() -> None:
    site = amostra.para_o_site()
    texto = _texto_do_pdf(amostra.pdf())
    assert "O que a base mostra" in texto
    assert "Limites e cuidados" in texto
    assert "ODbL" in texto
    assert "recomendação de investimento" in texto
    for titulo in ("Auditor e controladas", "Ofertas e fundos", "Setor regulado"):
        assert titulo in texto
    assert "370 fundos tinham papéis da empresa" in texto
    assert site["destaques"][1]["texto"][:40] in texto


def test_pdf_e_o_mesmo_a_cada_geracao() -> None:
    assert amostra.pdf() == amostra.pdf()


def test_rodape_do_pdf_diz_de_onde_vem_o_dado_sem_yahoo() -> None:
    texto = _texto_do_pdf(amostra.pdf())
    assert "Yahoo" not in texto
    assert "Dados entregues à CVM e às agências reguladoras" in texto
