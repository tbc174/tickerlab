"""Cobrança com o Stripe (SOMENTE em modo de teste): assinar o Pro, gerenciar e receber eventos.

Duas metades:
- falar com o Stripe: criar a página de pagamento (Checkout) e o portal da assinatura;
- reagir ao que o Stripe conta (webhook): trocar o plano do usuário. Esta parte é idempotente
  (o Stripe repete entregas) e tolera eventos fora de ordem, inclusive no mesmo segundo.

Nenhuma chave fica no código: tudo vem de variáveis de ambiente. A chave secreta precisa ser de
teste (`sk_test_...`); uma chave de produção é recusada de propósito.
"""

import logging
import os
import secrets
import string
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
import stripe

from src.banco.modelo import assinaturas, eventos_stripe, usuarios
from src.banco.usuarios import mudar_plano

log = logging.getLogger(__name__)

VARIAVEL_DA_CHAVE = "STRIPE_SECRET_KEY"
VARIAVEL_DO_SEGREDO_DO_WEBHOOK = "STRIPE_WEBHOOK_SECRET"
VARIAVEL_DO_PRECO = "STRIPE_PRICE_ID"
VARIAVEL_DA_URL = "TICKERLAB_URL_PUBLICA"

STATUS_QUE_DAO_O_PRO = frozenset({"active", "trialing", "past_due"})
# estados finais: o Stripe nunca reativa uma assinatura que chegou a eles
STATUS_ENCERRADOS = frozenset({"canceled", "incomplete_expired"})
PREFIXOS_DE_CHAVE_DE_TESTE = ("sk_test_", "rk_test_")  # secreta ou restrita (preferida)
EVENTOS_DE_CHECKOUT_PAGO = (
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
)
EVENTOS_APENAS_REGISTRADOS = (
    "invoice.paid",
    "invoice.payment_failed",
    "checkout.session.async_payment_failed",
)
EVENTOS_DA_ASSINATURA = (
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
)


class CobrancaIndisponivelError(Exception):
    """A cobrança não está configurada (ou está configurada de forma insegura)."""


@dataclass(frozen=True)
class ConfiguracaoDaCobranca:
    chave_secreta: str
    id_do_preco: str
    url_do_app: str


def ler_configuracao(
    ambiente: Mapping[str, str] | None = None,
) -> ConfiguracaoDaCobranca:
    """Lê e confere a configuração. Levanta `CobrancaIndisponivelError` se algo faltar."""
    ambiente = os.environ if ambiente is None else ambiente
    chave = (ambiente.get(VARIAVEL_DA_CHAVE) or "").strip()
    preco = (ambiente.get(VARIAVEL_DO_PRECO) or "").strip()
    url = (ambiente.get(VARIAVEL_DA_URL) or "").strip().rstrip("/")
    if not chave or not preco or not url:
        raise CobrancaIndisponivelError(
            f"Faltam {VARIAVEL_DA_CHAVE}, {VARIAVEL_DO_PRECO} ou {VARIAVEL_DA_URL}."
        )
    if not chave.startswith(PREFIXOS_DE_CHAVE_DE_TESTE):
        raise CobrancaIndisponivelError(
            "A chave do Stripe precisa ser de TESTE (começa com rk_test_ ou sk_test_). "
            "Este projeto não cobra dinheiro de verdade."
        )
    if not preco.startswith("price_"):
        raise CobrancaIndisponivelError("O preço do Stripe deve começar com price_.")
    if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise CobrancaIndisponivelError(
            "A URL pública do app deve usar HTTPS (ou localhost para testes)."
        )
    return ConfiguracaoDaCobranca(chave, preco, url)


def cobranca_esta_configurada(ambiente: Mapping[str, str] | None = None) -> bool:
    try:
        ler_configuracao(ambiente)
    except CobrancaIndisponivelError:
        return False
    return True


# --- falar com o Stripe -------------------------------------------------------------------
def _cliente(configuracao: ConfiguracaoDaCobranca) -> stripe.StripeClient:
    return stripe.StripeClient(configuracao.chave_secreta)


