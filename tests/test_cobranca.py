"""Testes da cobrança: configuração, páginas do Stripe (simuladas) e eventos do webhook."""

import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
import stripe

from src import cobranca
from src.banco.modelo import assinaturas, eventos_stripe, metadata
from src.banco.usuarios import buscar_por_id, entrar, mudar_plano
from src.cobranca import (
    CobrancaIndisponivelError,
    buscar_assinatura,
    cobranca_esta_configurada,
    criar_pagina_de_pagamento,
    criar_portal_da_assinatura,
    ler_configuracao,
    pode_assinar,
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
        "cus_1",
        configuracao=ler_configuracao(AMBIENTE),
        cliente=cliente,
    )
    assert url == "https://stripe.exemplo/checkout"
    _, p = cliente.chamadas[0]
    assert p["mode"] == "subscription"
    assert p["line_items"] == [{"price": "price_123", "quantity": 1}]
    assert p["client_reference_id"] == str(usuario)
    assert p["subscription_data"]["metadata"]["usuario_id"] == str(usuario)
    # sempre o cliente guardado, nunca customer_email (achado 1b do Codex)
    assert p["customer"] == "cus_1" and "customer_email" not in p
    assert p["success_url"] == "https://servidor.exemplo.ts.net:8443/?assinatura=ok"
    assert "payment_method_types" not in p
    assert p["integration_identifier"].startswith("tickerlab-pro-")
    assert len(p["integration_identifier"]) == len("tickerlab-pro-") + 8


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
        criar_pagina_de_pagamento(uuid.uuid4(), "cus_1")


# --- quem pode assinar (decisão 0029) ---
def test_enquanto_o_pagamento_e_de_teste_so_administrador_assina():
    assert pode_assinar(e_admin=True)
    assert not pode_assinar(e_admin=False)


def test_sem_a_trava_qualquer_conta_assina(monkeypatch):
    monkeypatch.setattr(cobranca, "ASSINATURA_SO_PARA_ADMINS", False)
    assert pode_assinar(e_admin=False)


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


def test_quem_era_plus_volta_ao_plus_quando_o_pro_e_apagado(conexao, ana):
    # N-02 (Master v3; ADR 0025 do autor): ao perder o Pro, volta ao plano de antes
    mudar_plano(conexao, ana.id, "plus")
    processar_evento(conexao, _checkout(ana))
    assert _plano(conexao, ana) == "pro"
    processar_evento(
        conexao, _assinatura("evt_2", "customer.subscription.deleted", "x", 300)
    )
    assert _plano(conexao, ana) == "plus"


def test_quem_era_plus_volta_ao_plus_quando_o_pro_e_cancelado(conexao, ana):
    mudar_plano(conexao, ana.id, "plus")
    processar_evento(conexao, _checkout(ana))
    processar_evento(
        conexao,
        _assinatura("evt_2", "customer.subscription.updated", "canceled", 200),
    )
    assert _plano(conexao, ana) == "plus"


def test_evento_repetido_no_pro_nao_esquece_o_plano_de_antes(conexao, ana):
    mudar_plano(conexao, ana.id, "plus")
    processar_evento(conexao, _checkout(ana))
    atualizada = "customer.subscription.updated"
    processar_evento(conexao, _assinatura("evt_2", atualizada, "active", 200))
    processar_evento(conexao, _assinatura("evt_3", atualizada, "canceled", 300))
    assert _plano(conexao, ana) == "plus"


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


def test_ativo_no_mesmo_segundo_do_cancelamento_nao_reativa_o_pro(conexao, ana):
    # regressão do achado A-02 (Master v3): o empate no segundo deixava passar o "active"
    processar_evento(conexao, _checkout(ana, criado=99))
    criado = "customer.subscription.created"
    processar_evento(conexao, _assinatura("evt_a", criado, "active", 99))
    apagada = "customer.subscription.deleted"
    processar_evento(conexao, _assinatura("evt_b", apagada, "canceled", 100))
    atualizada = "customer.subscription.updated"
    processar_evento(conexao, _assinatura("evt_c", atualizada, "active", 100))
    assert _plano(conexao, ana) == "gratuito"
    assert buscar_assinatura(conexao, ana.id).status == "canceled"


def test_no_mesmo_segundo_em_qualquer_ordem_termina_cancelada(conexao, ana):
    processar_evento(conexao, _checkout(ana, criado=99))
    atualizada = "customer.subscription.updated"
    processar_evento(conexao, _assinatura("evt_c", atualizada, "active", 100))
    apagada = "customer.subscription.deleted"
    processar_evento(conexao, _assinatura("evt_b", apagada, "canceled", 100))
    assert _plano(conexao, ana) == "gratuito"


