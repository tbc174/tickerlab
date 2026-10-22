"""Organizações, chaves e direitos da API externa no banco (N7; ADR 0108, linha 117).

As regras da chave (formato, hash, contexto) ficam em `src/chaves_da_api.py`; as quotas, em
`src/planos.py`. Aqui ficam as consultas, com o mesmo isolamento da sala: toda função de uma
organização recebe `organizacao_id` pelo nome e filtra por ele; para outra organização a resposta é a
de um id que não existe (`False`, `[]` ou `ChaveInexistenteError`).

Nada se apaga para suspender ou revogar: preenche-se `suspensa_em`, `suspenso_em` ou `revogada_em`.
O consumo (D10) é agregado por organização, chave, dia (UTC), canal, finalidade e conjunto: sem IP,
parâmetro de busca nem corpo de resposta.
A auditoria leva só ids, o prefixo da chave e códigos; nunca a chave, o hash nem o nome da organização.
Quem chama (o script do admin, PR 3) decide quando fazer o commit.
"""

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from base import cnpj as cnpj_
from src import auditoria
from src.banco.modelo import (
    FINALIDADES_DA_ORGANIZACAO,
    MOTIVOS_DA_SUSPENSAO,
    PLANOS_DA_API,
    TAMANHO_MAXIMO_DO_CONJUNTO,
    TAMANHO_MAXIMO_DO_NOME_DA_ORGANIZACAO,
    chaves_da_api,
    consumo_da_api,
    direitos_da_organizacao,
    organizacoes,
)
from src.chaves_da_api import (
    TAMANHO_DO_HASH,
    ChaveNova,
    ContextoDaChave,
    MotivoDaRecusa,
    gerar_chave,
    hash_da_chave,
    separar,
)
from src.planos import limites_da_api

log = logging.getLogger(__name__)

PRAZO_DA_ROTACAO = timedelta(
    days=7
)  # a antiga vale mais uma semana para o cliente trocar
INTERVALO_DO_ULTIMO_USO = timedelta(
    hours=1
)  # gravar a cada pedido seria uma escrita por pedido
_INSERT_DO_BANCO = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}
# comparado quando o prefixo não existe, para os dois caminhos fazerem a mesma conta
_HASH_DE_NINGUEM = "0" * TAMANHO_DO_HASH


class OrganizacaoInvalidaError(ValueError):
    """Nome, CNPJ ou plano da API que não serve, ou organização que não existe."""


class OrganizacaoSuspensaError(ValueError):
    """A organização está suspensa: não ganha chave nova até ser reativada."""


class LimiteDeChavesError(ValueError):
    """A organização já tem as chaves ativas que o plano da API permite."""


class ChaveInexistenteError(LookupError):
    """A chave não existe, é de outra organização, foi revogada ou já está de saída."""


@dataclass(frozen=True)
class Organizacao:
    id: uuid.UUID
    nome: str
    cnpj: str | None
    plano_da_api: str
    suspensa_em: datetime | None
    motivo_da_suspensao: str | None
    criada_em: datetime


@dataclass(frozen=True)
class ChaveListada:
    """O que se mostra de uma chave: nunca o hash."""

    id: uuid.UUID
    prefixo: str
    criada_em: datetime
    expira_em: datetime | None
    revogada_em: datetime | None
    ultimo_uso: datetime | None


@dataclass(frozen=True)
class ConsumoDoMes:
    """A soma do mês de uma organização: `pedidos` aceitos (é o que a quota conta), as `linhas`
    servidas neles e os `negados` (o portão ou o contrato disseram não)."""

    pedidos: int
    linhas: int
    negados: int


@dataclass(frozen=True)
class Direito:
    id: uuid.UUID
    organizacao_id: uuid.UUID
    conjunto: str
    finalidade: str
    vigente_desde: date
    vigente_ate: date | None
    suspenso_em: datetime | None


def _agora() -> datetime:
    return datetime.now(UTC)


def _com_fuso(momento: datetime | None) -> datetime | None:
    # o SQLite devolve a hora sem fuso: ela foi gravada em UTC
    if momento is None or momento.tzinfo is not None:
        return momento
    return momento.replace(tzinfo=UTC)


# ---------------------------------------------------------------- organização


