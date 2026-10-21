"""O trabalho da pessoa na sala: evidências, contradições e checklist (B-20, PR 4).

Mesma regra de `src/banco/sala.py`: toda função recebe `usuario_id` e `operacao_id` pelo nome, toda
consulta filtra pelos dois, e para outra conta a resposta é a de um id que não existe (`None` ou
`False`, a rota devolve 404). Nada aqui chama modelo: as contradições saem de uma regra fixa
(`src/sala/contradicoes.py`) e o checklist de uma lista fixa (`src/sala/checklists.py`).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

import sqlalchemy as sa

from src.banco import sala
from src.banco.modelo import (
    ESTADOS_DA_CONTRADICAO,
    REVISOES_DA_EVIDENCIA,
    TAMANHO_MAXIMO_DA_NOTA,
    checklist_da_sala,
    contradicoes_da_sala,
    evidencias_da_sala,
)
from src.sala import checklists, contradicoes

TAMANHO_DA_METRICA = 120
TAMANHO_DO_PERIODO = 20
TAMANHO_DO_VALOR_EM_TEXTO = 500
TAMANHO_DA_UNIDADE = 20
TAMANHO_DA_SECAO = 200
TAMANHO_DA_MOEDA = 3
# o que a pessoa pode pôr num item do checklist; "recebido" só vem de ligar um documento
ESTADOS_ESCOLHIDOS_PELA_PESSOA = ("pendente", "revisado", "contestado", "nao_se_aplica")
# o item mudou sem tocar no documento ligado a ele
SEM_MUDANCA: Final = object()


@dataclass(frozen=True)
class Evidencia:
    id: uuid.UUID
    operacao_id: uuid.UUID
    documento_id: uuid.UUID
    metrica: str
    periodo: str
    valor_numero: Decimal | None
    valor_texto: str | None
    unidade: str | None
    moeda: str | None
    pagina: int | None
    secao: str | None
    tabela: str | None
    trecho: str | None
    conferida: bool
    extraido_por: str
    estado_de_revisao: str
    criada_em: datetime


@dataclass(frozen=True)
class Contradicao:
    id: uuid.UUID
    operacao_id: uuid.UUID
    evidencia_a: uuid.UUID
    evidencia_b: uuid.UUID
    diferenca: Decimal | None
    estado: str
    nota: str | None
    criada_em: datetime


@dataclass(frozen=True)
class ItemDaOperacao:
    """Um item do checklist: o texto fixo mais o que a pessoa fez com ele."""

    codigo: str
    titulo: str
    ajuda: str
    estado: str
    documento_id: uuid.UUID | None
    nota: str | None
    atualizado_em: datetime | None


_COLUNAS_DA_EVIDENCIA = (
    evidencias_da_sala.c.id,
    evidencias_da_sala.c.operacao_id,
    evidencias_da_sala.c.documento_id,
    evidencias_da_sala.c.metrica,
    evidencias_da_sala.c.periodo,
    evidencias_da_sala.c.valor_numero,
    evidencias_da_sala.c.valor_texto,
    evidencias_da_sala.c.unidade,
    evidencias_da_sala.c.moeda,
    evidencias_da_sala.c.pagina,
    evidencias_da_sala.c.secao,
    evidencias_da_sala.c.tabela,
    evidencias_da_sala.c.trecho,
    evidencias_da_sala.c.conferida,
    evidencias_da_sala.c.extraido_por,
    evidencias_da_sala.c.estado_de_revisao,
    evidencias_da_sala.c.criada_em,
)
_COLUNAS_DA_CONTRADICAO = (
    contradicoes_da_sala.c.id,
    contradicoes_da_sala.c.operacao_id,
    contradicoes_da_sala.c.evidencia_a,
    contradicoes_da_sala.c.evidencia_b,
    contradicoes_da_sala.c.diferenca,
    contradicoes_da_sala.c.estado,
    contradicoes_da_sala.c.nota,
    contradicoes_da_sala.c.criada_em,
)


def _limpo(valor: str | None, maximo: int, nome: str) -> str | None:
    """O texto sem as pontas em branco; `None` se vazio; erro se passa do tamanho."""
    if valor is None:
        return None
    limpo = valor.strip()
    if len(limpo) > maximo:
        raise ValueError(f"{nome}: no máximo {maximo} caracteres.")
    return limpo or None


def _obrigatorio(valor: str, maximo: int, nome: str) -> str:
    limpo = _limpo(valor, maximo, nome)
    if limpo is None:
        raise ValueError(f"{nome}: preencha.")
    return limpo


def _moeda_valida(moeda: str | None) -> str | None:
    limpa = _limpo(moeda, TAMANHO_DA_MOEDA, "Moeda")
    if limpa is None:
        return None
    if len(limpa) != TAMANHO_DA_MOEDA or not limpa.isalpha():
        raise ValueError("Moeda: o código de 3 letras, como BRL ou USD.")
    return limpa.upper()


# --- evidências ---------------------------------------------------------------------------


def _da_evidencia(
    usuario_id: uuid.UUID, operacao_id: uuid.UUID, evidencia_id: uuid.UUID
) -> sa.ColumnElement[bool]:
    return sa.and_(
        evidencias_da_sala.c.id == evidencia_id,
        evidencias_da_sala.c.operacao_id == operacao_id,
        evidencias_da_sala.c.usuario_id == usuario_id,
    )


def _buscar_evidencia(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    evidencia_id: uuid.UUID,
) -> Evidencia | None:
    linha = conexao.execute(
        sa.select(*_COLUNAS_DA_EVIDENCIA).where(
            _da_evidencia(usuario_id, operacao_id, evidencia_id)
        )
    ).first()
    return Evidencia(**linha._mapping) if linha else None


def buscar_evidencia(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    evidencia_id: uuid.UUID,
) -> Evidencia | None:
    return _buscar_evidencia(conexao, usuario_id, operacao_id, evidencia_id)


def listar_evidencias(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> list[Evidencia]:
    """As evidências da sala, na ordem em que foram criadas; vazia se a sala não é da conta."""
    linhas = conexao.execute(
        sa.select(*_COLUNAS_DA_EVIDENCIA)
        .where(
            evidencias_da_sala.c.operacao_id == operacao_id,
            evidencias_da_sala.c.usuario_id == usuario_id,
        )
        .order_by(evidencias_da_sala.c.criada_em, evidencias_da_sala.c.id)
    )
    return [Evidencia(**linha._mapping) for linha in linhas]


def criar_evidencia(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    documento_id: uuid.UUID,
    metrica: str,
    periodo: str,
    valor_numero: Decimal | None,
    valor_texto: str | None,
    unidade: str | None,
    moeda: str | None,
    pagina: int | None,
    secao: str | None,
    tabela: str | None,
    trecho: str | None,
    conferida: bool,
) -> Evidencia | None:
    """Grava uma evidência criada pela pessoa; `None` se o documento não é desta sala e conta.

    `conferida` vem de fora (`src/sala/evidencias.py` compara o trecho com o texto da página):
    o banco só guarda. As contradições são refeitas na mesma transação.
    """
    dados = {
        "metrica": _obrigatorio(metrica, TAMANHO_DA_METRICA, "Métrica"),
        "periodo": _obrigatorio(periodo, TAMANHO_DO_PERIODO, "Período"),
        "valor_numero": valor_numero,
        "valor_texto": _limpo(valor_texto, TAMANHO_DO_VALOR_EM_TEXTO, "Valor"),
        "unidade": _limpo(unidade, TAMANHO_DA_UNIDADE, "Unidade"),
        "moeda": _moeda_valida(moeda),
        "pagina": pagina,
        "secao": _limpo(secao, TAMANHO_DA_SECAO, "Seção"),
        "tabela": _limpo(tabela, TAMANHO_DA_SECAO, "Tabela"),
        "trecho": _limpo(trecho, TAMANHO_MAXIMO_DA_NOTA, "Trecho"),
    }
    if dados["valor_numero"] is None and dados["valor_texto"] is None:
        raise ValueError("Informe o valor, em número ou em texto.")
    if pagina is not None and pagina < 1:
        raise ValueError("Página: a primeira é a 1.")
    if (
        sala.buscar_documento(
            conexao,
            usuario_id=usuario_id,
            operacao_id=operacao_id,
            documento_id=documento_id,
        )
        is None
    ):
        return None
    evidencia_id = uuid.uuid4()
    conexao.execute(
        sa.insert(evidencias_da_sala).values(
            id=evidencia_id,
            usuario_id=usuario_id,
            operacao_id=operacao_id,
            documento_id=documento_id,
            conferida=conferida,
            extraido_por="pessoa",
            **dados,
        )
    )
    sincronizar_contradicoes(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
    return _buscar_evidencia(conexao, usuario_id, operacao_id, evidencia_id)


def mudar_revisao_da_evidencia(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    evidencia_id: uuid.UUID,
    estado: str,
) -> Evidencia | None:
    """A pessoa revisa, contesta ou rejeita a evidência; a rejeitada sai da regra das contradições."""
    if estado not in REVISOES_DA_EVIDENCIA:
        raise ValueError(f"Escolha um destes: {', '.join(REVISOES_DA_EVIDENCIA)}.")
    atualizadas = conexao.execute(
        sa.update(evidencias_da_sala)
        .where(_da_evidencia(usuario_id, operacao_id, evidencia_id))
        .values(estado_de_revisao=estado)
    ).rowcount
    if not atualizadas:
        return None
    sincronizar_contradicoes(conexao, usuario_id=usuario_id, operacao_id=operacao_id)
    return _buscar_evidencia(conexao, usuario_id, operacao_id, evidencia_id)


def apagar_evidencia(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    evidencia_id: uuid.UUID,
) -> bool:
    """Apaga a evidência e, em cascata, as contradições que a citavam."""
    apagadas = conexao.execute(
        sa.delete(evidencias_da_sala).where(
            _da_evidencia(usuario_id, operacao_id, evidencia_id)
        )
    ).rowcount
    return apagadas > 0


# --- contradições -------------------------------------------------------------------------


def _medidas_da_sala(
    conexao: sa.Connection, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> list[contradicoes.Medida]:
    """As evidências que entram na regra: com número e não rejeitadas."""
    linhas = conexao.execute(
        sa.select(
            evidencias_da_sala.c.id,
            evidencias_da_sala.c.documento_id,
            evidencias_da_sala.c.metrica,
            evidencias_da_sala.c.periodo,
            evidencias_da_sala.c.valor_numero,
            evidencias_da_sala.c.unidade,
            evidencias_da_sala.c.moeda,
        ).where(
            evidencias_da_sala.c.operacao_id == operacao_id,
            evidencias_da_sala.c.usuario_id == usuario_id,
            evidencias_da_sala.c.valor_numero.is_not(None),
            evidencias_da_sala.c.estado_de_revisao != "rejeitado",
        )
    )
    return [
        contradicoes.Medida(
            evidencia_id=linha.id,
            documento_id=linha.documento_id,
            metrica=linha.metrica,
            periodo=linha.periodo,
            valor=Decimal(str(linha.valor_numero)),
            unidade=linha.unidade,
            moeda=linha.moeda,
        )
        for linha in linhas
    ]


def sincronizar_contradicoes(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> None:
    """Abre as contradições que a regra acha e ainda não existem; fecha as abertas que deixaram de valer.

    O que a pessoa já marcou ("explicada" ou "descartada") fica como está, com a nota.
    """
    achadas = {
        (a.evidencia_id, b.evidencia_id): diferenca
        for a, b, diferenca in contradicoes.achar_contradicoes(
            _medidas_da_sala(conexao, usuario_id, operacao_id)
        )
    }
    da_sala = sa.and_(
        contradicoes_da_sala.c.operacao_id == operacao_id,
        contradicoes_da_sala.c.usuario_id == usuario_id,
    )
    existentes = {
        (linha.evidencia_a, linha.evidencia_b): linha
        for linha in conexao.execute(
            sa.select(
                contradicoes_da_sala.c.id,
                contradicoes_da_sala.c.evidencia_a,
                contradicoes_da_sala.c.evidencia_b,
                contradicoes_da_sala.c.estado,
            ).where(da_sala)
        )
    }
    for par, linha in existentes.items():
        if par not in achadas and linha.estado == "aberta":
            conexao.execute(
                sa.delete(contradicoes_da_sala).where(
                    da_sala, contradicoes_da_sala.c.id == linha.id
                )
            )
    for (evidencia_a, evidencia_b), diferenca in achadas.items():
        if (evidencia_a, evidencia_b) not in existentes:
            conexao.execute(
                sa.insert(contradicoes_da_sala).values(
                    id=uuid.uuid4(),
                    usuario_id=usuario_id,
                    operacao_id=operacao_id,
                    evidencia_a=evidencia_a,
                    evidencia_b=evidencia_b,
                    diferenca=diferenca,
                )
            )


def listar_contradicoes(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> list[Contradicao]:
    linhas = conexao.execute(
        sa.select(*_COLUNAS_DA_CONTRADICAO)
        .where(
            contradicoes_da_sala.c.operacao_id == operacao_id,
            contradicoes_da_sala.c.usuario_id == usuario_id,
        )
        .order_by(contradicoes_da_sala.c.criada_em, contradicoes_da_sala.c.id)
    )
    return [Contradicao(**linha._mapping) for linha in linhas]


def mudar_contradicao(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    contradicao_id: uuid.UUID,
    estado: str,
    nota: str | None,
) -> Contradicao | None:
    """A pessoa marca "explicada" ou "descartada" (com nota) ou reabre; `None` se não é dela."""
    if estado not in ESTADOS_DA_CONTRADICAO:
        raise ValueError(f"Escolha um destes: {', '.join(ESTADOS_DA_CONTRADICAO)}.")
    nota_limpa = _limpo(nota, TAMANHO_MAXIMO_DA_NOTA, "Nota")
    if estado != "aberta" and nota_limpa is None:
        raise ValueError(
            "Escreva a nota: por que a contradição está explicada ou descartada."
        )
    da_contradicao = sa.and_(
        contradicoes_da_sala.c.id == contradicao_id,
        contradicoes_da_sala.c.operacao_id == operacao_id,
        contradicoes_da_sala.c.usuario_id == usuario_id,
    )
    atualizadas = conexao.execute(
        sa.update(contradicoes_da_sala)
        .where(da_contradicao)
        .values(estado=estado, nota=nota_limpa)
    ).rowcount
    if not atualizadas:
        return None
    linha = conexao.execute(
        sa.select(*_COLUNAS_DA_CONTRADICAO).where(da_contradicao)
    ).first()
    return Contradicao(**linha._mapping) if linha else None


# --- checklist ----------------------------------------------------------------------------


def _da_linha_do_checklist(
    usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> sa.ColumnElement[bool]:
    return sa.and_(
        checklist_da_sala.c.operacao_id == operacao_id,
        checklist_da_sala.c.usuario_id == usuario_id,
    )


def _linhas_do_checklist(
    conexao: sa.Connection, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> dict[str, sa.Row]:
    linhas = conexao.execute(
        sa.select(
            checklist_da_sala.c.codigo,
            checklist_da_sala.c.estado,
            checklist_da_sala.c.documento_id,
            checklist_da_sala.c.nota,
            checklist_da_sala.c.atualizado_em,
        ).where(_da_linha_do_checklist(usuario_id, operacao_id))
    )
    return {linha.codigo: linha for linha in linhas}


def _com_a_linha(
    item: checklists.ItemDoChecklist, linha: sa.Row | None
) -> ItemDaOperacao:
    return ItemDaOperacao(
        codigo=item.codigo,
        titulo=item.titulo,
        ajuda=item.ajuda,
        estado=linha.estado if linha else "pendente",
        documento_id=linha.documento_id if linha else None,
        nota=linha.nota if linha else None,
        atualizado_em=linha.atualizado_em if linha else None,
    )


def ler_checklist(
    conexao: sa.Connection, *, usuario_id: uuid.UUID, operacao_id: uuid.UUID
) -> list[ItemDaOperacao] | None:
    """Os itens do tipo da operação, na ordem da lista fixa; `None` se a sala não é da conta.

    Item que a pessoa nunca tocou não tem linha no banco e aparece "pendente".
    """
    operacao = sala.buscar_operacao(
        conexao, usuario_id=usuario_id, operacao_id=operacao_id
    )
    if operacao is None:
        return None
    linhas = _linhas_do_checklist(conexao, usuario_id, operacao_id)
    return [
        _com_a_linha(item, linhas.get(item.codigo))
        for item in checklists.itens_do_tipo(operacao.tipo)
    ]


def _estado_do_item(
    atual: str, escolhido: str | None, documento_id: uuid.UUID | None | object
) -> str:
    """O estado depois da mudança: o que a pessoa escolheu vale; ligar documento recebe sozinho."""
    if escolhido is not None:
        return escolhido
    if documento_id is SEM_MUDANCA:
        return atual
    if documento_id is not None and atual == "pendente":
        return "recebido"
    if documento_id is None and atual == "recebido":
        return "pendente"
    return atual


def mudar_item_do_checklist(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    operacao_id: uuid.UUID,
    codigo: str,
    estado: str | None = None,
    documento_id: uuid.UUID | None | object = SEM_MUDANCA,
    nota: str | None | object = SEM_MUDANCA,
) -> ItemDaOperacao | None:
    """Muda o estado, o documento ligado ou a nota de um item; `None` se a sala ou o item não existem.

    "revisado" só entra por aqui, escolhido pela pessoa. "recebido" nunca é escolhido: vem de ligar
    um documento a um item pendente (e desligar o documento o devolve a "pendente").
    """
    if estado is not None and estado not in ESTADOS_ESCOLHIDOS_PELA_PESSOA:
        raise ValueError(
            f"Escolha um destes: {', '.join(ESTADOS_ESCOLHIDOS_PELA_PESSOA)}."
        )
    operacao = sala.buscar_operacao(
        conexao, usuario_id=usuario_id, operacao_id=operacao_id
    )
    if operacao is None:
        return None
    item = checklists.item_do_tipo(operacao.tipo, codigo)
    if item is None:
        return None
    if (
        isinstance(documento_id, uuid.UUID)
        and sala.buscar_documento(
            conexao,
            usuario_id=usuario_id,
            operacao_id=operacao_id,
            documento_id=documento_id,
        )
        is None
    ):
        raise ValueError("Este documento não está nesta sala.")
    linha = _linhas_do_checklist(conexao, usuario_id, operacao_id).get(codigo)
    atual = linha.estado if linha else "pendente"
    valores = {
        "estado": _estado_do_item(atual, estado, documento_id),
        "documento_id": linha.documento_id if linha else None,
        "nota": linha.nota if linha else None,
        "atualizado_em": sa.func.now(),
    }
    if documento_id is not SEM_MUDANCA:
        valores["documento_id"] = documento_id
    if nota is not SEM_MUDANCA:
        valores["nota"] = _limpo(
            nota if isinstance(nota, str) or nota is None else None,
            TAMANHO_MAXIMO_DA_NOTA,
            "Nota",
        )
    if linha is None:
        conexao.execute(
            sa.insert(checklist_da_sala).values(
                id=uuid.uuid4(),
                usuario_id=usuario_id,
                operacao_id=operacao_id,
                codigo=codigo,
                **valores,
            )
        )
    else:
        conexao.execute(
            sa.update(checklist_da_sala)
            .where(
                _da_linha_do_checklist(usuario_id, operacao_id),
                checklist_da_sala.c.codigo == codigo,
            )
            .values(**valores)
        )
    nova = _linhas_do_checklist(conexao, usuario_id, operacao_id).get(codigo)
    return _com_a_linha(item, nova)
