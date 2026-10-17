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
# a conta já tem o cliente no Stripe (criado antes do primeiro Checkout), mas nenhuma assinatura
STATUS_SO_O_CLIENTE = "sem_assinatura"
PREFIXOS_DE_CHAVE_DE_TESTE = ("sk_test_", "rk_test_")  # secreta ou restrita (preferida)
# decisão 0029: com o login aberto a qualquer conta Google e o pagamento ainda de teste, qualquer
# pessoa viraria Pro com o cartão de teste; até a cobrança real, só administradores assinam
ASSINATURA_SO_PARA_ADMINS = True
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


class AssinaturaJaExisteError(Exception):
    """A conta já tem uma assinatura que não terminou: vai ao portal, não assina de novo."""


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


def pode_assinar(e_admin: bool) -> bool:
    """A trava da decisão 0029: enquanto o pagamento é de teste, só administradores assinam."""
    return not ASSINATURA_SO_PARA_ADMINS or e_admin


# --- o que a página de planos oferece (o Streamlit e o app novo mostram o mesmo) -----------
AVISO_SEM_COBRANCA = "A assinatura do plano Pro ainda não está disponível."
AVISO_DE_PLANOS_EM_BREVE = "Os planos pagos chegam em breve."
AVISO_DO_PLUS = "Plano Plus: a assinatura chega em breve."
NOTA_DO_CARTAO_DE_TESTE = (
    "Modo de teste: use o cartão 4242 4242 4242 4242, qualquer data futura."
)
RETORNO_DO_PAGAMENTO_OK = (
    "Pagamento recebido! O plano muda assim que o Stripe confirmar, em poucos segundos."
)
RETORNO_DO_PAGAMENTO_CANCELADO = "Pagamento cancelado. Nada foi cobrado."
PLANOS_QUE_ASSINAM_O_PRO = ("gratuito", "plus")


@dataclass(frozen=True)
class AcaoDaAssinatura:
    tipo: str | None  # "assinar", "gerenciar" ou None (nenhum botão)
    texto: str | None  # a frase que acompanha (ou explica a falta do botão)


def acao_da_assinatura(
    plano: str,
    e_admin: bool,
    assinatura: "Assinatura | None",
    configurada: bool,
) -> AcaoDaAssinatura:
    """Qual botão a página de planos mostra: assinar o Pro, gerenciar no portal ou nenhum.

    Quem tem uma assinatura que não terminou gerencia, em qualquer plano: o administrador pode ter
    rebaixado a conta, e a assinatura continua no Stripe (achado 1d do Codex, ADR 0091).
    """
    if not configurada:
        return AcaoDaAssinatura(None, AVISO_SEM_COBRANCA)
    if tem_assinatura_viva(assinatura):
        return AcaoDaAssinatura("gerenciar", None)
    if plano in PLANOS_QUE_ASSINAM_O_PRO:
        if not pode_assinar(e_admin):
            return AcaoDaAssinatura(None, AVISO_DE_PLANOS_EM_BREVE)
        return AcaoDaAssinatura(
            "assinar", AVISO_DO_PLUS if plano == "gratuito" else None
        )
    if assinatura is not None and assinatura.status != STATUS_SO_O_CLIENTE:
        return AcaoDaAssinatura("gerenciar", None)  # no portal ficam as faturas antigas
    return AcaoDaAssinatura(None, None)


def tem_assinatura_viva(assinatura: "Assinatura | None") -> bool:
    """Há uma assinatura no Stripe que ainda não chegou a um estado final."""
    return (
        assinatura is not None
        and assinatura.stripe_subscription_id is not None
        and assinatura.status not in STATUS_ENCERRADOS
    )


# --- falar com o Stripe -------------------------------------------------------------------
def _cliente(configuracao: ConfiguracaoDaCobranca) -> stripe.StripeClient:
    return stripe.StripeClient(configuracao.chave_secreta)


def _identificador_da_integracao() -> str:
    """Etiqueta das sessões no painel do Stripe: nome fixo + 8 letras aleatórias."""
    sufixo = "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
    return f"tickerlab-pro-{sufixo}"


def abrir_pagamento(
    motor: sa.Engine,
    usuario_id: uuid.UUID,
    email: str,
    configuracao: ConfiguracaoDaCobranca | None = None,
    cliente: stripe.StripeClient | None = None,
    caminho_de_volta: str = "/",
) -> str:
    """O caminho inteiro até o Checkout: confere, garante o cliente, fecha o pagamento aberto.

    Achado 1b do Codex (ADR 0091): sem cliente guardado, dois Checkouts abertos antes do primeiro
    webhook criavam dois clientes e duas assinaturas, e apagar a conta só encerrava a última. Agora
    a conta tem um cliente só, criado e guardado antes do primeiro Checkout; cada Checkout novo
    expira o que ficou aberto; e quem já tem assinatura viva vai ao portal, não assina de novo.
    """
    configuracao = configuracao or ler_configuracao()
    cliente = cliente or _cliente(configuracao)
    with motor.connect() as conexao:
        guardada = buscar_assinatura(conexao, usuario_id)
    if tem_assinatura_viva(guardada):
        raise AssinaturaJaExisteError("Esta conta já tem uma assinatura.")
    if guardada is not None:
        id_do_cliente = guardada.stripe_customer_id
    else:
        id_do_cliente = _criar_cliente(motor, usuario_id, email, cliente)
    _expirar_pagamentos_abertos(id_do_cliente, cliente)
    return criar_pagina_de_pagamento(
        usuario_id, id_do_cliente, configuracao, cliente, caminho_de_volta
    )


