"""API do TickerLab (FastAPI): saúde do serviço, webhook do Stripe, saída da Newsletter e das
Novidades por e-mail e a API de leitura v1 (`src/api_v1/`, desligada até a primeira tela nova).

Roda ao lado do app, num contêiner próprio:
    uvicorn src.api:app --host 0.0.0.0 --port 8000

As rotas existem com e sem o prefixo `/api`, para funcionar tanto se o proxy (Tailscale) tirar o
caminho quanto se ele o repassar.
"""

import html
import json
import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

import stripe
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api_v1 import api_v1_ligada
from src.banco import newsletter_por_email, novidades_por_email
from src.banco.conexao import banco_esta_saudavel, obter_engine
from src.cobranca import VARIAVEL_DO_SEGREDO_DO_WEBHOOK, processar_evento
from src.logs import configurar_logs

log = logging.getLogger(__name__)

TAMANHO_MAXIMO_DO_CORPO = 1_000_000  # bytes: os eventos do Stripe têm poucos KB

router = APIRouter()


@router.get("/saude", response_model=None)
def saude() -> dict[str, str] | JSONResponse:
    """Responde 200 se o banco responde, 503 se não (serve para o monitor do servidor)."""
    if banco_esta_saudavel():
        return {"status": "ok"}
    return JSONResponse({"status": "banco indisponível"}, status_code=503)


@router.post("/webhooks/stripe")
async def receber_webhook_do_stripe(request: Request) -> dict[str, str]:
    segredo = os.environ.get(VARIAVEL_DO_SEGREDO_DO_WEBHOOK, "")
    if not segredo:
        log.error("%s não configurado", VARIAVEL_DO_SEGREDO_DO_WEBHOOK)
        raise HTTPException(status_code=503, detail="Webhook não configurado.")
    anunciado = request.headers.get("content-length")
    if anunciado and anunciado.isdigit() and int(anunciado) > TAMANHO_MAXIMO_DO_CORPO:
        raise HTTPException(status_code=413, detail="Corpo grande demais.")
    corpo = await request.body()
    if len(corpo) > TAMANHO_MAXIMO_DO_CORPO:
        raise HTTPException(status_code=413, detail="Corpo grande demais.")
    try:
        # confere a assinatura do Stripe: sem isso qualquer pessoa poderia se dar o plano Pro
        stripe.Webhook.construct_event(
            corpo, request.headers.get("stripe-signature"), segredo
        )
        evento = json.loads(corpo)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Assinatura inválida.") from None
    try:
        with obter_engine().begin() as conexao:
            resultado = processar_evento(conexao, evento)
    except Exception:
        # 500 faz o Stripe tentar de novo mais tarde; a transação desfeita não deixa meio-termo
        log.exception("Falha ao processar um evento do Stripe")
        raise HTTPException(status_code=500, detail="Falha ao processar.") from None
    return {"resultado": resultado}


def _pagina(titulo: str, corpo: str) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{titulo}</title></head>"
        '<body style="font-family:Arial,sans-serif;max-width:520px;margin:48px auto;padding:0 16px">'
        f'<h1 style="font-size:22px">{titulo}</h1>{corpo}</body></html>'
    )


@router.get("/newsletter/sair")
def confirmar_saida_da_newsletter(codigo: str = "") -> HTMLResponse:
    """A página do link do e-mail: pede a confirmação (leitores de e-mail abrem links sozinhos;
    só o botão, um POST, descadastra)."""
    return _pagina(
        "Sair da Newsletter do TickerLab",
        "<p>Você deixa de receber a Newsletter por e-mail. Pode se inscrever de novo no app.</p>"
        f'<form method="post" action="?codigo={html.escape(codigo, quote=True)}">'
        '<button type="submit" style="font-size:16px;padding:10px 18px">Sair da Newsletter'
        "</button></form>",
    )


