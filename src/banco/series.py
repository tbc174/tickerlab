"""Séries macro com safras (Radar, PR 5): o valor de cada data e quando ele foi conhecido.

Só acréscimo. Gravar a mesma série de novo não cria nada; um valor revisto pela fonte vira uma
linha nova com a safra (`divulgado_em`) do dia em que apareceu, e a anterior continua lá. Assim
"como estava na data D" tem resposta: para cada data de referência, o valor da safra mais nova
até D. No Focus a safra é a data da pesquisa; nas outras fontes, o dia da coleta.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from src.banco.coletas import licenca_da_fonte
from src.banco.modelo import observacoes, series


@dataclass(frozen=True)
class SerieDoAcervo:
    codigo: str  # "família-detalhe": a família dá a licença (bcb, tesouro, yahoo)
    nome: str
    unidade: str
    frequencia: str
    uso_interno: bool = False  # Yahoo: nunca exportar nem redistribuir (ADR 0024)


def garantir_serie(conexao: sa.Connection, serie: SerieDoAcervo) -> None:
    """Cadastra a série no catálogo (ou atualiza nome, unidade e frequência)."""
    valores = {
        "nome": serie.nome,
        "unidade": serie.unidade,
        "frequencia": serie.frequencia,
        "licenca": licenca_da_fonte(serie.codigo),
        "uso_interno": serie.uso_interno,
    }
    existe = conexao.execute(
        sa.select(series.c.codigo).where(series.c.codigo == serie.codigo)
    ).first()
    if existe:
        conexao.execute(
            sa.update(series).where(series.c.codigo == serie.codigo).values(**valores)
        )
    else:
        conexao.execute(sa.insert(series).values(codigo=serie.codigo, **valores))


def _conhecidos_ate(
    conexao: sa.Connection, codigo: str, dia: date
) -> dict[date, float]:
    """O valor de cada data de referência na safra mais nova até `dia`."""
    linhas = conexao.execute(
        sa.select(observacoes.c.referencia, observacoes.c.valor)
        .where(observacoes.c.serie == codigo, observacoes.c.divulgado_em <= dia)
        .order_by(observacoes.c.divulgado_em, observacoes.c.registrado_em)
    )
    return {referencia: valor for referencia, valor in linhas}


def _mudou(anterior: float | None, novo: float) -> bool:
    return anterior is None or not math.isclose(anterior, novo, rel_tol=1e-12)


def gravar(
    conexao: sa.Connection,
    codigo: str,
    valores: pd.Series,
    divulgado_em: date,
    agora: datetime | None = None,
) -> int:
    """Grava as datas novas e as revistas de `valores` (índice = referência) na safra
    `divulgado_em`. Devolve quantas linhas entraram; valores vazios (NaN) são ignorados.

    Compara com o que se sabia até aquela safra: buscar de novo uma pesquisa antiga do Focus
    não a grava outra vez."""
    vigentes = _conhecidos_ate(conexao, codigo, divulgado_em)
    momento = agora or datetime.now(UTC)
    novas = [
        {
            "id": uuid.uuid4(),
            "serie": codigo,
            "referencia": referencia,
            "valor": float(valor),
            "divulgado_em": divulgado_em,
            "registrado_em": momento,
        }
        for referencia, valor in (
            (pd.Timestamp(r).date(), v) for r, v in valores.dropna().items()
        )
        if _mudou(vigentes.get(referencia), float(valor))
    ]
    if novas:
        conexao.execute(sa.insert(observacoes), novas)
    return len(novas)


def como_estava_em(conexao: sa.Connection, codigo: str, dia: date) -> pd.Series:
    """A série como era conhecida no fim de `dia` (a safra mais nova até ele, por referência)."""
    conhecidos = _conhecidos_ate(conexao, codigo, dia)
    serie = pd.Series(conhecidos, dtype=float, name=codigo)
    serie.index = pd.to_datetime(serie.index)
    return serie.sort_index()


def safras(
    conexao: sa.Connection, codigo: str, referencia: date
) -> list[tuple[date, float]]:
    """Todas as versões de uma data de referência, da mais antiga para a mais nova."""
    linhas = conexao.execute(
        sa.select(observacoes.c.divulgado_em, observacoes.c.valor)
        .where(observacoes.c.serie == codigo, observacoes.c.referencia == referencia)
        .order_by(observacoes.c.divulgado_em, observacoes.c.registrado_em)
    )
    return [(divulgado_em, valor) for divulgado_em, valor in linhas]


def tem_dados(conexao: sa.Connection, codigo: str) -> bool:
    return (
        conexao.execute(
            sa.select(observacoes.c.id).where(observacoes.c.serie == codigo).limit(1)
        ).first()
        is not None
    )


def series_para_exportar(conexao: sa.Connection) -> list[str]:
    """Os códigos das séries que podem sair do acervo (nunca as de uso interno)."""
    return list(
        conexao.execute(
            sa.select(series.c.codigo)
            .where(series.c.uso_interno.is_(False))
            .order_by(series.c.codigo)
        ).scalars()
    )
