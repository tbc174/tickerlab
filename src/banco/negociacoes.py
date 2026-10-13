"""Gravar e consultar as negociações de pessoas de dentro (Research R2) e os documentos já lidos.

Dados públicos, iguais para todos (sem `usuario_id`). A coleta roda fora do app
(`scripts/atualizar_negociacoes_cvm.py` e `scripts/atualizar_eventos_sec.py`); o app só consulta.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from src.banco.modelo import (
    documentos_lidos,
    negociacoes_internas,
    negociacoes_internas_versoes,
)
from src.banco.versoes import versionar
from src.links_das_fontes import link_da_fonte
from src.negociacoes import COLUNAS

TAMANHO_DO_LOTE = 5_000  # o SQLite limita o número de parâmetros de uma consulta


def _agora() -> datetime:
    return datetime.now(UTC)


def _em_pedacos(itens: Iterable[str]) -> Iterable[list[str]]:
    lista = list(dict.fromkeys(itens))
    for inicio in range(0, len(lista), TAMANHO_DO_LOTE):
        yield lista[inicio : inicio + TAMANHO_DO_LOTE]


def _versoes_guardadas(
    conexao: sa.Connection, fonte: str, documentos: Iterable[str]
) -> dict[str, int]:
    guardadas: dict[str, int] = {}
    for pedaco in _em_pedacos(documentos):
        consulta = (
            sa.select(
                negociacoes_internas.c.documento,
                sa.func.max(negociacoes_internas.c.versao),
            )
            .where(
                negociacoes_internas.c.fonte == fonte,
                negociacoes_internas.c.documento.in_(pedaco),
            )
            .group_by(negociacoes_internas.c.documento)
        )
        guardadas.update(conexao.execute(consulta).all())
    return guardadas


def _python(valor: object) -> object:
    """Vazio vira None e número do NumPy vira número do Python (o psycopg não aceita `int64`)."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    return valor.item() if hasattr(valor, "item") else valor


def _linhas(documento: pd.DataFrame, agora: datetime) -> list[dict]:
    linhas = []
    for linha in documento.to_dict("records"):
        valores = {c: _python(linha[c]) for c in COLUNAS}
        linhas.append({"id": uuid.uuid4(), **valores, "ingerido_em": agora})
    return linhas


def gravar_negociacoes(
    conexao: sa.Connection, tabela: pd.DataFrame, agora: datetime | None = None
) -> tuple[int, int]:
    """Grava documento por documento: novo entra; versão mais nova troca o documento inteiro;
    a mesma versão não muda nada. Devolve (documentos novos, documentos atualizados)."""
    if tabela.empty:
        return 0, 0
    agora = agora or _agora()
    novos = atualizados = 0
    for fonte, da_fonte in tabela.groupby("fonte"):
        guardadas = _versoes_guardadas(conexao, fonte, da_fonte["documento"])
        inserir = []
        for documento, linhas in da_fonte.groupby("documento"):
            versao, guardada = int(linhas["versao"].max()), guardadas.get(documento)
            if guardada is not None and versao <= guardada:
                continue
            if guardada is not None:
                conexao.execute(
                    sa.delete(negociacoes_internas).where(
                        negociacoes_internas.c.fonte == fonte,
                        negociacoes_internas.c.documento == documento,
                    )
                )
                atualizados += 1
            else:
                novos += 1
            do_documento = _linhas(linhas, agora)
            chave = {"fonte": fonte, "documento": documento}
            versionar(conexao, negociacoes_internas_versoes, chave, do_documento, agora)
            inserir += do_documento
        if inserir:
            conexao.execute(sa.insert(negociacoes_internas), inserir)
    return novos, atualizados


def ja_lidos(conexao: sa.Connection, fonte: str, documentos: Iterable[str]) -> set[str]:
    """Quais destes documentos a coleta já leu (com ou sem negociações)."""
    lidos: set[str] = set()
    for pedaco in _em_pedacos(documentos):
        lidos.update(
            conexao.execute(
                sa.select(documentos_lidos.c.documento).where(
                    documentos_lidos.c.fonte == fonte,
                    documentos_lidos.c.documento.in_(pedaco),
                )
            ).scalars()
        )
    return lidos


def marcar_como_lidos(
    conexao: sa.Connection, fonte: str, documentos: Iterable[str]
) -> None:
    novos = set(documentos) - ja_lidos(conexao, fonte, documentos)
    if novos:
        conexao.execute(
            sa.insert(documentos_lidos),
            [
                {"fonte": fonte, "documento": d, "lido_em": _agora()}
                for d in sorted(novos)
            ],
        )


def negociacoes(
    conexao: sa.Connection, desde: date, cnpjs: Iterable[str] | None = None
) -> pd.DataFrame:
    """As negociações tornadas públicas desde `desde` (de algumas empresas ou de todas)."""
    consulta = sa.select(*(negociacoes_internas.c[c] for c in COLUNAS)).where(
        negociacoes_internas.c.entregue_em >= desde
    )
    if cnpjs is not None:
        consulta = consulta.where(negociacoes_internas.c.cnpj.in_(list(cnpjs)))
    linhas = conexao.execute(
        consulta.order_by(
            negociacoes_internas.c.entregue_em.desc(),
            negociacoes_internas.c.data.desc(),
        )
    ).all()
    tabela = pd.DataFrame(linhas, columns=COLUNAS)
    # vazio = sem link: só endereço https da CVM ou da SEC vira link (src/links_das_fontes.py)
    tabela["link"] = [link_da_fonte(link) or "" for link in tabela["link"]]
    return tabela


def ultima_coleta(conexao: sa.Connection) -> datetime | None:
    return conexao.execute(
        sa.select(sa.func.max(negociacoes_internas.c.ingerido_em))
    ).scalar()
