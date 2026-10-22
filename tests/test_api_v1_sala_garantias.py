"""As rotas das garantias e exposições (src/api_v1/sala_garantias.py, B-17 PR 2).

Mesmo ambiente de `test_api_v1_sala_trabalho.py`. O que estes testes travam: o guarda da sala (sem
sessão 401, sem ser admin 404); operação de outra conta ou inexistente dá 404 igual, sem dado da
outra conta no corpo; a cobertura da rota é a mesma de `garantias.cobertura_da_exposicao`.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.banco import garantias
from src.banco.usuarios import entrar, mudar_papel
from src.conformidade import registrar_aceite
from tests.ajudantes_da_api import AGORA, da_sessao

D = Decimal
OPERACAO = {"tipo": "credito", "nome": "CCB da Alfa", "prazo_em_dias": 180}


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    acesso.LIMITE.zerar()


@pytest.fixture
def app():
    return api.criar_app({VARIAVEL_DA_CHAVE: "1"})


def _conta(banco, app, sub, admin=True):
    with banco.begin() as conexao:
        usuario = entrar(conexao, sub, f"{sub}@exemplo.com", sub.title())[0]
        registrar_aceite(conexao, usuario.id)
        if admin:
            mudar_papel(conexao, usuario.id, "admin")
    return TestClient(app, headers=da_sessao(banco, usuario)), usuario


@pytest.fixture
def ana(banco, app):
    return _conta(banco, app, "ana")


@pytest.fixture
def bia(banco, app):
    return _conta(banco, app, "bia")


def _operacao_com_garantia(banco, cliente, dono):
    operacao_id = uuid.UUID(cliente.post("/v1/operacoes", json=OPERACAO).json()["id"])
    with banco.begin() as conexao:
        exposicao = garantias.registrar_exposicao(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao_id,
            rotulo="Segredo da Alfa",
            valor=D("500"),
            moeda="BRL",
        )
        assert exposicao is not None
        garantia = garantias.registrar_garantia(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao_id,
            exposicao_id=exposicao.id,
            tipo="imovel",
            valor_avaliado=D("1000"),
            moeda="BRL",
            avaliado_em=date(2026, 10, 1),
            haircut=D("0.30"),
            liquidez="baixa",
            valido_ate=date(2099, 1, 1),
        )
        assert garantia is not None
    return operacao_id, exposicao, garantia


def test_a_cobertura_da_rota_e_a_do_calculo(banco, ana):
    cliente, dono = ana
    operacao_id, exposicao, _ = _operacao_com_garantia(banco, cliente, dono)
    with banco.connect() as conexao:
        esperada = garantias.cobertura_da_exposicao(
            conexao,
            usuario_id=dono.id,
            operacao_id=operacao_id,
            exposicao_id=exposicao.id,
        )
    resposta = cliente.get(f"/v1/operacoes/{operacao_id}/exposicoes")
    assert resposta.status_code == 200
    (item,) = resposta.json()
    assert item["id"] == str(exposicao.id)
    assert D(item["valor"]) == D("500")
    assert item["cobertura"] == esperada
    assert D(item["cobertura"]["cobertura"]) == D("1.4")  # 1000 x 0,70 / 500


def test_lista_as_garantias_e_filtra_por_exposicao(banco, ana):
    cliente, dono = ana
    operacao_id, _, garantia = _operacao_com_garantia(banco, cliente, dono)
    (item,) = cliente.get(f"/v1/operacoes/{operacao_id}/garantias").json()
    assert item["id"] == str(garantia.id)
    assert D(item["haircut"]) == D("0.30") and item["titular_ref"] is None
    filtrada = cliente.get(
        f"/v1/operacoes/{operacao_id}/garantias",
        params={"exposicao_id": str(uuid.uuid4())},
    )
    assert filtrada.status_code == 200 and filtrada.json() == []


@pytest.mark.parametrize("fim", ["garantias", "exposicoes"])
def test_operacao_de_outra_conta_ou_inexistente_da_o_mesmo_404(banco, ana, bia, fim):
    cliente, dono = ana
    operacao_id, *_ = _operacao_com_garantia(banco, cliente, dono)
    de_outra = bia[0].get(f"/v1/operacoes/{operacao_id}/{fim}")
    inexistente = bia[0].get(f"/v1/operacoes/{uuid.uuid4()}/{fim}")
    assert de_outra.status_code == inexistente.status_code == 404
    assert de_outra.json() == inexistente.json()
    corpo = de_outra.text
    assert "Segredo da Alfa" not in corpo and str(operacao_id) not in corpo


@pytest.mark.parametrize("fim", ["garantias", "exposicoes"])
def test_guarda_da_sala(banco, app, ana, fim):
    cliente, dono = ana
    operacao_id, *_ = _operacao_com_garantia(banco, cliente, dono)
    caminho = f"/v1/operacoes/{operacao_id}/{fim}"
    assert TestClient(app).get(caminho).status_code == 401
    comum, _ = _conta(banco, app, "carla", admin=False)
    assert comum.get(caminho).status_code == 404