def _nome_valido(nome: str) -> str:
    limpo = nome.strip()
    if not limpo or len(limpo) > TAMANHO_MAXIMO_DO_NOME_DA_ORGANIZACAO:
        raise OrganizacaoInvalidaError(
            f"O nome da organização precisa ter de 1 a "
            f"{TAMANHO_MAXIMO_DO_NOME_DA_ORGANIZACAO} caracteres."
        )
    return limpo


def _cnpj_valido(cnpj: str | None) -> str | None:
    if cnpj is None:
        return None
    completo = cnpj_.completo(cnpj)
    if completo is None or not cnpj_.dv_confere(completo):
        raise OrganizacaoInvalidaError("CNPJ inválido.")
    return completo


def _organizacao(linha: sa.Row) -> Organizacao:
    return Organizacao(
        id=linha.id,
        nome=linha.nome,
        cnpj=linha.cnpj,
        plano_da_api=linha.plano_da_api,
        suspensa_em=_com_fuso(linha.suspensa_em),
        motivo_da_suspensao=linha.motivo_da_suspensao,
        criada_em=_com_fuso(linha.criada_em),  # type: ignore[arg-type]
    )


def criar_organizacao(
    conexao: sa.Connection,
    *,
    nome: str,
    ator_id: uuid.UUID,
    cnpj: str | None = None,
    plano_da_api: str = PLANOS_DA_API[0],
    agora: datetime | None = None,
) -> Organizacao:
    if plano_da_api not in PLANOS_DA_API:
        raise OrganizacaoInvalidaError("Plano da API desconhecido.")
    organizacao_id = uuid.uuid4()
    conexao.execute(
        sa.insert(organizacoes).values(
            id=organizacao_id,
            nome=_nome_valido(nome),
            cnpj=_cnpj_valido(cnpj),
            plano_da_api=plano_da_api,
            criada_em=agora or _agora(),
            criada_por=ator_id,
        )
    )
    auditoria.registrar(
        conexao,
        ator_id,
        auditoria.ACAO_ORGANIZACAO_CRIADA,
        alvo_id=organizacao_id,
        detalhes={"plano_da_api": plano_da_api},
    )
    criada = buscar_organizacao(conexao, organizacao_id)
    assert criada is not None
    return criada


def buscar_organizacao(
    conexao: sa.Connection, organizacao_id: uuid.UUID, *, travar: bool = False
) -> Organizacao | None:
    """A organização, ou None. `travar` segura a linha até o commit (emitir e rotacionar chaves)."""
    consulta = sa.select(organizacoes).where(organizacoes.c.id == organizacao_id)
    if travar:
        consulta = consulta.with_for_update()
    linha = conexao.execute(consulta).one_or_none()
    return None if linha is None else _organizacao(linha)


def listar_organizacoes(conexao: sa.Connection) -> list[Organizacao]:
    """Todas as organizações, da mais antiga para a mais nova (só o admin chama; ver `src/administracao_das_chaves.py`)."""
    linhas = conexao.execute(
        sa.select(organizacoes).order_by(organizacoes.c.criada_em, organizacoes.c.id)
    )
    return [_organizacao(linha) for linha in linhas]


def _organizacao_ativa(
    conexao: sa.Connection, organizacao_id: uuid.UUID
) -> Organizacao:
    organizacao = buscar_organizacao(conexao, organizacao_id, travar=True)
    if organizacao is None:
        raise OrganizacaoInvalidaError("Organização inexistente.")
    if organizacao.suspensa_em is not None:
        raise OrganizacaoSuspensaError("A organização está suspensa.")
    return organizacao


def suspender_organizacao(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    motivo: str,
    ator_id: uuid.UUID,
    agora: datetime | None = None,
) -> bool:
    """Todas as chaves da organização param de entrar; nada é apagado. False se já estava."""
    if motivo not in MOTIVOS_DA_SUSPENSAO:
        raise ValueError(
            f"Motivo da suspensão fora da lista: {', '.join(MOTIVOS_DA_SUSPENSAO)}."
        )
    mudou = conexao.execute(
        sa.update(organizacoes)
        .where(
            organizacoes.c.id == organizacao_id, organizacoes.c.suspensa_em.is_(None)
        )
        .values(suspensa_em=agora or _agora(), motivo_da_suspensao=motivo)
    ).rowcount
    if mudou:
        auditoria.registrar(
            conexao,
            ator_id,
            auditoria.ACAO_ORGANIZACAO_SUSPENSA,
            alvo_id=organizacao_id,
            detalhes={"motivo": motivo},
        )
    return bool(mudou)


