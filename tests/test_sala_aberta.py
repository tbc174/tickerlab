"""A sala de dados deixou de ser só interna (D13 do plano do B-20): as páginas e os textos públicos."""

from pathlib import Path

from src import paginas
from src.conformidade import PASTA_DOS_TEXTOS

FRASE_ANTIGA = "contas internas"


def test_a_pagina_da_sala_nao_e_so_de_administradores():
    pagina = paginas.pagina("sala_de_dados")
    assert not pagina.somente_admin
    assert pagina.grupo != paginas.GRUPO_ADMIN


def test_a_sala_aparece_no_conteudo_do_app_em_react():
    chaves = {
        p["chave"]
        for p in __import__("scripts.exportar_conteudo", fromlist=["_"])._paginas()
    }
    assert "sala_de_dados" in chaves


def test_termos_e_privacidade_nao_dizem_mais_que_a_sala_e_so_interna():
    for nome in ("termos.md", "privacidade.md"):
        texto = Path(PASTA_DOS_TEXTOS, nome).read_text(encoding="utf-8")
        assert FRASE_ANTIGA not in texto, nome
        assert "sala de dados" in texto.lower(), nome


def test_o_site_publicado_tambem_perdeu_a_frase():
    raiz = Path(PASTA_DOS_TEXTOS).parent
    for nome in ("termos.html", "privacidade.html"):
        assert FRASE_ANTIGA not in (raiz / "site" / nome).read_text(encoding="utf-8"), (
            nome
        )
