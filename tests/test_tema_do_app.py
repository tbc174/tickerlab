"""O tema do app (claro, escuro ou automático): a escolha guardada na conta vira o tema que o
Streamlit abre, sem recarregar sem parar e sem depender de detalhe interno que mude sem aviso."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import streamlit

from src import tema_do_app

RAIZ = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
precisa_do_node = pytest.mark.skipif(NODE is None, reason="Node não instalado")


def _decidir(escolha: str, instante: str, ativo: str, ja_recarregou: str | None):
    programa = (
        f"const sol = require({json.dumps(str(RAIZ / 'static' / 'tema' / 'sol.js'))});"
        f"const app = require({json.dumps(str(RAIZ / 'static' / 'tema' / 'app.js'))});"
        f"const r = app.decidir({json.dumps(escolha)}, new Date({json.dumps(instante)}),"
        f' "America/Sao_Paulo", {json.dumps(ativo)}, {json.dumps(ja_recarregou)}, sol);'
        "process.stdout.write(JSON.stringify(r));"
    )
    saida = subprocess.run(
        [NODE, "-e", programa], capture_output=True, text=True, check=True
    )
    return json.loads(saida.stdout)


MEIO_DIA = "2026-10-13T15:00:00Z"  # 12h em São Paulo
NOITE = "2026-10-14T02:00:00Z"  # 23h em São Paulo


@precisa_do_node
@pytest.mark.parametrize(
    ("escolha", "instante", "tema"),
    [
        ("claro", NOITE, "claro"),
        ("escuro", MEIO_DIA, "escuro"),
        ("auto", MEIO_DIA, "claro"),
        ("auto", NOITE, "escuro"),
    ],
)
def test_a_escolha_vira_o_tema_do_streamlit(escolha, instante, tema):
    r = _decidir(escolha, instante, ativo=tema, ja_recarregou=None)
    assert r["tema"] == tema
    assert r["valorDoStreamlit"] == ("Dark" if tema == "escuro" else "Light")
    assert r["recarregar"] is False  # já está no tema certo


@precisa_do_node
def test_recarrega_uma_vez_so_quando_o_tema_e_outro():
    """Risco do plano: recarregar sem parar. Uma vez por sessão do navegador, e só se precisar."""
    assert _decidir("escuro", MEIO_DIA, ativo="claro", ja_recarregou=None)["recarregar"]
    # já recarregou para o escuro nesta aba e o Streamlit não mudou: não tenta de novo
    assert not _decidir("escuro", MEIO_DIA, ativo="claro", ja_recarregou="escuro")[
        "recarregar"
    ]
    # a pessoa mudou de ideia: pode recarregar para o novo tema
    assert _decidir("claro", MEIO_DIA, ativo="escuro", ja_recarregou="escuro")[
        "recarregar"
    ]


def test_o_streamlit_guarda_o_tema_onde_o_script_escreve():
    """Risco do plano: o Streamlit mudar a chave numa atualização. Aqui o CI quebra antes."""
    pasta = Path(streamlit.__file__).parent / "static" / "static" / "js"
    codigo = "".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in pasta.glob("*.js")
    )
    assert "stActiveTheme-${window.location.pathname}" in codigo
    versao = re.search(
        r"var \w+=(\d+),\w+=`stActiveTheme-\$\{window\.location\.pathname\}`", codigo
    )
    assert versao and int(versao.group(1)) == tema_do_app.VERSAO_DA_CHAVE_DO_STREAMLIT


def test_escolha_desconhecida_vira_automatico():
    assert tema_do_app.normalizar("claro") == "claro"
    assert tema_do_app.normalizar("escuro") == "escuro"
    for estranha in (None, "", "rosa", 3, "AUTO"):
        assert tema_do_app.normalizar(estranha) == "auto"


def test_o_script_leva_a_escolha_as_paginas_e_o_calculo_do_sol():
    html = tema_do_app.script("escuro", ["/", "/visao-geral", "/risco"])
    assert html.startswith("<script>") and html.endswith("</script>")
    assert '"escuro"' in html and '["/", "/visao-geral", "/risco"]' in html
    assert "temaDoMomento" in html  # o sol.js vem junto
    assert (
        "</script" not in html[len("<script>") : -len("</script>")]
    )  # nada fecha antes da hora