def reativar_organizacao(
    conexao: sa.Connection, *, organizacao_id: uuid.UUID, ator_id: uuid.UUID
) -> bool:
    mudou = conexao.execute(
        sa.update(organizacoes)
        .where(
            organizacoes.c.id == organizacao_id, organizacoes.c.suspensa_em.is_not(None)
        )
        .values(suspensa_em=None, motivo_da_suspensao=None)
    ).rowcount
    if mudou:
        auditoria.registrar(
            conexao,
            ator_id,
            auditoria.ACAO_ORGANIZACAO_REATIVADA,
            alvo_id=organizacao_id,
        )
    return bool(mudou)


# ---------------------------------------------------------------- chaves


def _gravar_chave(
    conexao: sa.Connection,
    organizacao_id: uuid.UUID,
    ator_id: uuid.UUID,
    agora: datetime,
) -> ChaveNova:
    prefixo, valor = gerar_chave()
    chave_id = uuid.uuid4()
    conexao.execute(
        sa.insert(chaves_da_api).values(
            id=chave_id,
            organizacao_id=organizacao_id,
            prefixo=prefixo,
            hash_da_chave=hash_da_chave(valor),
            criada_em=agora,
            criada_por=ator_id,
        )
    )
    return ChaveNova(chave_id=chave_id, prefixo=prefixo, valor=valor)


def _chaves_ativas(conexao: sa.Connection, organizacao_id: uuid.UUID) -> int:
    # a antiga de uma rotação (com `expira_em`) está de saída e não ocupa vaga
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(chaves_da_api)
        .where(
            chaves_da_api.c.organizacao_id == organizacao_id,
            chaves_da_api.c.revogada_em.is_(None),
            chaves_da_api.c.expira_em.is_(None),
        )
    ).scalar_one()


def emitir_chave(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    ator_id: uuid.UUID,
    agora: datetime | None = None,
) -> ChaveNova:
    """Uma chave nova. O valor só existe nesta volta: mostre uma vez e não guarde."""
    organizacao = _organizacao_ativa(conexao, organizacao_id)
    maximo = limites_da_api(organizacao.plano_da_api).chaves_ativas
    if _chaves_ativas(conexao, organizacao_id) >= maximo:
        raise LimiteDeChavesError(
            f"O plano da API permite {maximo} chaves ativas: revogue ou rotacione uma."
        )
    nova = _gravar_chave(conexao, organizacao_id, ator_id, agora or _agora())
    auditoria.registrar(
        conexao,
        ator_id,
        auditoria.ACAO_CHAVE_EMITIDA,
        alvo_id=nova.chave_id,
        detalhes={"organizacao_id": str(organizacao_id), "prefixo": nova.prefixo},
    )
    return nova


def rotacionar_chave(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    chave_id: uuid.UUID,
    ator_id: uuid.UUID,
    agora: datetime | None = None,
) -> ChaveNova:
    """Emite a substituta e deixa a antiga valer por `PRAZO_DA_ROTACAO`.

    Só gira uma chave ativa e sem prazo: a revogada, a que já está de saída e a de outra
    organização dão `ChaveInexistenteError`.
    """
    momento = agora or _agora()
    _organizacao_ativa(conexao, organizacao_id)
    mudou = conexao.execute(
        sa.update(chaves_da_api)
        .where(
            chaves_da_api.c.id == chave_id,
            chaves_da_api.c.organizacao_id == organizacao_id,
            chaves_da_api.c.revogada_em.is_(None),
            chaves_da_api.c.expira_em.is_(None),
        )
        .values(expira_em=momento + PRAZO_DA_ROTACAO)
    ).rowcount
    if not mudou:
        raise ChaveInexistenteError("Chave inexistente, revogada ou já em rotação.")
    nova = _gravar_chave(conexao, organizacao_id, ator_id, momento)
    auditoria.registrar(
        conexao,
        ator_id,
        auditoria.ACAO_CHAVE_ROTACIONADA,
        alvo_id=chave_id,
        detalhes={
            "organizacao_id": str(organizacao_id),
            "chave_nova_id": str(nova.chave_id),
            "prefixo": nova.prefixo,
        },
    )
    return nova


