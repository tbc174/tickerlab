"""Assinar o Pro e gerenciar a assinatura dentro do app (Stripe simulado)."""

import pytest

from src.banco.usuarios import mudar_papel, mudar_plano
from telas.conta import assinatura as assinatura_na_tela
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario

STRIPE = {
    "STRIPE_SECRET_KEY": "sk_test_abc",
    "STRIPE_PRICE_ID": "price_123",
    "TICKERLAB_URL_PUBLICA": "https://servidor.exemplo.ts.net:8443",
}


@pytest.fixture
def stripe_ligado(monkeypatch):
    for chave, valor in STRIPE.items():
        monkeypatch.setenv(chave, valor)
    chamadas = []

    def pagina(motor, usuario_id, email, **_):
        chamadas.append(("pagamento", usuario_id, email))
        return "https://checkout.stripe.exemplo/sessao"

    def portal(id_do_cliente, **_):
        chamadas.append(("portal", id_do_cliente))
        return "https://portal.stripe.exemplo/sessao"

    # troca onde a tela usa: telas/conta/assinatura.py importa as funções pelo nome, e um módulo
    # importado guarda o que recebeu na primeira vez (o app.py, que roda de novo a cada execução,
    # pegava a troca feita em src.cobranca)
    monkeypatch.setattr(assinatura_na_tela, "abrir_pagamento", pagina)
    monkeypatch.setattr(assinatura_na_tela, "criar_portal_da_assinatura", portal)
    return chamadas


def _rotulos(app):
    return [b.label for b in app.button]


def _links(app):
    """Endereços dos botões de link (o AppTest não tem um acessor para eles)."""
    achados = []

    def percorrer(bloco):
        for filho in bloco.children.values():
            proto = getattr(filho, "proto", None)
            if type(proto).__name__ == "LinkButton":
                achados.append(proto.url)
            if hasattr(filho, "children"):
                percorrer(filho)

    percorrer(app.main)
    return achados


def _textos(app):
    return " ".join([*(i.value for i in app.info), *(c.value for c in app.caption)])


def _entrar_como_admin(monkeypatch, banco, sub, email):
    """Enquanto o pagamento é de teste, só administrador assina (decisão 0029)."""
    entrar_como(monkeypatch, sub, email)
    abrir_app()
    with banco.begin() as conexao:
        mudar_papel(conexao, id_do_usuario(banco, sub), "admin")


def _assinar(banco, sub, cliente="cus_1"):
    """Simula o que o webhook faz: guarda a assinatura e passa o usuário para o Pro."""
    from src.banco.modelo import assinaturas

    usuario = id_do_usuario(banco, sub)
    with banco.begin() as conexao:
        conexao.execute(
            assinaturas.insert().values(
                usuario_id=usuario,
                stripe_customer_id=cliente,
                stripe_subscription_id="sub_1",
                status="active",
                cancela_no_fim=False,
                evento_em=1,
            )
        )
        mudar_plano(conexao, usuario, "pro")


def test_sem_stripe_configurado_nao_oferece_assinatura(banco, monkeypatch):
    for chave in STRIPE:
        monkeypatch.delenv(chave, raising=False)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    assert not app.exception
    assert not [r for r in _rotulos(app) if r.startswith("Assinar")]
    assert "ainda não está disponível" in _textos(app)


def test_gratuito_assina_pelo_convite_de_um_recurso_do_pro(
    banco, stripe_ligado, monkeypatch
):
    _entrar_como_admin(monkeypatch, banco, "ana", "ana@exemplo.com")
    app = abrir_app("pares")
    app.button(key="assinar_recurso_pares").click().run()
    assert not app.exception
    assert _links(app) == ["https://checkout.stripe.exemplo/sessao"]
    tipo, usuario, email = stripe_ligado[0]
    assert (tipo, email) == ("pagamento", "ana@exemplo.com")
    assert usuario == id_do_usuario(banco, "ana")


