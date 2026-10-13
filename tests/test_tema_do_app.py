"""O tema do app (claro, escuro ou automático): a escolha guardada na conta vira o tema que o
Streamlit abre, sem recarregar sem parar e sem depender de detalhe interno que mude sem aviso."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import streamlit
import streamlit.testing.v1

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


def _escolha_efetiva(escolha: str, guardada: bool, no_navegador: str | None) -> str:
    programa = (
        f"const app = require({json.dumps(str(RAIZ / 'static' / 'tema' / 'app.js'))});"
        f"process.stdout.write(JSON.stringify(app.escolhaEfetiva("
        f"{json.dumps(escolha)}, {json.dumps(guardada)}, {json.dumps(no_navegador)})));"
    )
    saida = subprocess.run(
        [NODE, "-e", programa], capture_output=True, text=True, check=True
    )
    return json.loads(saida.stdout)


@precisa_do_node
def test_sem_login_a_escolha_sobrevive_a_recarga():
    """Sem login, a sessão do Streamlit some ao recarregar: vale a escolha guardada no navegador."""
    # a sessão nova não sabe de nada ("auto" de padrão): vale a do navegador
    assert _escolha_efetiva("auto", False, "escuro") == "escuro"
    # a pessoa acabou de escolher, ou a escolha veio da conta: ela manda
    assert _escolha_efetiva("claro", True, "escuro") == "claro"
    # nada guardado em lugar nenhum: o padrão
    assert _escolha_efetiva("auto", False, None) == "auto"
    assert (
        _escolha_efetiva("auto", False, "rosa") == "auto"
    )  # lixo no navegador não vale


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
    html = tema_do_app.script("escuro", ["/", "/visao-geral", "/risco"], guardada=True)
    assert html.startswith("<script>") and html.endswith("</script>")
    assert 'aplicar("escuro", true, ["/", "/visao-geral", "/risco"]' in html
    assert "temaDoMomento" in html  # o sol.js vem junto
    # o Streamlit passa o HTML pelo DOMPurify, que apaga o <script> inteiro se o texto dele tiver
    # "<" seguido de letra, barra ou "!" (até num comentário, como "<página>")
    assert not re.search(r"<[/\w!]", html[len("<script>") : -len("</script>")])
    assert (
        "</script" not in html[len("<script>") : -len("</script>")]
    )  # nada fecha antes da hora


# --- a escolha em Minha conta → Meus dados (tela) ----------------------------------------------
def _script_do_tema(app) -> str:
    return " ".join(
        h.proto.body for h in app.get("html") if "TickerLabTemaDoApp" in h.proto.body
    )


def test_aparencia_em_meus_dados_guarda_a_escolha_na_conta(banco, monkeypatch):
    from src.banco import dados_do_usuario as repo
    from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario

    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("meus_dados")
    escolha = app.button_group(key="escolha_do_tema")
    assert escolha.value == "auto"  # quem nunca escolheu fica no Automático
    with banco.begin() as conexao:  # o que já estava guardado não pode sumir
        repo.salvar_preferencias(conexao, id_do_usuario(banco, "ana"), {"taxa": "CDI"})
    escolha.set_value("escuro").run()
    assert not app.exception
    assert app.session_state["tema_do_app"] == "escuro"
    with banco.connect() as conexao:
        guardadas = repo.carregar_preferencias(conexao, id_do_usuario(banco, "ana"))
    assert guardadas == {"taxa": "CDI", "tema": "escuro"}
    assert 'aplicar("escuro"' in _script_do_tema(app)


def test_a_escolha_da_conta_vale_quando_a_pessoa_volta(banco, monkeypatch):
    from src.banco import dados_do_usuario as repo
    from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario

    entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    abrir_app()  # cria a conta
    with banco.begin() as conexao:
        repo.salvar_preferencias(
            conexao, id_do_usuario(banco, "bia"), {"tema": "claro"}
        )
    app = abrir_app()  # sessão nova
    assert app.session_state["tema_do_app"] == "claro"
    assert 'aplicar("claro"' in _script_do_tema(app)


def test_sem_login_tambem_da_para_escolher(monkeypatch):
    from tests.ajudantes_da_conta import ir_para

    app = streamlit.testing.v1.AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "meus_dados")
    app.button_group(key="escolha_do_tema").set_value("claro").run()
    assert not app.exception
    assert 'aplicar("claro"' in _script_do_tema(app)


def test_tolerancia_da_ficha_fica_guardada_na_conta(banco, monkeypatch):
    from src.banco import dados_do_usuario as repo
    from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario

    entrar_como(monkeypatch, "caio", "caio@exemplo.com")
    app = abrir_app("backtest")
    app.number_input(key="ficha_tolerancia").set_value(20).run()
    assert not app.exception
    with banco.connect() as conexao:
        guardadas = repo.carregar_preferencias(conexao, id_do_usuario(banco, "caio"))
    assert guardadas["tolerancia_de_queda"] == 0.2
    volta = abrir_app("backtest")  # sessão nova
    assert volta.number_input(key="ficha_tolerancia").value == 20