def revogar_chave(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    chave_id: uuid.UUID,
    ator_id: uuid.UUID,
    agora: datetime | None = None,
) -> bool:
    """A chave para de entrar no pedido seguinte. False se já estava revogada ou não é desta."""
    mudou = conexao.execute(
        sa.update(chaves_da_api)
        .where(
            chaves_da_api.c.id == chave_id,
            chaves_da_api.c.organizacao_id == organizacao_id,
            chaves_da_api.c.revogada_em.is_(None),
        )
        .values(revogada_em=agora or _agora())
    ).rowcount
    if mudou:
        auditoria.registrar(
            conexao,
            ator_id,
            auditoria.ACAO_CHAVE_REVOGADA,
            alvo_id=chave_id,
            detalhes={"organizacao_id": str(organizacao_id)},
        )
    return bool(mudou)


def listar_chaves(
    conexao: sa.Connection, organizacao_id: uuid.UUID
) -> list[ChaveListada]:
    linhas = conexao.execute(
        sa.select(
            chaves_da_api.c.id,
            chaves_da_api.c.prefixo,
            chaves_da_api.c.criada_em,
            chaves_da_api.c.expira_em,
            chaves_da_api.c.revogada_em,
            chaves_da_api.c.ultimo_uso,
        )
        .where(chaves_da_api.c.organizacao_id == organizacao_id)
        .order_by(chaves_da_api.c.criada_em, chaves_da_api.c.prefixo)
    )
    return [
        ChaveListada(
            id=linha.id,
            prefixo=linha.prefixo,
            criada_em=_com_fuso(linha.criada_em),  # type: ignore[arg-type]
            expira_em=_com_fuso(linha.expira_em),
            revogada_em=_com_fuso(linha.revogada_em),
            ultimo_uso=_com_fuso(linha.ultimo_uso),
        )
        for linha in linhas
    ]


def _recusa(motivo: MotivoDaRecusa, prefixo: str | None) -> MotivoDaRecusa:
    # o motivo fica no log; para fora, toda recusa é o mesmo 401 (D8). Nunca o segredo.
    log.info("chave da API recusada: %s (prefixo %s)", motivo.value, prefixo or "-")
    return motivo


def _marcar_uso(
    conexao: sa.Connection,
    chave_id: uuid.UUID,
    ultimo_uso: datetime | None,
    agora: datetime,
) -> None:
    if ultimo_uso is not None and agora - ultimo_uso < INTERVALO_DO_ULTIMO_USO:
        return
    conexao.execute(
        sa.update(chaves_da_api)
        .where(chaves_da_api.c.id == chave_id)
        .values(ultimo_uso=agora)
    )


def conferir_chave(
    conexao: sa.Connection, texto: str, *, agora: datetime | None = None
) -> ContextoDaChave | MotivoDaRecusa:
    """O contexto da organização dona da chave, ou o motivo da recusa (lista fechada).

    O prefixo acha a linha; o hash da chave inteira é comparado em tempo constante, também quando
    o prefixo não existe (contra um hash de ninguém), para o tempo não dizer qual parte errou.
    """
    momento = agora or _agora()
    prefixo = separar(texto)
    if prefixo is None:
        return _recusa(MotivoDaRecusa.FORMATO, None)
    linha = conexao.execute(
        sa.select(
            chaves_da_api.c.id,
            chaves_da_api.c.organizacao_id,
            chaves_da_api.c.hash_da_chave,
            chaves_da_api.c.expira_em,
            chaves_da_api.c.revogada_em,
            chaves_da_api.c.ultimo_uso,
            organizacoes.c.plano_da_api,
            organizacoes.c.suspensa_em,
        )
        .join(organizacoes, organizacoes.c.id == chaves_da_api.c.organizacao_id)
        .where(chaves_da_api.c.prefixo == prefixo)
    ).one_or_none()
    esperado = _HASH_DE_NINGUEM if linha is None else linha.hash_da_chave
    confere = hmac.compare_digest(hash_da_chave(texto), esperado)
    if linha is None or not confere:
        return _recusa(MotivoDaRecusa.DESCONHECIDA, prefixo)
    if linha.revogada_em is not None:
        return _recusa(MotivoDaRecusa.REVOGADA, prefixo)
    expira_em = _com_fuso(linha.expira_em)
    if expira_em is not None and expira_em <= momento:
        return _recusa(MotivoDaRecusa.VENCIDA, prefixo)
    if linha.suspensa_em is not None:
        return _recusa(MotivoDaRecusa.ORGANIZACAO_SUSPENSA, prefixo)
    _marcar_uso(conexao, linha.id, _com_fuso(linha.ultimo_uso), momento)
    return ContextoDaChave(
        organizacao_id=linha.organizacao_id,
        chave_id=linha.id,
        prefixo=prefixo,
        plano_da_api=linha.plano_da_api,
    )