def _identificador_da_integracao() -> str:
    """Etiqueta das sessões no painel do Stripe: nome fixo + 8 letras aleatórias."""
    sufixo = "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
    return f"tickerlab-pro-{sufixo}"


def criar_pagina_de_pagamento(
    usuario_id: uuid.UUID,
    email: str,
    id_do_cliente: str | None = None,
    configuracao: ConfiguracaoDaCobranca | None = None,
    cliente: stripe.StripeClient | None = None,
) -> str:
    """Cria a sessão do Checkout para assinar o Pro e devolve o endereço dela."""
    configuracao = configuracao or ler_configuracao()
    parametros: dict = {
        "mode": "subscription",
        "line_items": [{"price": configuracao.id_do_preco, "quantity": 1}],
        "client_reference_id": str(usuario_id),
        "success_url": f"{configuracao.url_do_app}/?assinatura=ok",
        "cancel_url": f"{configuracao.url_do_app}/?assinatura=cancelada",
        "subscription_data": {"metadata": {"usuario_id": str(usuario_id)}},
        "allow_promotion_codes": False,
        "integration_identifier": _identificador_da_integracao(),
    }
    if id_do_cliente:
        parametros["customer"] = id_do_cliente
    else:
        parametros["customer_email"] = email
    sessao = (cliente or _cliente(configuracao)).v1.checkout.sessions.create(
        params=parametros
    )
    return sessao.url


def criar_portal_da_assinatura(
    id_do_cliente: str,
    configuracao: ConfiguracaoDaCobranca | None = None,
    cliente: stripe.StripeClient | None = None,
) -> str:
    """Endereço do portal onde a pessoa troca o cartão, vê faturas ou cancela."""
    configuracao = configuracao or ler_configuracao()
    sessao = (cliente or _cliente(configuracao)).v1.billing_portal.sessions.create(
        params={"customer": id_do_cliente, "return_url": f"{configuracao.url_do_app}/"}
    )
    return sessao.url


# --- assinatura de um usuário -------------------------------------------------------------
@dataclass(frozen=True)
class Assinatura:
    usuario_id: uuid.UUID
    stripe_customer_id: str
    stripe_subscription_id: str | None
    status: str
    periodo_fim: datetime | None
    cancela_no_fim: bool


def buscar_assinatura(
    conexao: sa.Connection, usuario_id: uuid.UUID
) -> Assinatura | None:
    linha = conexao.execute(
        sa.select(assinaturas).where(assinaturas.c.usuario_id == usuario_id)
    ).first()
    if linha is None:
        return None
    return Assinatura(
        usuario_id=linha.usuario_id,
        stripe_customer_id=linha.stripe_customer_id,
        stripe_subscription_id=linha.stripe_subscription_id,
        status=linha.status,
        periodo_fim=linha.periodo_fim,
        cancela_no_fim=linha.cancela_no_fim,
    )


def encerrar_cobranca(
    assinatura: Assinatura | None,
    configuracao: ConfiguracaoDaCobranca | None = None,
    cliente: stripe.StripeClient | None = None,
) -> None:
    """Cancela a assinatura e apaga o cliente no Stripe (usado ao apagar a conta).

    Se algo falhar, levanta o erro: quem chama não deve apagar a conta enquanto a cobrança
    continuar existindo. O que já não existe mais no Stripe é tratado como já feito.
    """
    if assinatura is None:
        return
    cliente = cliente or _cliente(configuracao or ler_configuracao())
    if assinatura.stripe_subscription_id and assinatura.status not in (
        "canceled",
        "incomplete_expired",
    ):
        try:
            cliente.v1.subscriptions.cancel(assinatura.stripe_subscription_id)
        except stripe.InvalidRequestError:
            log.info("Assinatura já não existia no Stripe")
    try:
        cliente.v1.customers.delete(assinatura.stripe_customer_id)
    except stripe.InvalidRequestError:
        log.info("Cliente já não existia no Stripe")


