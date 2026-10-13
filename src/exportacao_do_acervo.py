"""Exportação controlada do acervo (Radar, PR 7; ADR 0024 do autor): só para administradores.

Sai um zip com os dados (CSV ou Parquet, com todas as versões guardadas) e um LEIA-ME com a
fonte e a licença de cada parte. Regras:

- **Só fontes com licença que permite**: CVM, SEC, Banco Central, Tesouro dos EUA. As séries de uso
  interno (preços do Yahoo) **nunca** saem, e o teste confere.
- **ODbL** (CVM e Banco Central): citar a fonte; uma base derivada publicada continua sob a ODbL.
  O LEIA-ME diz isso.
- Cada exportação fica na auditoria (quem, qual base, formato e quantas linhas; só ids).
"""

import io
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
import sqlalchemy as sa

from src import auditoria
from src.administracao import exigir_admin
from src.banco.coletas import licenca_da_fonte
from src.banco.modelo import (
    demonstracoes_versoes,
    eventos_versoes,
    observacoes,
    series,
)
from src.banco.series import series_para_exportar

FORMATOS = ("csv", "parquet")
ACAO_ACERVO_EXPORTADO = "acervo_exportado"
PREFIXO_DO_CIK = "CIK"  # demonstrações da SEC guardam o CIK no lugar do CNPJ
AVISO_ODBL = (
    "Partes sob a Open Database License (ODbL 1.0): cite a fonte; se publicar uma base derivada "
    "destes dados, ela continua sob a ODbL (https://opendatacommons.org/licenses/odbl/1-0/)."
)


class ExportacaoInvalidaError(ValueError):
    """Base ou formato que não existe."""


@dataclass(frozen=True)
class Base:
    nome: str
    descricao: str


BASES = {
    "series": Base(
        "Séries macro", "BC (SGS, PTAX, Focus) e Tesouro dos EUA, todas as safras"
    ),
    "eventos": Base("Eventos", "CVM (IPE) e SEC, todas as versões"),
    "demonstracoes": Base("Demonstrações", "CVM (DFP e ITR) e SEC, todas as versões"),
}


def _familia(fonte: str) -> str:
    """A família da fonte para a licença: "cvm_ipe" → "cvm"; "bcb-sgs-433" → "bcb"."""
    return fonte.replace("_", "-").split("-", 1)[0]


def _tabela_de_series(conexao: sa.Connection) -> pd.DataFrame:
    permitidas = series_para_exportar(conexao)  # nunca as de uso interno
    consulta = (
        sa.select(
            observacoes.c.serie,
            series.c.nome,
            series.c.unidade,
            observacoes.c.referencia,
            observacoes.c.valor,
            observacoes.c.divulgado_em,
            observacoes.c.registrado_em,
        )
        .join(series, series.c.codigo == observacoes.c.serie)
        .where(observacoes.c.serie.in_(permitidas), series.c.uso_interno.is_(False))
        .order_by(
            observacoes.c.serie, observacoes.c.referencia, observacoes.c.divulgado_em
        )
    )
    tabela = pd.DataFrame(conexao.execute(consulta).mappings().all())
    if not tabela.empty:
        tabela["fonte"] = tabela["serie"].map(_familia)
    return tabela


def _tabela(
    conexao: sa.Connection, versoes: sa.Table, ordem: list[str]
) -> pd.DataFrame:
    consulta = sa.select(versoes).order_by(*[versoes.c[c] for c in ordem])
    tabela = pd.DataFrame(conexao.execute(consulta).mappings().all())
    return tabela.drop(columns=["id_da_versao"], errors="ignore")


def ler_base(conexao: sa.Connection, base: str) -> pd.DataFrame:
    """A base inteira, com as versões, pronta para sair (sem nada de uso interno)."""
    if base == "series":
        return _tabela_de_series(conexao)
    if base == "eventos":
        return _tabela(conexao, eventos_versoes, ["fonte", "protocolo", "versao"])
    if base == "demonstracoes":
        tabela = _tabela(
            conexao,
            demonstracoes_versoes,
            ["cnpj", "documento", "referencia", "id_da_versao"],
        )
        if not tabela.empty:
            da_sec = tabela["cnpj"].str.startswith(PREFIXO_DO_CIK)
            tabela["fonte"] = da_sec.map({True: "sec", False: "cvm"})
        return tabela
    raise ExportacaoInvalidaError(f"Base desconhecida: {base}")


def _familias(tabela: pd.DataFrame) -> list[str]:
    if tabela.empty or "fonte" not in tabela:
        return []
    return sorted({_familia(f) for f in tabela["fonte"].dropna().unique()})


def leia_me(base: str, tabela: pd.DataFrame, agora: datetime) -> str:
    """O texto que acompanha os dados: o que é, de onde veio e sob qual licença."""
    familias = _familias(tabela)
    linhas = [
        f"TickerLab: exportação do acervo, base {BASES[base].nome}",
        f"Gerada em {agora:%d/%m/%Y %H:%M} (UTC). {len(tabela)} linhas.",
        f"Conteúdo: {BASES[base].descricao}. Cada revisão da fonte é uma linha a mais;",
        "registrado_em/substituido_em (ou divulgado_em, nas séries) dizem quando valia.",
        "",
        "Fontes e licenças:",
        *[f"- {familia.upper()}: {licenca_da_fonte(familia)}" for familia in familias],
    ]
    if any("ODbL" in licenca_da_fonte(f) for f in familias):
        linhas += ["", AVISO_ODBL]
    linhas += ["", "Dados para estudo; nada aqui é recomendação de investimento."]
    return "\n".join(linhas) + "\n"


def _dados(tabela: pd.DataFrame, formato: str) -> bytes:
    if formato == "csv":
        return tabela.to_csv(index=False).encode("utf-8")
    saida = io.BytesIO()
    tabela.to_parquet(saida, index=False)
    return saida.getvalue()


def exportar(
    conexao: sa.Connection,
    ator_id: uuid.UUID | None,
    base: str,
    formato: str,
    agora: datetime | None = None,
) -> tuple[str, bytes]:
    """O nome e o conteúdo do zip. Só administradores; o pedido fica na auditoria."""
    exigir_admin(conexao, ator_id)
    if base not in BASES or formato not in FORMATOS:
        raise ExportacaoInvalidaError("Escolha uma base e um formato da lista.")
    agora = agora or datetime.now(UTC)
    tabela = ler_base(conexao, base)
    nome = f"tickerlab-{base}-{agora:%Y%m%d}"
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr(f"{nome}.{formato}", _dados(tabela, formato))
        arquivo.writestr("LEIA-ME.txt", leia_me(base, tabela, agora))
    auditoria.registrar(
        conexao,
        ator_id,
        ACAO_ACERVO_EXPORTADO,
        detalhes={"base": base, "formato": formato, "linhas": len(tabela)},
    )
    return f"{nome}.zip", saida.getvalue()
