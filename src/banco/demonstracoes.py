"""Gravar e ler as demonstrações financeiras da CVM (Research, etapa 3a).

Dados públicos, iguais para todos. A coleta roda fora do app (`scripts/atualizar_fundamentos.py`);
o app só lê. Um documento (empresa + DFP/ITR + data) é trocado inteiro quando chega uma versão
mais nova: nunca ficam contas de versões diferentes misturadas.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from src.banco.modelo import (
    demonstracoes,
    demonstracoes_versoes,
    documentos_financeiros,
    documentos_financeiros_versoes,
    setores_cvm,
)
from src.banco.versoes import versionar
from src.links_das_fontes import link_da_fonte


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


PREFIXO_DO_CIK = "CIK"  # empresas dos EUA (SEC) guardadas no lugar do CNPJ


def gravar_setores(conexao: sa.Connection, setores: pd.DataFrame) -> int:
    """Substitui o mapa CNPJ → setor da CVM (um cadastro vazio não apaga o guardado).

    Os setores das empresas dos EUA (`CIK...`, gravados por `gravar_setor`) ficam intactos.
    """
    if setores.empty:
        return 0
    conexao.execute(
        sa.delete(setores_cvm).where(~setores_cvm.c.cnpj.startswith(PREFIXO_DO_CIK))
    )
    conexao.execute(
        sa.insert(setores_cvm),
        [
            {"cnpj": l.cnpj, "setor": (l.setor or "")[:120]}
            for l in setores.itertuples()
        ],
    )
    return len(setores)


def gravar_setor(conexao: sa.Connection, chave: str, setor: str) -> None:
    """O setor de uma empresa só (as dos EUA chegam uma por vez, pela coleta da SEC)."""
    conexao.execute(sa.delete(setores_cvm).where(setores_cvm.c.cnpj == chave))
    conexao.execute(
        sa.insert(setores_cvm).values(cnpj=chave, setor=(setor or "")[:120])
    )


def referencias_guardadas(conexao: sa.Connection, chave: str) -> set[date]:
    """As datas de balanço já guardadas de uma empresa."""
    return set(
        conexao.execute(
            sa.select(documentos_financeiros.c.referencia).where(
                documentos_financeiros.c.cnpj == chave
            )
        ).scalars()
    )


def _linha_da_conta(l: object) -> dict:
    """Uma conta lida (linha de `ler_demonstracoes`) no formato da tabela `demonstracoes`."""
    return {
        "cnpj": l.cnpj,  # type: ignore[attr-defined]
        "documento": l.documento,  # type: ignore[attr-defined]
        "referencia": l.referencia,  # type: ignore[attr-defined]
        "periodo": l.periodo,  # type: ignore[attr-defined]
        "fim": l.fim,  # type: ignore[attr-defined]
        "conta": l.conta,  # type: ignore[attr-defined]
        "inicio": _data(l.inicio),  # type: ignore[attr-defined]
        "versao": int(l.versao),  # type: ignore[attr-defined]
        "valor": float(l.valor),  # type: ignore[attr-defined]
    }


def _versoes_guardadas(conexao: sa.Connection, cnpjs: list[str]) -> dict[tuple, int]:
    """(cnpj, documento, referencia) → versão guardada, só das empresas pedidas."""
    return {
        (l.cnpj, l.documento, l.referencia): l.versao
        for l in conexao.execute(
            sa.select(
                documentos_financeiros.c.cnpj,
                documentos_financeiros.c.documento,
                documentos_financeiros.c.referencia,
                documentos_financeiros.c.versao,
            ).where(documentos_financeiros.c.cnpj.in_(cnpjs))
        )
    }


def _trocar_documento(
    conexao: sa.Connection, doc: object, linhas: pd.DataFrame | None, agora: datetime
) -> None:
    """Apaga a versão guardada de um documento e grava a nova, inteira (contas e índice).

    A versão anterior continua em `demonstracoes_versoes` (Radar, PR 4)."""
    filtro = (
        (demonstracoes.c.cnpj == doc.cnpj)
        & (demonstracoes.c.documento == doc.documento)
        & (demonstracoes.c.referencia == doc.referencia)
    )
    conexao.execute(sa.delete(demonstracoes).where(filtro))
    contas = [
        _linha_da_conta(l)
        for l in (linhas.itertuples(index=False) if linhas is not None else [])
    ]
    if contas:
        conexao.execute(sa.insert(demonstracoes), contas)
    chave = {"cnpj": doc.cnpj, "documento": doc.documento, "referencia": doc.referencia}
    versionar(conexao, demonstracoes_versoes, chave, contas, agora)
    conexao.execute(
        sa.delete(documentos_financeiros).where(
            (documentos_financeiros.c.cnpj == doc.cnpj)
            & (documentos_financeiros.c.documento == doc.documento)
            & (documentos_financeiros.c.referencia == doc.referencia)
        )
    )
    indice = {
        **chave,
        "versao": int(doc.versao),
        "empresa": doc.empresa[:200],
        "recebido_em": _data(doc.recebido_em),
        "link": doc.link[:500],
    }
    conexao.execute(
        sa.insert(documentos_financeiros).values(**indice, coletado_em=agora)
    )
    versionar(conexao, documentos_financeiros_versoes, chave, [indice], agora)


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
    # só as empresas deste lote: a coleta da SEC grava uma empresa por vez
    guardadas = _versoes_guardadas(conexao, sorted(set(documentos["cnpj"])))
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


def acrescentar_contas_novas(
    conexao: sa.Connection,
    contas: pd.DataFrame,
    documentos: pd.DataFrame,
    agora: datetime | None = None,
) -> int:
    """Grava as contas que o leitor passou a ler em documentos já guardados **na mesma versão**.

    Não é reapresentação: os valores sempre estiveram naquela versão do documento, o TickerLab só
    passou a lê-los (série 2 da base de ML, PR 1). Por isso entram na versão aberta de
    `demonstracoes_versoes` com o `registrado_em` dela, sem fechar nada, e "como estava em D"
    continua verdadeiro. Conta que já existe no documento não é tocada (mudança de valor é
    reapresentação, de `gravar_demonstracoes`). Devolve quantas contas gravou.
    """
    if documentos.empty or contas.empty:
        return 0
    agora = agora or datetime.now(UTC)
    cnpjs = sorted(set(documentos["cnpj"]))
    guardadas = _versoes_guardadas(conexao, cnpjs)
    mesma_versao = {
        (d.cnpj, d.documento, d.referencia)
        for d in documentos.itertuples(index=False)
        if guardadas.get((d.cnpj, d.documento, d.referencia)) == d.versao
    }
    existentes = {
        tuple(linha)
        for linha in conexao.execute(
            sa.select(
                demonstracoes.c.cnpj,
                demonstracoes.c.documento,
                demonstracoes.c.referencia,
                demonstracoes.c.conta,
            ).where(demonstracoes.c.cnpj.in_(cnpjs))
        )
    }
    v = demonstracoes_versoes
    registrada_em = {
        (l.cnpj, l.documento, l.referencia): l.desde
        for l in conexao.execute(
            sa.select(
                v.c.cnpj,
                v.c.documento,
                v.c.referencia,
                sa.func.min(v.c.registrado_em).label("desde"),
            )
            .where(v.c.cnpj.in_(cnpjs), v.c.substituido_em.is_(None))
            .group_by(v.c.cnpj, v.c.documento, v.c.referencia)
        )
    }
    novas = [
        _linha_da_conta(l)
        for l in contas.itertuples(index=False)
        if (l.cnpj, l.documento, l.referencia) in mesma_versao
        and (l.cnpj, l.documento, l.referencia, l.conta) not in existentes
    ]
    if not novas:
        return 0
    conexao.execute(sa.insert(demonstracoes), novas)
    conexao.execute(
        sa.insert(v),
        [
            {
                **n,
                "registrado_em": registrada_em.get(
                    (n["cnpj"], n["documento"], n["referencia"]), agora
                ),
            }
            for n in novas
        ],
    )
    return len(novas)


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
    # vazio = sem link: só endereço https da CVM ou da SEC vira link (src/links_das_fontes.py)
    documentos["link"] = [link_da_fonte(link) or "" for link in documentos["link"]]
    setor = conexao.execute(
        sa.select(setores_cvm.c.setor).where(setores_cvm.c.cnpj == cnpj)
    ).scalar()
    return DadosDaEmpresa(contas, documentos, setor or "")


def ultima_coleta_de_demonstracoes(conexao: sa.Connection) -> datetime | None:
    return conexao.execute(
        sa.select(sa.func.max(documentos_financeiros.c.coletado_em))
    ).scalar()
