"""As rotas do trabalho na sala: evidências, contradições e checklist (B-20, PR 4).

Mesmas regras de `src/api_v1/sala.py`: só admin (404 para as outras contas), 404 e não 403 para o
que é de outra conta, nada de rota de admin sobre a sala de outra pessoa. Nenhuma rota chama modelo:
o trecho de uma evidência é conferido por código contra o texto da página (D10) e as contradições
saem de uma regra fixa.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from src.api_v1.acesso import exigir_api_ligada
from src.api_v1.sala import SEM_DOCUMENTO, SEM_SALA, Conta, _ou_404
from src.banco import sala, sala_trabalho
from src.banco.conexao import obter_engine
from src.banco.modelo import TAMANHO_MAXIMO_DA_NOTA
from src.sala import cofre, documentos, evidencias

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

SEM_EVIDENCIA = "Esta evidência não existe ou já foi apagada."
SEM_CONTRADICAO = "Esta contradição não existe ou já foi apagada."
SEM_ITEM = "Este item não existe no checklist desta operação."


class PedidoDeEvidenciaV1(BaseModel):
    documento_id: uuid.UUID
    metrica: str = Field(max_length=sala_trabalho.TAMANHO_DA_METRICA)
    periodo: str = Field(max_length=sala_trabalho.TAMANHO_DO_PERIODO)
    valor_numero: Decimal | None = Field(default=None, max_digits=28, decimal_places=6)
    valor_texto: str | None = Field(
        default=None, max_length=sala_trabalho.TAMANHO_DO_VALOR_EM_TEXTO
    )
    unidade: str | None = Field(
        default=None, max_length=sala_trabalho.TAMANHO_DA_UNIDADE
    )
    moeda: str | None = Field(default=None, max_length=sala_trabalho.TAMANHO_DA_MOEDA)
    pagina: int | None = Field(default=None, ge=1)
    secao: str | None = Field(default=None, max_length=sala_trabalho.TAMANHO_DA_SECAO)
    tabela: str | None = Field(default=None, max_length=sala_trabalho.TAMANHO_DA_SECAO)
    trecho: str | None = Field(default=None, max_length=TAMANHO_MAXIMO_DA_NOTA)


class PedidoDeRevisaoV1(BaseModel):
    estado: Literal["automatico", "revisado", "contestado", "rejeitado"]


class PedidoDeContradicaoV1(BaseModel):
    estado: Literal["aberta", "explicada", "descartada"]
    nota: str | None = Field(default=None, max_length=TAMANHO_MAXIMO_DA_NOTA)


class PedidoDeItemV1(BaseModel):
    """Só o que veio no pedido muda: `documento_id: null` solta o documento, ausente não mexe."""

    estado: Literal["pendente", "revisado", "contestado", "nao_se_aplica"] | None = None
    documento_id: uuid.UUID | None = None
    nota: str | None = Field(default=None, max_length=TAMANHO_MAXIMO_DA_NOTA)


class EvidenciaV1(BaseModel):
    id: uuid.UUID
    documento_id: uuid.UUID
    metrica: str
    periodo: str
    valor_numero: Decimal | None
    valor_texto: str | None
    unidade: str | None
    moeda: str | None
    pagina: int | None
    secao: str | None
    tabela: str | None
    trecho: str | None
    conferida: bool  # o trecho foi achado na página; falso = "não conferida"
    extraido_por: str
    estado_de_revisao: str
    criada_em: datetime


class ContradicaoV1(BaseModel):
    id: uuid.UUID
    evidencia_a: uuid.UUID
    evidencia_b: uuid.UUID
    diferenca: Decimal | None
    estado: str
    nota: str | None
    criada_em: datetime


class ItemDoChecklistV1(BaseModel):
    codigo: str
    titulo: str
    ajuda: str
    estado: str
    documento_id: uuid.UUID | None
    nota: str | None
    atualizado_em: datetime | None


def _evidencia_v1(e: sala_trabalho.Evidencia) -> EvidenciaV1:
    return EvidenciaV1(
        **{campo: getattr(e, campo) for campo in EvidenciaV1.model_fields}
    )


def _contradicao_v1(c: sala_trabalho.Contradicao) -> ContradicaoV1:
    return ContradicaoV1(
        **{campo: getattr(c, campo) for campo in ContradicaoV1.model_fields}
    )


def _item_v1(i: sala_trabalho.ItemDaOperacao) -> ItemDoChecklistV1:
    return ItemDoChecklistV1(
        **{campo: getattr(i, campo) for campo in ItemDoChecklistV1.model_fields}
    )


def _ou_422[T](fazer: Callable[[], T]) -> T:
    try:
        return fazer()
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro


def _trecho_confere(
    conexao: sa.Connection,
    conta_id: uuid.UUID,
    operacao_id: uuid.UUID,
    pedido: PedidoDeEvidenciaV1,
) -> bool:
    """Compara o trecho com o texto da página; sem texto lido (ou sem chave) é "não conferida"."""
    try:
        paginas = documentos.texto_do_documento(
            conexao,
            usuario_id=conta_id,
            operacao_id=operacao_id,
            documento_id=pedido.documento_id,
        )
    except (cofre.CifraInvalidaError, OSError) as erro:
        log.warning(
            "o texto do documento %s não abriu para conferir: %s",
            pedido.documento_id,
            type(erro).__name__,
        )
        return False
    return evidencias.trecho_confere(paginas, pedido.pagina, pedido.trecho)


def _operacao_aberta(
    conexao: sa.Connection, conta_id: uuid.UUID, operacao_id: uuid.UUID
) -> None:
    operacao = _ou_404(
        sala.buscar_operacao(conexao, usuario_id=conta_id, operacao_id=operacao_id)
    )
    if operacao.situacao != "aberta":
        raise HTTPException(
            status_code=409, detail="A operação está encerrada: não recebe evidências."
        )


# --- evidências ---------------------------------------------------------------------------


@router.post("/operacoes/{operacao_id}/evidencias", status_code=201)
def criar_evidencia(
    conta: Conta, operacao_id: uuid.UUID, pedido: PedidoDeEvidenciaV1
) -> EvidenciaV1:
    """Registra uma evidência: onde o número está (documento, página, trecho) e o que ele diz."""
    with obter_engine().begin() as conexao:
        _operacao_aberta(conexao, conta.id, operacao_id)
        conferida = _trecho_confere(conexao, conta.id, operacao_id, pedido)
        evidencia = _ou_422(
            lambda: sala_trabalho.criar_evidencia(
                conexao,
                usuario_id=conta.id,
                operacao_id=operacao_id,
                conferida=conferida,
                **pedido.model_dump(),
            )
        )
    return _evidencia_v1(_ou_404(evidencia, SEM_DOCUMENTO))


@router.get("/operacoes/{operacao_id}/evidencias")
def listar_evidencias(conta: Conta, operacao_id: uuid.UUID) -> list[EvidenciaV1]:
    ids = {"usuario_id": conta.id, "operacao_id": operacao_id}
    with obter_engine().connect() as conexao:
        _ou_404(sala.buscar_operacao(conexao, **ids), SEM_SALA)
        return [
            _evidencia_v1(e) for e in sala_trabalho.listar_evidencias(conexao, **ids)
        ]


@router.patch("/operacoes/{operacao_id}/evidencias/{evidencia_id}")
def revisar_evidencia(
    conta: Conta,
    operacao_id: uuid.UUID,
    evidencia_id: uuid.UUID,
    pedido: PedidoDeRevisaoV1,
) -> EvidenciaV1:
    """Revisa, contesta ou rejeita a evidência (a rejeitada não entra nas contradições)."""
    with obter_engine().begin() as conexao:
        evidencia = sala_trabalho.mudar_revisao_da_evidencia(
            conexao,
            usuario_id=conta.id,
            operacao_id=operacao_id,
            evidencia_id=evidencia_id,
            estado=pedido.estado,
        )
    return _evidencia_v1(_ou_404(evidencia, SEM_EVIDENCIA))


@router.delete("/operacoes/{operacao_id}/evidencias/{evidencia_id}", status_code=204)
def apagar_evidencia(
    conta: Conta, operacao_id: uuid.UUID, evidencia_id: uuid.UUID
) -> Response:
    with obter_engine().begin() as conexao:
        apagada = sala_trabalho.apagar_evidencia(
            conexao,
            usuario_id=conta.id,
            operacao_id=operacao_id,
            evidencia_id=evidencia_id,
        )
    _ou_404(apagada or None, SEM_EVIDENCIA)
    return Response(status_code=204)


# --- contradições -------------------------------------------------------------------------


@router.get("/operacoes/{operacao_id}/contradicoes")
def listar_contradicoes(conta: Conta, operacao_id: uuid.UUID) -> list[ContradicaoV1]:
    ids = {"usuario_id": conta.id, "operacao_id": operacao_id}
    with obter_engine().connect() as conexao:
        _ou_404(sala.buscar_operacao(conexao, **ids), SEM_SALA)
        return [
            _contradicao_v1(c)
            for c in sala_trabalho.listar_contradicoes(conexao, **ids)
        ]


@router.patch("/operacoes/{operacao_id}/contradicoes/{contradicao_id}")
def marcar_contradicao(
    conta: Conta,
    operacao_id: uuid.UUID,
    contradicao_id: uuid.UUID,
    pedido: PedidoDeContradicaoV1,
) -> ContradicaoV1:
    """Marca como "explicada" ou "descartada" (a nota é obrigatória) ou reabre."""
    with obter_engine().begin() as conexao:
        contradicao = _ou_422(
            lambda: sala_trabalho.mudar_contradicao(
                conexao,
                usuario_id=conta.id,
                operacao_id=operacao_id,
                contradicao_id=contradicao_id,
                estado=pedido.estado,
                nota=pedido.nota,
            )
        )
    return _contradicao_v1(_ou_404(contradicao, SEM_CONTRADICAO))


# --- checklist ----------------------------------------------------------------------------


@router.get("/operacoes/{operacao_id}/checklist")
def ver_checklist(conta: Conta, operacao_id: uuid.UUID) -> list[ItemDoChecklistV1]:
    with obter_engine().connect() as conexao:
        itens = sala_trabalho.ler_checklist(
            conexao, usuario_id=conta.id, operacao_id=operacao_id
        )
    return [_item_v1(i) for i in _ou_404(itens, SEM_SALA)]


@router.patch("/operacoes/{operacao_id}/checklist/{codigo}")
def mudar_item(
    conta: Conta,
    operacao_id: uuid.UUID,
    codigo: Annotated[str, Field(max_length=60)],
    pedido: PedidoDeItemV1,
) -> ItemDoChecklistV1:
    """Marca o item, liga ou solta um documento, escreve a nota. Ligar um documento a um item
    pendente o põe em "recebido"; "revisado" é sempre a pessoa que marca."""
    enviados = pedido.model_fields_set
    mudancas = {
        campo: getattr(pedido, campo)
        for campo in ("documento_id", "nota")
        if campo in enviados
    }
    with obter_engine().begin() as conexao:
        item = _ou_422(
            lambda: sala_trabalho.mudar_item_do_checklist(
                conexao,
                usuario_id=conta.id,
                operacao_id=operacao_id,
                codigo=codigo,
                estado=pedido.estado,
                **mudancas,
            )
        )
    return _item_v1(_ou_404(item, SEM_ITEM))
