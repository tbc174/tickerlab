"""Gzip nas respostas da API externa (linha 848): só em `/data/`, só se o cliente pedir, corpo igual."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import api
from src.api_externa import VARIAVEL_DA_CHAVE
from src.api_externa.compressao import TAMANHO_MINIMO, GzipSoNaApiExterna

GRANDE = {"linhas": ["x" * 50] * 200}
PEQUENA = {"ok": True}


def _app_de_prova() -> TestClient:
    app = FastAPI()
    app.add_middleware(GzipSoNaApiExterna)
    app.get("/data/v1/grande")(lambda: GRANDE)
    app.get("/api/data/v1/grande")(lambda: GRANDE)
    app.get("/data/v1/pequena")(lambda: PEQUENA)
    app.get("/api/v1/grande")(lambda: GRANDE)
    return TestClient(app)


def test_resposta_grande_da_api_externa_sai_em_gzip_com_o_mesmo_corpo():
    cliente = _app_de_prova()
    for caminho in ("/data/v1/grande", "/api/data/v1/grande"):
        comprimida = cliente.get(caminho, headers={"Accept-Encoding": "gzip"})
        assert comprimida.headers["content-encoding"] == "gzip"
        assert comprimida.json() == GRANDE  # o cliente descomprime sozinho
        assert int(comprimida.headers["content-length"]) < len(str(GRANDE)) // 5


def test_sem_pedir_gzip_vem_puro():
    resposta = _app_de_prova().get(
        "/data/v1/grande", headers={"Accept-Encoding": "identity"}
    )
    assert "content-encoding" not in resposta.headers
    assert resposta.json() == GRANDE


def test_resposta_pequena_nao_comprime():
    assert len(str(PEQUENA)) < TAMANHO_MINIMO
    resposta = _app_de_prova().get(
        "/data/v1/pequena", headers={"Accept-Encoding": "gzip"}
    )
    assert "content-encoding" not in resposta.headers


def test_fora_da_api_externa_nao_comprime():
    resposta = _app_de_prova().get(
        "/api/v1/grande", headers={"Accept-Encoding": "gzip"}
    )
    assert "content-encoding" not in resposta.headers


def _classes_do_app(ambiente: dict[str, str]) -> list[type]:
    return [m.cls for m in api.criar_app(ambiente).user_middleware]


def test_so_entra_no_app_com_a_api_externa_ligada(banco):
    assert GzipSoNaApiExterna in _classes_do_app({VARIAVEL_DA_CHAVE: "1"})
    assert GzipSoNaApiExterna not in _classes_do_app({})
