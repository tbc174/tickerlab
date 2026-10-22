"""As rotas das garantias e exposições da operação (B-17, PR 2): só leitura.

Mesmas regras de `src/api_v1/sala.py`: o guarda `Conta` (hoje só admin, 404 para as outras contas) e
404, não 403, para a operação de outra conta ou que não existe. A conta da cobertura é a de
`src/garantias/cobertura.py`, chamada por `src/banco/garantias.py`: aqui só entram a conta logada e
o desenho das respostas. Valor em dinheiro, haircut e cobertura saem em texto, sem perder casa
decimal. O titular só aparece como id opaco (`titular_ref`); o corpo do erro nunca traz dado da conta.
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api_v1.acesso import exigir_api_ligada
from src.api_v1.sala import SEM_SALA, Conta, _ou_404
from src.banco import garantias, sala
from src.banco.conexao import obter_engine

router = APIRouter(prefix="/v1", dependencies=[Depends(exigir_api_ligada)])


class GarantiaV1(BaseModel):
    id: uuid.UUID
    exposicao_id: uuid.UUID
    tipo: str
    valor_avaliado: str
    moeda: str
    avaliado_em: date
    haircut: str
    liquidez: str
    prioridade: int
    onus_anteriores: str
    valido_ate: date | None
    titular_ref: str | None
    laudo_id: uuid.UUID | None
    laudo_pagina: int | None
    criada_em: datetime


class CoberturaV1(BaseModel):
    """A cobertura com a fórmula e as parcelas (`calcular_cobertura`), tudo em tipos simples."""

    exposicao_id: str
    formula: str
    moeda: str
    exposicao: str | None
    valor_protegido_vigente: str | None
    cobertura: str | None
    cobertura_contando_as_vencidas: str | None
    parcelas: list[dict]
    fora_da_conta: list[dict]


class ExposicaoV1(BaseModel):
    id: uuid.UUID
    rotulo: str
    valor: str
    moeda: str
    vencimento: date | None
    criada_em: datetime
    cobertura: CoberturaV1


def _garantia_v1(g: garantias.Garantia) -> GarantiaV1:
    return GarantiaV1(
        id=g.id,
        exposicao_id=g.exposicao_id,
        tipo=g.tipo,
        valor_avaliado=format(g.valor_avaliado, "f"),
        moeda=g.moeda,
        avaliado_em=g.avaliado_em,
        haircut=format(g.haircut, "f"),
        liquidez=g.liquidez,
        prioridade=g.prioridade,
        onus_anteriores=format(g.onus_anteriores, "f"),
        valido_ate=g.valido_ate,
        titular_ref=g.titular_ref,
        laudo_id=g.laudo_id,
        laudo_pagina=g.laudo_pagina,
        criada_em=g.criada_em,
    )


@router.get("/operacoes/{operacao_id}/garantias")
def listar_garantias(
    conta: Conta, operacao_id: uuid.UUID, exposicao_id: uuid.UUID | None = None
) -> list[GarantiaV1]:
    """As garantias da operação (de uma exposição, se pedida), da mais prioritária à menos."""
    ids = {"usuario_id": conta.id, "operacao_id": operacao_id}
    with obter_engine().connect() as conexao:
        _ou_404(sala.buscar_operacao(conexao, **ids), SEM_SALA)
        return [
            _garantia_v1(g)
            for g in garantias.listar_garantias(
                conexao, **ids, exposicao_id=exposicao_id
            )
        ]


@router.get("/operacoes/{operacao_id}/exposicoes")
def listar_exposicoes(conta: Conta, operacao_id: uuid.UUID) -> list[ExposicaoV1]:
    """As exposições da operação, cada uma com a cobertura calculada na hora."""
    ids = {"usuario_id": conta.id, "operacao_id": operacao_id}
    with obter_engine().connect() as conexao:
        _ou_404(sala.buscar_operacao(conexao, **ids), SEM_SALA)
        saida = []
        for e in garantias.listar_exposicoes(conexao, **ids):
            cobertura = garantias.cobertura_da_exposicao(
                conexao, **ids, exposicao_id=e.id
            )
            if cobertura is None:  # apagada entre as duas leituras
                continue
            saida.append(
                ExposicaoV1(
                    id=e.id,
                    rotulo=e.rotulo,
                    valor=format(e.valor, "f"),
                    moeda=e.moeda,
                    vencimento=e.vencimento,
                    criada_em=e.criada_em,
                    cobertura=CoberturaV1(**cobertura),
                )
            )
        return saida
