"""Gravar e consultar quem tem cada ação (Research R3): fundos da CVM e gestores da SEC.

Dados públicos, iguais para todos. Cada coleta **troca o mês (ou trimestre) inteiro** de uma fonte:
o arquivo da CVM é refeito quando fundos atrasados entregam, então o mais novo sempre vence.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from src.banco.modelo import (
    cobertura_de_detentores,
    cobertura_de_detentores_versoes,
    detentores_por_acao,
    detentores_por_acao_versoes,
    maiores_detentores,
    maiores_detentores_versoes,
)
from src.banco.versoes import versionar
from src.detentores import COLUNAS_DO_RESUMO, COLUNAS_DOS_MAIORES


def _registros(tabela: pd.DataFrame, colunas: list[str]) -> list[dict]:
    """Linhas prontas para o banco: números do NumPy viram números do Python."""
    return [
        {c: (v.item() if hasattr(v, "item") else v) for c, v in linha.items()}
        for linha in tabela[colunas].to_dict("records")
    ]


def gravar_competencia(
    conexao: sa.Connection,
    resumo: pd.DataFrame,
    maiores: pd.DataFrame,
    informantes: int,
    agora: datetime | None = None,
) -> int:
    """Troca os dados de uma competência inteira (resumo, maiores e cobertura).

    Devolve quantas ações entraram. Se algo mudou, a versão anterior continua nas tabelas
    `*_versoes` (Radar, PR 4); refazer com o mesmo arquivo não cria versão.
    """
    if resumo.empty:
        return 0
    chaves = resumo[["fonte", "competencia"]].drop_duplicates()
    if len(chaves) != 1:
        raise ValueError("gravar_competencia recebe uma competência por vez.")
    fonte, competencia = chaves.iloc[0]
    agora = agora or datetime.now(UTC)
    for tabela in (detentores_por_acao, maiores_detentores, cobertura_de_detentores):
        conexao.execute(
            sa.delete(tabela).where(
                tabela.c.fonte == fonte, tabela.c.competencia == competencia
            )
        )
    chave = {"fonte": fonte, "competencia": competencia}
    cobertura = {**chave, "informantes": int(informantes)}
    conexao.execute(
        sa.insert(cobertura_de_detentores).values(**cobertura, coletado_em=agora)
    )
    por_acao = _registros(resumo, COLUNAS_DO_RESUMO)
    conexao.execute(
        sa.insert(detentores_por_acao),
        [{**linha, "coletado_em": agora} for linha in por_acao],
    )
    os_maiores = [] if maiores.empty else _registros(maiores, COLUNAS_DOS_MAIORES)
    if os_maiores:
        conexao.execute(sa.insert(maiores_detentores), os_maiores)
    versionar(conexao, cobertura_de_detentores_versoes, chave, [cobertura], agora)
    versionar(conexao, detentores_por_acao_versoes, chave, por_acao, agora)
    versionar(conexao, maiores_detentores_versoes, chave, os_maiores, agora)
    return len(resumo)


def competencias(conexao: sa.Connection, fonte: str) -> list[date]:
    """As competências guardadas de uma fonte, da mais nova para a mais velha."""
    consulta = (
        sa.select(detentores_por_acao.c.competencia)
        .where(detentores_por_acao.c.fonte == fonte)
        .distinct()
        .order_by(detentores_por_acao.c.competencia.desc())
    )
    return list(conexao.execute(consulta).scalars())


def cobertura(conexao: sa.Connection, fonte: str) -> dict[date, int]:
    """competência → quantos fundos (ou gestores) informaram."""
    consulta = sa.select(
        cobertura_de_detentores.c.competencia, cobertura_de_detentores.c.informantes
    ).where(cobertura_de_detentores.c.fonte == fonte)
    return dict(conexao.execute(consulta).all())


def historico_do_ativo(conexao: sa.Connection, fonte: str, codigo: str) -> pd.DataFrame:
    """O resumo de todas as competências de uma ação, da mais velha para a mais nova."""
    consulta = (
        sa.select(*(detentores_por_acao.c[c] for c in COLUNAS_DO_RESUMO))
        .where(
            detentores_por_acao.c.fonte == fonte, detentores_por_acao.c.codigo == codigo
        )
        .order_by(detentores_por_acao.c.competencia)
    )
    return pd.DataFrame(conexao.execute(consulta).all(), columns=COLUNAS_DO_RESUMO)


def maiores_do_ativo(
    conexao: sa.Connection, fonte: str, codigo: str, competencia: date
) -> pd.DataFrame:
    consulta = (
        sa.select(*(maiores_detentores.c[c] for c in COLUNAS_DOS_MAIORES))
        .where(
            maiores_detentores.c.fonte == fonte,
            maiores_detentores.c.codigo == codigo,
            maiores_detentores.c.competencia == competencia,
        )
        .order_by(maiores_detentores.c.tipo, maiores_detentores.c.posicao)
    )
    return pd.DataFrame(conexao.execute(consulta).all(), columns=COLUNAS_DOS_MAIORES)


def resumo_do_mercado(
    conexao: sa.Connection, fonte: str, datas: Iterable[date]
) -> pd.DataFrame:
    """O resumo de todas as ações nas competências pedidas (para comparar um mês com o outro)."""
    consulta = sa.select(*(detentores_por_acao.c[c] for c in COLUNAS_DO_RESUMO)).where(
        detentores_por_acao.c.fonte == fonte,
        detentores_por_acao.c.competencia.in_(list(datas)),
    )
    return pd.DataFrame(conexao.execute(consulta).all(), columns=COLUNAS_DO_RESUMO)
