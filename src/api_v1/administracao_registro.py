"""O registro de ações e os eventos do Stripe na Administração do app novo (linha 962, PR 5): duas
leituras, as mesmas da página antiga.

`GET /v1/admin/registro` devolve as últimas ações gravadas na auditoria (mudança de plano e de papel,
bloqueio, chave emitida, acervo exportado, aceite dos termos...), das mais novas para as mais antigas, e
`GET /v1/admin/eventos-do-stripe` os últimos eventos que o webhook processou. Nenhuma das duas muda nada.

Quem entra: como em todo `/v1/admin`, a conta administradora no banco, conferida a cada pedido: as rotas
daqui se registram no `router` único da Administração (`acesso_do_admin`) e chegam ao app por
`src/api_v1/administracao.py`, que importa este módulo. Para quem não é administrador a resposta é o mesmo
404 de um endereço que não existe; as funções da regra (`src/administracao.py`) conferem de novo, na mesma
conexão da leitura.

A auditoria guarda só ids e dados técnicos, nunca e-mail nem nome, e continua assim. Para a tela dizer quem
fez o quê, o e-mail da conta que fez e o da conta que sofreu a ação são lidos na hora, das contas que ainda
existem, e saem só nesta resposta, para o administrador (o mesmo dado que a busca de contas já mostra a
ele); de conta apagada sai só o id. O alvo que não é uma conta (organização, chave, operação) também sai só
como id. Este módulo não escreve em log, nada vai no endereço, nada é guardado em cache
(`Cache-Control: no-store`) e estas rotas ficam fora do contrato público (`openapi_v1`).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from src import administracao as adm
from src.api_v1.acesso_do_admin import Admin, leitura, router
from src.auditoria import Registro

# quantas linhas cada leitura devolve; havendo mais, a resposta avisa (`cortado`)
LIMITE_DO_REGISTRO = 100
LIMITE_DE_EVENTOS = 50


class AcaoV1(BaseModel):
    id: uuid.UUID
    quando: datetime
    acao: str  # o código gravado na auditoria (`plano_alterado`, `chave_emitida`...)
    ator_id: (
        uuid.UUID | None
    )  # nulo: a conta que fez foi apagada, ou foi o próprio serviço
    ator_email: str | None  # só de conta que ainda existe
    alvo_id: uuid.UUID | None
    alvo_email: str | None  # só quando o alvo é uma conta que ainda existe
    foi_voce: bool
    detalhes: dict[str, Any]  # ids e dados técnicos, como a auditoria gravou


class RegistroV1(BaseModel):
    """As últimas ações, das mais novas para as mais antigas."""

    acoes: list[AcaoV1]
    cortado: bool  # há ações mais antigas do que as devolvidas


class EventoDoStripeV1(BaseModel):
    id: str
    tipo: str
    processado_em: datetime


class EventosDoStripeV1(BaseModel):
    """Os últimos eventos do Stripe que o webhook processou, dos mais novos para os mais antigos."""

    eventos: list[EventoDoStripeV1]
    cortado: bool


def _em_utc(momento: datetime) -> datetime:
    """O momento com o fuso escrito: o SQLite devolve a hora sem fuso (o banco grava em UTC), e sem ele
    o navegador leria a hora como se fosse a do computador de quem olha."""
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=UTC)


def _acao(
    linha: Registro, emails: dict[uuid.UUID, str], de_quem_pede: uuid.UUID
) -> AcaoV1:
    return AcaoV1(
        id=linha.id,
        quando=_em_utc(linha.criado_em),
        acao=linha.acao,
        ator_id=linha.ator_id,
        ator_email=emails.get(linha.ator_id) if linha.ator_id else None,
        alvo_id=linha.alvo_id,
        alvo_email=emails.get(linha.alvo_id) if linha.alvo_id else None,
        foi_voce=linha.ator_id == de_quem_pede,
        detalhes=linha.detalhes,
    )


@router.get("/registro")
def registro(conta: Admin) -> RegistroV1:
    """As últimas ações da auditoria: o que foi feito, quando, por qual conta e sobre o quê."""
    with leitura() as conexao:
        # uma a mais do que a tela mostra, só para saber se há ações mais antigas
        linhas = adm.auditoria_recente(conexao, conta.id, LIMITE_DO_REGISTRO + 1)
        mostradas = linhas[:LIMITE_DO_REGISTRO]
        ids = {i for l in mostradas for i in (l.ator_id, l.alvo_id) if i is not None}
        emails = adm.emails_das_contas(conexao, conta.id, ids)
    return RegistroV1(
        acoes=[_acao(linha, emails, conta.id) for linha in mostradas],
        cortado=len(linhas) > LIMITE_DO_REGISTRO,
    )


@router.get("/eventos-do-stripe")
def eventos_do_stripe(conta: Admin) -> EventosDoStripeV1:
    """Os últimos eventos do Stripe processados (id, tipo e quando): servem para conferir se o webhook
    está recebendo."""
    with leitura() as conexao:
        linhas = adm.eventos_recentes_do_stripe(
            conexao, conta.id, LIMITE_DE_EVENTOS + 1
        )
    return EventosDoStripeV1(
        eventos=[
            EventoDoStripeV1(id=id_, tipo=tipo, processado_em=_em_utc(quando))
            for id_, tipo, quando in linhas[:LIMITE_DE_EVENTOS]
        ],
        cortado=len(linhas) > LIMITE_DE_EVENTOS,
    )
