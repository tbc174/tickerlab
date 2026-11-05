"""O site da TickerLab Data (`site-api/`): em dia com o portão da API, honesto e servido na raiz da API."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.gerar_site_api import DESTINO, catalogo_do_site
from src import api
from src.api_externa.rotas import router

PASTA = Path(__file__).resolve().parent.parent / "site-api"
PAGINAS = (PASTA / "index.html", PASTA / "docs" / "index.html")
SCRIPTS = tuple((PASTA / "estatico").glob("*.js"))


def _texto_publico() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in (*PAGINAS, *SCRIPTS))


def test_catalogo_do_site_esta_em_dia_com_o_portao():
    gravado = json.loads(DESTINO.read_text(encoding="utf-8"))
    assert gravado == json.loads(json.dumps(catalogo_do_site())), (
        "Rode `python -m scripts.gerar_site_api` e faça o commit."
    )


def test_todo_conjunto_e_toda_fonte_do_portao_aparecem_na_documentacao():
    docs = (PASTA / "docs" / "index.html").read_text(encoding="utf-8")
    for conjunto, dono in catalogo_do_site().items():
        assert conjunto in docs
        for fonte in dono["fontes"]:  # type: ignore[attr-defined]
            assert fonte in docs, f"{fonte} falta na tabela de direitos"


def test_numeros_da_cobertura_batem_com_o_codigo():
    html = (PASTA / "index.html").read_text(encoding="utf-8")
    catalogo = catalogo_do_site()
    fontes = {f for dono in catalogo.values() for f in dono["fontes"]}  # type: ignore[attr-defined]
    rotas_de_dado = {
        r.path
        for r in router.routes
        if r.path not in ("/data/v1/catalog", "/data/v1/usage")  # type: ignore[attr-defined]
    }
    assert f'data-conta="conjuntos">{len(catalogo)}<' in html
    assert f'data-conta="fontes">{len(fontes)}<' in html
    assert f'data-conta="rotas">{len(router.routes)}<' in html
    assert len(rotas_de_dado) == len(router.routes) - 2


def test_toda_rota_citada_no_site_existe_na_api():
    existentes = {r.path for r in router.routes}  # type: ignore[attr-defined]
    citadas = set(re.findall(r"/data/v1(?:/[A-Za-z0-9{}/_]+)?", _texto_publico()))
    conhecidas = {c.rstrip("/") for c in citadas}
    normalizadas = {re.sub(r"/\d{14}", "/{cnpj}", c) for c in conhecidas}
    desconhecidas = {
        c
        for c in normalizadas
        if c not in existentes and c != "/data/v1" and not c.endswith("/batch")
    }
    assert not desconhecidas, f"rotas que não existem: {desconhecidas}"
    assert (
        "/data/v1/companies/batch" in existentes
        and "/data/v1/funds/batch" in existentes
    )


@pytest.mark.parametrize(
    "proibido", ["Criar chave", "pip install", "/v1/demonstracoes", "protótipo"]
)
def test_site_nao_promete_o_que_nao_existe(proibido):
    assert proibido not in _texto_publico()


def test_site_nao_promete_rentabilidade():
    texto = _texto_publico().lower()
    for frase in ("rentabilidade garantida", "retorno garantido", "lucro garantido"):
        assert frase not in texto
    assert "recomendação de investimento" in texto


@pytest.fixture
def cliente():
    return TestClient(api.criar_app())


def test_site_e_servido_na_raiz_da_api(cliente):
    assert cliente.get("/").status_code == 200
    assert "TickerLab" in cliente.get("/").text
    assert cliente.get("/docs/").status_code == 200
    assert cliente.get("/docs").status_code == 200
    assert cliente.get("/estatico/api.css").status_code == 200
    fonte = cliente.get("/estatico/Manrope-VariableFont_wght.woff2")
    assert fonte.status_code == 200


def test_o_resto_da_api_segue_igual(cliente, monkeypatch):
    assert cliente.get("/qualquer-coisa").status_code == 404
    assert cliente.get("/qualquer-coisa").json() == {"detail": "Not Found"}
    assert cliente.get("/estatico/../src/api.py").status_code in (400, 404)
    assert cliente.get("/openapi.json").status_code == 404
