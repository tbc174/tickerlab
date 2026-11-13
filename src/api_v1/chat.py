"""A rota do chat de IA do app (linha 903): `POST /v1/chat`, com login, só leitura, em NDJSON.

O analista pergunta; o modelo responde consultando só as 12 ferramentas do conector (`src/chat/`), e cada
linha da resposta é um evento (`src/chat/conversa.py`): as consultas, o texto, o "Como cheguei aqui" e os
avisos.

Antes de qualquer chamada ao modelo, nesta ordem:

1. `TICKERLAB_CHAT=1`; sem ela, 503 "Chat não disponível." e nada sai (ligar em produção é só do Tiago);
2. a chave do modelo só do chat (`ANTHROPIC_API_KEY_CHAT`, nunca a geral) e o modelo com preço na tabela
   (`src/chat/custo.py`); senão o mesmo 503;
3. a conta numa organização ativa com uma chave da API ativa (o contrato dela diz o que as ferramentas
   veem, e o consumo fica na conta dessa chave); senão 403;
4. as ferramentas abertas (o catálogo da organização respondeu);
5. a cota da conta (10 por dia e 50 por mês) e o teto do mês somando todas as contas (`LIMITES_DO_CHAT`);
   429 na cota, 503 "pausado" no teto.

A pergunta só é gravada (em curso, já contando na cota e no teto) quando a resposta começa, dentro do
gerador, sob a trava das reservas e conferindo de novo: um pedido que passou na frente vira uma linha de
erro. Assim o `finally` do gerador sempre fecha a linha que ele abriu; se a tela fecha antes de a resposta
começar, nada é gravado nem gasto. O processo que morre no meio deixa a linha em curso, e a próxima reserva
a fecha como erro (`fechar_abandonadas`).

O registro de cada pergunta leva só ids e números (tokens, custo, latência): nem e-mail, nem nome, nem o
texto da pergunta ou da resposta.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import httpx
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src import chat
from src.api_v1.acesso import conta_com_acesso, exigir_api_ligada
from src.banco import perguntas_do_chat
from src.banco.chaves_da_api import contexto_da_organizacao
from src.banco.conexao import obter_engine
from src.banco.membros_da_organizacao import organizacao_da_conta
from src.banco.usuarios import Usuario
from src.chat.conversa import Conversa, Modelo, TrocaAnterior
from src.chat.custo import (
    UsoDoModelo,
    custo_em_microdolares,
    tem_preco,
    teto_em_microdolares,
)
from src.chat.estado import (
    MENSAGEM_COTA_DO_DIA,
    MENSAGEM_COTA_DO_MES,
    MENSAGEM_DESLIGADO,
    MENSAGEM_PAUSADO,
    MENSAGEM_SEM_CHAVE,
    MENSAGEM_SEM_ORGANIZACAO,
    FatosDoChat,
    Situacao,
    estado_para_a_tela,
)
from src.chat.ferramentas import (
    CaixaDeFerramentas,
    FerramentasIndisponiveis,
    transporte_interno,
)
from src.chat.instrucoes import instrucoes_do_chat
from src.chaves_da_api import ContextoDaChave
from src.planos import LIMITES_DO_CHAT, LimitesDoChat

registro = logging.getLogger(__name__)

Conta = Annotated[Usuario, Depends(conta_com_acesso)]
router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

MILISSEGUNDOS_POR_SEGUNDO = 1000
ERRO = perguntas_do_chat.ERRO
MENSAGEM_FERRAMENTAS = (
    "As consultas do chat não responderam agora; tente de novo em instantes."
)
MENSAGEM_DE_ERRO = (
    "A resposta parou por um erro do nosso lado; a pergunta pode ser feita de novo."
)


class TrocaAnteriorV1(BaseModel):
    """Uma pergunta e a resposta de antes, que a tela reenvia para o modelo ter o contexto."""

    pergunta: str = Field(max_length=LIMITES_DO_CHAT.caracteres_da_pergunta)
    resposta: str = Field(max_length=LIMITES_DO_CHAT.caracteres_do_historico)


class PedidoDoChatV1(BaseModel):
    pergunta: str = Field(
        min_length=1, max_length=LIMITES_DO_CHAT.caracteres_da_pergunta
    )
    historico: list[TrocaAnteriorV1] = Field(
        default_factory=list, max_length=LIMITES_DO_CHAT.perguntas_no_historico
    )


def agora() -> datetime:
    """A hora do pedido (os testes trocam esta função)."""
    return datetime.now(UTC)


def modelo_para(nome: str) -> Modelo:
    """O modelo de verdade; os testes trocam esta função por um dublê (nenhuma chamada paga)."""
    from src.chat.modelo_anthropic import ModeloDaAnthropic

    return ModeloDaAnthropic(nome)


def transporte_para(contexto: ContextoDaChave) -> httpx.AsyncBaseTransport:
    """A API externa por dentro do processo (os testes podem trocar por um dublê)."""
    return transporte_interno(contexto)


def _recusa(status: int, mensagem: str) -> HTTPException:
    return HTTPException(status_code=status, detail=mensagem)


def _contexto_da_conta(usuario_id: uuid.UUID, momento: datetime) -> ContextoDaChave:
    with obter_engine().connect() as conexao:
        organizacao_id = organizacao_da_conta(conexao, usuario_id)
        if organizacao_id is None:
            raise _recusa(403, MENSAGEM_SEM_ORGANIZACAO)
        contexto = contexto_da_organizacao(conexao, organizacao_id, agora=momento)
    if contexto is None:
        raise _recusa(403, MENSAGEM_SEM_CHAVE)
    return contexto


def _conferir_cota_e_teto(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    momento: datetime,
    limites: LimitesDoChat,
) -> None:
    hoje = perguntas_do_chat.perguntas_desde(
        conexao, usuario_id, perguntas_do_chat.inicio_do_dia(momento)
    )
    if hoje >= limites.perguntas_por_dia:
        raise _recusa(429, MENSAGEM_COTA_DO_DIA)
    no_mes = perguntas_do_chat.perguntas_desde(
        conexao, usuario_id, perguntas_do_chat.inicio_do_mes(momento)
    )
    if no_mes >= limites.perguntas_por_mes:
        raise _recusa(429, MENSAGEM_COTA_DO_MES)
    reserva = limites.reserva_por_pergunta_em_microdolares
    gasto = perguntas_do_chat.gasto_do_mes(
        conexao, momento, reserva_em_microdolares=reserva
    )
    if gasto + reserva > teto_em_microdolares(limites):
        raise _recusa(503, MENSAGEM_PAUSADO)


def _conferir(usuario_id: uuid.UUID, momento: datetime, limites: LimitesDoChat) -> None:
    """A cota e o teto antes de a resposta começar, para responder 429 ou 503 (sem gravar nada)."""
    with obter_engine().connect() as conexao:
        _conferir_cota_e_teto(conexao, usuario_id, momento, limites)


@dataclass(frozen=True)
class _Pergunta:
    """Quem pergunta, por qual organização e a que modelo: o que a reserva e o registro precisam."""

    usuario_id: uuid.UUID
    organizacao_id: uuid.UUID
    modelo: str
    momento: datetime
    limites: LimitesDoChat


def _reservar(pergunta: _Pergunta) -> uuid.UUID:
    """Confere a cota e o teto de novo e grava a pergunta em curso, na mesma transação e sob a trava."""
    reserva = pergunta.limites.reserva_por_pergunta_em_microdolares
    with obter_engine().begin() as conexao:
        # a trava vem antes da contagem: pedidos simultâneos contam um depois do outro
        perguntas_do_chat.travar_reservas(conexao)
        perguntas_do_chat.fechar_abandonadas(
            conexao, pergunta.momento, reserva_em_microdolares=reserva
        )
        _conferir_cota_e_teto(
            conexao, pergunta.usuario_id, pergunta.momento, pergunta.limites
        )
        return perguntas_do_chat.reservar(
            conexao,
            usuario_id=pergunta.usuario_id,
            organizacao_id=pergunta.organizacao_id,
            modelo=pergunta.modelo,
            agora=pergunta.momento,
        )


def _uso_da_pergunta(
    modelo: str, uso: UsoDoModelo, chamadas: int, *, custo_minimo: int = 0
) -> perguntas_do_chat.UsoDaPergunta:
    return perguntas_do_chat.UsoDaPergunta(
        tokens_de_entrada=uso.entrada,
        tokens_de_saida=uso.saida,
        tokens_lidos_do_cache=uso.cache_lido,
        tokens_gravados_no_cache=uso.cache_gravado,
        custo_em_microdolares=max(custo_em_microdolares(modelo, uso), custo_minimo),
        chamadas_de_ferramenta=chamadas,
    )


def _fechar(
    pergunta_id: uuid.UUID,
    pergunta: _Pergunta,
    estado: str,
    uso: perguntas_do_chat.UsoDaPergunta,
    latencia_ms: int,
) -> None:
    """Completa a linha da pergunta e grava o registro (só ids e números)."""
    try:
        with obter_engine().begin() as conexao:
            perguntas_do_chat.concluir(
                conexao, pergunta_id, estado=estado, uso=uso, latencia_ms=latencia_ms
            )
    except sa.exc.SQLAlchemyError as erro:
        # a linha fica em curso e conta pela reserva no teto: erra para o lado de gastar menos
        registro.error(
            "chat_pergunta_sem_fechar pergunta_id=%s erro=%s",
            pergunta_id,
            type(erro).__name__,
        )
    campos = {
        "evento": "chat_pergunta",
        "pergunta_id": str(pergunta_id),
        "usuario_id": str(pergunta.usuario_id),
        "organizacao_id": str(pergunta.organizacao_id),
        "modelo": pergunta.modelo,
        "estado": estado,
        "tokens_de_entrada": uso.tokens_de_entrada,
        "tokens_de_saida": uso.tokens_de_saida,
        "tokens_lidos_do_cache": uso.tokens_lidos_do_cache,
        "tokens_gravados_no_cache": uso.tokens_gravados_no_cache,
        "custo_em_microdolares": uso.custo_em_microdolares,
        "chamadas_de_ferramenta": uso.chamadas_de_ferramenta,
        "latencia_ms": latencia_ms,
    }
    registro.info(json.dumps(campos, ensure_ascii=False))


def _linha(evento: dict[str, object]) -> bytes:
    return (json.dumps(evento, ensure_ascii=False) + "\n").encode("utf-8")


async def _resposta(
    conversa: Conversa,
    pergunta: _Pergunta,
    texto: str,
    historico: list[TrocaAnterior],
    relogio: Callable[[], float] = time.perf_counter,
) -> AsyncIterator[bytes]:
    try:
        pergunta_id = await run_in_threadpool(_reservar, pergunta)
    except HTTPException as recusa:
        # outro pedido passou na frente entre a conferência e a reserva: nada foi gravado nem gasto
        yield _linha({"tipo": "erro", "mensagem": recusa.detail})
        return
    except Exception as erro:  # noqa: BLE001 - sem reserva, sem modelo; a conexão fecha limpa
        registro.warning("chat_sem_reserva erro=%s", type(erro).__name__)
        yield _linha({"tipo": "erro", "mensagem": MENSAGEM_DE_ERRO})
        return
    inicio = relogio()
    terminou = False
    try:
        async for evento in conversa.eventos(texto, historico):
            yield _linha(evento)
        terminou = True
    except Exception as erro:  # noqa: BLE001 - o erro vira uma linha; a conexão fecha limpa
        registro.warning(
            "chat_falhou pergunta_id=%s erro=%s", pergunta_id, type(erro).__name__
        )
        yield _linha({"tipo": "erro", "mensagem": MENSAGEM_DE_ERRO})
    finally:
        # sem o fim (erro, ou a tela fechou no meio), a pergunta fica como erro, com o que gastou
        estado = conversa.estado if terminou else ERRO
        latencia = round((relogio() - inicio) * MILISSEGUNDOS_POR_SEGUNDO)
        # o uso só chega no fim de cada volta: a que parou no meio já pode ter sido paga e não aparece.
        # A pergunta que não terminou fica pela reserva (o pior caso), para o teto errar para menos; a que
        # refez alguma volta também (a tentativa que falhou foi paga e o uso dela não chega)
        reserva = pergunta.limites.reserva_por_pergunta_em_microdolares
        uso = _uso_da_pergunta(
            pergunta.modelo,
            conversa.uso,
            conversa.chamadas,
            custo_minimo=reserva if not terminou or conversa.recomecos else 0,
        )
        _fechar(pergunta_id, pergunta, estado, uso, latencia)


@router.post("/chat")
async def perguntar(pedido: PedidoDoChatV1, conta: Conta) -> StreamingResponse:
    """A resposta do chat, um evento JSON por linha (`application/x-ndjson`)."""
    limites = LIMITES_DO_CHAT
    nome_do_modelo = chat.modelo_do_chat()
    if not chat.chat_ligado():
        raise _recusa(503, MENSAGEM_DESLIGADO)
    if not chat.tem_chave_do_modelo() or not tem_preco(nome_do_modelo):
        registro.warning(
            "chat_sem_configuracao tem_chave=%s modelo_com_preco=%s",
            chat.tem_chave_do_modelo(),
            tem_preco(nome_do_modelo),
        )
        raise _recusa(503, MENSAGEM_DESLIGADO)
    momento = agora()
    contexto = await run_in_threadpool(_contexto_da_conta, conta.id, momento)
    # a cota e o teto antes do catálogo: quem já estourou não gasta o limite por minuto da organização
    await run_in_threadpool(_conferir, conta.id, momento, limites)
    try:
        caixa = await CaixaDeFerramentas.abrir(
            transporte_para(contexto),
            identificador=f"chat:{contexto.prefixo}",
            limites=limites,
        )
    except FerramentasIndisponiveis as erro:
        registro.warning("chat_sem_ferramentas motivo=%s", erro)
        raise _recusa(503, MENSAGEM_FERRAMENTAS) from None
    conversa = Conversa(
        modelo=modelo_para(nome_do_modelo),
        caixa=caixa,
        instrucoes=_instrucoes_de_hoje(momento),
        limites=limites,
    )
    pergunta = _Pergunta(
        usuario_id=conta.id,
        organizacao_id=contexto.organizacao_id,
        modelo=nome_do_modelo,
        momento=momento,
        limites=limites,
    )
    historico = [TrocaAnterior(t.pergunta, t.resposta) for t in pedido.historico]
    return StreamingResponse(
        _resposta(conversa, pergunta, pedido.pergunta, historico),
        media_type="application/x-ndjson",
    )


class EstadoDoChatV1(BaseModel):
    """Se a conta pode perguntar agora e, se não, por quê; com a cota, os limites e o que dizer na tela."""

    situacao: Situacao
    pode_perguntar: bool
    mensagem: str | None
    perguntas_hoje: int
    perguntas_por_dia: int
    perguntas_no_mes: int
    perguntas_por_mes: int
    caracteres_da_pergunta: int
    perguntas_no_historico: int
    caracteres_do_historico: int
    como_funciona: str
    exemplos: list[str]
    limites: list[str]


def _chat_configurado() -> bool:
    """A chave de ligar, a chave do modelo e o modelo com preço: o que a rota de perguntar confere primeiro."""
    return (
        chat.chat_ligado()
        and chat.tem_chave_do_modelo()
        and tem_preco(chat.modelo_do_chat())
    )


def _fatos_da_conta(
    usuario_id: uuid.UUID, momento: datetime, limites: LimitesDoChat
) -> FatosDoChat:
    """O que a pergunta desta conta ouviria agora; só leitura, nada é gravado nem reservado."""
    ligado = _chat_configurado()
    with obter_engine().connect() as conexao:
        organizacao_id = organizacao_da_conta(conexao, usuario_id)
        tem_chave = (
            organizacao_id is not None
            and contexto_da_organizacao(conexao, organizacao_id, agora=momento)
            is not None
        )
        hoje = perguntas_do_chat.perguntas_desde(
            conexao, usuario_id, perguntas_do_chat.inicio_do_dia(momento)
        )
        no_mes = perguntas_do_chat.perguntas_desde(
            conexao, usuario_id, perguntas_do_chat.inicio_do_mes(momento)
        )
        reserva = limites.reserva_por_pergunta_em_microdolares
        gasto = perguntas_do_chat.gasto_do_mes(
            conexao, momento, reserva_em_microdolares=reserva
        )
    return FatosDoChat(
        ligado=ligado,
        tem_organizacao=organizacao_id is not None,
        tem_chave_da_api=tem_chave,
        perguntas_hoje=hoje,
        perguntas_no_mes=no_mes,
        # só se o teto pausou: o gasto em dinheiro não sai da rota
        pausado=gasto + reserva > teto_em_microdolares(limites),
    )


@router.get("/chat/estado", response_model=EstadoDoChatV1)
async def estado_do_chat(conta: Conta) -> dict[str, object]:
    """O estado do chat para a tela "Perguntar": a primeira recusa que a pergunta ouviria, ou "pronto".

    A ordem é a de `POST /v1/chat`. Com o chat desligado a tela ainda abre, para dizer que ele não foi
    ligado e o que vai fazer.
    """
    limites = LIMITES_DO_CHAT
    fatos = await run_in_threadpool(_fatos_da_conta, conta.id, agora(), limites)
    return estado_para_a_tela(fatos, limites)


def _instrucoes_de_hoje(momento: datetime) -> str:
    from src.chat.modelo_anthropic import instrucoes_com_a_data

    return instrucoes_com_a_data(instrucoes_do_chat(), momento)
