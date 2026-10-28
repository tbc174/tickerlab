"""A rota do radar exige a conta e não busca dados na internet."""

import json

from fastapi.testclient import TestClient

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE
from src.api_v1.acesso import conta_com_acesso
from tests.test_radar_imobiliario import (
    dados_radar,  # noqa: F401 - fixture compartilhada
)


def test_radar_sem_conta_nao_expoe_dados(monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    cliente = TestClient(api.criar_app({VARIAVEL_DA_CHAVE: "1"}))
    assert cliente.get("/api/v1/radar-imobiliario").status_code == 401


def test_radar_validado_filtros_e_indisponibilidade(dados_radar, tmp_path, monkeypatch):  # noqa: F811 - fixture importada
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    arquivo = tmp_path / "radar.json"
    monkeypatch.setenv("TICKERLAB_RADAR_IMOBILIARIO", str(arquivo))
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    app.dependency_overrides[conta_com_acesso] = lambda: object()
    cliente = TestClient(app)
    rota = "/api/v1/radar-imobiliario"
    assert cliente.get(rota).status_code == 503
    arquivo.write_text(json.dumps(dados_radar), encoding="utf-8")
    resposta = cliente.get(rota, params={"cidade": "SP", "recorte": "todos"})
    assert resposta.status_code == 200
    assert resposta.json()["serie"][-1]["localizadas"] == 12
    assert cliente.get(rota, params={"cidade": "XXX"}).status_code == 422
    assert cliente.get(rota, params={"recorte": "../segredo"}).status_code == 422
