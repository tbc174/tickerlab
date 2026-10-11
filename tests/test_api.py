"""Testes da API: saúde e o webhook do Stripe com assinatura de verdade (calculada nos testes)."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from src import api
from src.banco.usuarios import buscar_por_id, entrar

SEGREDO = "whsec_teste"


@pytest.fixture
def cliente(banco, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SEGREDO)
    return TestClient(api.app)


@pytest.fixture
def ana(banco):
    with banco.begin() as conexao:
        return entrar(conexao, "ana", "ana@exemplo.com")[0]


def _assinar(corpo: bytes, segredo: str = SEGREDO, momento: int | None = None) -> str:
    t = int(time.time()) if momento is None else momento
    v1 = hmac.new(segredo.encode(), f"{t}.".encode() + corpo, hashlib.sha256)
    return f"t={t},v1={v1.hexdigest()}"


def _evento(ana, id_evento="evt_1"):
    return {
        "id": id_evento,
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {
            "object": {
                "mode": "subscription",
                "client_reference_id": str(ana.id),
                "customer": "cus_ana",
                "subscription": "sub_ana",
                "payment_status": "paid",
            }
        },
    }


def _enviar(cliente, evento, assinatura=None, rota="/webhooks/stripe"):
    corpo = json.dumps(evento).encode()
    return cliente.post(
        rota,
        content=corpo,
        headers={"stripe-signature": assinatura or _assinar(corpo)},
    )


def _plano(banco, usuario):
    with banco.connect() as conexao:
        return buscar_por_id(conexao, usuario.id).plano


def test_saude_com_banco_ok(banco, cliente):
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200 and resposta.json() == {"status": "ok"}
    assert cliente.get("/api/saude").status_code == 200


def test_saude_com_banco_fora_do_ar(cliente, monkeypatch):
    monkeypatch.setattr(api, "banco_esta_saudavel", lambda: False)
    assert cliente.get("/saude").status_code == 503


def test_webhook_assinado_troca_o_plano(banco, cliente, ana):
    resposta = _enviar(cliente, _evento(ana))
    assert resposta.status_code == 200 and resposta.json() == {"resultado": "aplicado"}
    assert _plano(banco, ana) == "pro"


def test_webhook_tambem_responde_com_o_prefixo_api(banco, cliente, ana):
    resposta = _enviar(cliente, _evento(ana), rota="/api/webhooks/stripe")
    assert resposta.status_code == 200
    assert _plano(banco, ana) == "pro"


def test_entrega_repetida_e_reconhecida(banco, cliente, ana):
    _enviar(cliente, _evento(ana))
    resposta = _enviar(cliente, _evento(ana))
    assert resposta.status_code == 200 and resposta.json() == {"resultado": "duplicado"}


def test_assinatura_falsa_e_recusada_e_nada_muda(banco, cliente, ana):
    corpo = json.dumps(_evento(ana)).encode()
    falsa = _assinar(corpo, segredo="whsec_do_atacante")
    resposta = cliente.post(
        "/webhooks/stripe", content=corpo, headers={"stripe-signature": falsa}
    )
    assert resposta.status_code == 400
    assert _plano(banco, ana) == "gratuito"


def test_sem_cabecalho_de_assinatura_e_recusado(banco, cliente, ana):
    resposta = cliente.post(
        "/webhooks/stripe", content=json.dumps(_evento(ana)).encode()
    )
    assert resposta.status_code == 400
    assert _plano(banco, ana) == "gratuito"


def test_assinatura_velha_demais_e_recusada(banco, cliente, ana):
    corpo = json.dumps(_evento(ana)).encode()
    velha = _assinar(corpo, momento=int(time.time()) - 3600)
    assert _enviar(cliente, _evento(ana), assinatura=velha).status_code == 400
    assert _plano(banco, ana) == "gratuito"


def test_corpo_alterado_depois_de_assinado_e_recusado(banco, cliente, ana):
    original = json.dumps(_evento(ana)).encode()
    assinatura = _assinar(original)
    adulterado = original.replace(b"cus_ana", b"cus_xxx")
    resposta = cliente.post(
        "/webhooks/stripe",
        content=adulterado,
        headers={"stripe-signature": assinatura},
    )
    assert resposta.status_code == 400


def test_sem_segredo_configurado_o_webhook_fica_fora(banco, ana, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    cliente = TestClient(api.app)
    assert _enviar(cliente, _evento(ana)).status_code == 503
    assert _plano(banco, ana) == "gratuito"


def test_corpo_gigante_e_recusado(banco, cliente):
    resposta = cliente.post(
        "/webhooks/stripe",
        content=b"x" * (api.TAMANHO_MAXIMO_DO_CORPO + 1),
        headers={"stripe-signature": "t=1,v1=a"},
    )
    assert resposta.status_code == 413


def test_falha_interna_devolve_500_para_o_stripe_tentar_de_novo(
    banco, cliente, ana, monkeypatch
):
    def quebra(*_a, **_k):
        raise RuntimeError("falhou")

    monkeypatch.setattr(api, "processar_evento", quebra)
    assert _enviar(cliente, _evento(ana)).status_code == 500


def test_a_documentacao_automatica_fica_desligada(cliente):
    for rota in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(rota).status_code == 404
