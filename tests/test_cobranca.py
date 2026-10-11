"""Testes da cobrança: configuração, páginas do Stripe (simuladas) e eventos do webhook."""

import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from src import cobranca
from src.banco.modelo import eventos_stripe, metadata
from src.banco.usuarios import buscar_por_id, entrar, mudar_plano
from src.cobranca import (
    CobrancaIndisponivelError,
    buscar_assinatura,
    cobranca_esta_configurada,
    criar_pagina_de_pagamento,
    criar_portal_da_assinatura,
    ler_configuracao,
    processar_evento,
)

AMBIENTE = {
    "STRIPE_SECRET_KEY": "sk_test_abc",
    "STRIPE_PRICE_ID": "price_123",
    "TICKERLAB_URL_PUBLICA": "https://servidor.exemplo.ts.net:8443/",
}


# --- configuração ---
def test_configuracao_valida_tira_a_barra_final():
    configuracao = ler_configuracao(AMBIENTE)
    assert configuracao.url_do_app == "https://servidor.exemplo.ts.net:8443"
    assert cobranca_esta_configurada(AMBIENTE)


def test_chave_restrita_de_teste_tambem_vale():
    assert cobranca_esta_configurada({**AMBIENTE, "STRIPE_SECRET_KEY": "rk_test_x"})


@pytest.mark.parametrize("chave", ["sk_live_abc", "rk_live_abc", "abc", ""])
def test_chave_que_nao_e_de_teste_e_recusada(chave):
    with pytest.raises(CobrancaIndisponivelError):
        ler_configuracao({**AMBIENTE, "STRIPE_SECRET_KEY": chave})


@pytest.mark.parametrize("faltando", list(AMBIENTE))
def test_falta_de_variavel_desliga_a_cobranca(faltando):
    ambiente = {k: v for k, v in AMBIENTE.items() if k != faltando}
    assert not cobranca_esta_configurada(ambiente)


def test_preco_e_url_precisam_ter_cara_certa():
    with pytest.raises(CobrancaIndisponivelError, match="price_"):
        ler_configuracao({**AMBIENTE, "STRIPE_PRICE_ID": "prod_1"})
    with pytest.raises(CobrancaIndisponivelError, match="HTTPS"):
        ler_configuracao({**AMBIENTE, "TICKERLAB_URL_PUBLICA": "http://exemplo.com"})
    assert cobranca_esta_configurada(
        {**AMBIENTE, "TICKERLAB_URL_PUBLICA": "http://localhost:8501"}
    )


# --- páginas do Stripe (cliente simulado) ---
class ClienteFalso:
    def __init__(self):
        self.chamadas = []
        self.v1 = SimpleNamespace(
            checkout=SimpleNamespace(sessions=self._sessoes("checkout")),
            billing_portal=SimpleNamespace(sessions=self._sessoes("portal")),
        )

    def _sessoes(self, tipo):
        def criar(params):
            self.chamadas.append((tipo, params))
            return SimpleNamespace(url=f"https://stripe.exemplo/{tipo}")

        return SimpleNamespace(create=criar)


def test_pagina_de_pagamento_leva_o_usuario_e_o_preco():
    cliente, usuario = ClienteFalso(), uuid.uuid4()
    url = criar_pagina_de_pagamento(
        usuario,
        "ana@exemplo.com",
        configuracao=ler_configuracao(AMBIENTE),
        cliente=cliente,
    )
    assert url == "https://stripe.exemplo/checkout"
    _, p = cliente.chamadas[0]
    assert p["mode"] == "subscription"
    assert p["line_items"] == [{"price": "price_123", "quantity": 1}]
    assert p["client_reference_id"] == str(usuario)
    assert p["subscription_data"]["metadata"]["usuario_id"] == str(usuario)
    assert p["customer_email"] == "ana@exemplo.com" and "customer" not in p
    assert p["success_url"] == "https://servidor.exemplo.ts.net:8443/?assinatura=ok"
    assert "payment_method_types" not in p
    assert p["integration_identifier"].startswith("tickerlab-pro-")
    assert len(p["integration_identifier"]) == len("tickerlab-pro-") + 8


def test_quem_ja_e_cliente_reusa_o_cliente_do_stripe():
    cliente = ClienteFalso()
    criar_pagina_de_pagamento(
        uuid.uuid4(),
        "ana@exemplo.com",
        id_do_cliente="cus_1",
        configuracao=ler_configuracao(AMBIENTE),
        cliente=cliente,
    )
    _, p = cliente.chamadas[0]
    assert p["customer"] == "cus_1" and "customer_email" not in p


def test_portal_da_assinatura():
    cliente = ClienteFalso()
    url = criar_portal_da_assinatura(
        "cus_1", configuracao=ler_configuracao(AMBIENTE), cliente=cliente
    )
    assert url == "https://stripe.exemplo/portal"
    assert cliente.chamadas[0][1] == {
        "customer": "cus_1",
        "return_url": "https://servidor.exemplo.ts.net:8443/",
    }


