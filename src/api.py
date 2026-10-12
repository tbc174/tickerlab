"""API do TickerLab (FastAPI): saúde do serviço, webhook do Stripe e saída da Newsletter.

Roda ao lado do app, num contêiner próprio:
    uvicorn src.api:app --host 0.0.0.0 --port 8000

As rotas existem com e sem o prefixo `/api`, para funcionar tanto se o proxy (Tailscale) tirar o
caminho quanto se ele o repassar.
"""

import html
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import stripe
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.banco import newsletter_por_email
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


@asynccontextmanager
async def _ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    configurar_logs()  # ao subir o serviço (nos testes, sem servidor, não mexe nos logs)
    yield


app = FastAPI(
    title="TickerLab API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=_ciclo_de_vida,
)
app.include_router(router)
app.include_router(router, prefix="/api")
