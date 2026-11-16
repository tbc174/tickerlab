"""A administração das chaves da API externa para a tela do admin (N7, linha 169).

Cada função confere no banco que quem pede é administrador (`exigir_admin`) e só então chama as
consultas de `src/banco/chaves_da_api.py`, as mesmas do script `scripts/chaves_da_api.py`. Quem chama
decide o commit. A chave nova (`ChaveNova.valor`) só existe na volta de `emitir` e `rotacionar`: a
tela mostra uma vez e não guarda; aqui ela não vai para log nem para auditoria (que leva só ids e o
prefixo) e a visão da organização nunca carrega o hash.

O painel (`painel_da_organizacao`, linha 955) é a mesma visão com o que a Administração do app novo
mostra de relance: as quotas do plano, quantas chaves ocupam vaga, o que a API oferece e o contrato
ainda não liga, e a permissão `pessoa_na_tela` e os membros só como estado e número.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

import sqlalchemy as sa

from src.administracao import exigir_admin
from src.api_externa.conjuntos import novidades
from src.banco import chaves_da_api as cb
from src.banco import membros_da_organizacao as membros
from src.chaves_da_api import ChaveNova
from src.planos import LimitesDaApi, limites_da_api
from src.portao_externo import Canal, Finalidade, LinhaDeDireito, regras_vigentes

# os erros que o admin pode causar e que a mensagem já explica (a tela mostra o texto, sem traceback)
ERROS_ESPERADOS = (
    cb.OrganizacaoInvalidaError,
    cb.OrganizacaoSuspensaError,
    cb.LimiteDeChavesError,
    cb.ChaveInexistenteError,
    ValueError,
)

# o estado de uma chave na lista (a de saída é a antiga de uma rotação, dentro do prazo)
CHAVE_ATIVA = "ativa"
CHAVE_DE_SAIDA = "de_saida"
CHAVE_EXPIRADA = "expirada"
CHAVE_REVOGADA = "revogada"

# por que um conjunto da API ainda não sai para a organização
MOTIVO_SEM_CONTRATO = "sem_contrato"
MOTIVO_SUSPENSO_PARA_TODOS = "suspenso_para_todos"

# o que a API por chave libera de cada vez: o par (conjunto, finalidade)
type Oferta = tuple[str, str]
# o que a API por chave serve conferindo o contrato direto, sem linha de direito no portão (há teste
# que cobra: conjunto novo em `src/api_externa/conjuntos/` sem linha no portão tem de entrar aqui)
OFERTAS_FORA_DO_PORTAO: frozenset[Oferta] = frozenset(
    {(novidades.CONJUNTO, Finalidade.ANALISE.value)}
)


@dataclass(frozen=True)
class VisaoDaOrganizacao:
    """O que a tela mostra de uma organização: nunca o hash nem a chave."""

    organizacao: cb.Organizacao
    chaves: list[cb.ChaveListada]
    direitos: list[cb.Direito]
    consumo: cb.ConsumoDoMes


@dataclass(frozen=True)
class ConjuntoDesligado:
    """Um conjunto que a API oferece, para uma finalidade, e que hoje não sai para a organização, com o
    motivo."""

    conjunto: str
    finalidade: str
    motivo: str


@dataclass(frozen=True)
class PainelDaOrganizacao:
    """A organização de relance. Das contas vinculadas sai só o número: nunca o id nem o e-mail."""

    visao: VisaoDaOrganizacao
    limites: LimitesDaApi
    chaves_ativas: int
    desligados: list[ConjuntoDesligado]
    pessoa_na_tela: bool
    membros: int


def estado_da_chave(chave: cb.ChaveListada, agora: datetime) -> str:
    """Revogada ganha de tudo; com prazo, a chave é a antiga de uma rotação (de saída ou já vencida)."""
    if chave.revogada_em is not None:
        return CHAVE_REVOGADA
    if chave.expira_em is None:
        return CHAVE_ATIVA
    return CHAVE_DE_SAIDA if chave.expira_em > agora else CHAVE_EXPIRADA


def chaves_que_ocupam_vaga(chaves: Iterable[cb.ChaveListada]) -> int:
    """Quantas contam para o limite do plano: a mesma regra de quem emite (sem revogação e sem prazo)."""
    return sum(
        1 for chave in chaves if chave.revogada_em is None and chave.expira_em is None
    )


def ofertas_da_api_externa(linhas: Iterable[LinhaDeDireito]) -> frozenset[Oferta]:
    """O que a API por chave oferece, tirado das linhas de direito do portão: o par conjunto e
    finalidade, o mesmo que o catálogo da chave e o `contrato_permite` conferem."""
    return frozenset(
        (linha.conjunto, linha.finalidade.value)
        for linha in linhas
        if linha.canal == Canal.API_EXTERNA
    )


def ofertas_da_api() -> frozenset[Oferta]:
    """Todo par (conjunto, finalidade) que a API por chave serve hoje: as linhas vigentes do portão
    mais o que ela serve fora delas."""
    return ofertas_da_api_externa(regras_vigentes().linhas) | OFERTAS_FORA_DO_PORTAO


def conjuntos_desligados(
    oferecidos: Iterable[Oferta],
    contratados: Iterable[Oferta],
    suspensos_para_todos: Iterable[str],
) -> list[ConjuntoDesligado]:
    """O que a API oferece menos o que o contrato liga, par a par (conjunto e finalidade), em ordem de
    nome: o conjunto contratado para outra finalidade continua desligado. O conjunto parado para todas
    as organizações aparece com esse motivo, mesmo que o contrato o tenha."""
    suspensos = set(suspensos_para_todos)
    ligados = {oferta for oferta in contratados if oferta[0] not in suspensos}
    return [
        ConjuntoDesligado(
            conjunto,
            finalidade,
            MOTIVO_SUSPENSO_PARA_TODOS
            if conjunto in suspensos
            else MOTIVO_SEM_CONTRATO,
        )
        for conjunto, finalidade in sorted(set(oferecidos) - ligados)
    ]


def listar_organizacoes(
    conexao: sa.Connection, ator_id: uuid.UUID
) -> list[cb.Organizacao]:
    exigir_admin(conexao, ator_id)
    return cb.listar_organizacoes(conexao)


def ver_organizacao(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID, hoje: date
) -> VisaoDaOrganizacao:
    """Chaves (pelo prefixo), direitos vigentes e consumo do mês de `hoje` (UTC)."""
    exigir_admin(conexao, ator_id)
    organizacao = cb.buscar_organizacao(conexao, organizacao_id)
    if organizacao is None:
        raise cb.OrganizacaoInvalidaError("Organização inexistente.")
    return VisaoDaOrganizacao(
        organizacao=organizacao,
        chaves=cb.listar_chaves(conexao, organizacao_id),
        direitos=cb.direitos_vigentes(conexao, organizacao_id, hoje),
        consumo=cb.consumo_do_mes(conexao, organizacao_id, hoje),
    )


def painel_da_organizacao(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    organizacao_id: uuid.UUID,
    hoje: date,
    *,
    oferecidos: Iterable[Oferta],
) -> PainelDaOrganizacao:
    """A visão da organização mais as quotas do plano, o que ainda está desligado dentre os pares
    (conjunto, finalidade) `oferecidos` pela API, a permissão `pessoa_na_tela` (só o estado) e quantas
    contas estão vinculadas.

    "Desligado" olha só o contrato e a suspensão para todos. Não olha se a tabela do conjunto está pronta
    nem as marcas da fonte: um conjunto contratado pode estar fora desta lista e ainda assim ser negado
    pelo portão."""
    visao = ver_organizacao(conexao, ator_id, organizacao_id, hoje)  # confere o admin
    suspensos = {s.conjunto for s in cb.conjuntos_suspensos_agora(conexao)}
    contratados = {(d.conjunto, d.finalidade) for d in visao.direitos}
    return PainelDaOrganizacao(
        visao=visao,
        limites=limites_da_api(visao.organizacao.plano_da_api),
        chaves_ativas=chaves_que_ocupam_vaga(visao.chaves),
        desligados=conjuntos_desligados(oferecidos, contratados, suspensos),
        pessoa_na_tela=cb.contrato_permite(
            conexao,
            organizacao_id,
            conjunto=membros.CONJUNTO_DE_PESSOA_NA_TELA,
            finalidade=membros.FINALIDADE_DA_TELA,
            dia=hoje,
        ),
        membros=len(membros.listar_membros(conexao, organizacao_id)),
    )


def criar_organizacao(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    *,
    nome: str,
    cnpj: str | None,
    plano_da_api: str,
) -> cb.Organizacao:
    exigir_admin(conexao, ator_id)
    return cb.criar_organizacao(
        conexao,
        nome=nome,
        cnpj=cnpj or None,
        plano_da_api=plano_da_api,
        ator_id=ator_id,
    )


def emitir_chave(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID
) -> ChaveNova:
    exigir_admin(conexao, ator_id)
    return cb.emitir_chave(conexao, organizacao_id=organizacao_id, ator_id=ator_id)


def rotacionar_chave(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    organizacao_id: uuid.UUID,
    chave_id: uuid.UUID,
) -> ChaveNova:
    exigir_admin(conexao, ator_id)
    return cb.rotacionar_chave(
        conexao, organizacao_id=organizacao_id, chave_id=chave_id, ator_id=ator_id
    )


def revogar_chave(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    organizacao_id: uuid.UUID,
    chave_id: uuid.UUID,
) -> bool:
    exigir_admin(conexao, ator_id)
    return cb.revogar_chave(
        conexao, organizacao_id=organizacao_id, chave_id=chave_id, ator_id=ator_id
    )


def suspender_organizacao(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID, motivo: str
) -> bool:
    exigir_admin(conexao, ator_id)
    return cb.suspender_organizacao(
        conexao, organizacao_id=organizacao_id, motivo=motivo, ator_id=ator_id
    )


def reativar_organizacao(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID
) -> bool:
    exigir_admin(conexao, ator_id)
    return cb.reativar_organizacao(
        conexao, organizacao_id=organizacao_id, ator_id=ator_id
    )