def test_expirar_uma_assinatura_antiga_nao_tira_o_pro_da_nova(conexao, ana):
    # N-01: um checkout ficou pendente (sub_ana) e a pessoa pagou outro (sub_nova); a
    # pendente expira depois e não pode derrubar o Pro que a nova dá
    processar_evento(conexao, _checkout(ana, criado=100, pagamento="unpaid"))
    criado = "customer.subscription.created"
    processar_evento(
        conexao, _assinatura("evt_2", criado, "active", 150, id="sub_nova")
    )
    assert _plano(conexao, ana) == "pro"
    atualizada = "customer.subscription.updated"
    processar_evento(
        conexao, _assinatura("evt_3", atualizada, "incomplete_expired", 200)
    )
    assert _plano(conexao, ana) == "pro"
    assert buscar_assinatura(conexao, ana.id).stripe_subscription_id == "sub_nova"


def test_assinar_de_novo_depois_de_cancelar_volta_ao_pro(conexao, ana):
    processar_evento(conexao, _checkout(ana, criado=100))
    apagada = "customer.subscription.deleted"
    processar_evento(conexao, _assinatura("evt_2", apagada, "canceled", 200))
    criado = "customer.subscription.created"
    processar_evento(
        conexao, _assinatura("evt_3", criado, "active", 300, id="sub_nova")
    )
    assert _plano(conexao, ana) == "pro"
    assert buscar_assinatura(conexao, ana.id).stripe_subscription_id == "sub_nova"


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


# --- o que a página de planos oferece (o Streamlit e o app novo decidem por aqui) ----------


def _assinatura_ativa(cliente="cus_1"):
    return cobranca.Assinatura(uuid.uuid4(), cliente, "sub_1", "active", None, False)


@pytest.mark.parametrize(
    ("plano", "admin", "assinatura", "configurada", "esperado"),
    [
        ("gratuito", True, None, False, (None, cobranca.AVISO_SEM_COBRANCA)),
        ("gratuito", False, None, True, (None, cobranca.AVISO_DE_PLANOS_EM_BREVE)),
        ("plus", False, None, True, (None, cobranca.AVISO_DE_PLANOS_EM_BREVE)),
        ("gratuito", True, None, True, ("assinar", cobranca.AVISO_DO_PLUS)),
        ("plus", True, None, True, ("assinar", None)),
        ("pro", False, "sim", True, ("gerenciar", None)),
        (
            "pro",
            True,
            None,
            True,
            (None, None),
        ),  # Pro dado por administrador: sem portal
    ],
)
def test_acao_da_assinatura(plano, admin, assinatura, configurada, esperado):
    acao = cobranca.acao_da_assinatura(
        plano, admin, _assinatura_ativa() if assinatura else None, configurada
    )
    assert (acao.tipo, acao.texto) == esperado


def test_pagina_de_pagamento_volta_para_o_caminho_pedido():
    cliente = ClienteFalso()
    criar_pagina_de_pagamento(
        uuid.uuid4(),
        "cus_1",
        configuracao=ler_configuracao(AMBIENTE),
        cliente=cliente,
        caminho_de_volta="/novo/planos",
    )
    _, p = cliente.chamadas[0]
    assert (
        p["success_url"]
        == "https://servidor.exemplo.ts.net:8443/novo/planos?assinatura=ok"
    )
    assert (
        p["cancel_url"]
        == "https://servidor.exemplo.ts.net:8443/novo/planos?assinatura=cancelada"
    )


def test_portal_volta_para_o_caminho_pedido():
    cliente = ClienteFalso()
    criar_portal_da_assinatura(
        "cus_1",
        configuracao=ler_configuracao(AMBIENTE),
        cliente=cliente,
        caminho_de_volta="/novo/planos",
    )
    assert cliente.chamadas[0][1]["return_url"] == (
        "https://servidor.exemplo.ts.net:8443/novo/planos"
    )


