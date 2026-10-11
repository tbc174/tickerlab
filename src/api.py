"""API do TickerLab (FastAPI): saúde do serviço e webhook do Stripe.

Roda ao lado do app, num contêiner próprio:
    uvicorn src.api:app --host 0.0.0.0 --port 8000

As rotas existem com e sem o prefixo `/api`, para funcionar tanto se o proxy (Tailscale) tirar o
caminho quanto se ele o repassar.
"""

import json
import logging
import os

import stripe
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.banco.conexao import banco_esta_saudavel, obter_engine
from src.cobranca import VARIAVEL_DO_SEGREDO_DO_WEBHOOK, processar_evento

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


app = FastAPI(title="TickerLab API", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)
app.include_router(router, prefix="/api")