# --- receber eventos (webhook) ------------------------------------------------------------
def _de_timestamp(valor: object) -> datetime | None:
    if isinstance(valor, int | float) and not isinstance(valor, bool):
        return datetime.fromtimestamp(valor, UTC)
    return None


def _fim_do_periodo(assinatura: Mapping) -> datetime | None:
    """O fim do período vem na assinatura (API antiga) ou no primeiro item (API nova)."""
    direto = _de_timestamp(assinatura.get("current_period_end"))
    if direto:
        return direto
    itens = (assinatura.get("items") or {}).get("data") or []
    return _de_timestamp(itens[0].get("current_period_end")) if itens else None


def _usuario_existe(conexao: sa.Connection, usuario_id: uuid.UUID) -> bool:
    return (
        conexao.execute(
            sa.select(usuarios.c.id).where(usuarios.c.id == usuario_id)
        ).first()
        is not None
    )


def _como_uuid(valor: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valor))
    except (ValueError, TypeError):
        return None


def _usuario_da_assinatura(
    conexao: sa.Connection, id_do_cliente: str | None, metadados: Mapping | None
) -> uuid.UUID | None:
    """Acha de quem é a assinatura: pelo cliente do Stripe ou pelo id guardado nos metadados."""
    if id_do_cliente:
        linha = conexao.execute(
            sa.select(assinaturas.c.usuario_id).where(
                assinaturas.c.stripe_customer_id == id_do_cliente
            )
        ).first()
        if linha:
            return linha.usuario_id
    candidato = _como_uuid((metadados or {}).get("usuario_id"))
    if candidato and _usuario_existe(conexao, candidato):
        return candidato
    return None


def _motivo_para_ignorar(
    existente: sa.Row, id_da_assinatura: str | None, status: str, criado_em: int
) -> str | None:
    """Por que um evento não deve mudar a assinatura guardada (None = pode aplicar).

    O Stripe não garante a ordem de entrega e o horário do evento vem em segundos: eventos
    diferentes no mesmo segundo podem chegar em qualquer ordem. Por isso o horário sozinho não
    basta: uma assinatura encerrada não volta, e o fim de uma assinatura antiga não tira o Pro
    que a assinatura atual dá.
    """
    if criado_em < existente.evento_em:
        return "mais velho que o último aplicado"
    guardada = existente.stripe_subscription_id
    mesma = id_da_assinatura is not None and id_da_assinatura == guardada
    if (
        mesma
        and existente.status in STATUS_ENCERRADOS
        and status not in STATUS_ENCERRADOS
    ):
        return "a assinatura já foi encerrada e o Stripe não a reativa"
    outra = id_da_assinatura is not None and guardada is not None and not mesma
    if (
        outra
        and existente.status in STATUS_QUE_DAO_O_PRO
        and status not in STATUS_QUE_DAO_O_PRO
    ):
        return "é de outra assinatura e tiraria o Pro que a atual dá"
    return None


def _gravar_assinatura(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    id_do_cliente: str,
    id_da_assinatura: str | None,
    status: str,
    periodo_fim: datetime | None,
    cancela_no_fim: bool | None,
    criado_em: int,
) -> bool:
    """Grava a assinatura se o evento puder mudar a guardada (veja `_motivo_para_ignorar`).

    Devolve se o evento foi aplicado (e, portanto, se o plano deve acompanhar o status).
    """
    existente = conexao.execute(
        sa.select(
            assinaturas.c.evento_em,
            assinaturas.c.status,
            assinaturas.c.stripe_subscription_id,
        ).where(assinaturas.c.usuario_id == usuario_id)
    ).first()
    valores = {
        "stripe_customer_id": id_do_cliente,
        "stripe_subscription_id": id_da_assinatura,
        "status": status,
        "evento_em": criado_em,
        "atualizada_em": datetime.now(UTC),
    }
    # o evento do Checkout não traz o fim do período nem o pedido de cancelamento: None quer
    # dizer "este evento não sabe", e o que já estava guardado fica como está
    if periodo_fim is not None:
        valores["periodo_fim"] = periodo_fim
    if cancela_no_fim is not None:
        valores["cancela_no_fim"] = cancela_no_fim
    if existente is None:
        valores.setdefault("cancela_no_fim", False)
        conexao.execute(sa.insert(assinaturas).values(usuario_id=usuario_id, **valores))
        return True
    motivo = _motivo_para_ignorar(existente, id_da_assinatura, status, criado_em)
    if motivo:
        log.info("Evento do Stripe ignorado: %s", motivo)
        return False
    conexao.execute(
        sa.update(assinaturas)
        .where(assinaturas.c.usuario_id == usuario_id)
        .values(**valores)
    )
    return True


