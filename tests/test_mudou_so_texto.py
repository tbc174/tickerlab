"""O CI só pula a suíte inteira quando a mudança é mesmo só de texto."""

import pytest

from scripts.mudou_so_texto import e_so_texto, mudou_so_texto


@pytest.mark.parametrize(
    "caminho",
    [
        "README.md",
        "CLAUDE.md",
        "trader/CLAUDE.md",
        "notas/erros-e-solucoes.md",
        "docs/padroes-de-codigo.md",
        "docs/imagens/inicio.png",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/erro.yml",
    ],
)
def test_texto_que_ninguem_le_em_execucao(caminho):
    assert e_so_texto(caminho)


@pytest.mark.parametrize(
    "caminho",
    [
        "app.py",
        "src/planos.py",
        "tests/test_planos.py",
        "conteudo/privacidade.md",  # texto do próprio app
        "conteudo/glossario.md",
        "docs/pre-registro-m2-v0.4.md",  # impressão digital conferida pelo trader
        "docs/banner.html",
        ".github/workflows/testes.yml",
        "requirements.txt",
        "scripts/mudou_so_texto.py",
    ],
)
def test_o_resto_roda_a_suite_inteira(caminho):
    assert not e_so_texto(caminho)


def test_um_arquivo_de_codigo_no_meio_do_texto_roda_tudo():
    assert mudou_so_texto(["README.md\n", "notas/python.md\n"])
    assert not mudou_so_texto(["README.md\n", "src/planos.py\n"])


def test_sem_arquivos_roda_tudo():
    assert not mudou_so_texto([])
    assert not mudou_so_texto(["\n", "  "])
