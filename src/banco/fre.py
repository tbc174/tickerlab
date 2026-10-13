"""Proventos e eventos de capital do FRE no banco (série 2 da base de ML, PR 6).

O FRE de cada ano repete os exercícios anteriores: gravar de novo o mesmo exercício (ou o mesmo
evento) fica com o documento mais novo (data de referência e versão maiores) e não duplica.
"""

import math
from datetime import date, datetime

import pandas as pd
import sqlalchemy as sa

from src.banco.modelo import fre_eventos_de_capital, fre_proventos


def _numero(valor: object) -> float | None:
    if valor is None:
        return None
    numero = float(valor)  # type: ignore[arg-type]
    return None if math.isnan(numero) else numero


def _dia(valor: object) -> date:
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _mais_novo(guardado: sa.Row | None, referencia: object, versao: int) -> bool:
    if guardado is None:
        return True
    return (_dia(referencia), versao) >= (guardado.referencia, guardado.versao)


def gravar_proventos(
    conexao: sa.Connection, proventos: pd.DataFrame, agora: datetime
) -> int:
    """Grava os proventos por exercício; devolve quantos entraram ou mudaram."""
    t, mudaram = fre_proventos, 0
    for linha in proventos.itertuples(index=False):
        chave = (t.c.cnpj == linha.cnpj) & (t.c.exercicio == _dia(linha.exercicio))
        guardado = conexao.execute(
            sa.select(t.c.referencia, t.c.versao).where(chave)
        ).first()
        if not _mais_novo(guardado, linha.referencia, int(linha.versao)):
            continue
        conexao.execute(sa.delete(t).where(chave))
        conexao.execute(
            sa.insert(t).values(
                cnpj=linha.cnpj,
                exercicio=_dia(linha.exercicio),
                referencia=_dia(linha.referencia),
                versao=int(linha.versao),
                lucro_ajustado=_numero(linha.lucro_ajustado),
                dividendo_total=_numero(linha.dividendo_total),
                payout=_numero(linha.payout),
                dividendos=_numero(linha.dividendos),
                jcp=_numero(linha.jcp),
                coletado_em=agora,
            )
        )
        mudaram += 1
    return mudaram


def gravar_eventos(
    conexao: sa.Connection, eventos: pd.DataFrame, agora: datetime
) -> int:
    """Grava os eventos de capital; devolve quantos entraram ou mudaram."""
    t, mudaram = fre_eventos_de_capital, 0
    for linha in eventos.itertuples(index=False):
        quantidade = _numero(linha.acoes_depois) or _numero(linha.acoes_novas)
        if quantidade is None:
            continue
        chave = (
            (t.c.cnpj == linha.cnpj)
            & (t.c.tipo == linha.tipo)
            & (t.c.data == _dia(linha.data))
            & (t.c.quantidade == round(quantidade))
        )
        guardado = conexao.execute(
            sa.select(t.c.referencia, t.c.versao).where(chave)
        ).first()
        if not _mais_novo(guardado, linha.referencia, int(linha.versao)):
            continue
        conexao.execute(sa.delete(t).where(chave))
        conexao.execute(
            sa.insert(t).values(
                cnpj=linha.cnpj,
                tipo=linha.tipo,
                data=_dia(linha.data),
                quantidade=round(quantidade),
                referencia=_dia(linha.referencia),
                versao=int(linha.versao),
                acoes_antes=_numero(linha.acoes_antes),
                acoes_depois=_numero(linha.acoes_depois),
                fator=_numero(linha.fator),
                acoes_novas=_numero(linha.acoes_novas),
                valor=_numero(linha.valor),
                coletado_em=agora,
            )
        )
        mudaram += 1
    return mudaram


def _tabela(conexao: sa.Connection, consulta: sa.Select) -> pd.DataFrame:
    resultado = conexao.execute(consulta)
    return pd.DataFrame(resultado.fetchall(), columns=list(resultado.keys()))


def proventos_de(conexao: sa.Connection, cnpj: str) -> pd.DataFrame:
    t = fre_proventos
    return _tabela(
        conexao, sa.select(t).where(t.c.cnpj == cnpj).order_by(t.c.exercicio)
    )


def eventos_de(conexao: sa.Connection, cnpj: str) -> pd.DataFrame:
    t = fre_eventos_de_capital
    return _tabela(conexao, sa.select(t).where(t.c.cnpj == cnpj).order_by(t.c.data))
