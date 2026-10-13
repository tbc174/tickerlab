"""PDF original dos relatórios da biblioteca (Master v3, Fase C.4; ADR 0021 do autor).

Além de "reabrir com os dados de hoje", a biblioteca guarda o PDF como foi entregue: quem
precisa provar o que um relatório dizia num dia baixa o arquivo original. Regras:

- **toda função recebe o `usuario_id` e filtra por ele** (como em `dados_do_usuario`);
- o relatório "Minha carteira" nunca é guardado (a planilha da B3 não fica no TickerLab);
- cada plano guarda até `Limites.pdfs_guardados` PDFs: passou, o mais antigo sai;
- depois de `DIAS_GUARDADO` dias o PDF some; excluir da biblioteca apaga na hora;
- o hash SHA-256 é conferido na hora de baixar (arquivo diferente do gravado não é entregue).
"""

import hashlib
import io
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src.banco.modelo import pdfs_originais, relatorios
from src.planos import limites_do

DIAS_GUARDADO = 365
TIPOS_NUNCA_GUARDADOS = frozenset({"minha_carteira"})
TAMANHO_MAXIMO_DO_PDF = 20 * 1024 * 1024  # um relatório tem de 100 a 300 KB


@dataclass(frozen=True)
class PdfGuardado:
    relatorio_id: uuid.UUID
    sha256: str
    tamanho: int
    gerado_em: datetime


def _agora() -> datetime:
    return datetime.now(UTC)


def pode_guardar(tipo: str) -> bool:
    return tipo not in TIPOS_NUNCA_GUARDADOS


def _hash(pdf: bytes) -> str:
    return hashlib.sha256(pdf).hexdigest()


def guardar_pdf_original(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    relatorio_id: uuid.UUID,
    plano: str | None,
    pdf: bytes,
    versoes: dict,
    agora: datetime | None = None,
) -> bool:
    """Guarda o PDF de um relatório do próprio usuário. Devolve se guardou.

    Não guarda "Minha carteira" nem relatório de outra pessoa. Depois de guardar, aplica o prazo
    e a cota do plano (os mais antigos saem).
    """
    if not pdf or len(pdf) > TAMANHO_MAXIMO_DO_PDF:
        raise ValueError("O PDF está vazio ou é grande demais para guardar.")
    tipo = conexao.execute(
        sa.select(relatorios.c.tipo).where(
            relatorios.c.id == relatorio_id, relatorios.c.usuario_id == usuario_id
        )
    ).scalar()
    if tipo is None or not pode_guardar(tipo):
        return False
    agora = agora or _agora()
    conexao.execute(
        sa.insert(pdfs_originais).values(
            relatorio_id=relatorio_id,
            usuario_id=usuario_id,
            pdf=pdf,
            sha256=_hash(pdf),
            tamanho=len(pdf),
            versoes=versoes,
            gerado_em=agora,
        )
    )
    _aplicar_prazo_e_cota(conexao, usuario_id, plano, agora)
    return True


def _aplicar_prazo_e_cota(
    conexao: sa.Connection, usuario_id: uuid.UUID, plano: str | None, agora: datetime
) -> None:
    do_usuario = pdfs_originais.c.usuario_id == usuario_id
    conexao.execute(
        sa.delete(pdfs_originais).where(
            do_usuario,
            pdfs_originais.c.gerado_em < agora - timedelta(days=DIAS_GUARDADO),
        )
    )
    alem_da_cota = (
        sa.select(pdfs_originais.c.relatorio_id)
        .where(do_usuario)
        .order_by(pdfs_originais.c.gerado_em.desc(), pdfs_originais.c.relatorio_id)
        .offset(limites_do(plano).pdfs_guardados)
    )
    sobrando = list(conexao.execute(alem_da_cota).scalars())
    if sobrando:
        conexao.execute(
            sa.delete(pdfs_originais).where(
                do_usuario, pdfs_originais.c.relatorio_id.in_(sobrando)
            )
        )


