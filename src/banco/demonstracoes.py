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
    tickers_dos_emissores,
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


TAMANHO_DO_SETOR = 120
TAMANHO_DO_TEXTO_DO_CADASTRO = 40  # situação e categoria


def _texto_do_cadastro(linha: dict, coluna: str, tamanho: int) -> str | None:
    """A coluna de texto cortada no tamanho da tabela; vazia ou ausente vira nulo."""
    texto = linha.get(coluna)
    return (texto[:tamanho] or None) if isinstance(texto, str) else None


def _data_do_cadastro(linha: dict, coluna: str) -> date | None:
    valor = linha.get(coluna)
    return valor if isinstance(valor, date) else None


def _linha_do_cadastro(linha: dict, agora: datetime) -> dict:
    return {
        "cnpj": linha["cnpj"],
        "setor": (linha["setor"] or "")[:TAMANHO_DO_SETOR],
        "situacao": _texto_do_cadastro(linha, "situacao", TAMANHO_DO_TEXTO_DO_CADASTRO),
        "situacao_desde": _data_do_cadastro(linha, "situacao_desde"),
        "categoria": _texto_do_cadastro(
            linha, "categoria", TAMANHO_DO_TEXTO_DO_CADASTRO
        ),
        "registro": _data_do_cadastro(linha, "registro"),
        "atualizado_em": agora,
    }


def gravar_setores(
    conexao: sa.Connection, setores: pd.DataFrame, agora: datetime | None = None
) -> int:
    """Substitui o cadastro da CVM (setor, situação, categoria, registro); vazio não apaga o guardado.

    Os setores das empresas dos EUA (`CIK...`, gravados por `gravar_setor`) ficam intactos. Um
    `setores` só com setor (de um arquivo antigo) grava as outras colunas nulas.
    """
    if setores.empty:
        return 0
    agora = agora or datetime.now(UTC)
    conexao.execute(
        sa.delete(setores_cvm).where(~setores_cvm.c.cnpj.startswith(PREFIXO_DO_CIK))
    )
    conexao.execute(
        sa.insert(setores_cvm),
        [_linha_do_cadastro(linha, agora) for linha in setores.to_dict("records")],
    )
    return len(setores)


