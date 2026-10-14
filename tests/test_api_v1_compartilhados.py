"""Testes das rotas públicas do link compartilhado (src/api_v1/compartilhados.py, onda 4)."""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src import api
from src import compartilhamentos as regras
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, compartilhados
from src.banco import compartilhamentos as links
from src.banco import dados_do_usuario as repo
from src.banco import pdfs_originais as pdfs
from src.banco.usuarios import entrar, mudar_plano
from tests.ajudantes_da_api import AGORA
from tests.test_compartilhamentos import _congelada

PDF = b"%PDF-1.7 relatorio de exemplo"
NAO_VALE = "Este link não existe ou não vale mais."
CABECALHOS = {
    "cache-control": "no-store",
    "x-robots-tag": "noindex, nofollow",
    "referrer-policy": "no-referrer",
}


@pytest.fixture
def cliente(banco, monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    compartilhados.LIMITE_POR_IP.zerar()
    return TestClient(api.criar_app({VARIAVEL_DA_CHAVE: "1"}))


@pytest.fixture
def ana(banco):
    with banco.begin() as conexao:
        usuario = entrar(conexao, "ana", "ana@exemplo.com", "Ana Souza")[0]
        mudar_plano(conexao, usuario.id, "pro")
    return usuario.id


def _link_da_ficha(banco, usuario_id, dias=30):
    with banco.begin() as conexao:
        return links.criar_link_da_ficha(conexao, usuario_id, "pro", _congelada(), dias)


def _link_do_pdf(banco, usuario_id):
    with banco.begin() as conexao:
        rid = repo.registrar_relatorio(
            conexao, usuario_id, "ativo", titulo="Petrobras em 2026"
        )
        pdfs.guardar_pdf_original(conexao, usuario_id, rid, "pro", PDF, {})
        return links.criar_link_do_pdf(conexao, usuario_id, "pro", rid, 30), rid


def _abrir(cliente, codigo, **kwargs):
    return cliente.post(
        "/api/v1/compartilhados/abrir", json={"codigo": codigo}, **kwargs
    )


def _cabecalhos_de_privacidade(resposta):
    for nome, valor in CABECALHOS.items():
        assert resposta.headers.get(nome) == valor, nome


def test_abrir_a_ficha_sem_login(cliente, banco, ana):
    resposta = _abrir(cliente, _link_da_ficha(banco, ana))
    assert resposta.status_code == 200
    _cabecalhos_de_privacidade(resposta)
    corpo = resposta.json()
    assert corpo["tipo"] == "ficha" and corpo["pdf"] is None
    assert corpo["titulo"] == "Foi sorte? Cruzamento de médias em PETR4"
    ficha = corpo["ficha"]
    assert ficha["ticker"] == "PETR4.SA"
    assert ficha["resultado"] == "não passou"
    assert [c["situacao"] for c in ficha["checagens"]] == [
        "passou", "não se aplica", "não passou", "não deu para medir", "passou",
    ]  # fmt: skip
    assert ficha["calculada_em"].startswith("2026-10-13T23:30")
    assert ficha["texto_do_veredito"].endswith(corpo["aviso"])


def test_resposta_publica_sem_email_nem_nome(cliente, banco, ana):
    for codigo in (_link_da_ficha(banco, ana), _link_do_pdf(banco, ana)[0]):
        texto = json.dumps(_abrir(cliente, codigo).json())
        assert "ana@exemplo.com" not in texto and "Ana Souza" not in texto
        assert str(ana) not in texto


def test_abrir_o_pdf_e_baixar(cliente, banco, ana):
    codigo, _ = _link_do_pdf(banco, ana)
    corpo = _abrir(cliente, codigo).json()
    assert corpo["tipo"] == "pdf" and corpo["ficha"] is None
    assert corpo["pdf"]["tamanho"] == len(PDF)
    assert corpo["pdf"]["nome_do_arquivo"] == "TickerLab-Petrobras-em-2026.pdf"
    resposta = cliente.post("/api/v1/compartilhados/pdf", json={"codigo": codigo})
    assert resposta.status_code == 200
    assert resposta.content == PDF
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["content-disposition"] == (
        'attachment; filename="TickerLab-Petrobras-em-2026.pdf"'
    )
    assert resposta.headers["x-content-type-options"] == "nosniff"
    _cabecalhos_de_privacidade(resposta)


def test_pdf_de_link_de_ficha_da_404(cliente, banco, ana):
    codigo = _link_da_ficha(banco, ana)
    resposta = cliente.post("/api/v1/compartilhados/pdf", json={"codigo": codigo})
    assert resposta.status_code == 404


def test_toda_falha_da_o_mesmo_404(cliente, banco, ana):
    revogado = _link_da_ficha(banco, ana)
    with banco.begin() as conexao:
        (link,) = links.listar_links(conexao, ana)
        links.revogar_link(conexao, ana, link.id)
    sem_pdf, rid = _link_do_pdf(banco, ana)
    with banco.begin() as conexao:
        pdfs.apagar_pdf_original(conexao, ana, rid)
    respostas = [
        _abrir(cliente, revogado),
        _abrir(cliente, sem_pdf),
        _abrir(cliente, regras.novo_codigo()),
        _abrir(cliente, "curto"),
        cliente.post("/api/v1/compartilhados/pdf", json={"codigo": sem_pdf}),
    ]
    for resposta in respostas:
        assert resposta.status_code == 404
        assert resposta.json() == {"detail": NAO_VALE}
        _cabecalhos_de_privacidade(resposta)


def test_vencido_da_404(cliente, banco, ana, monkeypatch):
    codigo = _link_da_ficha(banco, ana, dias=7)
    depois = datetime(2099, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(links, "_agora", lambda: depois)
    assert _abrir(cliente, codigo).status_code == 404


@pytest.mark.parametrize(
    "corpo",
    [{}, {"codigo": 1}, {"codigo": "x" * 65}, {"codigo": "a", "outro": 1}, []],
)
def test_corpo_estranho_da_422(cliente, corpo):
    resposta = cliente.post("/api/v1/compartilhados/abrir", json=corpo)
    assert resposta.status_code == 422


def test_corpo_grande_demais_da_413(cliente):
    resposta = cliente.post(
        "/api/v1/compartilhados/abrir",
        content=json.dumps({"codigo": "x" * 5000}),
        headers={"content-type": "application/json"},
    )
    assert resposta.status_code == 413


def test_limite_por_ip_devolve_429(cliente):
    de_um = {"CF-Connecting-IP": "203.0.113.7"}
    for _ in range(compartilhados.PEDIDOS_POR_MINUTO_POR_IP):
        assert _abrir(cliente, "curto", headers=de_um).status_code == 404
    resposta = _abrir(cliente, "curto", headers=de_um)
    assert resposta.status_code == 429
    _cabecalhos_de_privacidade(resposta)
    outro = {"CF-Connecting-IP": "198.51.100.2"}
    assert _abrir(cliente, "curto", headers=outro).status_code == 404


def test_get_nao_existe(cliente, banco, ana):
    """O código nunca vai no endereço: GET com ele não abre nada."""
    codigo = _link_da_ficha(banco, ana)
    assert (
        cliente.get(f"/api/v1/compartilhados/abrir?codigo={codigo}").status_code == 405
    )


def test_api_v1_desligada_da_404(banco, ana):
    codigo = _link_da_ficha(banco, ana)
    desligada = TestClient(api.criar_app({}))
    assert _abrir(desligada, codigo).status_code == 404


def test_funciona_tambem_sem_o_prefixo_api(cliente, banco, ana):
    codigo = _link_da_ficha(banco, ana)
    resposta = cliente.post("/v1/compartilhados/abrir", json={"codigo": codigo})
    assert resposta.status_code == 200
