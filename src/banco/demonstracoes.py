"""Gravar e ler as demonstrações financeiras da CVM (Research, etapa 3a).

Dados públicos, iguais para todos. A coleta roda fora do app (`scripts/atualizar_fundamentos.py`);
o app só lê. Um documento (empresa + DFP/ITR + data) é trocado inteiro quando chega uma versão
mais nova: nunca ficam contas de versões diferentes misturadas.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
import sqlalchemy as sa

from src.banco.modelo import demonstracoes, documentos_financeiros, setores_cvm


@dataclass(frozen=True)
class DadosDaEmpresa:
    contas: (
        pd.DataFrame
    )  # documento, referencia, versao, periodo, inicio, fim, conta, valor
    documentos: (
        pd.DataFrame
    )  # documento, referencia, versao, empresa, recebido_em, link
    setor: str


def _data(valor: object) -> object:
    return None if valor is None or pd.isna(valor) else valor


def gravar_setores(conexao: sa.Connection, setores: pd.DataFrame) -> int:
    """Substitui o mapa CNPJ → setor (um cadastro vazio não apaga o guardado)."""
    if setores.empty:
        return 0
    conexao.execute(sa.delete(setores_cvm))
    conexao.execute(
        sa.insert(setores_cvm),
        [
            {"cnpj": l.cnpj, "setor": (l.setor or "")[:120]}
            for l in setores.itertuples()
        ],
    )
    return len(setores)


def _trocar_documento(
    conexao: sa.Connection, doc: object, linhas: pd.DataFrame | None, agora: datetime
) -> None:
    """Apaga a versão guardada de um documento e grava a nova, inteira (contas e índice)."""
    filtro = (
        (demonstracoes.c.cnpj == doc.cnpj)
        & (demonstracoes.c.documento == doc.documento)
        & (demonstracoes.c.referencia == doc.referencia)
    )
    conexao.execute(sa.delete(demonstracoes).where(filtro))
    if linhas is not None and not linhas.empty:
        conexao.execute(
            sa.insert(demonstracoes),
            [
                {
                    "cnpj": l.cnpj,
                    "documento": l.documento,
                    "referencia": l.referencia,
                    "periodo": l.periodo,
                    "fim": l.fim,
                    "conta": l.conta,
                    "inicio": _data(l.inicio),
                    "versao": int(l.versao),
                    "valor": float(l.valor),
                }
                for l in linhas.itertuples(index=False)
            ],
        )
    conexao.execute(
        sa.delete(documentos_financeiros).where(
            (documentos_financeiros.c.cnpj == doc.cnpj)
            & (documentos_financeiros.c.documento == doc.documento)
            & (documentos_financeiros.c.referencia == doc.referencia)
        )
    )
    conexao.execute(
        sa.insert(documentos_financeiros).values(
            cnpj=doc.cnpj,
            documento=doc.documento,
            referencia=doc.referencia,
            versao=int(doc.versao),
            empresa=doc.empresa[:200],
            recebido_em=_data(doc.recebido_em),
            link=doc.link[:500],
            coletado_em=agora,
        )
    )


def gravar_demonstracoes(
    conexao: sa.Connection,
    contas: pd.DataFrame,
    documentos: pd.DataFrame,
    agora: datetime | None = None,
) -> int:
    """Grava os documentos novos ou com versão mais nova. Devolve quantos documentos mudaram.

    Rodar de novo com o mesmo arquivo não muda nada.
    """
    if documentos.empty:
        return 0
    agora = agora or datetime.now(UTC)
    guardadas = {
        (l.cnpj, l.documento, l.referencia): l.versao
        for l in conexao.execute(
            sa.select(
                documentos_financeiros.c.cnpj,
                documentos_financeiros.c.documento,
                documentos_financeiros.c.referencia,
                documentos_financeiros.c.versao,
            )
        )
    }
    mudaram = 0
    contas_por_documento = dict(
        tuple(contas.groupby(["cnpj", "documento", "referencia"]))
    )
    for doc in documentos.itertuples(index=False):
        chave = (doc.cnpj, doc.documento, doc.referencia)
        if guardadas.get(chave, 0) >= doc.versao:
            continue
        linhas = contas_por_documento.get(chave)
        _trocar_documento(conexao, doc, linhas, agora)
        mudaram += 1
    return mudaram


def dados_da_empresa(conexao: sa.Connection, cnpj: str) -> DadosDaEmpresa:
    """Tudo o que está guardado de uma companhia (para o cálculo dos fundamentos)."""
    contas = pd.DataFrame(
        conexao.execute(
            sa.select(
                demonstracoes.c.documento,
                demonstracoes.c.referencia,
                demonstracoes.c.versao,
                demonstracoes.c.periodo,
                demonstracoes.c.inicio,
                demonstracoes.c.fim,
                demonstracoes.c.conta,
                demonstracoes.c.valor,
            ).where(demonstracoes.c.cnpj == cnpj)
        ).all(),
        columns=[
            "documento",
            "referencia",
            "versao",
            "periodo",
            "inicio",
            "fim",
            "conta",
            "valor",
        ],
    )
    documentos = pd.DataFrame(
        conexao.execute(
            sa.select(
                documentos_financeiros.c.documento,
                documentos_financeiros.c.referencia,
                documentos_financeiros.c.versao,
                documentos_financeiros.c.empresa,
                documentos_financeiros.c.recebido_em,
                documentos_financeiros.c.link,
            ).where(documentos_financeiros.c.cnpj == cnpj)
        ).all(),
        columns=["documento", "referencia", "versao", "empresa", "recebido_em", "link"],
    )
    setor = conexao.execute(
        sa.select(setores_cvm.c.setor).where(setores_cvm.c.cnpj == cnpj)
    ).scalar()
    return DadosDaEmpresa(contas, documentos, setor or "")


def ultima_coleta_de_demonstracoes(conexao: sa.Connection) -> datetime | None:
    return conexao.execute(
        sa.select(sa.func.max(documentos_financeiros.c.coletado_em))
    ).scalar()
