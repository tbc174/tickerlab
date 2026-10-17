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
TOPICO_MODELO = (
    "topico_modelo"  # o mesmo, pela camada do modelo (à parte: a tela só usa depois
)
# da medição, ADR 0069)
TAMANHO_DO_LOTE = 5_000


def _em_dia(consulta: sa.Select) -> sa.Select:
    """Só as leituras feitas depois da versão vigente do documento.

    Quando a CVM reapresenta um fato (versão nova), o evento ganha `ingerido_em` novo: a leitura
    de antes fica velha, sai da tela e o fato volta para a fila (achado 7b do Codex). Nada é
    apagado. Leitura sem evento (o 10-K da SEC) continua valendo.
    """
    do_evento = (eventos.c.fonte == leituras.c.fonte) & (
        eventos.c.protocolo == leituras.c.documento
    )
    return consulta.select_from(leituras.outerjoin(eventos, do_evento)).where(
        sa.or_(
            eventos.c.ingerido_em.is_(None),
            leituras.c.lido_em >= eventos.c.ingerido_em,
        )
    )


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
    conexao: sa.Connection,
    fonte: str,
    tipo: str,
    documentos: Iterable[str],
    versao: str | None = None,
) -> set[str]:
    """Quais destes documentos já têm leitura (na versão atual do algoritmo, ou em `versao`)."""
    versao = versao or VERSAO
    pedidos = list(dict.fromkeys(documentos))
    achados: set[str] = set()
    for inicio in range(0, len(pedidos), TAMANHO_DO_LOTE):
        achados.update(
            conexao.execute(
                sa.select(leituras.c.documento).where(
                    leituras.c.fonte == fonte,
                    leituras.c.tipo == tipo,
                    leituras.c.versao == versao,
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
    consulta = _em_dia(
        sa.select(leituras.c.documento, leituras.c.resultado).where(
            leituras.c.fonte == fonte,
            leituras.c.tipo == RESUMO,
            leituras.c.documento.in_(pedidos[:TAMANHO_DO_LOTE]),
        )
    )
    return {
        documento: dict(resultado) for documento, resultado in conexao.execute(consulta)
    }


def _topicos_lidos(
    conexao: sa.Connection, fonte: str, tipo: str, pedidos: list[str]
) -> dict[str, topicos.LeituraDoTopico]:
    lidos: dict[str, topicos.LeituraDoTopico] = {}
    for inicio in range(0, len(pedidos), TAMANHO_DO_LOTE):
        consulta = _em_dia(
            sa.select(leituras.c.documento, leituras.c.resultado).where(
                leituras.c.fonte == fonte,
                leituras.c.tipo == tipo,
                leituras.c.versao == topicos.VERSAO,
                leituras.c.documento.in_(pedidos[inicio : inicio + TAMANHO_DO_LOTE]),
            )
        )
        for documento, resultado in conexao.execute(consulta):
            dados = dict(resultado)
            lidos[documento] = topicos.LeituraDoTopico(
                **{**dados, "secundarios": tuple(dados["secundarios"])}
            )
    return lidos


def topicos_dos_fatos(
    conexao: sa.Connection,
    fonte: str,
    fatos: Iterable[tuple[str, str]],
    com_modelo: bool = False,
) -> dict[str, topicos.LeituraDoTopico]:
    """protocolo → assunto, para cada (protocolo, título do IPE).

    Vale o lido do texto na versão atual do leitor; sem ele, o do título. Com `com_modelo`, onde as
    regras deixaram "Outros" e o modelo leu, vale o do modelo (a tela só liga isso depois da medição
    da ADR 0069).
    """
    titulos = dict(fatos)
    pedidos = list(titulos)
    pelas_regras = _topicos_lidos(conexao, fonte, TOPICO, pedidos)
    pelo_modelo = (
        _topicos_lidos(conexao, fonte, TOPICO_MODELO, pedidos) if com_modelo else {}
    )
    achados = {}
    for protocolo, titulo in titulos.items():
        leitura = pelas_regras.get(protocolo) or topicos.topico_do_titulo(titulo)
        if leitura.principal == topicos.OUTROS and protocolo in pelo_modelo:
            leitura = pelo_modelo[protocolo]
        achados[protocolo] = leitura
    return achados


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
    """Fatos relevantes ainda sem resumo (ou com o resumo de uma versão anterior do fato):
    (protocolo, cnpj, publicado em, link, título do IPE), do mais novo.

    O app baixa cada documento por esse link: um endereço que não seja da CVM ou da SEC fica de
    fora (o servidor nunca baixa nada de outro lugar).
    """
    lido_em_dia = sa.exists().where(
        leituras.c.fonte == fonte,
        leituras.c.documento == eventos.c.protocolo,
        leituras.c.tipo == RESUMO,
        leituras.c.versao == VERSAO,
        leituras.c.lido_em >= eventos.c.ingerido_em,  # depois da versão vigente (7b)
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
            ~lido_em_dia,
        )
        .order_by(eventos.c.publicado_em.desc())
        .limit(limite)
    )
    return [
        (protocolo, cnpj, publicado_em, seguro, assunto)
        for protocolo, cnpj, publicado_em, link, assunto in conexao.execute(consulta)
        if (seguro := link_da_fonte(link))
    ]