@router.post("/newsletter/sair")
def sair_da_newsletter(codigo: str = "") -> HTMLResponse:
    """Descadastra pelo código do e-mail (também o "cancelar inscrição" de um clique do Gmail)."""
    with obter_engine().begin() as conexao:
        saiu = newsletter_por_email.sair_pelo_codigo(conexao, codigo)
    if saiu:
        return _pagina("Pronto", "<p>Você não recebe mais a Newsletter por e-mail.</p>")
    return _pagina(
        "Nada a fazer",
        "<p>Este link já foi usado ou não vale mais. Se ainda recebe e-mails, cancele em "
        "Newsletter, no app.</p>",
    )


@router.get("/novidades/sair")
def confirmar_saida_das_novidades(codigo: str = "") -> HTMLResponse:
    """A página do link do e-mail de Novidades: pede a confirmação (como a da Newsletter)."""
    return _pagina(
        "Sair das Novidades do TickerLab",
        "<p>Você deixa de receber novidades e ofertas por e-mail. Pode pedir de novo em Meus "
        "dados, no app.</p>"
        f'<form method="post" action="?codigo={html.escape(codigo, quote=True)}">'
        '<button type="submit" style="font-size:16px;padding:10px 18px">Sair das Novidades'
        "</button></form>",
    )


@router.post("/novidades/sair")
def sair_das_novidades(codigo: str = "") -> HTMLResponse:
    """Tira das Novidades pelo código do e-mail (também a saída de um clique do Gmail)."""
    with obter_engine().begin() as conexao:
        saiu = novidades_por_email.sair_pelo_codigo(conexao, codigo)
    if saiu:
        return _pagina(
            "Pronto", "<p>Você não recebe mais novidades e ofertas por e-mail.</p>"
        )
    return _pagina(
        "Nada a fazer",
        "<p>Este link já foi usado ou não vale mais. Se ainda recebe e-mails, saia em Meus "
        "dados, no app.</p>",
    )


@asynccontextmanager
async def _ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    configurar_logs()  # ao subir o serviço (nos testes, sem servidor, não mexe nos logs)
    yield


def criar_app(ambiente: Mapping[str, str] | None = None) -> FastAPI:
    """A API; as rotas de leitura (v1) só entram com `TICKERLAB_API_V1=1` (ADR 0048)."""
    nova = FastAPI(
        title="TickerLab API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_ciclo_de_vida,
    )
    nova.include_router(router)
    nova.include_router(router, prefix="/api")
    if api_v1_ligada(ambiente):
        # só aqui: as contas da v1 carregam o pandas, e desligada a API continua leve
        from src.api_v1.acesso import CABECALHO_DO_MOTIVO
        from src.api_v1.compartilhados import router as router_compartilhados
        from src.api_v1.conta import router as router_da_conta
        from src.api_v1.entrada import router as router_da_entrada
        from src.api_v1.ferramentas import router as router_das_ferramentas
        from src.api_v1.rotas import router as router_v1
        from src.api_v1.sala import router as router_da_sala
        from src.api_v1.sala_garantias import router as router_das_garantias
        from src.api_v1.sala_painel import router as router_do_painel_da_sala
        from src.api_v1.sala_trabalho import router as router_do_trabalho_na_sala
        from src.planos import LimiteDoPlanoError

        @nova.exception_handler(LimiteDoPlanoError)
        async def _limite_do_plano(
            _pedido: Request, erro: LimiteDoPlanoError
        ) -> JSONResponse:
            # a mesma recusa de plano das páginas fechadas (acesso._recusa): o app novo lê o
            # cabeçalho e mostra o caminho para o plano maior; a frase do erro já sugere o Pro
            return JSONResponse(
                status_code=403,
                content={"detail": str(erro)},
                headers={CABECALHO_DO_MOTIVO: "plano"},
            )

        for rotas in (
            router_v1,
            router_compartilhados,
            router_da_conta,
            router_da_entrada,
            router_das_ferramentas,
            router_da_sala,
            router_do_painel_da_sala,
            router_do_trabalho_na_sala,
            router_das_garantias,
        ):
            nova.include_router(rotas)
            nova.include_router(rotas, prefix="/api")
    return nova


app = criar_app()