def _acompanhar_o_plano(
    conexao: sa.Connection, usuario_id: uuid.UUID, status: str
) -> None:
    mudar_plano(
        conexao, usuario_id, "pro" if status in STATUS_QUE_DAO_O_PRO else "gratuito"
    )


def _aplicar_checkout_concluido(
    conexao: sa.Connection, sessao: Mapping, criado_em: int
) -> None:
    if sessao.get("mode") != "subscription":
        return
    usuario_id = _como_uuid(sessao.get("client_reference_id"))
    id_do_cliente = sessao.get("customer")
    if not usuario_id or not id_do_cliente or not _usuario_existe(conexao, usuario_id):
        log.warning("Checkout concluído sem usuário ou cliente reconhecível: ignorado")
        return
    pago = sessao.get("payment_status") in ("paid", "no_payment_required")
    status = "active" if pago else "incomplete"
    if _gravar_assinatura(
        conexao,
        usuario_id,
        id_do_cliente,
        sessao.get("subscription"),
        status,
        None,
        None,
        criado_em,
    ):
        _acompanhar_o_plano(conexao, usuario_id, status)


def _aplicar_assinatura(
    conexao: sa.Connection, tipo: str, assinatura: Mapping, criado_em: int
) -> None:
    id_do_cliente = assinatura.get("customer")
    usuario_id = _usuario_da_assinatura(
        conexao, id_do_cliente, assinatura.get("metadata")
    )
    if not usuario_id or not id_do_cliente:
        log.warning("Assinatura do Stripe sem usuário reconhecível: ignorada")
        return
    status = (
        "canceled"
        if tipo == "customer.subscription.deleted"
        else str(assinatura.get("status") or "")
    )
    if not status:
        return
    if _gravar_assinatura(
        conexao,
        usuario_id,
        id_do_cliente,
        assinatura.get("id"),
        status,
        _fim_do_periodo(assinatura),
        bool(assinatura.get("cancel_at_period_end")),
        criado_em,
    ):
        _acompanhar_o_plano(conexao, usuario_id, status)


def processar_evento(conexao: sa.Connection, evento: Mapping) -> str:
    """Aplica um evento do Stripe já verificado. Devolve "aplicado", "duplicado" ou "ignorado".

    Tudo acontece na transação do chamador: se algo falhar, nada fica pela metade e o Stripe
    entrega o evento de novo.
    """
    id_do_evento = str(evento.get("id") or "")
    tipo = str(evento.get("type") or "")
    if not id_do_evento or not tipo:
        raise ValueError("Evento sem id ou tipo.")
    ja_visto = conexao.execute(
        sa.select(eventos_stripe.c.id).where(eventos_stripe.c.id == id_do_evento)
    ).first()
    if ja_visto:
        return "duplicado"
    conexao.execute(sa.insert(eventos_stripe).values(id=id_do_evento, tipo=tipo[:100]))

    objeto = (evento.get("data") or {}).get("object") or {}
    criado_em = int(evento.get("created") or 0)
    if tipo in EVENTOS_DE_CHECKOUT_PAGO:
        _aplicar_checkout_concluido(conexao, objeto, criado_em)
    elif tipo in EVENTOS_DA_ASSINATURA:
        _aplicar_assinatura(conexao, tipo, objeto, criado_em)
    elif tipo in EVENTOS_APENAS_REGISTRADOS:
        # o estado da assinatura chega pelos eventos customer.subscription.*
        log.info("Evento %s registrado", tipo)
        return "ignorado"
    else:
        return "ignorado"
    return "aplicado"
