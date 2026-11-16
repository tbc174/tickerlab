"""A Administração no app novo (linha 955): as rotas que só o administrador alcança.

Nesta primeira parte, só leitura: `GET /v1/admin/organizacoes` lista as organizações da API por chave e
`GET /v1/admin/organizacao?id=` devolve o painel de uma (situação, quotas do plano, consumo do mês, chaves
pelo prefixo, direitos em vigor, o que a API oferece e o contrato ainda não liga, o estado da permissão
`pessoa_na_tela` e quantas contas estão vinculadas).

Quem entra: a conta logada, com os termos aceitos **e** administradora no banco, conferida a cada pedido
por `conta_admin`, que é dependência do router inteiro (uma rota nova aqui já nasce fechada; há teste que
cobra). Para qualquer outra conta a resposta é o mesmo 404 de um endereço que não existe, antes de ler o que
foi pedido: não diz que a Administração existe nem se um id é de uma organização. As funções de
`src/administracao_das_chaves.py` conferem o administrador de novo, na mesma conexão da leitura.

O que nunca sai daqui: o valor ou o hash de uma chave (a leitura traz só o prefixo), e o id, o nome ou o
e-mail de uma conta vinculada (sai o número). Nada é guardado em cache (`Cache-Control: no-store`) e estas
rotas ficam fora do contrato público (`openapi_v1`).
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from src import administracao_das_chaves as adc
from src.administracao import PermissaoNegadaError, exigir_admin
from src.api_v1.acesso import conta_logada, exigir_api_ligada
from src.banco import chaves_da_api as cb
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario
from src.planos import limites_da_api
from src.portao_externo import regras_vigentes

ORGANIZACAO_INEXISTENTE = "Organização inexistente."


def conta_admin(conta: Annotated[Usuario, Depends(conta_logada)]) -> Usuario:
    """A conta logada, se for administradora agora (papel e bloqueio relidos do banco); senão o 404 de um
    endereço que não existe."""
    with obter_engine().connect() as conexao:
        try:
            exigir_admin(conexao, conta.id)
        except PermissaoNegadaError as erro:
            # o mesmo corpo da rota inexistente
            raise HTTPException(status_code=404) from erro
    return conta


def sem_cache(resposta: Response) -> None:
    """Nada da Administração fica guardado no navegador nem num intermediário."""
    resposta.headers["Cache-Control"] = "no-store"


Admin = Annotated[Usuario, Depends(conta_admin)]
# `conta_admin` vem antes de tudo o que a rota lê: a recusa não depende do que foi pedido
router = APIRouter(
    prefix="/v1/admin",
    dependencies=[
        Depends(exigir_api_ligada),
        Depends(conta_admin),
        Depends(sem_cache),
    ],
)


def hoje() -> date:
    """O dia de hoje em UTC, o mesmo do consumo e da vigência dos direitos (os testes trocam esta função)."""
    return datetime.now(UTC).date()


def agora() -> datetime:
    """A hora de agora em UTC, para o prazo das chaves (os testes trocam esta função)."""
    return datetime.now(UTC)


class OrganizacaoDaListaV1(BaseModel):
    id: uuid.UUID
    nome: str
    plano_da_api: str
    nome_do_plano: str
    suspensa: bool


class OrganizacoesV1(BaseModel):
    organizacoes: list[OrganizacaoDaListaV1]


class LimitesDoPlanoV1(BaseModel):
    pedidos_por_minuto: int
    pedidos_por_mes: int
    linhas_por_resposta: int
    chaves_ativas: int


class ConsumoDoMesV1(BaseModel):
    pedidos: int
    linhas: int
    negados: int


class ChaveDaOrganizacaoV1(BaseModel):
    """Uma chave pelo que a identifica: nunca o valor nem o hash."""

    id: uuid.UUID
    prefixo: str
    estado: (
        str  # "ativa", "de_saida" (a antiga de uma rotação), "expirada" ou "revogada"
    )
    criada_em: datetime
    expira_em: datetime | None
    revogada_em: datetime | None
    ultimo_uso: datetime | None


class DireitoEmVigorV1(BaseModel):
    conjunto: str
    finalidade: str
    vigente_desde: date
    vigente_ate: date | None


class ConjuntoDesligadoV1(BaseModel):
    conjunto: str
    motivo: str  # "sem_contrato" ou "suspenso_para_todos"


class PainelDaOrganizacaoV1(BaseModel):
    """A organização de relance. `pessoa_na_tela` é só o estado da permissão e `membros`, só o número."""

    id: uuid.UUID
    nome: str
    cnpj: str | None
    plano_da_api: str
    nome_do_plano: str
    criada_em: datetime
    suspensa_em: datetime | None
    motivo_da_suspensao: str | None
    limites: LimitesDoPlanoV1
    consumo: ConsumoDoMesV1
    chaves_ativas: int  # as que ocupam vaga no limite do plano
    chaves: list[ChaveDaOrganizacaoV1]
    direitos: list[DireitoEmVigorV1]
    ainda_desligado: list[ConjuntoDesligadoV1]
    pessoa_na_tela: bool
    membros: int


def _chave(chave: cb.ChaveListada, momento: datetime) -> ChaveDaOrganizacaoV1:
    return ChaveDaOrganizacaoV1(
        id=chave.id,
        prefixo=chave.prefixo,
        estado=adc.estado_da_chave(chave, momento),
        criada_em=chave.criada_em,
        expira_em=chave.expira_em,
        revogada_em=chave.revogada_em,
        ultimo_uso=chave.ultimo_uso,
    )


def _painel(
    painel: adc.PainelDaOrganizacao, momento: datetime
) -> PainelDaOrganizacaoV1:
    organizacao, limites, consumo = (
        painel.visao.organizacao,
        painel.limites,
        painel.visao.consumo,
    )
    return PainelDaOrganizacaoV1(
        id=organizacao.id,
        nome=organizacao.nome,
        cnpj=organizacao.cnpj,
        plano_da_api=organizacao.plano_da_api,
        nome_do_plano=limites.nome,
        criada_em=organizacao.criada_em,
        suspensa_em=organizacao.suspensa_em,
        motivo_da_suspensao=organizacao.motivo_da_suspensao,
        limites=LimitesDoPlanoV1(
            pedidos_por_minuto=limites.pedidos_por_minuto,
            pedidos_por_mes=limites.pedidos_por_mes,
            linhas_por_resposta=limites.linhas_por_resposta,
            chaves_ativas=limites.chaves_ativas,
        ),
        consumo=ConsumoDoMesV1(
            pedidos=consumo.pedidos, linhas=consumo.linhas, negados=consumo.negados
        ),
        chaves_ativas=painel.chaves_ativas,
        chaves=[_chave(chave, momento) for chave in painel.visao.chaves],
        direitos=[
            DireitoEmVigorV1(
                conjunto=direito.conjunto,
                finalidade=direito.finalidade,
                vigente_desde=direito.vigente_desde,
                vigente_ate=direito.vigente_ate,
            )
            for direito in painel.visao.direitos
        ],
        ainda_desligado=[
            ConjuntoDesligadoV1(conjunto=d.conjunto, motivo=d.motivo)
            for d in painel.desligados
        ],
        pessoa_na_tela=painel.pessoa_na_tela,
        membros=painel.membros,
    )


@router.get("/organizacoes")
def organizacoes(conta: Admin) -> OrganizacoesV1:
    """As organizações da API por chave, com o plano e se estão suspensas."""
    with obter_engine().connect() as conexao:
        try:
            lista = adc.listar_organizacoes(conexao, conta.id)
        except (
            PermissaoNegadaError
        ) as erro:  # deixou de ser admin entre as duas leituras
            raise HTTPException(status_code=404) from erro
    return OrganizacoesV1(
        organizacoes=[
            OrganizacaoDaListaV1(
                id=organizacao.id,
                nome=organizacao.nome,
                plano_da_api=organizacao.plano_da_api,
                nome_do_plano=limites_da_api(organizacao.plano_da_api).nome,
                suspensa=organizacao.suspensa_em is not None,
            )
            for organizacao in lista
        ]
    )


@router.get("/organizacao")
def organizacao(
    conta: Admin, organizacao_id: Annotated[uuid.UUID, Query(alias="id")]
) -> PainelDaOrganizacaoV1:
    """O painel de uma organização: situação, quotas, consumo do mês, chaves (pelo prefixo), direitos em
    vigor e o que ainda está desligado. O id vai na consulta, não no caminho."""
    oferecidos = adc.conjuntos_da_api_externa(regras_vigentes().linhas)
    with obter_engine().connect() as conexao:
        try:
            painel = adc.painel_da_organizacao(
                conexao, conta.id, organizacao_id, hoje(), oferecidos=oferecidos
            )
        except (
            PermissaoNegadaError
        ) as erro:  # deixou de ser admin entre as duas leituras
            raise HTTPException(status_code=404) from erro
        except cb.OrganizacaoInvalidaError as erro:
            raise HTTPException(
                status_code=404, detail=ORGANIZACAO_INEXISTENTE
            ) from erro
    return _painel(painel, agora())
