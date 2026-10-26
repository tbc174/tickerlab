"""Entrar com e-mail e código de 6 dígitos (plano do login com Microsoft e e-mail, PR 2).

`POST /v1/entrada/codigo` manda o código para o e-mail pelo Resend e responde sempre a mesma coisa
(202), exista conta ou não, o e-mail seja válido ou não, o limite tenha estourado ou não: quem
espiona não descobre quem tem conta. `POST /v1/entrada/confirmar` confere o código (regras em
`src/codigo_de_entrada.py`), cria a conta no primeiro acesso (ou entra na que tem o mesmo e-mail
confirmado) e abre a sessão de 30 dias, como o login do Google.

Os dois pedidos exigem a prova de origem do app (cabeçalho `X-TickerLab-Pedido` e `Origin` igual ao
`Host`), mesmo sem cookie: um site de fora não faz o TickerLab mandar e-mail em nome dele. O log
nunca leva o e-mail nem o código. O limite por IP fica na memória do processo (a API tem um só).
"""

import logging
import os
from typing import Annotated

import requests
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from src import codigo_de_entrada as codigos
from src.api_v1.acesso import (
    CABECALHO_DO_MOTIVO,
    LimiteDePedidos,
    agora,
    exigir_api_ligada,
)
from src.api_v1.compartilhados import ip_de_quem_pede
from src.api_v1.conta import (
    ContaV1,
    abrir_a_sessao,
    inicio_do_login,
    recusa_da_conta_bloqueada,
)
from src.api_v1.rotas import eu_da_conta
from src.api_v1.sessao import pedido_do_proprio_site
from src.banco.conexao import obter_engine
from src.banco.origens import gravar_origem
from src.banco.usuarios import (
    TAMANHO_MAXIMO_DO_EMAIL,
    ContaBloqueadaError,
    IdentidadeDoProvedor,
    Usuario,
    entrar_por_identidade,
)
from src.envio_newsletter import VARIAVEL_DA_CHAVE, EnvioFalhouError, enviar_pelo_resend
from src.origem import NOME_DO_COOKIE, ler_origem

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

VARIAVEL_DO_REMETENTE = "TICKERLAB_ENTRADA_REMETENTE"
REMETENTE_PADRAO = "TickerLab <entrada@tickerlab.com.br>"
UMA_HORA = 3600
PEDIDOS_DE_CODIGO_POR_IP = 10  # por hora
CONFERENCIAS_POR_IP = 30  # por hora
LIMITE_POR_IP = LimiteDePedidos(PEDIDOS_DE_CODIGO_POR_IP, janela=UMA_HORA)
LIMITE_DA_CONFERENCIA_POR_IP = LimiteDePedidos(CONFERENCIAS_POR_IP, janela=UMA_HORA)
TRANSPORTE = requests.post  # os testes trocam por um dublê
MENSAGEM = (
    "Se o e-mail estiver certo, o código chega em instantes (vale por 10 minutos)."
)


def enviar_o_codigo(para: str, codigo: str) -> None:
    """Manda o código pelo Resend; `EnvioFalhouError` (sem o e-mail na mensagem) se não der."""
    chave = os.environ.get(VARIAVEL_DA_CHAVE, "").strip()
    if not chave:
        raise EnvioFalhouError("chave do Resend não configurada")
    enviar_pelo_resend(
        para,
        codigos.montar_email(codigo),
        link_de_saida=None,
        idempotencia=f"entrada-{os.urandom(8).hex()}",
        chave=chave,
        transporte=TRANSPORTE,
        remetente=os.environ.get(VARIAVEL_DO_REMETENTE) or REMETENTE_PADRAO,
    )


class PedidoDeCodigoV1(BaseModel):
    email: str = Field(max_length=TAMANHO_MAXIMO_DO_EMAIL)


class RespostaDoPedidoV1(BaseModel):
    mensagem: str


class ConfirmacaoV1(BaseModel):
    email: str = Field(max_length=TAMANHO_MAXIMO_DO_EMAIL)
    codigo: str = Field(max_length=20)


def _exigir_o_proprio_site(pedido: Request) -> None:
    if not pedido_do_proprio_site(pedido):
        raise HTTPException(
            status_code=403,
            detail="Pedido recusado: ele não saiu do próprio TickerLab.",
            headers={CABECALHO_DO_MOTIVO: "pedido-de-fora"},
        )


def _barrar_excesso(limite: LimiteDePedidos, pedido: Request) -> None:
    if not limite.permitir(ip_de_quem_pede(pedido), agora()):
        raise HTTPException(
            status_code=429, detail="Muitos pedidos: tente de novo mais tarde."
        )


@router.post("/entrada/codigo", status_code=202)
def pedir_o_codigo(pedido: Request, corpo: PedidoDeCodigoV1) -> RespostaDoPedidoV1:
    """Manda um código de entrada para o e-mail (ou finge que mandou: a resposta é sempre igual)."""
    _exigir_o_proprio_site(pedido)
    _barrar_excesso(LIMITE_POR_IP, pedido)
    with obter_engine().begin() as conexao:
        codigo = codigos.pedir_codigo(conexao, corpo.email)
    if codigo is not None:
        try:
            enviar_o_codigo(corpo.email.strip().lower(), codigo)
        except EnvioFalhouError as erro:
            log.error("Código de entrada não enviado: %s", erro)
    return RespostaDoPedidoV1(mensagem=MENSAGEM)


def _entrar_pelo_email(
    email: str, cookie_de_origem: str | None
) -> tuple[Usuario, bool]:
    identidade = IdentidadeDoProvedor("email", email, email, email_confirmado=True)
    origem = ler_origem(cookie_de_origem)
    for tentativa in range(2):
        try:
            with obter_engine().begin() as conexao:
                usuario, primeira_vez = entrar_por_identidade(conexao, identidade)
                if primeira_vez and origem is not None:
                    gravar_origem(conexao, usuario.id, origem)
                return usuario, primeira_vez
        except IntegrityError:
            # outra aba criou a mesma conta no mesmo instante: a segunda tentativa entra nela
            if tentativa:
                raise
    raise AssertionError("inalcançável")


@router.post("/entrada/confirmar")
def confirmar_o_codigo(
    pedido: Request,
    resposta: Response,
    corpo: ConfirmacaoV1,
    tl_origem: Annotated[str | None, Cookie(alias=NOME_DO_COOKIE)] = None,
) -> ContaV1:
    """Confere o código e abre a sessão. Código errado, vencido, usado ou nunca pedido: 401 igual."""
    _exigir_o_proprio_site(pedido)
    _barrar_excesso(LIMITE_DA_CONFERENCIA_POR_IP, pedido)
    email = corpo.email.strip().lower()
    # transação própria: a tentativa errada precisa ficar gravada mesmo recusando o pedido
    with obter_engine().begin() as conexao:
        valeu = codigos.conferir_codigo(conexao, email, corpo.codigo)
    if not valeu:
        raise HTTPException(
            status_code=401,
            detail="Código incorreto ou vencido. Peça um novo.",
            headers={CABECALHO_DO_MOTIVO: "codigo"},
        )
    inicio = inicio_do_login()
    try:
        usuario, primeira_vez = _entrar_pelo_email(email, tl_origem)
    except ContaBloqueadaError as erro:
        raise recusa_da_conta_bloqueada(erro) from erro
    abrir_a_sessao(pedido, resposta, usuario, "email", inicio=inicio)
    return ContaV1(**eu_da_conta(usuario).model_dump(), primeira_vez=primeira_vez)
