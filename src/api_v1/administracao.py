"""A Administração no app novo (linha 955): as rotas que só o administrador alcança.

Leitura: `GET /v1/admin/organizacoes` lista as organizações da API por chave e
`GET /v1/admin/organizacao?id=` devolve o painel de uma (situação, quotas do plano, consumo do mês, chaves
pelo prefixo, direitos em vigor, o que a API oferece e o contrato ainda não liga, o estado da permissão
`pessoa_na_tela` e quantas contas estão vinculadas).

Escrita (PR 3), sempre `POST` com os ids no corpo, nunca no caminho: criar, suspender e reativar uma
organização; emitir, rotacionar e revogar uma chave. São as mesmas funções de
`src/administracao_das_chaves.py` que a Administração antiga usa, numa transação por pedido. O corpo só é
lido depois de `conta_admin` (`corpo`): para quem não é administrador a resposta é o mesmo 404, com corpo
torto, de organização nenhuma ou que nem é JSON. A chave e a organização vão sempre juntas: a chave de uma
organização não se troca nem se revoga pelo id de outra (a resposta é a de uma chave que não existe).
Conceder direito, vincular conta e ligar `pessoa_na_tela` não têm rota: seguem só do dono.

Quem entra: a conta logada, com os termos aceitos **e** administradora no banco, conferida a cada pedido
por `conta_admin`, que é dependência do router inteiro (uma rota nova aqui já nasce fechada; há teste que
cobra). Para qualquer outra conta a resposta é o mesmo 404 de um endereço que não existe, antes de ler o que
foi pedido: a resposta não depende do id, então não diz se ele é de uma organização (que estas rotas existem
não é segredo: o código é público e o visitante recebe 401). As funções de
`src/administracao_das_chaves.py` conferem o administrador de novo, na mesma conexão da leitura; se essa
segunda conferência recusar, a resposta é o mesmo 404.

"Ainda desligado" segue a regra da API por chave: o par conjunto e finalidade (o conjunto contratado para
outra finalidade continua desligado), sobre as linhas do portão mais o que a API serve fora delas
(`ofertas_da_api`, em `src/administracao_das_chaves.py`). Limite: olha o contrato e a suspensão para todos, não se a tabela do conjunto
está pronta nem as marcas da fonte; um conjunto fora da lista ainda pode ser negado pelo portão.

O que nunca sai daqui: o hash de uma chave, e o id, o nome ou o e-mail de uma conta vinculada (sai o
número). O valor de uma chave sai uma única vez, na resposta de quem a emitiu ou rotacionou (`ChaveNovaV1`);
nenhuma leitura o traz (só o prefixo) e este módulo não escreve em log. Nada é guardado em cache (`Cache-Control: no-store`) e estas
rotas ficam fora do contrato público (`openapi_v1`).
"""

import uuid
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.exc import IntegrityError

from src import administracao_das_chaves as adc
from src.administracao import PermissaoNegadaError, exigir_admin
from src.api_v1.acesso import conta_logada, exigir_api_ligada
from src.banco import chaves_da_api as cb
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario
from src.planos import limites_da_api

ORGANIZACAO_INEXISTENTE = "Organização inexistente."
CHAVE_INEXISTENTE = "Chave inexistente ou já revogada."
CNPJ_JA_CADASTRADO = "Já existe uma organização com este CNPJ."
PEDIDO_INVALIDO = "Pedido inválido: confira os campos."


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


class PlanoDaApiV1(BaseModel):
    plano_da_api: str
    nome_do_plano: str


class OrganizacoesV1(BaseModel):
    """A lista e, para os formulários da tela, os planos e os motivos de suspensão que o banco aceita."""

    organizacoes: list[OrganizacaoDaListaV1]
    planos_da_api: list[PlanoDaApiV1]
    motivos_da_suspensao: list[str]


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
    finalidade: str
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
            ConjuntoDesligadoV1(
                conjunto=d.conjunto, finalidade=d.finalidade, motivo=d.motivo
            )
            for d in painel.desligados
        ],
        pessoa_na_tela=painel.pessoa_na_tela,
        membros=painel.membros,
    )