def test_sem_configuracao_nao_cria_pagina(monkeypatch):
    for chave in AMBIENTE:
        monkeypatch.delenv(chave, raising=False)
    with pytest.raises(CobrancaIndisponivelError):
        criar_pagina_de_pagamento(uuid.uuid4(), "a@b.com")


# --- eventos do webhook ---
@pytest.fixture
def conexao():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    with motor.begin() as conexao:
        yield conexao


@pytest.fixture
def ana(conexao):
    return entrar(conexao, "ana", "ana@exemplo.com")[0]


@pytest.fixture
def bia(conexao):
    return entrar(conexao, "bia", "bia@exemplo.com")[0]


def _plano(conexao, usuario):
    return buscar_por_id(conexao, usuario.id).plano


def _checkout(usuario, id_evento="evt_1", criado=100, pagamento="paid"):
    return {
        "id": id_evento,
        "type": "checkout.session.completed",
        "created": criado,
        "data": {
            "object": {
                "mode": "subscription",
                "client_reference_id": str(usuario.id),
                "customer": "cus_ana",
                "subscription": "sub_ana",
                "payment_status": pagamento,
            }
        },
    }


def _assinatura(id_evento, tipo, status, criado, cliente="cus_ana", **extra):
    objeto = {"id": "sub_ana", "customer": cliente, "status": status, **extra}
    return {
        "id": id_evento,
        "type": tipo,
        "created": criado,
        "data": {"object": objeto},
    }


def test_checkout_pago_vira_pro_e_guarda_a_assinatura(conexao, ana):
    assert processar_evento(conexao, _checkout(ana)) == "aplicado"
    assert _plano(conexao, ana) == "pro"
    a = buscar_assinatura(conexao, ana.id)
    assert (a.stripe_customer_id, a.stripe_subscription_id, a.status) == (
        "cus_ana",
        "sub_ana",
        "active",
    )


def test_o_mesmo_evento_duas_vezes_so_vale_uma(conexao, ana):
    assert processar_evento(conexao, _checkout(ana)) == "aplicado"
    mudar_plano(conexao, ana.id, "gratuito")  # se reaplicasse, voltaria a Pro
    assert processar_evento(conexao, _checkout(ana)) == "duplicado"
    assert _plano(conexao, ana) == "gratuito"
    total = conexao.execute(sa.select(sa.func.count()).select_from(eventos_stripe))
    assert total.scalar_one() == 1


def test_pagamento_pendente_nao_libera_o_pro_ate_o_pagamento_assincrono(conexao, ana):
    processar_evento(conexao, _checkout(ana, pagamento="unpaid"))
    assert _plano(conexao, ana) == "gratuito"
    assert buscar_assinatura(conexao, ana.id).status == "incomplete"
    confirmado = _checkout(ana, "evt_2", 110, "paid")
    confirmado["type"] = "checkout.session.async_payment_succeeded"
    processar_evento(conexao, confirmado)
    assert _plano(conexao, ana) == "pro"


@pytest.mark.parametrize(
    ("status", "plano"),
    [
        ("active", "pro"),
        ("trialing", "pro"),
        ("past_due", "pro"),
        ("canceled", "gratuito"),
        ("unpaid", "gratuito"),
        ("incomplete_expired", "gratuito"),
        ("paused", "gratuito"),
    ],
)
def test_o_plano_acompanha_o_status_da_assinatura(conexao, ana, status, plano):
    processar_evento(conexao, _checkout(ana))
    processar_evento(
        conexao,
        _assinatura("evt_2", "customer.subscription.updated", status, 200),
    )
    assert _plano(conexao, ana) == plano


def test_assinatura_apagada_volta_ao_gratuito(conexao, ana):
    processar_evento(conexao, _checkout(ana))
    processar_evento(
        conexao, _assinatura("evt_2", "customer.subscription.deleted", "x", 300)
    )
    assert _plano(conexao, ana) == "gratuito"
    assert buscar_assinatura(conexao, ana.id).status == "canceled"


def test_evento_antigo_que_chega_atrasado_e_ignorado(conexao, ana):
    processar_evento(conexao, _checkout(ana, criado=100))
    processar_evento(
        conexao, _assinatura("evt_novo", "customer.subscription.deleted", "x", 500)
    )
    # um "active" mais velho chega depois do cancelamento: não pode reativar o Pro
    processar_evento(
        conexao,
        _assinatura("evt_velho", "customer.subscription.updated", "active", 300),
    )
    assert _plano(conexao, ana) == "gratuito"
    assert buscar_assinatura(conexao, ana.id).status == "canceled"


def test_fim_do_periodo_na_assinatura_ou_no_item(conexao, ana):
    processar_evento(conexao, _checkout(ana))
    processar_evento(
        conexao,
        _assinatura(
            "evt_2",
            "customer.subscription.updated",
            "active",
            200,
            current_period_end=1_900_000_000,
            cancel_at_period_end=True,
        ),
    )
    a = buscar_assinatura(conexao, ana.id)
    assert a.periodo_fim.year == 2030 and a.cancela_no_fim is True
    processar_evento(
        conexao,
        _assinatura(
            "evt_3",
            "customer.subscription.updated",
            "active",
            300,
            items={"data": [{"current_period_end": 2_000_000_000}]},
        ),
    )
    a = buscar_assinatura(conexao, ana.id)
    assert a.periodo_fim.year == 2033 and a.cancela_no_fim is False


