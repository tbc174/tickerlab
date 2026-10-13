"""Achados das regras de qualidade no banco (série 1 da base de ML, PR 3).

As regras fixas de `base/regras.py` rodam todo dia sobre os arquivos originais da CVM. Aqui ficam
os achados delas, só por acréscimo:

- **O mesmo achado de novo** (mesma regra, empresa, documento, data, grupo e conta) atualiza o
  texto e os valores da linha aberta; não cria outra. A data de origem (`valido_desde`) não muda.
- **O achado que sumiu** (a empresa corrigiu, ou a versão nova das regras não dispara mais) ganha
  `fechado_em`; nunca é apagado. Se voltar depois, abre uma linha nova.
- **Só fecha o que rodou:** uma regra que não rodou nesta vez (faltou o documento anterior, por
  exemplo) não fecha os achados dela.
"""

import math
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import sqlalchemy as sa

from base.regras import VERSAO_DAS_REGRAS, Achado
from src.banco.modelo import achados_de_qualidade as tabela

CHAVE = ("regra", "cnpj", "documento", "referencia", "grupo", "conta")
FUSO_DA_CVM = "America/Sao_Paulo"  # as datas de entrega da CVM vêm sem horário nem fuso


@dataclass(frozen=True)
class ResumoDaGravacao:
    novos: int
    atualizados: int
    fechados: int


def _data(valor: object) -> date:
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _momento(valor: object) -> datetime:
    """Em UTC; data sem fuso é a de Brasília (assim o SQLite e o PostgreSQL guardam igual)."""
    momento = pd.Timestamp(valor)  # type: ignore[arg-type]
    if momento.tzinfo is None:
        momento = momento.tz_localize(FUSO_DA_CVM)
    return momento.tz_convert("UTC").to_pydatetime()


def _numero(valor: float | None) -> float | None:
    return None if valor is None or math.isnan(valor) else float(valor)


def _chave(achado: Achado) -> tuple:
    return (
        achado.regra,
        achado.cnpj,
        achado.documento,
        _data(achado.referencia),
        achado.grupo,
        achado.conta,
    )


def _conferir(achados: list[Achado], documento: str, referencias: set[date]) -> None:
    for achado in achados:
        if achado.valido_desde is None:
            raise ValueError(f"achado {achado.regra} de {achado.cnpj} sem valido_desde")
        if achado.documento != documento or _data(achado.referencia) not in referencias:
            raise ValueError(
                f"achado {achado.regra} de {achado.cnpj} fora do documento rodado "
                f"({achado.documento} {achado.referencia:%d/%m/%Y})"
            )


def _campos(achado: Achado, agora: datetime) -> dict:
    return {
        "valor": _numero(achado.valor),
        "valor_esperado": _numero(achado.valor_esperado),
        "porque": achado.porque,
        "versao_das_regras": VERSAO_DAS_REGRAS,
        "calculado_em": agora,
    }


def gravar_achados(
    conexao: sa.Connection,
    achados: Iterable[Achado],
    regras: Iterable[str],
    documento: str,
    referencias: Iterable[object],
    agora: datetime,
) -> ResumoDaGravacao:
    """Grava os achados de uma rodada das `regras` sobre `documento` nas `referencias`.

    Os achados abertos dessas regras e referências que não vieram desta vez são fechados.
    """
    datas = {_data(r) for r in referencias}
    novos_achados = {_chave(a): a for a in achados}
    _conferir(list(novos_achados.values()), documento, datas)
    abertos = {
        tuple(getattr(linha, c) for c in CHAVE): linha.id
        for linha in conexao.execute(
            sa.select(tabela).where(
                tabela.c.documento == documento,
                tabela.c.referencia.in_(datas),
                tabela.c.regra.in_(list(regras)),
                tabela.c.fechado_em.is_(None),
            )
        )
    }
    atualizados = 0
    for chave, achado in novos_achados.items():
        if chave in abertos:
            conexao.execute(
                sa.update(tabela)
                .where(tabela.c.id == abertos[chave])
                .values(**_campos(achado, agora))
            )
            atualizados += 1
        else:
            conexao.execute(
                sa.insert(tabela).values(
                    id=uuid.uuid4(),
                    **dict(zip(CHAVE, chave, strict=True)),
                    valido_desde=_momento(achado.valido_desde),
                    **_campos(achado, agora),
                )
            )
    sumiram = [id_ for chave, id_ in abertos.items() if chave not in novos_achados]
    if sumiram:
        conexao.execute(
            sa.update(tabela).where(tabela.c.id.in_(sumiram)).values(fechado_em=agora)
        )
    return ResumoDaGravacao(len(novos_achados) - atualizados, atualizados, len(sumiram))


def achados_de(
    conexao: sa.Connection, cnpj: str, em: datetime | None = None
) -> list[sa.Row]:
    """Os achados de uma empresa: os abertos hoje, ou como eram no momento `em`."""
    consulta = sa.select(tabela).where(tabela.c.cnpj == cnpj)
    if em is None:
        consulta = consulta.where(tabela.c.fechado_em.is_(None))
    else:
        consulta = consulta.where(
            tabela.c.valido_desde <= em,
            sa.or_(tabela.c.fechado_em.is_(None), tabela.c.fechado_em > em),
        )
    ordem = (tabela.c.referencia.desc(), tabela.c.regra, tabela.c.conta)
    return list(conexao.execute(consulta.order_by(*ordem)))
