"""A rota `POST /v1/busca-por-cnpj` (molde B, PR 2): login, CNPJ errado, plano, fora da base e log."""

import logging

import pytest

from src.banco.usuarios import mudar_plano
from tests import test_api_v1_rotas as rotas
from tests.test_busca_por_cnpj import PETROBRAS, _gravar_ficha

chave = rotas.chave  # as fixtures da conta logada, as mesmas dos outros testes da API
cliente = rotas.cliente
ROTA = "/api/v1/busca-por-cnpj"


@pytest.fixture
def pasta_das_fichas(banco, tmp_path, monkeypatch):
    from tests.test_fundamentos_no_app import _coletar

    _coletar(banco)
    monkeypatch.setenv("TICKERLAB_DOSSIES", str(tmp_path))
    return _gravar_ficha(tmp_path)


def _como_pro(banco) -> None:
    with banco.begin() as conexao:
        mudar_plano(conexao, rotas._id_da_ana_no(banco), "pro")


def test_api_busca_encontrada(cliente, banco, pasta_das_fichas) -> None:
    _como_pro(banco)
    resposta = cliente.post(ROTA, json={"cnpj": "33.000.167/0001-01"})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["situacao"] == "encontrada" and dados["cnpj"] == "33.000.167/0001-01"
    assert "PETR4" in dados["tickers"] and dados["como_era_em"] == "2026-10-17"
    chaves = [s["chave"] for s in dados["secoes"]]
    assert chaves[:3] == ["cadastro", "auditor_e_controladas", "rede"]
    assert all(not s["trancada"] for s in dados["secoes"])
    assert dados["limites"] and dados["desligado"] and dados["fontes"]
    rede = dados["secoes"][2]
    assert rede["tabelas"][0]["linhas"][0][1] == "CPFL Paulista"


def test_api_do_gratuito_vem_trancada(cliente, pasta_das_fichas) -> None:
    resposta = cliente.post(ROTA, json={"cnpj": PETROBRAS})
    assert resposta.status_code == 200
    dados = resposta.json()
    trancadas = [s for s in dados["secoes"] if s["trancada"]]
    assert trancadas and dados["secoes"][0]["trancada"] is False
    assert "CPFL Paulista" not in resposta.text


def test_api_fora_da_base_aberta(cliente, pasta_das_fichas) -> None:
    resposta = cliente.post(ROTA, json={"cnpj": "11222333000181"})
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["situacao"] == "fora_da_base_aberta" and dados["secoes"] == []
    assert dados["avisos"] and dados["desligado"] and dados["limites"]


@pytest.mark.parametrize("cnpj", ["33000167000102", "abc", "", "1" * 400])
def test_api_cnpj_invalido_422(cliente, pasta_das_fichas, cnpj) -> None:
    resposta = cliente.post(ROTA, json={"cnpj": cnpj})
    assert resposta.status_code == 422
    assert cnpj[:6] not in resposta.text or cnpj in ("", "abc")


def test_api_sem_corpo_422(cliente) -> None:
    assert cliente.post(ROTA, json={}).status_code == 422


def test_api_sem_login_401(cliente) -> None:
    resposta = cliente.post(
        ROTA, json={"cnpj": PETROBRAS}, headers={"Authorization": ""}
    )
    assert resposta.status_code == 401


def test_cnpj_pedido_nao_vai_para_o_log(cliente, pasta_das_fichas, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        cliente.post(ROTA, json={"cnpj": PETROBRAS})
        cliente.post(ROTA, json={"cnpj": "11.222.333/0001-81"})
        cliente.post(ROTA, json={"cnpj": "33000167000102"})
    todo = " ".join(r.getMessage() for r in caplog.records)
    for trecho in ("33000167", "33.000.167", "11222333", "11.222.333"):
        assert trecho not in todo
    assert "busca por cnpj" in todo.lower()  # só a contagem (encontrada/fora)