# ---------------------------------------------------------------- direitos (o contrato)


def _direito(linha: sa.Row) -> Direito:
    return Direito(
        id=linha.id,
        organizacao_id=linha.organizacao_id,
        conjunto=linha.conjunto,
        finalidade=linha.finalidade,
        vigente_desde=linha.vigente_desde,
        vigente_ate=linha.vigente_ate,
        suspenso_em=_com_fuso(linha.suspenso_em),
    )


def _conjunto_valido(conjunto: str) -> str:
    limpo = conjunto.strip()
    if not limpo or len(limpo) > TAMANHO_MAXIMO_DO_CONJUNTO:
        raise ValueError(
            f"O conjunto precisa ter de 1 a {TAMANHO_MAXIMO_DO_CONJUNTO} caracteres."
        )
    return limpo


def _finalidade_valida(finalidade: str) -> str:
    if finalidade not in FINALIDADES_DA_ORGANIZACAO:
        raise ValueError(
            "A finalidade de uma organização é "
            f"{' ou '.join(FINALIDADES_DA_ORGANIZACAO)} (treino nunca)."
        )
    return finalidade


def conceder_direito(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    conjunto: str,
    finalidade: str,
    vigente_desde: date,
    ator_id: uuid.UUID,
    vigente_ate: date | None = None,
    agora: datetime | None = None,
) -> Direito:
    """Uma linha do contrato: o conjunto, para que finalidade e de quando a quando.

    Sozinha não libera nada: o pedido passa só se esta linha e o portão (N3) deixarem.
    """
    _finalidade_valida(finalidade)
    if vigente_ate is not None and vigente_ate < vigente_desde:
        raise ValueError("A vigência termina antes de começar.")
    if buscar_organizacao(conexao, organizacao_id) is None:
        raise OrganizacaoInvalidaError("Organização inexistente.")
    direito_id = uuid.uuid4()
    conjunto = _conjunto_valido(conjunto)
    conexao.execute(
        sa.insert(direitos_da_organizacao).values(
            id=direito_id,
            organizacao_id=organizacao_id,
            conjunto=conjunto,
            finalidade=finalidade,
            vigente_desde=vigente_desde,
            vigente_ate=vigente_ate,
            criado_em=agora or _agora(),
            criado_por=ator_id,
        )
    )
    auditoria.registrar(
        conexao,
        ator_id,
        auditoria.ACAO_DIREITO_CONCEDIDO,
        alvo_id=direito_id,
        detalhes={
            "organizacao_id": str(organizacao_id),
            "conjunto": conjunto,
            "finalidade": finalidade,
        },
    )
    linha = conexao.execute(
        sa.select(direitos_da_organizacao).where(
            direitos_da_organizacao.c.id == direito_id
        )
    ).one()
    return _direito(linha)


def _mudar_suspensao_do_direito(
    conexao: sa.Connection,
    organizacao_id: uuid.UUID,
    direito_id: uuid.UUID,
    suspenso_em: datetime | None,
) -> bool:
    ja_estava = (
        direitos_da_organizacao.c.suspenso_em.is_(None)
        if suspenso_em is not None
        else direitos_da_organizacao.c.suspenso_em.is_not(None)
    )
    return bool(
        conexao.execute(
            sa.update(direitos_da_organizacao)
            .where(
                direitos_da_organizacao.c.id == direito_id,
                direitos_da_organizacao.c.organizacao_id == organizacao_id,
                ja_estava,
            )
            .values(suspenso_em=suspenso_em)
        ).rowcount
    )


def suspender_direito(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    direito_id: uuid.UUID,
    ator_id: uuid.UUID,
    agora: datetime | None = None,
) -> bool:
    """O conjunto para de sair para esta organização; a linha fica. False se já estava."""
    mudou = _mudar_suspensao_do_direito(
        conexao, organizacao_id, direito_id, agora or _agora()
    )
    if mudou:
        auditoria.registrar(
            conexao,
            ator_id,
            auditoria.ACAO_DIREITO_SUSPENSO,
            alvo_id=direito_id,
            detalhes={"organizacao_id": str(organizacao_id)},
        )
    return mudou


