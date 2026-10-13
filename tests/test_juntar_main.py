"""Juntar a main num ramo (scripts/juntar_main.py): conflito em pasta gerada se refaz; conflito em
código para e pede uma pessoa."""

from scripts import juntar_main as jm


def test_pastas_geradas_sao_reconhecidas_nos_dois_jeitos_de_barra():
    assert jm.e_gerado("novo/assets/index-Cl1Ejl3O.js")
    assert jm.e_gerado("site\\index.html")
    assert jm.e_gerado("web/conteudo/paginas.json")
    assert not jm.e_gerado("web/src/App.tsx")  # o código do React não é gerado
    assert not jm.e_gerado("src/paginas.py")


def test_conflito_em_codigo_para_e_em_gerado_nao():
    conflitos = [
        "novo/index.html",
        "site/produto.html",
        "src/paginas.py",
        "tests/test_x.py",
    ]
    assert jm.conflitos_fora_dos_gerados(conflitos) == [
        "src/paginas.py",
        "tests/test_x.py",
    ]
    assert jm.conflitos_fora_dos_gerados(["novo/index.html"]) == []


def test_os_geradores_cobrem_as_tres_pastas():
    comandos = [" ".join(c) for c, _ in jm.GERADORES]
    assert any("exportar_conteudo" in c for c in comandos)  # web/conteudo/
    assert (
        any("gerar_site" in c for c in comandos) and "npm run site" in comandos
    )  # site/
    assert "npm run app" in comandos  # novo/
