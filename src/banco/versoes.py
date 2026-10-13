"""Versões das bases que a fonte reapresenta (Radar, PR 4): nada é apagado.

Cada base vigente (demonstrações, negociações, detentores) tem ao lado uma tabela `<base>_versoes`
com as mesmas colunas. Quando a coleta troca o conteúdo de uma chave (um documento, uma
competência), `versionar` compara com a versão aberta: se nada mudou, não grava nada; se mudou,
a aberta ganha `substituido_em` e a nova entra com `registrado_em`. "Como estava em D" =
registrado até D e não substituído até D.
"""

import math
from collections import Counter
from datetime import datetime

import sqlalchemy as sa

from src.banco.modelo import CHAVES_DAS_VERSOES

CONTROLE = ("id_da_versao", "registrado_em", "substituido_em")


def colunas_de_dados(versoes: sa.Table) -> list[str]:
    return [c.name for c in versoes.columns if c.name not in CONTROLE]


def _normalizar(valor: object) -> object:
    """O mesmo valor, venha do pandas ou do banco (para comparar as versões)."""
    if hasattr(valor, "item"):
        valor = valor.item()  # type: ignore[union-attr]  (números do NumPy)
    if isinstance(valor, datetime):
        return valor.date()  # as colunas comparadas são datas, não horários
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return valor


def _do_mesmo_grupo(
    versoes: sa.Table, chave: dict[str, object]
) -> sa.ColumnElement[bool]:
    return sa.and_(*[versoes.c[nome] == valor for nome, valor in chave.items()])


def versionar(
    conexao: sa.Connection,
    versoes: sa.Table,
    chave: dict[str, object],
    linhas: list[dict],
    agora: datetime,
) -> bool:
    """Guarda `linhas` como a versão nova de `chave`, se mudou algo. Devolve se gravou.

    Sem linhas = a fonte tirou tudo daquela chave: a versão aberta é só marcada como substituída.
    """
    colunas = colunas_de_dados(versoes)
    nome_da_base = versoes.name.removesuffix("_versoes")
    if set(chave) != set(CHAVES_DAS_VERSOES[nome_da_base]):
        raise ValueError(f"Chave errada para {nome_da_base}: {sorted(chave)}")
    aberta = _do_mesmo_grupo(versoes, chave) & versoes.c.substituido_em.is_(None)
    guardadas = Counter(
        tuple(_normalizar(v) for v in linha)
        for linha in conexao.execute(
            sa.select(*[versoes.c[c] for c in colunas]).where(aberta)
        )
    )
    novas = [{c: _normalizar(linha.get(c)) for c in colunas} for linha in linhas]
    if Counter(tuple(n.values()) for n in novas) == guardadas:
        return False
    conexao.execute(sa.update(versoes).where(aberta).values(substituido_em=agora))
    if novas:
        conexao.execute(
            sa.insert(versoes), [{**n, "registrado_em": agora} for n in novas]
        )
    return True


def como_estava_em(
    conexao: sa.Connection, versoes: sa.Table, momento: datetime, **filtro: object
) -> list[sa.Row]:
    """As linhas como o TickerLab as conhecia em `momento` (filtro opcional por coluna)."""
    consulta = sa.select(versoes).where(
        versoes.c.registrado_em <= momento,
        sa.or_(versoes.c.substituido_em.is_(None), versoes.c.substituido_em > momento),
    )
    if filtro:
        consulta = consulta.where(_do_mesmo_grupo(versoes, filtro))
    return list(conexao.execute(consulta.order_by(versoes.c.id_da_versao)))


def historico(
    conexao: sa.Connection, versoes: sa.Table, **chave: object
) -> list[sa.Row]:
    """Todas as versões de uma chave, da mais antiga para a mais nova."""
    consulta = sa.select(versoes).where(_do_mesmo_grupo(versoes, chave))
    return list(conexao.execute(consulta.order_by(versoes.c.id_da_versao)))