def reativar_direito(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    direito_id: uuid.UUID,
    ator_id: uuid.UUID,
) -> bool:
    mudou = _mudar_suspensao_do_direito(conexao, organizacao_id, direito_id, None)
    if mudou:
        auditoria.registrar(
            conexao,
            ator_id,
            auditoria.ACAO_DIREITO_REATIVADO,
            alvo_id=direito_id,
            detalhes={"organizacao_id": str(organizacao_id)},
        )
    return mudou


def _vigente(organizacao_id: uuid.UUID, dia: date) -> list[sa.ColumnElement[bool]]:
    tabela = direitos_da_organizacao
    return [
        tabela.c.organizacao_id == organizacao_id,
        tabela.c.suspenso_em.is_(None),
        tabela.c.vigente_desde <= dia,
        sa.or_(tabela.c.vigente_ate.is_(None), tabela.c.vigente_ate >= dia),
    ]


def direitos_vigentes(
    conexao: sa.Connection, organizacao_id: uuid.UUID, dia: date
) -> list[Direito]:
    """As linhas do contrato que valem no dia: não suspensas e dentro da vigência."""
    tabela = direitos_da_organizacao
    linhas = conexao.execute(
        sa.select(tabela)
        .where(*_vigente(organizacao_id, dia))
        .order_by(tabela.c.conjunto, tabela.c.finalidade)
    )
    return [_direito(linha) for linha in linhas]


def contrato_permite(
    conexao: sa.Connection,
    organizacao_id: uuid.UUID,
    *,
    conjunto: str,
    finalidade: str,
    dia: date,
) -> bool:
    """O contrato da organização tem linha vigente no dia para este conjunto e finalidade?"""
    tabela = direitos_da_organizacao
    return conexao.execute(
        sa.select(
            sa.exists().where(
                *_vigente(organizacao_id, dia),
                tabela.c.conjunto == conjunto,
                tabela.c.finalidade == finalidade,
            )
        )
    ).scalar_one()


# ---------------------------------------------------------------- consumo (D10)


def registrar_consumo(
    conexao: sa.Connection,
    contexto: ContextoDaChave,
    *,
    conjunto: str,
    finalidade: str,
    linhas: int,
    negado: bool = False,
    agora: datetime | None = None,
) -> None:
    """Soma um pedido da chave do `contexto` na linha do dia (UTC). Negado conta só em `negados`."""
    if linhas < 0:
        raise ValueError("O número de linhas servidas não pode ser negativo.")
    pedidos, servidas, negados = (0, 0, 1) if negado else (1, linhas, 0)
    inserir = _INSERT_DO_BANCO[conexao.dialect.name](consumo_da_api)
    conexao.execute(
        inserir.values(
            organizacao_id=contexto.organizacao_id,
            chave_id=contexto.chave_id,
            dia=(agora or _agora()).astimezone(UTC).date(),
            canal=contexto.canal.value,
            finalidade=_finalidade_valida(finalidade),
            conjunto=_conjunto_valido(conjunto),
            pedidos=pedidos,
            linhas=servidas,
            negados=negados,
        ).on_conflict_do_update(
            index_elements=list(consumo_da_api.primary_key.columns),
            set_={
                "pedidos": consumo_da_api.c.pedidos + inserir.excluded.pedidos,
                "linhas": consumo_da_api.c.linhas + inserir.excluded.linhas,
                "negados": consumo_da_api.c.negados + inserir.excluded.negados,
            },
        )
    )


def consumo_do_mes(
    conexao: sa.Connection, organizacao_id: uuid.UUID, dia: date
) -> ConsumoDoMes:
    """A soma do mês (UTC) que contém `dia`, de todas as chaves da organização."""
    inicio = dia.replace(day=1)
    fim = (inicio + timedelta(days=32)).replace(day=1)
    pedidos, linhas, negados = conexao.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(consumo_da_api.c.pedidos), 0),
            sa.func.coalesce(sa.func.sum(consumo_da_api.c.linhas), 0),
            sa.func.coalesce(sa.func.sum(consumo_da_api.c.negados), 0),
        ).where(
            consumo_da_api.c.organizacao_id == organizacao_id,
            consumo_da_api.c.dia >= inicio,
            consumo_da_api.c.dia < fim,
        )
    ).one()
    return ConsumoDoMes(pedidos=int(pedidos), linhas=int(linhas), negados=int(negados))
