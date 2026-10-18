"""O Streamlit é a versão clássica, em app.tickerlab.com.br/classico/ (plano de 18/10; ADR 0062, Emenda 1).

O caminho vem da variável que o próprio Streamlit lê (`STREAMLIT_SERVER_BASE_URL_PATH`): o compose
a dá ao serviço, a imagem confere a saúde no caminho certo e o app mostra o aviso com a volta ao app
novo. Sem a variável (PC, testes, CI) o app continua na raiz, como sempre.
"""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import classico

RAIZ = Path(__file__).resolve().parents[1]
VARIAVEL = classico.VARIAVEL_DO_CAMINHO_BASE


# --- o caminho (src/classico.py, sem Streamlit) --------------------------------------------
def test_sem_a_variavel_o_app_esta_na_raiz():
    assert classico.caminho_base({}) == ""
    assert classico.esta_no_classico({}) is False
    assert classico.url_da_saude({}) == "http://127.0.0.1:8501/_stcore/health"


def test_com_a_variavel_o_app_esta_em_classico():
    ambiente = {VARIAVEL: "classico"}
    assert classico.caminho_base(ambiente) == "/classico"
    assert classico.esta_no_classico(ambiente) is True
    assert (
        classico.url_da_saude(ambiente)
        == "http://127.0.0.1:8501/classico/_stcore/health"
    )


@pytest.mark.parametrize(
    "valor", ["/classico", "classico/", "/classico/", " classico "]
)
def test_barras_e_espacos_a_mais_na_variavel_nao_mudam_o_caminho(valor):
    assert classico.caminho_base({VARIAVEL: valor}) == "/classico"


def test_variavel_vazia_e_a_raiz():
    assert classico.caminho_base({VARIAVEL: ""}) == ""
    assert classico.caminho_base({VARIAVEL: "/"}) == ""


def test_os_enderecos_das_paginas_levam_o_caminho_base():
    """O tema é guardado por endereço no navegador (src/tema_do_app.py): em /classico, os
    endereços são os de lá."""
    na_raiz = classico.enderecos_das_paginas({})
    assert na_raiz[0] == "/" and "/visao-geral" in na_raiz
    em_classico = classico.enderecos_das_paginas({VARIAVEL: "classico"})
    assert em_classico[0] == "/classico/" and "/classico/visao-geral" in em_classico
    assert len(em_classico) == len(na_raiz)
    assert all(e.startswith("/classico/") for e in em_classico)


# --- o servidor: compose, imagem e CI ------------------------------------------------------
def test_o_compose_poe_o_streamlit_em_classico_e_a_api_nao():
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    app, api = compose.split("  tickerlab-api:")
    assert re.search(rf"^\s+{VARIAVEL}: classico\s*$", app, flags=re.MULTILINE)
    assert VARIAVEL not in api


def test_o_healthcheck_da_imagem_confere_a_saude_no_caminho_base():
    """A imagem roda com a variável no servidor: a saúde está em /classico/_stcore/health lá e
    em /_stcore/health no CI. O caminho vem de um lugar só (src/classico.py)."""
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    healthcheck = dockerfile[dockerfile.index("HEALTHCHECK") :].split("\n\n")[0]
    assert "src.classico" in healthcheck and "url_da_saude" in healthcheck
    assert "_stcore/health" not in healthcheck


def test_o_ci_sobe_a_imagem_na_raiz_e_em_classico():
    ci = (RAIZ / ".github" / "workflows" / "testes.yml").read_text(encoding="utf-8")
    assert f"{VARIAVEL}=classico" in ci
    assert "/classico/_stcore/health" in ci
    assert "8501/_stcore/health" in ci


# --- o app: o aviso da versão clássica -----------------------------------------------------
def _abrir(monkeypatch, em_classico: bool) -> AppTest:
    if em_classico:
        monkeypatch.setenv(VARIAVEL, "classico")
    else:
        monkeypatch.delenv(VARIAVEL, raising=False)
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    return app.run()


def _textos(app: AppTest) -> str:
    return " ".join(m.value for m in app.markdown)


def _script_do_tema(app: AppTest) -> str:
    return " ".join(
        h.proto.body for h in app.get("html") if "TickerLabTemaDoApp" in h.proto.body
    )


def test_em_classico_o_app_avisa_e_leva_ao_app_novo(monkeypatch):
    app = _abrir(monkeypatch, em_classico=True)
    assert not app.exception, [e.value for e in app.exception]
    textos = _textos(app)
    assert "versão clássica" in textos
    assert f"]({classico.ENDERECO_DO_APP_NOVO})" in textos  # o link de volta: a raiz
    assert "/classico/visao-geral" in _script_do_tema(app)


def test_na_raiz_nao_ha_aviso_nem_prefixo(monkeypatch):
    app = _abrir(monkeypatch, em_classico=False)
    assert not app.exception, [e.value for e in app.exception]
    assert "versão clássica" not in _textos(app)
    assert "/classico" not in _script_do_tema(app)