# --- achados 1b, 1d e 6b do Codex (ADR 0091): um cliente do Stripe por conta, criado antes ---
class StripeComClientes(ClienteFalso):
    """O cliente falso com clientes e pagamentos abertos (o Checkout que ninguém terminou)."""

    def __init__(self, abertas=()):
        super().__init__()
        self.abertas = list(abertas)
        criar_sessao = self.v1.checkout.sessions.create
        self.v1.checkout.sessions = SimpleNamespace(
            create=criar_sessao, list=self._listar, expire=self._expirar
        )
        self.v1.customers = SimpleNamespace(
            create=self._criar_cliente, delete=self._apagar_cliente
        )
        self.v1.subscriptions = SimpleNamespace(cancel=self._cancelar)

    def _criar_cliente(self, params, options=None):
        self.chamadas.append(("cliente", params, options))
        return SimpleNamespace(id="cus_novo")

    def _listar(self, params):
        self.chamadas.append(("listar", params))
        return SimpleNamespace(data=[SimpleNamespace(id=i) for i in self.abertas])

    def _expirar(self, id_da_sessao):
        self.chamadas.append(("expirar", id_da_sessao))

    def _apagar_cliente(self, id_do_cliente):
        self.chamadas.append(("apagar", id_do_cliente))

    def _cancelar(self, id_da_assinatura):
        self.chamadas.append(("cancelar", id_da_assinatura))

    def do_tipo(self, tipo):
        return [c for c in self.chamadas if c[0] == tipo]


