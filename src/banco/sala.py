"""A sala de dados no banco (B-20, PR 1): operações e o registro dos documentos, isolados por conta.

Toda função recebe `usuario_id` (e, quando é de uma operação, `operacao_id`) pelo nome, e toda
consulta filtra pelos dois. Para outra conta, a resposta é a mesma de um id que não existe (`None`
ou `False`): a rota devolve 404, não 403, e não confirma que o id existe (D11). Nem admin vê a sala
de outra pessoa: não há função "de todas as contas" aqui.

Os arquivos cifrados ficam no disco (`src/sala/documentos.py` junta banco, cifra e disco); aqui
ficam a chave da operação (embrulhada pela chave-mestra) e o nonce do documento, que nunca saem
do banco (nem na exportação dos dados).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa

from src import auditoria
from src.banco.modelo import (
    TAMANHO_MAXIMO_DO_NOME_DA_OPERACAO,
    TAMANHO_MAXIMO_DO_NOME_DO_DOCUMENTO,
    TIPOS_DE_DOCUMENTO,
    TIPOS_DE_OPERACAO,
    checklist_da_sala,
    contradicoes_da_sala,
    documentos_da_sala,
    evidencias_da_sala,
    garantias_da_operacao,
    operacoes,
)
from src.sala import retencao

TAMANHO_DO_SHA256 = 64
SITUACOES_DEPOIS_DA_LEITURA = ("lido", "sem_texto", "erro_na_leitura")
CARACTERES_HEXADECIMAIS = frozenset("0123456789abcdef")


class DocumentoRepetidoError(ValueError):
    """O mesmo arquivo (mesmo SHA-256) já está nesta sala."""


@dataclass(frozen=True)
class Operacao:
    id: uuid.UUID
    tipo: str
    nome: str
    situacao: str  # "aberta" ou "encerrada"
    retencao_ate: date
    criada_em: datetime
    atualizada_em: datetime


@dataclass(frozen=True)
class Documento:
    id: uuid.UUID
    operacao_id: uuid.UUID
    nome_original: str
    tipo: str
    tamanho_bytes: int
    paginas: int | None
    sha256: str
    situacao: str  # "na_fila", "lido", "sem_texto" ou "erro_na_leitura"
    lido_por: str | None
    recebido_em: datetime


_COLUNAS_DA_OPERACAO = (
    operacoes.c.id,
    operacoes.c.tipo,
    operacoes.c.nome,
    operacoes.c.situacao,
    operacoes.c.retencao_ate,
    operacoes.c.criada_em,
    operacoes.c.atualizada_em,
)
_COLUNAS_DO_DOCUMENTO = (
    documentos_da_sala.c.id,
    documentos_da_sala.c.operacao_id,
    documentos_da_sala.c.nome_original,
    documentos_da_sala.c.tipo,
    documentos_da_sala.c.tamanho_bytes,
    documentos_da_sala.c.paginas,
    documentos_da_sala.c.sha256,
    documentos_da_sala.c.situacao,
    documentos_da_sala.c.lido_por,
    documentos_da_sala.c.recebido_em,
)


def _da_conta(usuario_id: uuid.UUID, operacao_id: uuid.UUID) -> sa.ColumnElement[bool]:
    return sa.and_(operacoes.c.id == operacao_id, operacoes.c.usuario_id == usuario_id)


def _nome_valido(nome: str, maximo: int) -> str:
    limpo = nome.strip()
    if not 1 <= len(limpo) <= maximo:
        raise ValueError(f"O nome precisa ter de 1 a {maximo} caracteres.")
    return limpo


def _escolha_valida(valor: str, opcoes: tuple[str, ...]) -> str:
    if valor not in opcoes:
        raise ValueError(f"Escolha um destes: {', '.join(opcoes)}.")
    return valor


# --- operações ----------------------------------------------------------------------------


def criar_operacao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    tipo: str,
    nome: str,
    prazo_em_dias: int = retencao.PRAZO_PADRAO_EM_DIAS,
    hoje: date | None = None,
) -> Operacao:
    """Abre uma operação (a sala) da conta, com o prazo em que ela some sozinha."""
    hoje = hoje or retencao.hoje_em_brasilia()
    operacao_id = uuid.uuid4()
    conexao.execute(
        sa.insert(operacoes).values(
            id=operacao_id,
            usuario_id=usuario_id,
            tipo=_escolha_valida(tipo, TIPOS_DE_OPERACAO),
            nome=_nome_valido(nome, TAMANHO_MAXIMO_DO_NOME_DA_OPERACAO),
            retencao_ate=retencao.prazo_inicial(hoje, prazo_em_dias),
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_OPERACAO_CRIADA,
        operacao_id,
        {"tipo": tipo, "prazo_em_dias": prazo_em_dias},
    )
    operacao = buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
    assert operacao is not None  # acabou de entrar, na mesma transação
    return operacao


def listar_operacoes(
    conexao: sa.Connection, *, usuario_id: uuid.UUID
) -> list[Operacao]:
    """As operações da conta, da mais antiga para a mais nova."""
    linhas = conexao.execute(
        sa.select(*_COLUNAS_DA_OPERACAO)
        .where(operacoes.c.usuario_id == usuario_id)
        .order_by(operacoes.c.criada_em, operacoes.c.id)
    )
    return [Operacao(**linha._mapping) for linha in linhas]


def buscar_operacao(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> Operacao | None:
    """A operação, se for da conta; `None` se não existe ou é de outra pessoa."""
    linha = conexao.execute(
        sa.select(*_COLUNAS_DA_OPERACAO).where(_da_conta(usuario_id, operacao_id))
    ).first()
    return Operacao(**linha._mapping) if linha else None


def _mudar_operacao(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    **valores: object,
) -> Operacao | None:
    conexao.execute(
        sa.update(operacoes)
        .where(_da_conta(usuario_id, operacao_id))
        .values(**valores, atualizada_em=sa.func.now())
    )
    return buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id)


def encerrar_operacao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    hoje: date | None = None,
) -> Operacao | None:
    """Encerra a operação e deixa 30 dias para baixar a sala; encerrar de novo não muda nada."""
    operacao = buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
    if operacao is None or operacao.situacao == "encerrada":
        return operacao
    hoje = hoje or retencao.hoje_em_brasilia()
    return _mudar_operacao(
        conexao,
        usuario_id,
        operacao_id,
        situacao="encerrada",
        retencao_ate=retencao.prazo_ao_encerrar(hoje),
    )


def prorrogar_operacao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    dias: int,
    hoje: date | None = None,
) -> Operacao | None:
    """Empurra o prazo em que a operação some (até 365 dias a partir de hoje)."""
    operacao = buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
    if operacao is None:
        return None
    hoje = hoje or retencao.hoje_em_brasilia()
    novo = retencao.prazo_prorrogado(operacao.retencao_ate, hoje, dias)
    return _mudar_operacao(conexao, usuario_id, operacao_id, retencao_ate=novo)


def apagar_operacao(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> bool:
    """Apaga a operação e, em cascata, tudo o que há na sala. Devolve se havia o que apagar."""
    apagada = (
        conexao.execute(
            sa.delete(operacoes).where(_da_conta(usuario_id, operacao_id))
        ).rowcount
        > 0
    )
    if apagada:
        auditoria.registrar(
            conexao, usuario_id, auditoria.ACAO_OPERACAO_APAGADA, operacao_id, {}
        )
    return apagada


# --- documentos ---------------------------------------------------------------------------


def _sha256_valido(sha256: str) -> str:
    if len(sha256) != TAMANHO_DO_SHA256 or not set(sha256) <= CARACTERES_HEXADECIMAIS:
        raise ValueError("SHA-256 em hexadecimal minúsculo, com 64 caracteres.")
    return sha256


def _ja_esta_na_sala(
    conexao: sa.Connection, usuario_id: uuid.UUID, operacao_id: uuid.UUID, sha256: str
) -> bool:
    return (
        conexao.execute(
            sa.select(documentos_da_sala.c.id).where(
                documentos_da_sala.c.usuario_id == usuario_id,
                documentos_da_sala.c.operacao_id == operacao_id,
                documentos_da_sala.c.sha256 == sha256,
            )
        ).first()
        is not None
    )


def registrar_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    nome_original: str,
    tipo: str,
    tamanho_bytes: int,
    sha256: str,
) -> Documento | None:
    """Registra um documento recebido na sala (na fila para ler); `None` se a sala não é da conta.

    O nome do arquivo fica só aqui: nunca vai para a auditoria nem para os logs.
    """
    if tamanho_bytes <= 0:
        raise ValueError("Arquivo vazio.")
    dados = {
        "nome_original": _nome_valido(
            nome_original, TAMANHO_MAXIMO_DO_NOME_DO_DOCUMENTO
        ),
        "tipo": _escolha_valida(tipo, TIPOS_DE_DOCUMENTO),
        "tamanho_bytes": tamanho_bytes,
        "sha256": _sha256_valido(sha256),
    }
    if buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id) is None:
        return None
    if _ja_esta_na_sala(conexao, usuario_id, operacao_id, sha256):
        raise DocumentoRepetidoError("Este arquivo já está nesta sala.")
    documento_id = uuid.uuid4()
    conexao.execute(
        sa.insert(documentos_da_sala).values(
            id=documento_id, usuario_id=usuario_id, operacao_id=operacao_id, **dados
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_DOCUMENTO_ENVIADO,
        documento_id,
        {"operacao_id": str(operacao_id), "tipo": tipo, "tamanho_bytes": tamanho_bytes},
    )
    return _buscar_documento(conexao, usuario_id, operacao_id, documento_id)


def _do_documento(
    usuario_id: uuid.UUID, operacao_id: uuid.UUID, documento_id: uuid.UUID
) -> sa.ColumnElement[bool]:
    return sa.and_(
        documentos_da_sala.c.id == documento_id,
        documentos_da_sala.c.operacao_id == operacao_id,
        documentos_da_sala.c.usuario_id == usuario_id,
    )


def _buscar_documento(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
) -> Documento | None:
    linha = conexao.execute(
        sa.select(*_COLUNAS_DO_DOCUMENTO).where(
            _do_documento(usuario_id, operacao_id, documento_id)
        )
    ).first()
    return Documento(**linha._mapping) if linha else None


def buscar_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
) -> Documento | None:
    """O documento, se for da sala e da conta; `None` se não existe ou é de outra pessoa."""
    return _buscar_documento(conexao, usuario_id, operacao_id, documento_id)


def chave_da_operacao(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> tuple[bytes, int] | None:
    """A chave da operação embrulhada e a versão da chave-mestra; `None` se ainda não há chave."""
    linha = conexao.execute(
        sa.select(operacoes.c.chave_cifrada, operacoes.c.versao_da_chave).where(
            _da_conta(usuario_id, operacao_id), operacoes.c.chave_cifrada.is_not(None)
        )
    ).first()
    return (linha.chave_cifrada, linha.versao_da_chave) if linha else None


def guardar_chave_da_operacao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    chave_cifrada: bytes,
    versao_da_chave: int,
) -> bool:
    """Grava a chave da operação, só se ela ainda não tem uma. Devolve se gravou.

    Nunca troca uma chave existente: os arquivos já cifrados com ela ficariam ilegíveis. Dois
    envios ao mesmo tempo numa sala nova: um grava, o outro lê a chave que ficou.
    """
    return (
        conexao.execute(
            sa.update(operacoes)
            .where(
                _da_conta(usuario_id, operacao_id), operacoes.c.chave_cifrada.is_(None)
            )
            .values(chave_cifrada=chave_cifrada, versao_da_chave=versao_da_chave)
        ).rowcount
        > 0
    )


def guardar_nonce(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    nonce: bytes,
) -> bool:
    """Grava o nonce da cifra do arquivo original. Devolve se o documento é da conta."""
    return (
        conexao.execute(
            sa.update(documentos_da_sala)
            .where(_do_documento(usuario_id, operacao_id, documento_id))
            .values(nonce=nonce)
        ).rowcount
        > 0
    )


def nonce_do_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
) -> bytes | None:
    """O nonce da cifra do original; `None` se o documento não é da conta ou não tem arquivo."""
    return conexao.execute(
        sa.select(documentos_da_sala.c.nonce).where(
            _do_documento(usuario_id, operacao_id, documento_id)
        )
    ).scalar()


def marcar_leitura(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    situacao: str,
    paginas: int | None,
    lido_por: str,
) -> bool:
    """Grava o resultado da leitura (`lido`, `sem_texto` ou `erro_na_leitura`) e as páginas."""
    if situacao not in SITUACOES_DEPOIS_DA_LEITURA:
        raise ValueError(f"Situação depois da leitura: {SITUACOES_DEPOIS_DA_LEITURA}.")
    return (
        conexao.execute(
            sa.update(documentos_da_sala)
            .where(_do_documento(usuario_id, operacao_id, documento_id))
            .values(situacao=situacao, paginas=paginas, lido_por=lido_por)
        ).rowcount
        > 0
    )


def listar_documentos(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> list[Documento]:
    """Os documentos da sala, na ordem em que chegaram; lista vazia se a sala não é da conta."""
    linhas = conexao.execute(
        sa.select(*_COLUNAS_DO_DOCUMENTO)
        .where(
            documentos_da_sala.c.operacao_id == operacao_id,
            documentos_da_sala.c.usuario_id == usuario_id,
        )
        .order_by(documentos_da_sala.c.recebido_em, documentos_da_sala.c.id)
    )
    return [Documento(**linha._mapping) for linha in linhas]


def _soltar_do_checklist(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
) -> None:
    # o item que estava "recebido" por causa deste documento volta a "pendente"; os outros estados
    # foram escolhidos pela pessoa e ficam
    da_sala = sa.and_(
        checklist_da_sala.c.documento_id == documento_id,
        checklist_da_sala.c.operacao_id == operacao_id,
        checklist_da_sala.c.usuario_id == usuario_id,
    )
    conexao.execute(
        sa.update(checklist_da_sala)
        .where(da_sala)
        .values(
            documento_id=None,
            estado=sa.case(
                (checklist_da_sala.c.estado == "recebido", "pendente"),
                else_=checklist_da_sala.c.estado,
            ),
            atualizado_em=sa.func.now(),
        )
    )


def _soltar_das_garantias(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
) -> None:
    # a garantia fica (é dado da pessoa); só perde o laudo e a página citada
    conexao.execute(
        sa.update(garantias_da_operacao)
        .where(
            garantias_da_operacao.c.laudo_id == documento_id,
            garantias_da_operacao.c.operacao_id == operacao_id,
            garantias_da_operacao.c.usuario_id == usuario_id,
        )
        .values(laudo_id=None, laudo_pagina=None, atualizada_em=sa.func.now())
    )


def apagar_documento(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
) -> bool:
    """Apaga o documento, as evidências dele (em cascata) e o solta do checklist, na hora."""
    if _buscar_documento(conexao, usuario_id, operacao_id, documento_id) is None:
        return False
    _soltar_do_checklist(conexao, usuario_id, operacao_id, documento_id)
    _soltar_das_garantias(conexao, usuario_id, operacao_id, documento_id)
    conexao.execute(
        sa.delete(documentos_da_sala).where(
            _do_documento(usuario_id, operacao_id, documento_id)
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_DOCUMENTO_APAGADO,
        documento_id,
        {"operacao_id": str(operacao_id)},
    )
    return True


# --- exportação dos dados (LGPD) ----------------------------------------------------------


def _texto(valor: object) -> object:
    if isinstance(valor, date | datetime):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return format(valor.normalize(), "f")  # 100.000000 -> "100", sem notação 1E+2
    if isinstance(valor, uuid.UUID):
        return str(valor)
    return valor


# o que sai no "Exportar meus dados", coluna por coluna (lista fechada: coluna nova não sai sem
# alguém decidir; `test_sala_banco` trava que toda coluna está aqui ou em COLUNAS_QUE_NAO_SAEM)
COLUNAS_EXPORTADAS: dict[str, tuple[str, ...]] = {
    "documentos_da_sala": (
        "id",
        "operacao_id",
        "nome_original",
        "tipo",
        "tamanho_bytes",
        "paginas",
        "sha256",
        "situacao",
        "lido_por",
        "recebido_em",
    ),
    "evidencias_da_sala": (
        "id",
        "operacao_id",
        "documento_id",
        "metrica",
        "periodo",
        "valor_numero",
        "valor_texto",
        "unidade",
        "moeda",
        "pagina",
        "secao",
        "tabela",
        "trecho",
        "conferida",
        "extraido_por",
        "estado_de_revisao",
        "criada_em",
    ),
    "contradicoes_da_sala": (
        "id",
        "operacao_id",
        "evidencia_a",
        "evidencia_b",
        "diferenca",
        "estado",
        "nota",
        "criada_em",
    ),
    "checklist_da_sala": (
        "id",
        "operacao_id",
        "codigo",
        "estado",
        "documento_id",
        "nota",
        "atualizado_em",
    ),
}
# o que nunca sai: a conta (já é a da pessoa) e o que só serve para decifrar os arquivos
COLUNAS_QUE_NAO_SAEM: dict[str, frozenset[str]] = {
    "operacoes": frozenset({"usuario_id", "chave_cifrada", "versao_da_chave"}),
    "documentos_da_sala": frozenset({"usuario_id", "nonce"}),
    "evidencias_da_sala": frozenset({"usuario_id"}),
    "contradicoes_da_sala": frozenset({"usuario_id"}),
    "checklist_da_sala": frozenset({"usuario_id"}),
}


def _linhas(
    conexao: sa.Connection, tabela: sa.Table, usuario_id: uuid.UUID
) -> dict[uuid.UUID, list[dict]]:
    """As linhas da conta numa tabela da sala, agrupadas pela operação, só nas colunas exportadas."""
    colunas = [tabela.c[nome] for nome in COLUNAS_EXPORTADAS[tabela.name]]
    por_operacao: dict[uuid.UUID, list[dict]] = {}
    for linha in conexao.execute(
        sa.select(*colunas)
        .where(tabela.c.usuario_id == usuario_id)
        .order_by(tabela.c.id)
    ):
        dados = {nome: _texto(valor) for nome, valor in linha._mapping.items()}
        por_operacao.setdefault(linha.operacao_id, []).append(dados)
    return por_operacao


def dados_para_exportar(conexao: sa.Connection, *, usuario_id: uuid.UUID) -> list[dict]:
    """A sala inteira da conta para "Exportar meus dados": metadados, sem o conteúdo dos arquivos.

    Só saem as colunas de `COLUNAS_EXPORTADAS` (a operação sai pelos campos de `Operacao`): a chave
    da operação e o nonce do arquivo ficam de fora, porque não dizem nada à pessoa e só serviriam
    para decifrar o arquivo. Os arquivos saem pelo "Baixar a sala" (PR 3).
    """
    documentos = _linhas(conexao, documentos_da_sala, usuario_id)
    evidencias = _linhas(conexao, evidencias_da_sala, usuario_id)
    contradicoes = _linhas(conexao, contradicoes_da_sala, usuario_id)
    checklist = _linhas(conexao, checklist_da_sala, usuario_id)
    return [
        {
            **{nome: _texto(valor) for nome, valor in vars(operacao).items()},
            "documentos": documentos.get(operacao.id, []),
            "evidencias": evidencias.get(operacao.id, []),
            "contradicoes": contradicoes.get(operacao.id, []),
            "checklist": checklist.get(operacao.id, []),
        }
        for operacao in listar_operacoes(conexao, usuario_id=usuario_id)
    ]