def _criar_cliente(
    motor: sa.Engine,
    usuario_id: uuid.UUID,
    email: str,
    cliente: stripe.StripeClient,
) -> str:
    """Cria o cliente no Stripe e o guarda já (status `sem_assinatura`).

    Guardado antes do pagamento, ele é apagado junto com a conta mesmo que o webhook ainda não
    tenha chegado (achado 6b): apagar o cliente no Stripe também cancela as assinaturas dele. A
    chave de idempotência faz dois cliques ao mesmo tempo receberem o mesmo cliente.
    """
    criado = cliente.v1.customers.create(
        params={"email": email, "metadata": {"usuario_id": str(usuario_id)}},
        options={"idempotency_key": f"tickerlab-cliente-{usuario_id}"},
    )
    try:
        with motor.begin() as conexao:
            conexao.execute(
                sa.insert(assinaturas).values(
                    usuario_id=usuario_id,
                    stripe_customer_id=criado.id,
                    stripe_subscription_id=None,
                    status=STATUS_SO_O_CLIENTE,
                    cancela_no_fim=False,
                    evento_em=0,
                    atualizada_em=datetime.now(UTC),
                )
            )
    except sa.exc.IntegrityError:
        # o outro clique guardou primeiro; pela chave de idempotência, é o mesmo cliente
        log.info("Cliente do Stripe já guardado por outro pedido")
    return criado.id


def _expirar_pagamentos_abertos(
    id_do_cliente: str, cliente: stripe.StripeClient
) -> None:
    """Fecha os Checkouts que o cliente abriu e não terminou: cada um viraria uma assinatura."""
    abertas = cliente.v1.checkout.sessions.list(
        params={"customer": id_do_cliente, "status": "open", "limit": 100}
    )
    for sessao in abertas.data:
        try:
            cliente.v1.checkout.sessions.expire(sessao.id)
        except stripe.InvalidRequestError:
            log.info("Checkout aberto já tinha terminado")


def criar_pagina_de_pagamento(
    usuario_id: uuid.UUID,
    id_do_cliente: str,
    configuracao: ConfiguracaoDaCobranca | None = None,
    cliente: stripe.StripeClient | None = None,
    caminho_de_volta: str = "/",
) -> str:
    """Cria a sessão do Checkout para assinar o Pro e devolve o endereço dela.

    Quem chama é `abrir_pagamento`, que garante o cliente e fecha o pagamento aberto antes.
    `caminho_de_volta` é escolhido pelo código (o app atual volta para "/", o app novo para a página
    de planos), nunca por quem chama a API: assim o Stripe nunca devolve a pessoa para outro site.
    """
    configuracao = configuracao or ler_configuracao()
    volta = f"{configuracao.url_do_app}{caminho_de_volta}"
    parametros: dict = {
        "mode": "subscription",
        "line_items": [{"price": configuracao.id_do_preco, "quantity": 1}],
        "client_reference_id": str(usuario_id),
        "success_url": f"{volta}?assinatura=ok",
        "cancel_url": f"{volta}?assinatura=cancelada",
        "subscription_data": {"metadata": {"usuario_id": str(usuario_id)}},
        "allow_promotion_codes": False,
        "integration_identifier": _identificador_da_integracao(),
        "customer": id_do_cliente,
    }
    sessao = (cliente or _cliente(configuracao)).v1.checkout.sessions.create(
        params=parametros
    )
    return sessao.url


def criar_portal_da_assinatura(
    id_do_cliente: str,
    configuracao: ConfiguracaoDaCobranca | None = None,
    cliente: stripe.StripeClient | None = None,
    caminho_de_volta: str = "/",
) -> str:
    """Endereço do portal onde a pessoa troca o cartão, vê faturas ou cancela."""
    configuracao = configuracao or ler_configuracao()
    sessao = (cliente or _cliente(configuracao)).v1.billing_portal.sessions.create(
        params={
            "customer": id_do_cliente,
            "return_url": f"{configuracao.url_do_app}{caminho_de_volta}",
        }
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
    if tem_assinatura_viva(assinatura):
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
    """O plano segue a assinatura: com ela ativa, Pro; sem ela, o plano de antes do Pro (N-02).

    Ao ganhar o Pro, guarda o plano que o usuário tinha (o Plus dado pelo administrador, por
    exemplo); um evento repetido com o usuário já no Pro não apaga essa lembrança.
    """
    do_usuario = assinaturas.c.usuario_id == usuario_id
    if status in STATUS_QUE_DAO_O_PRO:
        atual = conexao.execute(
            sa.select(usuarios.c.plano).where(usuarios.c.id == usuario_id)
        ).scalar_one_or_none()
        if atual is not None and atual != "pro":
            conexao.execute(
                sa.update(assinaturas).where(do_usuario).values(plano_sem_o_pro=atual)
            )
        mudar_plano(conexao, usuario_id, "pro")
        return
    anterior = conexao.execute(
        sa.select(assinaturas.c.plano_sem_o_pro).where(do_usuario)
    ).scalar_one_or_none()
    mudar_plano(conexao, usuario_id, anterior or "gratuito")


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