@pytest.fixture
def motor():
    motor = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    sa.event.listen(motor, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    metadata.create_all(motor)
    return motor


def _cadastrar(motor, sub="ana"):
    with motor.begin() as c:
        return entrar(c, sub, f"{sub}@exemplo.com")[0]


def _abrir(motor, usuario, stripe_falso):
    return cobranca.abrir_pagamento(
        motor,
        usuario.id,
        usuario.email,
        configuracao=ler_configuracao(AMBIENTE),
        cliente=stripe_falso,
    )


def test_dois_pagamentos_antes_do_primeiro_webhook_usam_o_mesmo_cliente(motor):
    """1b: sem cliente guardado, cada Checkout criava um cliente (e uma assinatura) novo."""
    ana, stripe_falso = _cadastrar(motor), StripeComClientes()
    _abrir(motor, ana, stripe_falso)
    _abrir(motor, ana, stripe_falso)
    assert len(stripe_falso.do_tipo("cliente")) == 1
    pagamentos = [p for _, p in stripe_falso.do_tipo("checkout")]
    assert [p["customer"] for p in pagamentos] == ["cus_novo", "cus_novo"]
    assert all("customer_email" not in p for p in pagamentos)
    with motor.connect() as c:
        guardada = buscar_assinatura(c, ana.id)
    assert guardada.stripe_customer_id == "cus_novo"
    assert guardada.stripe_subscription_id is None


def test_o_cliente_e_criado_com_o_email_e_uma_chave_de_idempotencia(motor):
    ana, stripe_falso = _cadastrar(motor), StripeComClientes()
    _abrir(motor, ana, stripe_falso)
    _, params, opcoes = stripe_falso.do_tipo("cliente")[0]
    assert params["email"] == "ana@exemplo.com"
    assert params["metadata"] == {"usuario_id": str(ana.id)}
    assert str(ana.id) in opcoes["idempotency_key"]


def test_abrir_um_pagamento_expira_o_que_ficou_aberto(motor):
    """1b: dois Checkouts abertos do mesmo cliente dariam duas assinaturas."""
    ana, stripe_falso = _cadastrar(motor), StripeComClientes(abertas=["cs_velho"])
    _abrir(motor, ana, stripe_falso)
    assert stripe_falso.do_tipo("listar")[0][1] == {
        "customer": "cus_novo",
        "status": "open",
        "limit": 100,
    }
    tipos = [c[0] for c in stripe_falso.chamadas]
    assert stripe_falso.do_tipo("expirar") == [("expirar", "cs_velho")]
    assert tipos.index("expirar") < tipos.index("checkout")


def test_checkout_que_terminou_no_meio_nao_impede_o_novo(motor):
    """Entre listar e expirar, o Checkout aberto pode ter terminado: o Stripe recusa o expire."""
    ana, stripe_falso = _cadastrar(motor), StripeComClientes(abertas=["cs_velho"])

    def expirar_tarde(id_da_sessao):
        raise stripe.InvalidRequestError("Session is not open", "session")

    stripe_falso.v1.checkout.sessions.expire = expirar_tarde
    assert _abrir(motor, ana, stripe_falso)
    assert stripe_falso.do_tipo("checkout")


def test_dois_cliques_ao_mesmo_tempo_guardam_um_cliente_so(motor):
    """O outro clique guardou o cliente entre a leitura e a gravação: segue com o mesmo cliente."""
    ana, stripe_falso = _cadastrar(motor), StripeComClientes()
    criar = stripe_falso.v1.customers.create

    def criar_depois_do_outro_clique(params, options=None):
        criado = criar(params, options)
        with motor.begin() as c:
            c.execute(
                sa.insert(assinaturas).values(
                    usuario_id=ana.id,
                    stripe_customer_id=criado.id,
                    status=cobranca.STATUS_SO_O_CLIENTE,
                    evento_em=0,
                )
            )
        return criado

    stripe_falso.v1.customers.create = criar_depois_do_outro_clique
    _abrir(motor, ana, stripe_falso)
    assert stripe_falso.do_tipo("checkout")[0][1]["customer"] == "cus_novo"
    with motor.connect() as c:
        assert (
            c.execute(sa.select(sa.func.count()).select_from(assinaturas)).scalar() == 1
        )


def test_quem_tem_assinatura_viva_nao_abre_outro_pagamento(motor):
    """1b e 1d: rebaixada pelo administrador, a conta ainda tem a assinatura no Stripe."""
    ana, stripe_falso = _cadastrar(motor), StripeComClientes()
    _abrir(motor, ana, stripe_falso)
    evento = _checkout(ana)
    evento["data"]["object"]["customer"] = "cus_novo"
    with motor.begin() as c:
        processar_evento(c, evento)
        mudar_plano(c, ana.id, "gratuito")
    with pytest.raises(cobranca.AssinaturaJaExisteError):
        _abrir(motor, ana, stripe_falso)
    assert len(stripe_falso.do_tipo("checkout")) == 1


def test_assinatura_encerrada_deixa_assinar_de_novo_com_o_mesmo_cliente(motor):
    ana, stripe_falso = _cadastrar(motor), StripeComClientes()
    _abrir(motor, ana, stripe_falso)
    with motor.begin() as c:
        processar_evento(
            c,
            _assinatura(
                "evt_x", "customer.subscription.deleted", "canceled", 300, "cus_novo"
            ),
        )
    _abrir(motor, ana, stripe_falso)
    assert len(stripe_falso.do_tipo("cliente")) == 1
    assert len(stripe_falso.do_tipo("checkout")) == 2


def test_o_checkout_concluido_completa_o_cliente_guardado(motor):
    ana, stripe_falso = _cadastrar(motor), StripeComClientes()
    _abrir(motor, ana, stripe_falso)
    evento = _checkout(ana)
    evento["data"]["object"]["customer"] = "cus_novo"
    with motor.begin() as c:
        assert processar_evento(c, evento) == "aplicado"
        assert _plano(c, ana) == "pro"
        guardada = buscar_assinatura(c, ana.id)
    assert (guardada.stripe_subscription_id, guardada.status) == ("sub_ana", "active")


def test_apagar_a_conta_antes_do_webhook_apaga_o_cliente_no_stripe(motor):
    """6b: sem nada guardado, apagar a conta não chamava o Stripe e o cliente ficava lá.

    Apagar o cliente no Stripe também cancela as assinaturas dele.
    """
    ana, stripe_falso = _cadastrar(motor), StripeComClientes()
    _abrir(motor, ana, stripe_falso)
    with motor.connect() as c:
        guardada = buscar_assinatura(c, ana.id)
    cobranca.encerrar_cobranca(guardada, cliente=stripe_falso)
    assert stripe_falso.do_tipo("apagar") == [("apagar", "cus_novo")]
    assert stripe_falso.do_tipo("cancelar") == []


def _guardada(status, assinatura="sub_1"):
    return cobranca.Assinatura(uuid.uuid4(), "cus_1", assinatura, status, None, False)


@pytest.mark.parametrize(
    ("plano", "admin", "guardada", "esperado"),
    [
        # 1d: rebaixada pelo administrador, a assinatura viva continua com o portal
        ("gratuito", True, _guardada("active"), ("gerenciar", None)),
        ("plus", False, _guardada("past_due"), ("gerenciar", None)),
        ("gratuito", False, _guardada("incomplete"), ("gerenciar", None)),
        # encerrada: pode assinar de novo
        ("gratuito", True, _guardada("canceled"), ("assinar", cobranca.AVISO_DO_PLUS)),
        ("plus", True, _guardada("incomplete_expired"), ("assinar", None)),
        # só o cliente guardado, sem assinatura ainda
        (
            "gratuito",
            True,
            _guardada("sem_assinatura", None),
            ("assinar", cobranca.AVISO_DO_PLUS),
        ),
        ("pro", True, _guardada("sem_assinatura", None), (None, None)),
        ("pro", False, _guardada("canceled"), ("gerenciar", None)),
    ],
)
def test_acao_com_a_assinatura_guardada(plano, admin, guardada, esperado):
    acao = cobranca.acao_da_assinatura(plano, admin, guardada, True)
    assert (acao.tipo, acao.texto) == esperado