def gravar_setor(conexao: sa.Connection, chave: str, setor: str) -> None:
    """O setor de uma empresa só (as dos EUA chegam uma por vez, pela coleta da SEC)."""
    conexao.execute(sa.delete(setores_cvm).where(setores_cvm.c.cnpj == chave))
    conexao.execute(
        sa.insert(setores_cvm).values(
            cnpj=chave, setor=(setor or "")[:TAMANHO_DO_SETOR]
        )
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


_COLUNAS_DA_CONTA = (
    "cnpj", "documento", "referencia", "periodo", "fim", "conta", "inicio", "versao", "valor",
)  # fmt: skip


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


def _na_mesma_versao(
    conexao: sa.Connection, documentos: pd.DataFrame, cnpjs: list[str]
) -> set[tuple]:
    """(cnpj, documento, referencia) dos documentos lidos que já estão guardados nesta versão."""
    guardadas = _versoes_guardadas(conexao, cnpjs)
    return {
        (d.cnpj, d.documento, d.referencia)
        for d in documentos.itertuples(index=False)
        if guardadas.get((d.cnpj, d.documento, d.referencia)) == d.versao
    }


def _registro_das_versoes_abertas(
    conexao: sa.Connection, cnpjs: list[str]
) -> dict[tuple, datetime]:
    """(cnpj, documento, referencia) → desde quando vale a versão aberta do documento."""
    v = demonstracoes_versoes
    return {
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
    mesma_versao = _na_mesma_versao(conexao, documentos, cnpjs)
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
    registrada_em = _registro_das_versoes_abertas(conexao, cnpjs)
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
        sa.insert(demonstracoes_versoes),
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


# contas que o leitor lia errado e passou a ler certo (relatório de fim da série 2, conferido no PDF
# da DFP 2025): o LPA quando a 1ª classe é zero (Vale, Gol) e a depreciação que somava linhas de
# juros "ao custo amortizado" (Itaú, Serena...)
LEITURAS_CORRIGIDAS = ("lpa_basico", "depreciacao")


def _por_conta(linhas: list[dict]) -> dict[tuple, list[dict]]:
    """(cnpj, documento, referencia, conta) → as linhas daquela conta no documento."""
    grupos: dict[tuple, list[dict]] = {}
    for linha in linhas:
        chave = (linha["cnpj"], linha["documento"], linha["referencia"], linha["conta"])
        grupos.setdefault(chave, []).append(linha)
    return grupos


def _mesmos_valores(a: list[dict], b: list[dict]) -> bool:
    def assinatura(linhas: list[dict]) -> list[tuple]:
        return sorted(
            (
                l["periodo"],
                str(l["fim"]),
                str(l["inicio"]),
                l["versao"],
                round(l["valor"], 4),
            )
            for l in linhas
        )

    return assinatura(a) == assinatura(b)


def corrigir_leituras(
    conexao: sa.Connection,
    contas: pd.DataFrame,
    documentos: pd.DataFrame,
    agora: datetime | None = None,
) -> int:
    """Troca, nos documentos já guardados **na mesma versão**, as contas de `LEITURAS_CORRIGIDAS`.

    Não é reapresentação: o valor certo sempre esteve naquela versão do documento; o TickerLab é que
    o lia errado. Como em `acrescentar_contas_novas`, a troca vale na versão aberta de
    `demonstracoes_versoes`, com o `registrado_em` dela e sem fechar nada, para "como estava em D"
    mostrar o que o documento dizia. Rodar de novo não muda nada. Devolve quantas contas trocou.
    """
    if documentos.empty or contas.empty:
        return 0
    agora = agora or datetime.now(UTC)
    cnpjs = sorted(set(documentos["cnpj"]))
    mesma_versao = _na_mesma_versao(conexao, documentos, cnpjs)
    lidas = _por_conta(
        [
            _linha_da_conta(l)
            for l in contas[contas["conta"].isin(LEITURAS_CORRIGIDAS)].itertuples(
                index=False
            )
            if (l.cnpj, l.documento, l.referencia) in mesma_versao
        ]
    )
    guardadas = _por_conta(
        [
            dict(l._mapping)
            for l in conexao.execute(
                sa.select(*[demonstracoes.c[c] for c in _COLUNAS_DA_CONTA]).where(
                    demonstracoes.c.cnpj.in_(cnpjs),
                    demonstracoes.c.conta.in_(LEITURAS_CORRIGIDAS),
                )
            )
            if (l.cnpj, l.documento, l.referencia) in mesma_versao
        ]
    )
    trocar = [
        chave
        for chave in lidas.keys() | guardadas.keys()
        if not _mesmos_valores(lidas.get(chave, []), guardadas.get(chave, []))
    ]
    registrada_em = _registro_das_versoes_abertas(conexao, cnpjs)
    for chave in trocar:
        _trocar_conta(
            conexao, chave, lidas.get(chave, []), registrada_em.get(chave[:3], agora)
        )
    return len(trocar)


def _trocar_conta(
    conexao: sa.Connection, chave: tuple, linhas: list[dict], registrada_em: datetime
) -> None:
    """Uma conta de um documento, trocada na tabela vigente e na versão aberta."""
    cnpj, documento, referencia, conta = chave
    for tabela, filtro_extra in (
        (demonstracoes, sa.true()),
        (demonstracoes_versoes, demonstracoes_versoes.c.substituido_em.is_(None)),
    ):
        conexao.execute(
            sa.delete(tabela).where(
                tabela.c.cnpj == cnpj,
                tabela.c.documento == documento,
                tabela.c.referencia == referencia,
                tabela.c.conta == conta,
                filtro_extra,
            )
        )
    if linhas:
        conexao.execute(sa.insert(demonstracoes), linhas)
        conexao.execute(
            sa.insert(demonstracoes_versoes),
            [{**l, "registrado_em": registrada_em} for l in linhas],
        )


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


def setores_dos_tickers(conexao: sa.Connection, tickers: list[str]) -> dict[str, str]:
    """O setor da CVM de cada ticker (com .SA) que tem empresa e setor cadastrados.

    Ticker sem empresa na CVM (FII, ETF, BDR) ou empresa sem setor fica de fora do dicionário.
    """
    if not tickers:
        return {}
    linhas = conexao.execute(
        sa.select(tickers_dos_emissores.c.ticker, setores_cvm.c.setor)
        .join(setores_cvm, setores_cvm.c.cnpj == tickers_dos_emissores.c.cnpj)
        .where(tickers_dos_emissores.c.ticker.in_(tickers), setores_cvm.c.setor != "")
    )
    return {ticker: setor for ticker, setor in linhas}
