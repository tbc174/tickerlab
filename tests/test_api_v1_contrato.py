"""O contrato publicado da API v1 (docs/api/openapi-v1.json): a interface nova confia nele."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src import api
from src.api_v1.rotas import openapi_v1

ARQUIVO = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi-v1.json"


def test_o_esquema_publicado_esta_em_dia():
    """Mudou uma rota ou um esquema? Rode `python -m scripts.gerar_openapi` e revise o diff."""
    publicado = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    assert publicado == openapi_v1(), "docs/api/openapi-v1.json está velho"


def test_o_esquema_tem_as_rotas_de_leitura():
    caminhos = set(openapi_v1()["paths"])
    assert caminhos == {
        "/v1/configuracao",
        "/v1/conta",
        "/v1/sair",
        "/v1/sair-de-todos",
        "/v1/entrada/codigo",
        "/v1/entrada/confirmar",
        "/v1/aceite-dos-termos",
        "/v1/eu",
        "/v1/visao-geral",
        "/v1/risco",
        "/v1/retorno-mensal",
        "/v1/comparacao",
        "/v1/backtest",
        "/v1/juros-e-inflacao",
        "/v1/precos-de-referencia",
        "/v1/commodities/cafe/mapa",
        "/v1/linha-do-tempo",
        "/v1/relatorio-empresa",
        "/v1/meu-plano",
        "/v1/links-compartilhados",
        "/v1/revogar-link",
        "/v1/simulacoes",
        "/v1/salvar-simulacao",
        "/v1/apagar-simulacao",
        "/v1/pulse",
        "/v1/meus-dados",
        "/v1/pagamento-da-assinatura",
        "/v1/portal-da-assinatura",
        "/v1/painel-do-cafe",
        "/v1/busca-por-cnpj",
        "/v1/busca-por-cnpj/pdf",
    }


def test_a_documentacao_interativa_continua_fechada_em_producao():
    cliente = TestClient(api.app)
    for caminho in ("/docs", "/redoc", "/openapi.json", "/api/docs"):
        assert cliente.get(caminho).status_code == 404, caminho
