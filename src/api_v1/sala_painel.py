"""O que a tela da sala mostra (B-20, PR 5): `/v1/sala` e `/v1/operacoes/{id}/painel`.

Mesmas regras de `src/api_v1/sala.py`: conta logada e 404, não 403, para o
que é de outra conta. A tela não calcula nem escreve nada: os textos, os rótulos dos estados, os
dias que faltam para a operação sumir, o aviso de prazo e a descrição de cada contradição (qual
métrica, período, documentos e valores) saem daqui. Mudar algo (criar, enviar, marcar) usa as rotas
de `sala.py` e `sala_trabalho.py`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api_v1.acesso import exigir_api_ligada
from src.api_v1.sala import (
    SEM_SALA,
    Conta,
    DocumentoV1,
    OperacaoV1,
    _documento_v1,
    _operacao_v1,
    _ou_404,
)
from src.api_v1.sala_trabalho import (
    EvidenciaV1,
    ItemDoChecklistV1,
    _evidencia_v1,
    _item_v1,
)
from src.banco import sala, sala_trabalho
from src.banco.conexao import obter_engine
from src.sala import retencao, textos

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])

DOCUMENTO_APAGADO = "documento apagado"
# itens do checklist que ainda pedem a revisão da pessoa
ITENS_A_REVISAR = ("pendente", "recebido", "contestado")


class OpcaoV1(BaseModel):
    valor: str
    rotulo: str


class OperacaoDaListaV1(OperacaoV1):
    dias_ate_sumir: int
    aviso_de_prazo: str | None
    documentos: int
    contradicoes_abertas: int


class SalaV1(BaseModel):
    """A página da sala: o que ela explica e as operações da conta."""

    conceitos: dict[str, str]
    tipos: list[OpcaoV1]
    prazos_em_dias: list[int]
    prazo_padrao_em_dias: int
    operacoes: list[OperacaoDaListaV1]


class ContradicaoDoPainelV1(BaseModel):
    """Uma contradição já descrita: o que os dois documentos dizem, lado a lado."""

    id: uuid.UUID
    estado: str
    rotulo_do_estado: str
    nota: str | None
    metrica: str
    periodo: str
    unidade: str | None
    moeda: str | None
    diferenca: Decimal | None
    documento_a: str
    documento_b: str
    valor_a: str
    valor_b: str
    criada_em: datetime


class EvidenciaDoPainelV1(EvidenciaV1):
    documento: str  # o nome do documento (a tela não cruza ids)
    valor: str  # o valor como a pessoa o registrou, com a unidade


class ItemDoPainelV1(ItemDoChecklistV1):
    rotulo_do_estado: str
    documento: str | None


class DocumentoDoPainelV1(DocumentoV1):
    rotulo_da_situacao: str


class PainelV1(BaseModel):
    operacao: OperacaoDaListaV1
    tipo_rotulo: str
    documentos: list[DocumentoDoPainelV1]
    evidencias: list[EvidenciaDoPainelV1]
    contradicoes: list[ContradicaoDoPainelV1]
    checklist: list[ItemDoPainelV1]
    estados_do_checklist: list[OpcaoV1]
    itens_a_revisar: int


def _opcoes(rotulos: dict[str, str]) -> list[OpcaoV1]:
    return [OpcaoV1(valor=v, rotulo=r) for v, r in rotulos.items()]


def _da_lista(
    operacao: sala.Operacao, hoje: date, documentos: int, abertas: int
) -> OperacaoDaListaV1:
    return OperacaoDaListaV1(
        **_operacao_v1(operacao).model_dump(),
        dias_ate_sumir=retencao.dias_ate_sumir(operacao.retencao_ate, hoje),
        aviso_de_prazo=textos.aviso_de_prazo(
            operacao.situacao, operacao.retencao_ate, hoje
        ),
        documentos=documentos,
        contradicoes_abertas=abertas,
    )


def _abertas(contradicoes: list[sala_trabalho.Contradicao]) -> int:
    return sum(1 for c in contradicoes if c.estado == "aberta")


@router.get("/sala")
def ver_a_sala(conta: Conta) -> SalaV1:
    hoje = retencao.hoje_em_brasilia()
    operacoes = []
    with obter_engine().connect() as conexao:
        for operacao in sala.listar_operacoes(conexao, usuario_id=conta.id):
            ids = {"usuario_id": conta.id, "operacao_id": operacao.id}
            operacoes.append(
                _da_lista(
                    operacao,
                    hoje,
                    len(sala.listar_documentos(conexao, **ids)),
                    _abertas(sala_trabalho.listar_contradicoes(conexao, **ids)),
                )
            )
    return SalaV1(
        conceitos=textos.CONCEITOS,
        tipos=_opcoes(textos.TIPOS_DE_OPERACAO),
        prazos_em_dias=list(retencao.PRAZOS_DE_GUARDA_EM_DIAS),
        prazo_padrao_em_dias=retencao.PRAZO_PADRAO_EM_DIAS,
        operacoes=operacoes,
    )


def _valor_em_texto(e: sala_trabalho.Evidencia) -> str:
    valor = e.valor_texto if e.valor_numero is None else f"{e.valor_numero:f}"
    partes = [valor or "sem valor", e.unidade, e.moeda]
    return " ".join(p for p in partes if p)


def _contradicao(
    c: sala_trabalho.Contradicao,
    por_id: dict[uuid.UUID, sala_trabalho.Evidencia],
    nomes: dict[uuid.UUID, str],
) -> ContradicaoDoPainelV1 | None:
    a, b = por_id.get(c.evidencia_a), por_id.get(c.evidencia_b)
    if a is None or b is None:
        return None
    return ContradicaoDoPainelV1(
        id=c.id,
        estado=c.estado,
        rotulo_do_estado=textos.ESTADOS_DA_CONTRADICAO[c.estado],
        nota=c.nota,
        metrica=a.metrica,
        periodo=a.periodo,
        unidade=a.unidade,
        moeda=a.moeda,
        diferenca=c.diferenca,
        documento_a=nomes.get(a.documento_id, DOCUMENTO_APAGADO),
        documento_b=nomes.get(b.documento_id, DOCUMENTO_APAGADO),
        valor_a=_valor_em_texto(a),
        valor_b=_valor_em_texto(b),
        criada_em=c.criada_em,
    )


def _montar_o_painel(
    conexao: sa.Connection, operacao: sala.Operacao, ids: dict
) -> PainelV1:
    documentos = sala.listar_documentos(conexao, **ids)
    evidencias = sala_trabalho.listar_evidencias(conexao, **ids)
    contradicoes = sala_trabalho.listar_contradicoes(conexao, **ids)
    itens = sala_trabalho.ler_checklist(conexao, **ids) or []
    nomes = {d.id: d.nome_original for d in documentos}
    por_id = {e.id: e for e in evidencias}
    descritas = [_contradicao(c, por_id, nomes) for c in contradicoes]
    return PainelV1(
        operacao=_da_lista(
            operacao,
            retencao.hoje_em_brasilia(),
            len(documentos),
            _abertas(contradicoes),
        ),
        tipo_rotulo=textos.TIPOS_DE_OPERACAO[operacao.tipo],
        documentos=[
            DocumentoDoPainelV1(
                **_documento_v1(d).model_dump(),
                rotulo_da_situacao=textos.ESTADOS_DO_DOCUMENTO[d.situacao],
            )
            for d in documentos
        ],
        evidencias=[
            EvidenciaDoPainelV1(
                **_evidencia_v1(e).model_dump(),
                documento=nomes.get(e.documento_id, DOCUMENTO_APAGADO),
                valor=_valor_em_texto(e),
            )
            for e in evidencias
        ],
        contradicoes=[d for d in descritas if d is not None],
        checklist=[
            ItemDoPainelV1(
                **_item_v1(i).model_dump(),
                rotulo_do_estado=textos.ESTADOS_DO_ITEM[i.estado],
                documento=nomes.get(i.documento_id) if i.documento_id else None,
            )
            for i in itens
        ],
        estados_do_checklist=_opcoes(textos.ESTADOS_DO_ITEM),
        itens_a_revisar=sum(1 for i in itens if i.estado in ITENS_A_REVISAR),
    )


@router.get("/operacoes/{operacao_id}/painel")
def ver_o_painel(conta: Conta, operacao_id: uuid.UUID) -> PainelV1:
    ids = {"usuario_id": conta.id, "operacao_id": operacao_id}
    with obter_engine().connect() as conexao:
        operacao = _ou_404(sala.buscar_operacao(conexao, **ids), SEM_SALA)
        return _montar_o_painel(conexao, operacao, ids)
