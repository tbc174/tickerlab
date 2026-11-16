"""As contas do app na Administração do app novo (linha 955, PR 4): os números do serviço, a busca de
contas e as quatro mudanças da página antiga (plano, papel, bloquear e desbloquear).

São as mesmas funções de `src/administracao.py` que a Administração antiga usa, numa transação por pedido;
as travas são as da regra (ninguém tira o próprio acesso nem bloqueia a si mesmo, o serviço não fica sem
administrador, e quem está na lista de administradores do servidor não é rebaixado nem bloqueado por aqui)
e chegam à tela com a frase dela. Mudar o plano aqui não cria nem cancela assinatura no Stripe.

Quem entra: como em todo `/v1/admin`, a conta administradora no banco, conferida a cada pedido: as rotas
daqui se registram no `router` único da Administração (`acesso_do_admin`), então uma rota nova já nasce
fechada. Chegam ao app por `src/api_v1/administracao.py`, que importa este módulo. Para quem não é
administrador a resposta é o mesmo 404 de um endereço que não existe, antes de ler o corpo; as funções da
regra conferem de novo, na mesma transação da mudança.

Nada vai no endereço: a busca é `POST` com o termo no corpo, porque o termo costuma ser um e-mail e o
endereço fica no histórico do navegador e pode ficar em log de servidor. Este módulo não escreve em log, e
as recusas não repetem o que veio no pedido. O e-mail e o nome das contas saem só na resposta da busca, para
o administrador. Nada é guardado em cache (`Cache-Control: no-store`) e estas rotas ficam fora do contrato
público (`openapi_v1`).
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, HTTPException
from pydantic import AfterValidator, BaseModel, Field

from src import administracao as adm
from src.api_v1.acesso_do_admin import Admin, Pedido, corpo, router
from src.banco.conexao import obter_engine
from src.banco.modelo import MOTIVOS_DO_BLOQUEIO, PAPEIS, PLANOS

# quantas contas a busca devolve; havendo mais, a resposta avisa (`cortada`) e a tela pede para afinar
LIMITE_DE_CONTAS = 100
TAMANHO_MAXIMO_DA_BUSCA = 200
# o status do Stripe que a página antiga conta como "assinatura ativa"
ASSINATURA_ATIVA = "active"


def _um_de(validos: tuple[str, ...]) -> Callable[[str], str]:
    """A conferência de um campo que só aceita os valores da lista (o erro não repete o que veio)."""

    def conferir(valor: str) -> str:
        if valor not in validos:
            raise ValueError("fora da lista")
        return valor

    return conferir


class ResumoV1(BaseModel):
    """Os números do serviço, os mesmos da página antiga."""

    usuarios: int
    gratuito: int
    plus: int
    pro: int
    administradores: int
    novos_na_semana: int
    ativos_na_semana: int
    simulacoes: int
    assinaturas_ativas: int
    eventos_do_stripe: int


class ContaV1(BaseModel):
    id: uuid.UUID
    email: str
    nome: str | None
    papel: str
    plano: str
    criado_em: datetime
    ultimo_acesso: datetime | None
    status_da_assinatura: str | None
    simulacoes: int
    bloqueada_em: datetime | None
    motivo_do_bloqueio: str | None
    e_voce: bool  # a conta de quem pediu: a tela não oferece tirar o próprio acesso nem se bloquear


class ContasV1(BaseModel):
    """As contas achadas (mais novas primeiro) e, para os formulários da tela, o que o banco aceita."""

    contas: list[ContaV1]
    cortada: bool  # há mais contas do que as devolvidas: afine a busca
    planos: list[str]
    papeis: list[str]
    motivos_do_bloqueio: list[str]


class BuscaV1(Pedido):
    busca: str = Field(default="", max_length=TAMANHO_MAXIMO_DA_BUSCA)


class PlanoPedidoV1(Pedido):
    id: uuid.UUID
    plano: Annotated[str, AfterValidator(_um_de(PLANOS))]


class PapelPedidoV1(Pedido):
    id: uuid.UUID
    papel: Annotated[str, AfterValidator(_um_de(PAPEIS))]


class BloqueioPedidoV1(Pedido):
    id: uuid.UUID
    motivo: Annotated[str, AfterValidator(_um_de(MOTIVOS_DO_BLOQUEIO))]


class ContaPedidaV1(Pedido):
    id: uuid.UUID


class BloqueadaV1(BaseModel):
    sessoes_encerradas: int


@contextmanager
def _leitura() -> Iterator[sa.Connection]:
    try:
        with obter_engine().connect() as conexao:
            yield conexao
    except (
        adm.PermissaoNegadaError
    ) as erro:  # deixou de ser admin entre as duas leituras
        raise HTTPException(status_code=404) from erro


@contextmanager
def _mudanca() -> Iterator[sa.Connection]:
    """Uma transação de escrita: a recusa da regra desfaz tudo e vira a resposta, com a frase da regra
    (as frases da regra não trazem e-mail nem o que veio no pedido)."""
    try:
        with obter_engine().begin() as conexao:
            yield conexao
    except (
        adm.PermissaoNegadaError
    ) as erro:  # deixou de ser admin entre a dependência e a escrita
        raise HTTPException(status_code=404) from erro
    except adm.UsuarioNaoEncontradoError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except adm.OperacaoInvalidaError as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro


def _conta(linha: adm.LinhaDeUsuario, de_quem_pede: uuid.UUID) -> ContaV1:
    return ContaV1(
        id=linha.id,
        email=linha.email,
        nome=linha.nome,
        papel=linha.papel,
        plano=linha.plano,
        criado_em=linha.criado_em,
        ultimo_acesso=linha.ultimo_acesso,
        status_da_assinatura=linha.status_da_assinatura,
        simulacoes=linha.simulacoes,
        bloqueada_em=linha.bloqueada_em,
        motivo_do_bloqueio=linha.motivo_do_bloqueio,
        e_voce=linha.id == de_quem_pede,
    )


@router.get("/resumo")
def resumo(conta: Admin) -> ResumoV1:
    """Os números do serviço: contas por plano, administradores, novas e ativas na semana, simulações,
    assinaturas ativas e eventos do Stripe recebidos."""
    with _leitura() as conexao:
        numeros = adm.resumo_geral(conexao, conta.id)
    return ResumoV1(
        usuarios=numeros["usuarios"],
        gratuito=numeros["gratuito"],
        plus=numeros["plus"],
        pro=numeros["pro"],
        administradores=numeros["administradores"],
        novos_na_semana=numeros["novos_na_semana"],
        ativos_na_semana=numeros["ativos_na_semana"],
        simulacoes=numeros["simulacoes"],
        assinaturas_ativas=numeros["assinaturas_por_status"].get(ASSINATURA_ATIVA, 0),
        eventos_do_stripe=numeros["eventos_do_stripe"],
    )


@router.post("/contas/buscar")
def buscar_contas(
    conta: Admin, pedido: Annotated[BuscaV1, Depends(corpo(BuscaV1))]
) -> ContasV1:
    """As contas do app, mais novas primeiro; `busca` filtra por parte do e-mail ou do nome. É `POST`
    para o termo ir no corpo, e não no endereço."""
    with _leitura() as conexao:
        # uma a mais do que a tela mostra, só para saber se a lista foi cortada
        linhas = adm.listar_usuarios(
            conexao, conta.id, pedido.busca, LIMITE_DE_CONTAS + 1
        )
    return ContasV1(
        contas=[_conta(linha, conta.id) for linha in linhas[:LIMITE_DE_CONTAS]],
        cortada=len(linhas) > LIMITE_DE_CONTAS,
        planos=list(PLANOS),
        papeis=list(PAPEIS),
        motivos_do_bloqueio=list(MOTIVOS_DO_BLOQUEIO),
    )


@router.post("/conta/plano", status_code=204)
def mudar_o_plano(
    conta: Admin, pedido: Annotated[PlanoPedidoV1, Depends(corpo(PlanoPedidoV1))]
) -> None:
    """Muda o plano da conta. Não cria nem cancela assinatura no Stripe."""
    with _mudanca() as conexao:
        adm.alterar_plano(conexao, conta.id, pedido.id, pedido.plano)


@router.post("/conta/papel", status_code=204)
def mudar_o_papel(
    conta: Admin, pedido: Annotated[PapelPedidoV1, Depends(corpo(PapelPedidoV1))]
) -> None:
    """Torna a conta administradora ou comum, dentro das travas da regra."""
    with _mudanca() as conexao:
        adm.alterar_papel(conexao, conta.id, pedido.id, pedido.papel)


@router.post("/conta/bloquear")
def bloquear(
    conta: Admin, pedido: Annotated[BloqueioPedidoV1, Depends(corpo(BloqueioPedidoV1))]
) -> BloqueadaV1:
    """Bloqueia a conta no incidente: encerra as sessões dela na hora e para o login. Não apaga nada."""
    with _mudanca() as conexao:
        encerradas = adm.bloquear_conta(conexao, conta.id, pedido.id, pedido.motivo)
    return BloqueadaV1(sessoes_encerradas=encerradas)


@router.post("/conta/desbloquear", status_code=204)
def desbloquear(
    conta: Admin, pedido: Annotated[ContaPedidaV1, Depends(corpo(ContaPedidaV1))]
) -> None:
    """Tira o bloqueio: o login volta (as sessões encerradas não voltam; a pessoa entra de novo)."""
    with _mudanca() as conexao:
        adm.desbloquear_conta(conexao, conta.id, pedido.id)
