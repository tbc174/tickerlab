"""Os links compartilhados no banco (onda 4 da ADR 0046). As regras ficam em `src/compartilhamentos.py`.

Dois lados:
- **a conta** (criar, listar, revogar, exportar): toda consulta filtra por `usuario_id`;
- **o público** (`abrir_link`, `pdf_do_link`): só com o código. Formato inválido nem chega ao
  banco; vencido, revogado, inexistente, PDF apagado ou com o hash trocado devolvem `None`, sem
  dizer qual foi o caso (quem tenta adivinhar não aprende nada).

O código do link só existe na volta de `criar_*`: o banco guarda o hash dele.
"""

import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from src import compartilhamentos as regras
from src.banco import pdfs_originais as pdfs
from src.banco.modelo import compartilhamentos, pdfs_originais, relatorios, usuarios
from src.compartilhamentos import FichaCongelada
from src.planos import conferir_links

log = logging.getLogger(__name__)

TAMANHO_MAXIMO_DO_NOME_DO_ARQUIVO = 60


class LinkInvalidoError(ValueError):
    """Não dá para compartilhar isto (não é da pessoa, não existe ou nunca se compartilha)."""


def _agora() -> datetime:
    return datetime.now(UTC)


def _com_fuso(momento: datetime | None) -> datetime | None:
    # o SQLite devolve a hora sem fuso: ela foi gravada em UTC
    if momento is None or momento.tzinfo is not None:
        return momento
    return momento.replace(tzinfo=UTC)


# --- a conta -------------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkDaConta:
    id: uuid.UUID
    tipo: str
    titulo: str
    criado_em: datetime
    expira_em: datetime
    revogado_em: datetime | None
    visitas: int
    ultima_visita_em: datetime | None
    situacao: str  # "ativo", "vencido" ou "revogado"


def _situacao(
    revogado_em: datetime | None, expira_em: datetime, agora: datetime
) -> str:
    if revogado_em is not None:
        return "revogado"
    return "ativo" if expira_em > agora else "vencido"


def _valendo(agora: datetime) -> sa.ColumnElement[bool]:
    return sa.and_(
        compartilhamentos.c.revogado_em.is_(None),
        compartilhamentos.c.expira_em > agora,
    )


def contar_ativos(
    conexao: sa.Connection, usuario_id: uuid.UUID, agora: datetime | None = None
) -> int:
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(compartilhamentos)
        .where(
            compartilhamentos.c.usuario_id == usuario_id, _valendo(agora or _agora())
        )
    ).scalar_one()


def _criar(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    plano: str | None,
    dias: int,
    agora: datetime,
    **valores: object,
) -> str:
    expira_em = regras.expira_em(agora, dias)
    conferir_links(plano, contar_ativos(conexao, usuario_id, agora))
    codigo = regras.novo_codigo()
    conexao.execute(
        sa.insert(compartilhamentos).values(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            codigo_hash=regras.hash_do_codigo(codigo),
            criado_em=agora,
            expira_em=expira_em,
            **valores,
        )
    )
    return codigo


def criar_link_da_ficha(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    plano: str | None,
    ficha: dict,
    dias: int,
    agora: datetime | None = None,
) -> str:
    """Guarda a ficha congelada e devolve o código do link (a única vez que ele aparece)."""
    lida = regras.ler_ficha_congelada(ficha)  # nunca guarda o que não se lê de volta
    return _criar(
        conexao,
        usuario_id,
        plano,
        dias,
        agora or _agora(),
        tipo="ficha",
        ficha=ficha,
        titulo=regras.titulo_da_ficha(lida.ticker, lida.estrategia),
    )


def criar_link_do_pdf(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    plano: str | None,
    relatorio_id: uuid.UUID,
    dias: int,
    agora: datetime | None = None,
) -> str:
    """Um link para o PDF original guardado na biblioteca da própria pessoa."""
    agora = agora or _agora()
    relatorio = conexao.execute(
        sa.select(relatorios.c.tipo, relatorios.c.titulo).where(
            relatorios.c.id == relatorio_id, relatorios.c.usuario_id == usuario_id
        )
    ).first()
    if (
        relatorio is None
        or not pdfs.pode_guardar(relatorio.tipo)
        or relatorio_id not in pdfs.pdfs_guardados(conexao, usuario_id, agora)
    ):
        raise LinkInvalidoError("Este PDF não está guardado na sua biblioteca.")
    return _criar(
        conexao,
        usuario_id,
        plano,
        dias,
        agora,
        tipo="pdf",
        relatorio_id=relatorio_id,
        titulo=relatorio.titulo or f"Relatório em PDF ({relatorio.tipo})",
    )


def listar_links(
    conexao: sa.Connection, usuario_id: uuid.UUID, agora: datetime | None = None
) -> list[LinkDaConta]:
    """Os links da pessoa, do mais novo para o mais antigo."""
    agora = agora or _agora()
    linhas = conexao.execute(
        sa.select(compartilhamentos)
        .where(compartilhamentos.c.usuario_id == usuario_id)
        .order_by(compartilhamentos.c.criado_em.desc(), compartilhamentos.c.id)
    ).all()
    lista = []
    for l in linhas:
        expira_em = _com_fuso(l.expira_em)
        revogado_em = _com_fuso(l.revogado_em)
        assert expira_em is not None
        lista.append(
            LinkDaConta(
                id=l.id,
                tipo=l.tipo,
                titulo=l.titulo,
                criado_em=_com_fuso(l.criado_em) or agora,
                expira_em=expira_em,
                revogado_em=revogado_em,
                visitas=l.visitas,
                ultima_visita_em=_com_fuso(l.ultima_visita_em),
                situacao=_situacao(revogado_em, expira_em, agora),
            )
        )
    return lista


