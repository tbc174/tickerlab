"""O funil de originação no banco (B-33): a fase, o próximo passo e os contatos de cada operação.

É um caderno: guarda o que a pessoa anotou e nada mais. Nada aqui envia e-mail ou mensagem, faz
pedido a terceiros nem muda a fase sozinho; a fase só muda por `mudar_fase`, chamada por uma ação da
pessoa. Mesmo isolamento da sala (`src/banco/sala.py`): toda função recebe `usuario_id` (e
`operacao_id`, quando é de um negócio) pelo nome e filtra pelos dois; para outra conta a resposta é a
de um id que não existe (`None` ou `False`; a rota devolve 404, não 403).

Auditoria só com ids e códigos de fase: origem, próximo passo e texto do contato nunca saem daqui.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

import sqlalchemy as sa

from src import auditoria
from src.banco.modelo import (
    FASES_DO_NEGOCIO,
    TAMANHO_MAXIMO_DO_CONTATO,
    TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO,
    contatos_do_negocio,
    negocios_da_originacao,
)
from src.banco.sala import buscar_operacao
from src.sala.retencao import hoje_em_brasilia

FASE_INICIAL = FASES_DO_NEGOCIO[0]
CAMPOS_DO_NEGOCIO = ("origem", "alvo", "proximo_passo", "responsavel")


class NegocioJaExisteError(ValueError):
    """A operação já tem o negócio dela: é um por operação."""


@dataclass(frozen=True)
class Negocio:
    operacao_id: uuid.UUID
    fase: str
    origem: str
    alvo: str | None
    proximo_passo: str | None
    responsavel: str | None
    fase_desde: date
    criado_em: datetime
    atualizado_em: datetime


@dataclass(frozen=True)
class Contato:
    id: uuid.UUID
    operacao_id: uuid.UUID
    descricao: str
    ocorreu_em: date
    registrado_em: datetime


_COLUNAS_DO_NEGOCIO = tuple(
    c for c in negocios_da_originacao.c if c.name != "usuario_id"
)
_COLUNAS_DO_CONTATO = tuple(c for c in contatos_do_negocio.c if c.name != "usuario_id")


def _do_negocio(
    usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> sa.ColumnElement[bool]:
    return sa.and_(
        negocios_da_originacao.c.operacao_id == operacao_id,
        negocios_da_originacao.c.usuario_id == usuario_id,
    )


def _texto_obrigatorio(valor: str, nome: str) -> str:
    limpo = valor.strip()
    if not 1 <= len(limpo) <= TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO:
        raise ValueError(
            f"{nome}: de 1 a {TAMANHO_MAXIMO_DO_TEXTO_DO_NEGOCIO} caracteres."
        )
    return limpo


def _texto_opcional(valor: str | None, nome: str) -> str | None:
    """Texto vazio ou só espaços vira `None` (campo sem preencher)."""
    if valor is None or not valor.strip():
        return None
    return _texto_obrigatorio(valor, nome)


def _fase_valida(fase: str) -> str:
    if fase not in FASES_DO_NEGOCIO:
        raise ValueError(f"Escolha uma destas fases: {', '.join(FASES_DO_NEGOCIO)}.")
    return fase


# --- negócios -----------------------------------------------------------------------------


def abrir_negocio(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    origem: str,
    alvo: str | None = None,
    proximo_passo: str | None = None,
    responsavel: str | None = None,
    hoje: date | None = None,
) -> Negocio | None:
    """Abre o negócio da operação na fase `ideia`; `None` se a operação não é da conta."""
    dados = {
        "origem": _texto_obrigatorio(origem, "Origem"),
        "alvo": _texto_opcional(alvo, "Alvo"),
        "proximo_passo": _texto_opcional(proximo_passo, "Próximo passo"),
        "responsavel": _texto_opcional(responsavel, "Responsável"),
    }
    if buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id) is None:
        return None
    if buscar_negocio(conexao, usuario_id=usuario_id, operacao_id=operacao_id):
        raise NegocioJaExisteError("Esta operação já tem o negócio dela.")
    conexao.execute(
        sa.insert(negocios_da_originacao).values(
            usuario_id=usuario_id,
            operacao_id=operacao_id,
            fase=FASE_INICIAL,
            fase_desde=hoje or hoje_em_brasilia(),
            **dados,
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_NEGOCIO_ABERTO,
        operacao_id,
        {"fase": FASE_INICIAL},
    )
    return buscar_negocio(conexao, usuario_id=usuario_id, operacao_id=operacao_id)


def buscar_negocio(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> Negocio | None:
    """O negócio da operação, se for da conta; `None` se não existe ou é de outra pessoa."""
    linha = conexao.execute(
        sa.select(*_COLUNAS_DO_NEGOCIO).where(_do_negocio(usuario_id, operacao_id))
    ).first()
    return Negocio(**linha._mapping) if linha else None


def listar_negocios(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, fase: str | None = None
) -> list[Negocio]:
    """Os negócios da conta (de uma fase, se pedida), do que mudou de fase há mais tempo ao mais novo."""
    consulta = sa.select(*_COLUNAS_DO_NEGOCIO).where(
        negocios_da_originacao.c.usuario_id == usuario_id
    )
    if fase is not None:
        consulta = consulta.where(negocios_da_originacao.c.fase == _fase_valida(fase))
    consulta = consulta.order_by(
        negocios_da_originacao.c.fase_desde, negocios_da_originacao.c.operacao_id
    )
    return [Negocio(**linha._mapping) for linha in conexao.execute(consulta)]


def mudar_fase(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    fase: str,
    hoje: date | None = None,
) -> Negocio | None:
    """Muda a fase por decisão da pessoa; o único caminho para isso. Mesma fase não muda nada."""
    nova = _fase_valida(fase)
    negocio = buscar_negocio(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
    if negocio is None or negocio.fase == nova:
        return negocio
    conexao.execute(
        sa.update(negocios_da_originacao)
        .where(_do_negocio(usuario_id, operacao_id))
        .values(
            fase=nova,
            fase_desde=hoje or hoje_em_brasilia(),
            atualizado_em=sa.func.now(),
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_NEGOCIO_FASE_MUDADA,
        operacao_id,
        {"de": negocio.fase, "para": nova},
    )
    return buscar_negocio(conexao, usuario_id=usuario_id, operacao_id=operacao_id)


def atualizar_negocio(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    **campos: str | None,
) -> Negocio | None:
    """Troca os campos de texto dados (`origem`, `alvo`, `proximo_passo`, `responsavel`).

    Não mexe na fase. Vazio limpa o campo (menos a origem, que é obrigatória).
    """
    desconhecidos = set(campos) - set(CAMPOS_DO_NEGOCIO)
    if desconhecidos:
        raise ValueError(f"Campo que não existe: {', '.join(sorted(desconhecidos))}.")
    valores = {
        nome: (
            _texto_obrigatorio(texto or "", "Origem")
            if nome == "origem"
            else _texto_opcional(texto, nome)
        )
        for nome, texto in campos.items()
    }
    negocio = buscar_negocio(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
    if negocio is None or not valores:
        return negocio
    conexao.execute(
        sa.update(negocios_da_originacao)
        .where(_do_negocio(usuario_id, operacao_id))
        .values(**valores, atualizado_em=sa.func.now())
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_NEGOCIO_ATUALIZADO,
        operacao_id,
        {"campos": sorted(valores)},
    )
    return buscar_negocio(conexao, usuario_id=usuario_id, operacao_id=operacao_id)


# --- contatos anotados à mão ---------------------------------------------------------------


def registrar_contato(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    descricao: str,
    ocorreu_em: date | None = None,
) -> Contato | None:
    """Anota um contato que a pessoa fez (texto livre); `None` se não há negócio da conta.

    É só o registro: não há destinatário nem canal, e nada é enviado.
    """
    limpa = descricao.strip()
    if not 1 <= len(limpa) <= TAMANHO_MAXIMO_DO_CONTATO:
        raise ValueError(
            f"Descreva o contato em até {TAMANHO_MAXIMO_DO_CONTATO} caracteres."
        )
    if buscar_negocio(conexao, usuario_id=usuario_id, operacao_id=operacao_id) is None:
        return None
    contato_id = uuid.uuid4()
    conexao.execute(
        sa.insert(contatos_do_negocio).values(
            id=contato_id,
            usuario_id=usuario_id,
            operacao_id=operacao_id,
            descricao=limpa,
            ocorreu_em=ocorreu_em or hoje_em_brasilia(),
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_CONTATO_REGISTRADO,
        contato_id,
        {"operacao_id": str(operacao_id)},
    )
    return _buscar_contato(conexao, usuario_id, operacao_id, contato_id)


def _do_contato(
    usuario_id: uuid.UUID, operacao_id: uuid.UUID, contato_id: uuid.UUID
) -> sa.ColumnElement[bool]:
    return sa.and_(
        contatos_do_negocio.c.id == contato_id,
        contatos_do_negocio.c.operacao_id == operacao_id,
        contatos_do_negocio.c.usuario_id == usuario_id,
    )


def _buscar_contato(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    contato_id: uuid.UUID,
) -> Contato | None:
    linha = conexao.execute(
        sa.select(*_COLUNAS_DO_CONTATO).where(
            _do_contato(usuario_id, operacao_id, contato_id)
        )
    ).first()
    return Contato(**linha._mapping) if linha else None


def listar_contatos(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> list[Contato]:
    """Os contatos anotados, do mais recente ao mais antigo; vazia se o negócio não é da conta."""
    linhas = conexao.execute(
        sa.select(*_COLUNAS_DO_CONTATO)
        .where(
            contatos_do_negocio.c.operacao_id == operacao_id,
            contatos_do_negocio.c.usuario_id == usuario_id,
        )
        .order_by(
            contatos_do_negocio.c.ocorreu_em.desc(),
            contatos_do_negocio.c.registrado_em.desc(),
            contatos_do_negocio.c.id,
        )
    )
    return [Contato(**linha._mapping) for linha in linhas]


def apagar_contato(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    contato_id: uuid.UUID,
) -> bool:
    """Apaga o contato, na hora. Devolve se havia o que apagar."""
    apagado = (
        conexao.execute(
            sa.delete(contatos_do_negocio).where(
                _do_contato(usuario_id, operacao_id, contato_id)
            )
        ).rowcount
        > 0
    )
    if apagado:
        auditoria.registrar(
            conexao,
            usuario_id,
            auditoria.ACAO_CONTATO_APAGADO,
            contato_id,
            {"operacao_id": str(operacao_id)},
        )
    return apagado


# --- exportação dos dados (LGPD) ----------------------------------------------------------


def _como_texto(valor: object) -> object:
    if isinstance(valor, date | datetime):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    return valor


def dados_para_exportar(conexao: sa.Connection, *, usuario_id: uuid.UUID) -> list[dict]:
    """O funil inteiro da conta para "Exportar meus dados": um item por negócio, com os contatos."""
    contatos_por_operacao: dict[uuid.UUID, list[dict]] = {}
    for linha in conexao.execute(
        sa.select(*_COLUNAS_DO_CONTATO)
        .where(contatos_do_negocio.c.usuario_id == usuario_id)
        .order_by(contatos_do_negocio.c.ocorreu_em, contatos_do_negocio.c.id)
    ):
        contatos_por_operacao.setdefault(linha.operacao_id, []).append(
            {n: _como_texto(v) for n, v in linha._mapping.items() if n != "operacao_id"}
        )
    return [
        {
            **{n: _como_texto(v) for n, v in vars(negocio).items()},
            "contatos": contatos_por_operacao.get(negocio.operacao_id, []),
        }
        for negocio in listar_negocios(conexao, usuario_id=usuario_id)
    ]


__all__ = [
    "Contato",
    "Negocio",
    "NegocioJaExisteError",
    "abrir_negocio",
    "apagar_contato",
    "atualizar_negocio",
    "buscar_negocio",
    "dados_para_exportar",
    "listar_contatos",
    "listar_negocios",
    "mudar_fase",
    "registrar_contato",
]
