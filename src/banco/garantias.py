"""As garantias das operações da sala no banco (B-17): exposição, garantia e a cobertura delas.

É um caderno com uma conta: guarda o que a pessoa anotou e calcula a cobertura com a fórmula à vista
(`src/garantias/cobertura.py`). Nada aqui diz se a garantia é boa ou ruim, converte moeda ou mexe numa
garantia vencida: validade vencida é só alerta. Mesmo isolamento da sala (`src/banco/sala.py`): toda
função recebe `usuario_id` e `operacao_id` pelo nome e filtra pelos dois; para outra conta a resposta é
a de um id que não existe (`None` ou `False`; a rota devolve 404, não 403).

Titular e avalista entram só como id opaco (`titular_ref`); o nome fica no laudo, que é um documento da
sala. Auditoria só com ids e códigos: rótulo, titular e valores nunca saem daqui.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa

from src import auditoria
from src.banco.modelo import (
    LIQUIDEZES_DA_GARANTIA,
    TAMANHO_MAXIMO_DO_ROTULO_DA_EXPOSICAO,
    TIPOS_DE_GARANTIA,
    exposicoes_da_operacao,
    garantias_da_operacao,
)
from src.banco.sala import buscar_documento, buscar_operacao
from src.garantias.cobertura import GarantiaParaAConta, calcular_cobertura
from src.sala.retencao import hoje_em_brasilia

_MOEDA = re.compile(r"[A-Z]{3}")
_REFERENCIA = re.compile(r"[A-Za-z0-9_:\-]{1,60}")
_SO_DIGITOS_E_TRACOS = re.compile(r"[\d\-]+")


@dataclass(frozen=True)
class Exposicao:
    id: uuid.UUID
    operacao_id: uuid.UUID
    rotulo: str
    valor: Decimal
    moeda: str
    vencimento: date | None
    criada_em: datetime
    atualizada_em: datetime


@dataclass(frozen=True)
class Garantia:
    id: uuid.UUID
    operacao_id: uuid.UUID
    exposicao_id: uuid.UUID
    tipo: str
    valor_avaliado: Decimal
    moeda: str
    avaliado_em: date
    haircut: Decimal
    liquidez: str
    prioridade: int
    onus_anteriores: Decimal
    valido_ate: date | None
    titular_ref: str | None
    laudo_id: uuid.UUID | None
    laudo_pagina: int | None
    criada_em: datetime
    atualizada_em: datetime


_COLUNAS_DA_EXPOSICAO = tuple(
    c for c in exposicoes_da_operacao.c if c.name != "usuario_id"
)
_COLUNAS_DA_GARANTIA = tuple(
    c for c in garantias_da_operacao.c if c.name != "usuario_id"
)


def _da_exposicao(
    usuario_id: uuid.UUID, operacao_id: uuid.UUID, exposicao_id: uuid.UUID
) -> sa.ColumnElement[bool]:
    return sa.and_(
        exposicoes_da_operacao.c.id == exposicao_id,
        exposicoes_da_operacao.c.operacao_id == operacao_id,
        exposicoes_da_operacao.c.usuario_id == usuario_id,
    )


def _da_garantia(
    usuario_id: uuid.UUID, operacao_id: uuid.UUID, garantia_id: uuid.UUID
) -> sa.ColumnElement[bool]:
    return sa.and_(
        garantias_da_operacao.c.id == garantia_id,
        garantias_da_operacao.c.operacao_id == operacao_id,
        garantias_da_operacao.c.usuario_id == usuario_id,
    )


def _moeda_valida(moeda: str) -> str:
    codigo = moeda.strip().upper()
    if not _MOEDA.fullmatch(codigo):
        raise ValueError("Moeda: o código de 3 letras, como BRL.")
    return codigo


def _valor_valido(valor: Decimal, nome: str, *, positivo: bool = False) -> Decimal:
    if not isinstance(valor, Decimal) or not valor.is_finite():
        raise ValueError(f"{nome}: um número.")
    if valor < 0 or (positivo and valor == 0):
        raise ValueError(f"{nome}: {'maior que zero' if positivo else 'zero ou mais'}.")
    return valor


def _titular_valido(titular_ref: str | None) -> str | None:
    """Só id opaco: recusa o que parece CPF e qualquer texto com espaço, ponto ou barra (nome)."""
    if titular_ref is None or not titular_ref.strip():
        return None
    ref = titular_ref.strip()
    if not _REFERENCIA.fullmatch(ref) or (
        _SO_DIGITOS_E_TRACOS.fullmatch(ref) and len(re.sub(r"\D", "", ref)) == 11
    ):
        raise ValueError(
            "Titular: use o id (letras, números, - _ :), nunca nome nem CPF."
        )
    return ref


# --- exposições ---------------------------------------------------------------------------


def registrar_exposicao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    rotulo: str,
    valor: Decimal,
    moeda: str,
    vencimento: date | None = None,
) -> Exposicao | None:
    """Registra a dívida a cobrir; `None` se a operação não é da conta."""
    limpo = rotulo.strip()
    if not 1 <= len(limpo) <= TAMANHO_MAXIMO_DO_ROTULO_DA_EXPOSICAO:
        raise ValueError(
            f"Rótulo: de 1 a {TAMANHO_MAXIMO_DO_ROTULO_DA_EXPOSICAO} caracteres."
        )
    dados = {
        "rotulo": limpo,
        "valor": _valor_valido(valor, "Valor", positivo=True),
        "moeda": _moeda_valida(moeda),
        "vencimento": vencimento,
    }
    if buscar_operacao(conexao, usuario_id=usuario_id, operacao_id=operacao_id) is None:
        return None
    exposicao_id = uuid.uuid4()
    conexao.execute(
        sa.insert(exposicoes_da_operacao).values(
            id=exposicao_id, usuario_id=usuario_id, operacao_id=operacao_id, **dados
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_EXPOSICAO_REGISTRADA,
        exposicao_id,
        {"operacao_id": str(operacao_id)},
    )
    return buscar_exposicao(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        exposicao_id=exposicao_id,
    )


def buscar_exposicao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    exposicao_id: uuid.UUID,
) -> Exposicao | None:
    linha = conexao.execute(
        sa.select(*_COLUNAS_DA_EXPOSICAO).where(
            _da_exposicao(usuario_id, operacao_id, exposicao_id)
        )
    ).first()
    return Exposicao(**linha._mapping) if linha else None


def listar_exposicoes(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> list[Exposicao]:
    linhas = conexao.execute(
        sa.select(*_COLUNAS_DA_EXPOSICAO)
        .where(
            exposicoes_da_operacao.c.operacao_id == operacao_id,
            exposicoes_da_operacao.c.usuario_id == usuario_id,
        )
        .order_by(exposicoes_da_operacao.c.criada_em, exposicoes_da_operacao.c.id)
    )
    return [Exposicao(**linha._mapping) for linha in linhas]


def apagar_exposicao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    exposicao_id: uuid.UUID,
) -> bool:
    """Apaga a exposição e, em cascata, as garantias que a cobrem."""
    apagada = (
        conexao.execute(
            sa.delete(exposicoes_da_operacao).where(
                _da_exposicao(usuario_id, operacao_id, exposicao_id)
            )
        ).rowcount
        > 0
    )
    if apagada:
        auditoria.registrar(
            conexao,
            usuario_id,
            auditoria.ACAO_EXPOSICAO_APAGADA,
            exposicao_id,
            {"operacao_id": str(operacao_id)},
        )
    return apagada


# --- garantias ----------------------------------------------------------------------------


def _laudo_valido(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    laudo_id: uuid.UUID | None,
    laudo_pagina: int | None,
) -> None:
    if (laudo_id is None) != (laudo_pagina is None):
        raise ValueError("Laudo: informe o documento e a página citada, os dois.")
    if laudo_id is None:
        return
    if laudo_pagina is None or laudo_pagina < 1:
        raise ValueError("Laudo: a página começa em 1.")
    documento = buscar_documento(
        conexao, usuario_id=usuario_id, operacao_id=operacao_id, documento_id=laudo_id
    )
    if documento is None:
        raise ValueError("Laudo: escolha um documento desta sala.")
    # o total de páginas só se sabe depois da leitura; antes disso a página citada não é conferida
    if documento.paginas and laudo_pagina > documento.paginas:
        raise ValueError("Laudo: o documento não tem essa página.")


def registrar_garantia(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    exposicao_id: uuid.UUID,
    tipo: str,
    valor_avaliado: Decimal,
    moeda: str,
    avaliado_em: date,
    haircut: Decimal,
    liquidez: str,
    prioridade: int = 1,
    onus_anteriores: Decimal = Decimal(0),
    valido_ate: date | None = None,
    titular_ref: str | None = None,
    laudo_id: uuid.UUID | None = None,
    laudo_pagina: int | None = None,
) -> Garantia | None:
    """Registra a garantia de uma exposição; `None` se a exposição não é da conta e da operação."""
    if tipo not in TIPOS_DE_GARANTIA:
        raise ValueError(f"Tipo: escolha um destes: {', '.join(TIPOS_DE_GARANTIA)}.")
    if liquidez not in LIQUIDEZES_DA_GARANTIA:
        raise ValueError(f"Liquidez: {', '.join(LIQUIDEZES_DA_GARANTIA)}.")
    if prioridade < 1:
        raise ValueError("Prioridade: 1 ou mais.")
    haircut_valido = _valor_valido(haircut, "Haircut")
    if haircut_valido > 1:
        raise ValueError("Haircut: uma fração de 0 a 1 (0,30 é 30%).")
    dados = {
        "tipo": tipo,
        "valor_avaliado": _valor_valido(valor_avaliado, "Valor avaliado"),
        "moeda": _moeda_valida(moeda),
        "avaliado_em": avaliado_em,
        "haircut": haircut_valido,
        "liquidez": liquidez,
        "prioridade": prioridade,
        "onus_anteriores": _valor_valido(onus_anteriores, "Ônus anteriores"),
        "valido_ate": valido_ate,
        "titular_ref": _titular_valido(titular_ref),
    }
    if (
        buscar_exposicao(
            conexao,
            usuario_id=usuario_id,
            operacao_id=operacao_id,
            exposicao_id=exposicao_id,
        )
        is None
    ):
        return None
    _laudo_valido(conexao, usuario_id, operacao_id, laudo_id, laudo_pagina)
    garantia_id = uuid.uuid4()
    conexao.execute(
        sa.insert(garantias_da_operacao).values(
            id=garantia_id,
            usuario_id=usuario_id,
            operacao_id=operacao_id,
            exposicao_id=exposicao_id,
            laudo_id=laudo_id,
            laudo_pagina=laudo_pagina,
            **dados,
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_GARANTIA_REGISTRADA,
        garantia_id,
        {
            "operacao_id": str(operacao_id),
            "exposicao_id": str(exposicao_id),
            "tipo": tipo,
        },
    )
    return buscar_garantia(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        garantia_id=garantia_id,
    )


def buscar_garantia(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    garantia_id: uuid.UUID,
) -> Garantia | None:
    linha = conexao.execute(
        sa.select(*_COLUNAS_DA_GARANTIA).where(
            _da_garantia(usuario_id, operacao_id, garantia_id)
        )
    ).first()
    return Garantia(**linha._mapping) if linha else None


def listar_garantias(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    exposicao_id: uuid.UUID | None = None,
) -> list[Garantia]:
    """As garantias da operação (de uma exposição, se pedida), da mais prioritária à menos."""
    consulta = sa.select(*_COLUNAS_DA_GARANTIA).where(
        garantias_da_operacao.c.operacao_id == operacao_id,
        garantias_da_operacao.c.usuario_id == usuario_id,
    )
    if exposicao_id is not None:
        consulta = consulta.where(garantias_da_operacao.c.exposicao_id == exposicao_id)
    consulta = consulta.order_by(
        garantias_da_operacao.c.prioridade,
        garantias_da_operacao.c.criada_em,
        garantias_da_operacao.c.id,
    )
    return [Garantia(**linha._mapping) for linha in conexao.execute(consulta)]


def apagar_garantia(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    garantia_id: uuid.UUID,
) -> bool:
    apagada = (
        conexao.execute(
            sa.delete(garantias_da_operacao).where(
                _da_garantia(usuario_id, operacao_id, garantia_id)
            )
        ).rowcount
        > 0
    )
    if apagada:
        auditoria.registrar(
            conexao,
            usuario_id,
            auditoria.ACAO_GARANTIA_APAGADA,
            garantia_id,
            {"operacao_id": str(operacao_id)},
        )
    return apagada


# --- cobertura ----------------------------------------------------------------------------


def cobertura_da_exposicao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    exposicao_id: uuid.UUID,
    hoje: date | None = None,
) -> dict | None:
    """A cobertura da exposição com a fórmula e as parcelas; `None` se não é da conta."""
    exposicao = buscar_exposicao(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        exposicao_id=exposicao_id,
    )
    if exposicao is None:
        return None
    garantias = listar_garantias(
        conexao,
        usuario_id=usuario_id,
        operacao_id=operacao_id,
        exposicao_id=exposicao_id,
    )
    resultado = calcular_cobertura(
        exposicao=exposicao.valor,
        moeda=exposicao.moeda,
        garantias=[
            GarantiaParaAConta(
                id=str(g.id),
                valor_avaliado=g.valor_avaliado,
                haircut=g.haircut,
                onus_anteriores=g.onus_anteriores,
                moeda=g.moeda,
                valido_ate=g.valido_ate,
            )
            for g in garantias
        ],
        hoje=hoje or hoje_em_brasilia(),
    )
    return {"exposicao_id": str(exposicao_id), **resultado}


# --- exportação dos dados (LGPD) ----------------------------------------------------------


def _como_texto(valor: object) -> object:
    if isinstance(valor, date | datetime):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, Decimal):
        return format(valor, "f")
    return valor


def dados_para_exportar(conexao: sa.Connection, *, usuario_id: uuid.UUID) -> dict:
    """Exposições e garantias da conta para "Exportar meus dados", em texto simples."""
    exposicoes = conexao.execute(
        sa.select(*_COLUNAS_DA_EXPOSICAO)
        .where(exposicoes_da_operacao.c.usuario_id == usuario_id)
        .order_by(exposicoes_da_operacao.c.criada_em, exposicoes_da_operacao.c.id)
    )
    garantias = conexao.execute(
        sa.select(*_COLUNAS_DA_GARANTIA)
        .where(garantias_da_operacao.c.usuario_id == usuario_id)
        .order_by(garantias_da_operacao.c.criada_em, garantias_da_operacao.c.id)
    )
    return {
        "exposicoes": [
            {n: _como_texto(v) for n, v in linha._mapping.items()}
            for linha in exposicoes
        ],
        "garantias": [
            {n: _como_texto(v) for n, v in linha._mapping.items()}
            for linha in garantias
        ],
    }


__all__ = [
    "Exposicao",
    "Garantia",
    "apagar_exposicao",
    "apagar_garantia",
    "buscar_exposicao",
    "buscar_garantia",
    "cobertura_da_exposicao",
    "dados_para_exportar",
    "listar_exposicoes",
    "listar_garantias",
    "registrar_exposicao",
    "registrar_garantia",
]