def test_gratuito_assina_pelo_botao_da_conta(banco, stripe_ligado, monkeypatch):
    _entrar_como_admin(monkeypatch, banco, "ana", "ana@exemplo.com")
    app = abrir_app()
    app.button(key="assinar_conta").click().run()
    assert _links(app) == ["https://checkout.stripe.exemplo/sessao"]


def test_conta_comum_nao_assina_enquanto_o_pagamento_e_de_teste(
    banco, stripe_ligado, monkeypatch
):
    entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    for pagina in (None, "pares", "planos"):
        app = abrir_app(pagina)
        assert not app.exception
        assert not [r for r in _rotulos(app) if r.startswith("Assinar")]
        assert "4242" not in _textos(app)
        assert "em breve" in _textos(app)
    assert stripe_ligado == []


def test_conta_comum_nao_cria_pagamento_mesmo_chamando_a_tela(
    banco, stripe_ligado, monkeypatch
):
    """Defesa em profundidade: sem o botão e também sem a página do Stripe."""
    entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    app = abrir_app()
    usuario = app.session_state["usuario"]
    toasts = []
    monkeypatch.setattr(assinatura_na_tela.st, "toast", toasts.append)
    monkeypatch.setattr(
        assinatura_na_tela.st, "session_state", {"usuario": usuario, "assinatura": None}
    )
    assinatura_na_tela._preparar_link_de_pagamento("conta")
    assert stripe_ligado == []
    assert toasts


def test_assinante_gerencia_pelo_portal_e_nao_ve_assinar(
    banco, stripe_ligado, monkeypatch
):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    _assinar(banco, "ana")
    app = abrir_app()
    assert not app.exception
    assert not [r for r in _rotulos(app) if r.startswith("Assinar")]
    app.button(key="gerenciar_conta").click().run()
    assert _links(app) == ["https://portal.stripe.exemplo/sessao"]
    assert stripe_ligado[0] == ("portal", "cus_1")


def test_rebaixado_pelo_administrador_ainda_gerencia_a_assinatura(
    banco, stripe_ligado, monkeypatch
):
    """Achado 1d do Codex (ADR 0091): a assinatura continua no Stripe depois do rebaixamento."""
    _entrar_como_admin(monkeypatch, banco, "ana", "ana@exemplo.com")
    _assinar(banco, "ana")
    with banco.begin() as conexao:
        mudar_plano(conexao, id_do_usuario(banco, "ana"), "gratuito")
    app = abrir_app()
    assert not app.exception
    assert not [r for r in _rotulos(app) if r.startswith("Assinar")]
    app.button(key="gerenciar_conta").click().run()
    assert _links(app) == ["https://portal.stripe.exemplo/sessao"]


def test_pro_dado_por_administrador_nao_tem_portal(banco, stripe_ligado, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    with banco.begin() as conexao:
        mudar_plano(conexao, id_do_usuario(banco, "ana"), "pro")
    app = abrir_app()
    assert not [r for r in _rotulos(app) if r.startswith("Gerenciar")]
    assert not [r for r in _rotulos(app) if r.startswith("Assinar")]


def test_volta_do_pagamento_mostra_o_aviso_e_atualiza_o_plano(
    banco, stripe_ligado, monkeypatch
):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    assert app.session_state["usuario"].plano == "gratuito"
    _assinar(banco, "ana")  # o webhook chegou
    app.query_params["assinatura"] = "ok"
    app.run()
    assert not app.exception
    assert "Pagamento recebido" in " ".join(s.value for s in app.success)
    assert app.session_state["usuario"].plano == "pro"


def test_pagamento_cancelado_nao_muda_nada(banco, stripe_ligado, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    app.query_params["assinatura"] = "cancelada"
    app.run()
    assert "Nada foi cobrado" in _textos(app)
    assert app.session_state["usuario"].plano == "gratuito"