def _da_lista(organizacao: cb.Organizacao) -> OrganizacaoDaListaV1:
    return OrganizacaoDaListaV1(
        id=organizacao.id,
        nome=organizacao.nome,
        plano_da_api=organizacao.plano_da_api,
        nome_do_plano=limites_da_api(organizacao.plano_da_api).nome,
        suspensa=organizacao.suspensa_em is not None,
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
        organizacoes=[_da_lista(organizacao) for organizacao in lista],
        planos_da_api=[
            PlanoDaApiV1(plano_da_api=plano, nome_do_plano=limites_da_api(plano).nome)
            for plano in cb.PLANOS_DA_API
        ],
        motivos_da_suspensao=list(cb.MOTIVOS_DA_SUSPENSAO),
    )


@router.get("/organizacao")
def organizacao(
    conta: Admin, organizacao_id: Annotated[uuid.UUID, Query(alias="id")]
) -> PainelDaOrganizacaoV1:
    """O painel de uma organização: situação, quotas, consumo do mês, chaves (pelo prefixo), direitos em
    vigor e o que ainda está desligado. O id vai na consulta, não no caminho."""
    with obter_engine().connect() as conexao:
        try:
            painel = adc.painel_da_organizacao(
                conexao,
                conta.id,
                organizacao_id,
                hoje(),
                oferecidos=adc.ofertas_da_api(),
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


# --- escrita ------------------------------------------------------------------------------


class _Pedido(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NovaOrganizacaoV1(_Pedido):
    nome: str
    cnpj: str | None = None
    plano_da_api: str


class OrganizacaoPedidaV1(_Pedido):
    id: uuid.UUID


class SuspensaoV1(_Pedido):
    id: uuid.UUID
    motivo: str  # um de `motivos_da_suspensao`, da lista


class EmissaoV1(_Pedido):
    organizacao_id: uuid.UUID


class ChavePedidaV1(_Pedido):
    """A chave vai sempre com a organização dela: o par é conferido no banco."""

    organizacao_id: uuid.UUID
    chave_id: uuid.UUID


class MudouV1(BaseModel):
    mudou: bool  # False: já estava assim


class ChaveNovaV1(BaseModel):
    """A chave recém-emitida. `valor` existe só nesta resposta: a tela mostra uma vez e não guarda."""

    id: uuid.UUID
    prefixo: str
    valor: str
    antiga_vale_por_dias: int | None  # só na rotação: o prazo da chave antiga


def corpo[M: BaseModel](modelo: type[M]) -> Callable[[Request], Coroutine[Any, Any, M]]:
    """A dependência que lê o corpo do pedido como `modelo`.

    A rota não declara o corpo como parâmetro de propósito: o FastAPI leria o JSON antes das dependências,
    e a resposta a quem não é administrador dependeria do que foi mandado. Assim o corpo só é lido depois
    de `conta_admin` (as dependências do router vêm antes das da rota; há teste que cobra)."""

    async def ler(pedido: Request) -> M:
        try:
            return modelo.model_validate_json(await pedido.body())
        except ValidationError:
            # sem encadear: o erro do pydantic repete o que veio no pedido
            raise HTTPException(status_code=422, detail=PEDIDO_INVALIDO) from None

    return ler


@contextmanager
def _escrita(*, organizacao_invalida: int) -> Iterator[sa.Connection]:
    """Uma transação de escrita: a recusa da regra desfaz tudo e vira a resposta, com a frase da regra.

    `organizacao_invalida` é o status de `OrganizacaoInvalidaError`: 422 ao criar (nome, CNPJ ou plano
    que não valem) e 404 nas outras rotas (lá o erro só quer dizer que a organização não existe)."""
    try:
        with obter_engine().begin() as conexao:
            yield conexao
    except (
        PermissaoNegadaError
    ) as erro:  # deixou de ser admin entre a dependência e a escrita
        raise HTTPException(status_code=404) from erro
    except cb.ChaveInexistenteError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except (cb.OrganizacaoSuspensaError, cb.LimiteDeChavesError) as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro
    except cb.OrganizacaoInvalidaError as erro:
        raise HTTPException(
            status_code=organizacao_invalida, detail=str(erro)
        ) from erro
    except ValueError as erro:  # o motivo da suspensão fora da lista
        raise HTTPException(status_code=422, detail=str(erro)) from erro


def _mudou_ou_404(
    conexao: sa.Connection, organizacao_id: uuid.UUID, mudou: bool
) -> MudouV1:
    """`mudou=False` de uma organização que existe é "já estava assim"; de uma que não existe, 404."""
    if not mudou and cb.buscar_organizacao(conexao, organizacao_id) is None:
        raise HTTPException(status_code=404, detail=ORGANIZACAO_INEXISTENTE)
    return MudouV1(mudou=mudou)


@router.post("/organizacoes")
def criar_organizacao(
    conta: Admin,
    pedido: Annotated[NovaOrganizacaoV1, Depends(corpo(NovaOrganizacaoV1))],
) -> OrganizacaoDaListaV1:
    """Cria uma organização da API por chave, sem chave e sem direito nenhum."""
    try:
        with _escrita(organizacao_invalida=422) as conexao:
            criada = adc.criar_organizacao(
                conexao,
                conta.id,
                nome=pedido.nome,
                cnpj=pedido.cnpj,
                plano_da_api=pedido.plano_da_api,
            )
    except IntegrityError:
        # o CNPJ é único na tabela; sem encadear: o erro do banco não vai à resposta nem ao log
        raise HTTPException(status_code=409, detail=CNPJ_JA_CADASTRADO) from None
    return _da_lista(criada)


@router.post("/organizacao/suspender")
def suspender_organizacao(
    conta: Admin, pedido: Annotated[SuspensaoV1, Depends(corpo(SuspensaoV1))]
) -> MudouV1:
    """Suspende a organização: nenhuma chave dela entra até reativar. Nada é apagado."""
    with _escrita(organizacao_invalida=404) as conexao:
        mudou = adc.suspender_organizacao(conexao, conta.id, pedido.id, pedido.motivo)
        return _mudou_ou_404(conexao, pedido.id, mudou)


@router.post("/organizacao/reativar")
def reativar_organizacao(
    conta: Admin,
    pedido: Annotated[OrganizacaoPedidaV1, Depends(corpo(OrganizacaoPedidaV1))],
) -> MudouV1:
    """Reativa a organização suspensa: as chaves dela voltam a entrar."""
    with _escrita(organizacao_invalida=404) as conexao:
        mudou = adc.reativar_organizacao(conexao, conta.id, pedido.id)
        return _mudou_ou_404(conexao, pedido.id, mudou)


@router.post("/chaves/emitir")
def emitir_chave(
    conta: Admin, pedido: Annotated[EmissaoV1, Depends(corpo(EmissaoV1))]
) -> ChaveNovaV1:
    """Emite uma chave para a organização. O valor vem só nesta resposta."""
    with _escrita(organizacao_invalida=404) as conexao:
        nova = adc.emitir_chave(conexao, conta.id, pedido.organizacao_id)
    return ChaveNovaV1(
        id=nova.chave_id,
        prefixo=nova.prefixo,
        valor=nova.valor,
        antiga_vale_por_dias=None,
    )


@router.post("/chaves/rotacionar")
def rotacionar_chave(
    conta: Admin, pedido: Annotated[ChavePedidaV1, Depends(corpo(ChavePedidaV1))]
) -> ChaveNovaV1:
    """Emite a substituta de uma chave ativa; a antiga vale mais `PRAZO_DA_ROTACAO`. O valor da nova vem
    só nesta resposta."""
    with _escrita(organizacao_invalida=404) as conexao:
        nova = adc.rotacionar_chave(
            conexao, conta.id, pedido.organizacao_id, pedido.chave_id
        )
    return ChaveNovaV1(
        id=nova.chave_id,
        prefixo=nova.prefixo,
        valor=nova.valor,
        antiga_vale_por_dias=cb.PRAZO_DA_ROTACAO.days,
    )


@router.post("/chaves/revogar")
def revogar_chave(
    conta: Admin, pedido: Annotated[ChavePedidaV1, Depends(corpo(ChavePedidaV1))]
) -> MudouV1:
    """Revoga a chave: ela para de entrar no pedido seguinte. Não se desfaz."""
    with _escrita(organizacao_invalida=404) as conexao:
        mudou = adc.revogar_chave(
            conexao, conta.id, pedido.organizacao_id, pedido.chave_id
        )
    if not mudou:  # de outra organização, inexistente ou já revogada: a mesma resposta
        raise HTTPException(status_code=404, detail=CHAVE_INEXISTENTE)
    return MudouV1(mudou=True)