def test_assinatura_antes_do_checkout_usa_os_metadados_como_plano_b(conexao, ana):
    processar_evento(
        conexao,
        _assinatura(
            "evt_1",
            "customer.subscription.created",
            "active",
            90,
            metadata={"usuario_id": str(ana.id)},
        ),
    )
    assert _plano(conexao, ana) == "pro"
    assert buscar_assinatura(conexao, ana.id).stripe_customer_id == "cus_ana"


def test_assinatura_de_desconhecido_e_ignorada_sem_erro(conexao, ana):
    processar_evento(
        conexao,
        _assinatura("evt_1", "customer.subscription.updated", "active", 90, "cus_x"),
    )
    processar_evento(
        conexao,
        _assinatura(
            "evt_2",
            "customer.subscription.updated",
            "active",
            91,
            "cus_y",
            metadata={"usuario_id": str(uuid.uuid4())},
        ),
    )
    assert _plano(conexao, ana) == "gratuito"


def test_evento_de_um_cliente_nao_mexe_no_plano_de_outro(conexao, ana, bia):
    processar_evento(conexao, _checkout(ana))
    mudar_plano(conexao, bia.id, "pro")  # Pro dado por um administrador
    processar_evento(
        conexao, _assinatura("evt_2", "customer.subscription.deleted", "x", 300)
    )
    assert _plano(conexao, ana) == "gratuito"
    assert _plano(conexao, bia) == "pro"


def test_checkout_que_nao_e_assinatura_ou_sem_usuario_e_ignorado(conexao, ana):
    avulso = _checkout(ana)
    avulso["data"]["object"]["mode"] = "payment"
    processar_evento(conexao, avulso)
    sem_usuario = _checkout(ana, "evt_2")
    sem_usuario["data"]["object"]["client_reference_id"] = "lixo"
    processar_evento(conexao, sem_usuario)
    outro = _checkout(ana, "evt_3")
    outro["data"]["object"]["client_reference_id"] = str(uuid.uuid4())
    processar_evento(conexao, outro)
    assert _plano(conexao, ana) == "gratuito"
    assert buscar_assinatura(conexao, ana.id) is None


@pytest.mark.parametrize(
    "tipo", ["invoice.payment_failed", "invoice.paid", "charge.refunded", "outro.tipo"]
)
def test_eventos_sem_efeito_sao_registrados_e_ignorados(conexao, ana, tipo):
    evento = {"id": "evt_1", "type": tipo, "created": 1, "data": {"object": {}}}
    assert processar_evento(conexao, evento) == "ignorado"
    assert processar_evento(conexao, evento) == "duplicado"


@pytest.mark.parametrize("evento", [{}, {"id": "x"}, {"type": "y"}])
def test_evento_sem_id_ou_tipo_e_erro(conexao, evento):
    with pytest.raises(ValueError):
        processar_evento(conexao, evento)


def test_falha_no_meio_nao_deixa_o_evento_marcado_como_visto(monkeypatch):
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    metadata.create_all(motor)
    with motor.begin() as c:
        usuario = entrar(c, "ana", "ana@exemplo.com")[0]

    def quebra(*_a, **_k):
        raise RuntimeError("falhou")

    monkeypatch.setattr(cobranca, "_acompanhar_o_plano", quebra)
    with pytest.raises(RuntimeError), motor.begin() as c:
        processar_evento(c, _checkout(usuario))
    with motor.connect() as c:  # tudo foi desfeito: o Stripe pode entregar de novo
        total = c.execute(sa.select(sa.func.count()).select_from(eventos_stripe))
        assert total.scalar_one() == 0
        assert buscar_assinatura(c, usuario.id) is None


def test_checkout_no_mesmo_segundo_nao_apaga_o_fim_do_periodo(conexao, ana):
    """No pagamento real, a assinatura e o checkout chegam juntos, em qualquer ordem."""
    processar_evento(
        conexao,
        _assinatura(
            "evt_a",
            "customer.subscription.created",
            "active",
            100,
            current_period_end=1_900_000_000,
            cancel_at_period_end=True,
            metadata={"usuario_id": str(ana.id)},
        ),
    )
    processar_evento(conexao, _checkout(ana, "evt_b", criado=100))
    a = buscar_assinatura(conexao, ana.id)
    assert a.periodo_fim is not None and a.periodo_fim.year == 2030
    assert a.cancela_no_fim is True
    assert _plano(conexao, ana) == "pro"


def test_checkout_primeiro_e_assinatura_depois_completa_os_dados(conexao, ana):
    processar_evento(conexao, _checkout(ana, "evt_a", criado=100))
    assert buscar_assinatura(conexao, ana.id).periodo_fim is None
    processar_evento(
        conexao,
        _assinatura(
            "evt_b",
            "customer.subscription.created",
            "active",
            100,
            current_period_end=1_900_000_000,
        ),
    )
    assert buscar_assinatura(conexao, ana.id).periodo_fim.year == 2030
