"""Gravar e consultar as leituras dos documentos (Research R5): resumos e fatores de risco.

Dados públicos, iguais para todos. A coleta roda fora do app (`scripts/atualizar_leituras_cvm.py`
e a coleta da SEC); o app só consulta.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime

import sqlalchemy as sa

from src import topicos
from src.banco.modelo import eventos, leituras
from src.leitura import VERSAO
from src.links_das_fontes import link_da_fonte

RESUMO, RISCOS = "resumo", "riscos"
TOPICO = "topico"  # o assunto do fato relevante (leitor v2, ADR 0069), com a versão de topicos
TAMANHO_DO_LOTE = 5_000


def gravar_leitura(
    conexao: sa.Connection,
    fonte: str,
    documento: str,
    tipo: str,
    cnpj: str,
    referencia: date | None,
    resultado: dict,
    versao: str = VERSAO,
) -> None:
    """Grava (ou troca) a leitura de um documento (`versao`: a do algoritmo que leu)."""
    conexao.execute(
        sa.delete(leituras).where(
            leituras.c.fonte == fonte,
            leituras.c.documento == documento,
            leituras.c.tipo == tipo,
        )
    )
    conexao.execute(
        sa.insert(leituras).values(
            fonte=fonte,
            documento=documento,
            tipo=tipo,
            cnpj=cnpj,
            referencia=referencia,
            resultado=resultado,
            versao=versao,
            lido_em=datetime.now(UTC),
        )
    )


def lidos(
    conexao: sa.Connection, fonte: str, tipo: str, documentos: Iterable[str]
) -> set[str]:
    """Quais destes documentos já têm leitura (na versão atual do algoritmo)."""
    pedidos = list(dict.fromkeys(documentos))
    achados: set[str] = set()
    for inicio in range(0, len(pedidos), TAMANHO_DO_LOTE):
        achados.update(
            conexao.execute(
                sa.select(leituras.c.documento).where(
                    leituras.c.fonte == fonte,
                    leituras.c.tipo == tipo,
                    leituras.c.versao == VERSAO,
                    leituras.c.documento.in_(
                        pedidos[inicio : inicio + TAMANHO_DO_LOTE]
                    ),
                )
            ).scalars()
        )
    return achados


def resumos(
    conexao: sa.Connection, fonte: str, documentos: Iterable[str]
) -> dict[str, dict]:
    """protocolo → resumo (para mostrar junto dos eventos)."""
    pedidos = list(dict.fromkeys(documentos))
    if not pedidos:
        return {}
    consulta = sa.select(leituras.c.documento, leituras.c.resultado).where(
        leituras.c.fonte == fonte,
        leituras.c.tipo == RESUMO,
        leituras.c.documento.in_(pedidos[:TAMANHO_DO_LOTE]),
    )
    return {
        documento: dict(resultado) for documento, resultado in conexao.execute(consulta)
    }


def topicos_dos_fatos(
    conexao: sa.Connection, fonte: str, fatos: Iterable[tuple[str, str]]
) -> dict[str, topicos.LeituraDoTopico]:
    """protocolo → assunto, para cada (protocolo, título do IPE).

    Vale o lido do texto (ou do modelo) na versão atual do leitor; sem ele, o do título.
    """
    titulos = dict(fatos)
    lidos: dict[str, topicos.LeituraDoTopico] = {}
    pedidos = list(titulos)
    for inicio in range(0, len(pedidos), TAMANHO_DO_LOTE):
        consulta = sa.select(leituras.c.documento, leituras.c.resultado).where(
            leituras.c.fonte == fonte,
            leituras.c.tipo == TOPICO,
            leituras.c.versao == topicos.VERSAO,
            leituras.c.documento.in_(pedidos[inicio : inicio + TAMANHO_DO_LOTE]),
        )
        for documento, resultado in conexao.execute(consulta):
            dados = dict(resultado)
            lidos[documento] = topicos.LeituraDoTopico(
                **{**dados, "secundarios": tuple(dados["secundarios"])}
            )
    return {
        protocolo: lidos.get(protocolo) or topicos.topico_do_titulo(titulo)
        for protocolo, titulo in titulos.items()
    }


def ultima_de_riscos(
    conexao: sa.Connection, cnpj: str
) -> tuple[str, date | None, dict] | None:
    """(protocolo do 10-K, data-base, comparação) mais recente de uma empresa, ou None."""
    linha = conexao.execute(
        sa.select(leituras.c.documento, leituras.c.referencia, leituras.c.resultado)
        .where(leituras.c.cnpj == cnpj, leituras.c.tipo == RISCOS)
        .order_by(
            leituras.c.referencia.desc().nulls_last()
        )  # no PostgreSQL, nulo viria antes
        .limit(1)
    ).first()
    return (
        None
        if linha is None
        else (linha.documento, linha.referencia, dict(linha.resultado))
    )


def fatos_sem_leitura(
    conexao: sa.Connection, fonte: str, categoria: str, desde: date, limite: int
) -> list[tuple[str, str, date, str, str]]:
    """Fatos relevantes ainda sem resumo: (protocolo, cnpj, publicado em, link, título do IPE),
    do mais novo.

    O app baixa cada documento por esse link: um endereço que não seja da CVM ou da SEC fica de
    fora (o servidor nunca baixa nada de outro lugar).
    """
    ja = sa.select(leituras.c.documento).where(
        leituras.c.fonte == fonte,
        leituras.c.tipo == RESUMO,
        leituras.c.versao == VERSAO,
    )
    consulta = (
        sa.select(
            eventos.c.protocolo,
            eventos.c.cnpj,
            eventos.c.publicado_em,
            eventos.c.link,
            eventos.c.assunto,
        )
        .where(
            eventos.c.fonte == fonte,
            eventos.c.categoria == categoria,
            eventos.c.publicado_em >= desde,
            eventos.c.protocolo.not_in(ja),
        )
        .order_by(eventos.c.publicado_em.desc())
        .limit(limite)
    )
    return [
        (protocolo, cnpj, publicado_em, seguro, assunto)
        for protocolo, cnpj, publicado_em, link, assunto in conexao.execute(consulta)
        if (seguro := link_da_fonte(link))
    ]