def pdfs_guardados(
    conexao: sa.Connection, usuario_id: uuid.UUID, agora: datetime | None = None
) -> dict[uuid.UUID, PdfGuardado]:
    """Os PDFs guardados do usuário (sem o conteúdo), dentro do prazo, por relatório."""
    limite = (agora or _agora()) - timedelta(days=DIAS_GUARDADO)
    return {
        l.relatorio_id: PdfGuardado(l.relatorio_id, l.sha256, l.tamanho, l.gerado_em)
        for l in conexao.execute(
            sa.select(
                pdfs_originais.c.relatorio_id,
                pdfs_originais.c.sha256,
                pdfs_originais.c.tamanho,
                pdfs_originais.c.gerado_em,
            ).where(
                pdfs_originais.c.usuario_id == usuario_id,
                pdfs_originais.c.gerado_em >= limite,
            )
        )
    }


def baixar_pdf_original(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    relatorio_id: uuid.UUID,
    agora: datetime | None = None,
) -> bytes | None:
    """O PDF como foi entregue, se for deste usuário, estiver no prazo e o hash conferir."""
    limite = (agora or _agora()) - timedelta(days=DIAS_GUARDADO)
    linha = conexao.execute(
        sa.select(pdfs_originais.c.pdf, pdfs_originais.c.sha256).where(
            pdfs_originais.c.relatorio_id == relatorio_id,
            pdfs_originais.c.usuario_id == usuario_id,
            pdfs_originais.c.gerado_em >= limite,
        )
    ).first()
    if linha is None or _hash(bytes(linha.pdf)) != linha.sha256:
        return None
    return bytes(linha.pdf)


def apagar_pdf_original(
    conexao: sa.Connection, usuario_id: uuid.UUID, relatorio_id: uuid.UUID
) -> None:
    conexao.execute(
        sa.delete(pdfs_originais).where(
            pdfs_originais.c.relatorio_id == relatorio_id,
            pdfs_originais.c.usuario_id == usuario_id,
        )
    )


def apagar_pdfs_vencidos(conexao: sa.Connection, agora: datetime | None = None) -> int:
    """Manutenção (de todos os usuários): apaga os PDFs com mais de `DIAS_GUARDADO` dias.

    Não lê nenhum dado: só apaga pelo prazo. Devolve quantos saíram.
    """
    limite = (agora or _agora()) - timedelta(days=DIAS_GUARDADO)
    return conexao.execute(
        sa.delete(pdfs_originais).where(pdfs_originais.c.gerado_em < limite)
    ).rowcount


def pdfs_em_zip(
    conexao: sa.Connection, usuario_id: uuid.UUID, agora: datetime | None = None
) -> bytes:
    """Todos os PDFs guardados do usuário num .zip (exportação da LGPD).

    Sem PDF guardado, o .zip leva só um aviso (o arquivo continua válido para abrir).
    """
    limite = (agora or _agora()) - timedelta(days=DIAS_GUARDADO)
    linhas = conexao.execute(
        sa.select(
            pdfs_originais.c.pdf,
            pdfs_originais.c.gerado_em,
            pdfs_originais.c.relatorio_id,
            relatorios.c.tipo,
        )
        .join(relatorios, relatorios.c.id == pdfs_originais.c.relatorio_id)
        .where(
            pdfs_originais.c.usuario_id == usuario_id,
            pdfs_originais.c.gerado_em >= limite,
        )
        .order_by(pdfs_originais.c.gerado_em)
    ).all()
    arquivo = io.BytesIO()
    with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED) as zip_:
        if not linhas:
            zip_.writestr(
                "LEIA-ME.txt", "Nenhum PDF original guardado na sua biblioteca.\n"
            )
        for l in linhas:
            nome = (
                f"{l.gerado_em:%Y-%m-%d_%H%M%S}_{l.tipo}_{str(l.relatorio_id)[:8]}.pdf"
            )
            zip_.writestr(nome, bytes(l.pdf))
    return arquivo.getvalue()