def revogar_link(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    link_id: uuid.UUID,
    agora: datetime | None = None,
) -> bool:
    """Revoga um link da própria pessoa. Devolve se revogou (False: não é dela ou já estava)."""
    return (
        conexao.execute(
            sa.update(compartilhamentos)
            .where(
                compartilhamentos.c.id == link_id,
                compartilhamentos.c.usuario_id == usuario_id,
                compartilhamentos.c.revogado_em.is_(None),
            )
            .values(revogado_em=agora or _agora())
        ).rowcount
        > 0
    )


def dados_para_exportar(
    conexao: sa.Connection, usuario_id: uuid.UUID, agora: datetime | None = None
) -> list[dict]:
    """Os links na exportação dos dados (sem o hash; o código nunca foi guardado)."""
    fichas = dict(
        conexao.execute(
            sa.select(compartilhamentos.c.id, compartilhamentos.c.ficha).where(
                compartilhamentos.c.usuario_id == usuario_id
            )
        ).all()
    )
    return [
        {
            "tipo": l.tipo,
            "titulo": l.titulo,
            "criado_em": l.criado_em.isoformat(),
            "expira_em": l.expira_em.isoformat(),
            "revogado_em": l.revogado_em and l.revogado_em.isoformat(),
            "visitas": l.visitas,
            "ultima_visita_em": l.ultima_visita_em and l.ultima_visita_em.isoformat(),
            "situacao": l.situacao,
            "ficha": fichas.get(l.id),
        }
        for l in listar_links(conexao, usuario_id, agora)
    ]


# --- o público -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PdfDoLink:
    nome_do_arquivo: str
    tamanho: int  # bytes
    sha256: str
    gerado_em: datetime


@dataclass(frozen=True)
class LinkAberto:
    """O que a página pública mostra. Nada sobre quem compartilhou."""

    tipo: str
    titulo: str
    criado_em: datetime
    expira_em: datetime
    ficha: FichaCongelada | None = None
    pdf: PdfDoLink | None = None


def nome_do_arquivo(titulo: str) -> str:
    """ "Petrobras em 2026" → "TickerLab-Petrobras-em-2026.pdf" (só letras sem acento e números)."""
    sem_acento = (
        unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    )
    pedacos = re.sub(r"[^A-Za-z0-9]+", "-", sem_acento).strip("-")
    return f"TickerLab-{pedacos[:TAMANHO_MAXIMO_DO_NOME_DO_ARQUIVO] or 'relatorio'}.pdf"


def _linha_valendo(
    conexao: sa.Connection, codigo: object, agora: datetime
) -> sa.Row[Any] | None:
    if not regras.codigo_valido(codigo):
        return None
    assert isinstance(codigo, str)
    # o link da conta bloqueada no incidente para de abrir (e volta no desbloqueio)
    return conexao.execute(
        sa.select(compartilhamentos)
        .join(usuarios, usuarios.c.id == compartilhamentos.c.usuario_id)
        .where(
            compartilhamentos.c.codigo_hash == regras.hash_do_codigo(codigo),
            _valendo(agora),
            usuarios.c.bloqueada_em.is_(None),
        )
    ).first()


def _pdf_da_linha(
    conexao: sa.Connection, linha: sa.Row[Any], agora: datetime
) -> bytes | None:
    """O PDF do link, se ainda estiver guardado (e no prazo) e o hash conferir."""
    return pdfs.baixar_pdf_original(
        conexao, linha.usuario_id, linha.relatorio_id, agora
    )


def abrir_link(
    conexao: sa.Connection, codigo: object, agora: datetime | None = None
) -> LinkAberto | None:
    """O conteúdo do link para a página pública (e conta a visita), ou `None`."""
    agora = agora or _agora()
    linha = _linha_valendo(conexao, codigo, agora)
    if linha is None:
        return None
    ficha = pdf = None
    if linha.tipo == "ficha":
        try:
            ficha = regras.ler_ficha_congelada(linha.ficha)
        except ValueError:
            log.warning("Ficha compartilhada ilegível no banco (link %s)", linha.id)
            return None
    else:
        conteudo = _pdf_da_linha(conexao, linha, agora)
        if conteudo is None:
            return None
        guardado = conexao.execute(
            sa.select(pdfs_originais.c.sha256, pdfs_originais.c.gerado_em).where(
                pdfs_originais.c.relatorio_id == linha.relatorio_id,
                pdfs_originais.c.usuario_id == linha.usuario_id,
            )
        ).one()
        pdf = PdfDoLink(
            nome_do_arquivo=nome_do_arquivo(linha.titulo),
            tamanho=len(conteudo),
            sha256=guardado.sha256,
            gerado_em=_com_fuso(guardado.gerado_em) or agora,
        )
    conexao.execute(
        sa.update(compartilhamentos)
        .where(compartilhamentos.c.id == linha.id)
        .values(visitas=compartilhamentos.c.visitas + 1, ultima_visita_em=agora)
    )
    return LinkAberto(
        tipo=linha.tipo,
        titulo=linha.titulo,
        criado_em=_com_fuso(linha.criado_em) or agora,
        expira_em=_com_fuso(linha.expira_em) or agora,
        ficha=ficha,
        pdf=pdf,
    )


def pdf_do_link(
    conexao: sa.Connection, codigo: object, agora: datetime | None = None
) -> tuple[str, bytes] | None:
    """O nome do arquivo e o PDF de um link de PDF valendo, ou `None` (não conta visita)."""
    agora = agora or _agora()
    linha = _linha_valendo(conexao, codigo, agora)
    if linha is None or linha.tipo != "pdf":
        return None
    conteudo = _pdf_da_linha(conexao, linha, agora)
    if conteudo is None:
        return None
    return nome_do_arquivo(linha.titulo), conteudo
