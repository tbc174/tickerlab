"""Gravar e consultar os eventos públicos da CVM (Research, etapa 2a).

São dados públicos e iguais para todos (não há `usuario_id` aqui). A coleta roda fora do app,
por `scripts/atualizar_eventos.py`; o app só consulta.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
import sqlalchemy as sa

from src.banco.modelo import eventos, tickers_dos_emissores
from src.eventos import FONTE_IPE


@dataclass(frozen=True)
class Evento:
    ticker: str
    empresa: str
    rotulo: str
    tema: str
    materialidade: int
    assunto: str
    referencia: date | None
    publicado_em: date
    link: str
    fonte: str
    protocolo: str
    versao: int


def _agora() -> datetime:
    return datetime.now(UTC)


ORIGEM_CVM, ORIGEM_SEC = "cvm", "sec"
TAMANHO_DO_LOTE = 5_000


def gravar_tickers(
    conexao: sa.Connection,
    tabela: pd.DataFrame,
    agora: datetime | None = None,
    origem: str = ORIGEM_CVM,
) -> int:
    """Substitui o mapa ticker → empresa de uma origem (CVM: CNPJ; SEC: `CIK...`).

    A outra origem fica intacta: a coleta da CVM não apaga as empresas dos EUA, nem o contrário.
    Devolve quantos ficaram.
    """
    if tabela.empty:
        return 0  # nunca apaga o mapa por causa de um arquivo vazio
    agora = agora or _agora()
    da_sec = tickers_dos_emissores.c.cnpj.like("CIK%")
    conexao.execute(
        sa.delete(tickers_dos_emissores).where(
            da_sec if origem == ORIGEM_SEC else ~da_sec
        )
    )
    conexao.execute(
        sa.insert(tickers_dos_emissores),
        [
            {
                "ticker": l.ticker,
                "codigo": l.codigo,
                "cnpj": l.cnpj,
                "empresa": l.empresa[:200],
                "valor_mobiliario": (l.valor_mobiliario or "")[:80],
                "atualizado_em": agora,
            }
            for l in tabela.itertuples(index=False)
        ],
    )
    return len(tabela)


def versoes_gravadas(
    conexao: sa.Connection, fonte: str, protocolos: Iterable[str]
) -> dict[str, int]:
    """protocolo → versão guardada, só para os protocolos pedidos que já estão no banco.

    Consulta em pedaços: o SQLite limita o número de parâmetros de uma consulta.
    """
    pedidos = list(dict.fromkeys(protocolos))
    existentes: dict[str, int] = {}
    for inicio in range(0, len(pedidos), TAMANHO_DO_LOTE):
        pedaco = pedidos[inicio : inicio + TAMANHO_DO_LOTE]
        existentes.update(
            conexao.execute(
                sa.select(eventos.c.protocolo, eventos.c.versao).where(
                    eventos.c.fonte == fonte, eventos.c.protocolo.in_(pedaco)
                )
            ).all()
        )
    return existentes


def gravar_eventos(
    conexao: sa.Connection,
    tabela: pd.DataFrame,
    fonte: str = FONTE_IPE,
    agora: datetime | None = None,
) -> tuple[int, int]:
    """Acrescenta os eventos novos e atualiza os que ganharam versão nova.

    Devolve (novos, atualizados). Rodar duas vezes com o mesmo arquivo não muda nada.
    """
    if tabela.empty:
        return 0, 0
    agora = agora or _agora()
    existentes = versoes_gravadas(conexao, fonte, tabela["protocolo"])
    novos, atualizados = [], 0
    for l in tabela.itertuples(index=False):
        valores = {
            "versao": int(l.versao),
            "cnpj": l.cnpj,
            "empresa": l.empresa[:200],
            "categoria": l.categoria[:160],
            "tipo": (l.tipo or "")[:300],
            "assunto": l.assunto or "",
            "rotulo": l.rotulo[:60],
            "tema": l.tema,
            "materialidade": int(l.materialidade),
            "referencia": l.referencia if pd.notna(l.referencia) else None,
            "publicado_em": l.publicado_em,
            "link": l.link[:500],
            "ingerido_em": agora,
        }
        versao_guardada = existentes.get(l.protocolo)
        if versao_guardada is None:
            novos.append(
                {
                    "id": uuid.uuid4(),
                    "fonte": fonte,
                    "protocolo": l.protocolo,
                    **valores,
                }
            )
        elif int(l.versao) > versao_guardada:
            conexao.execute(
                sa.update(eventos)
                .where(eventos.c.fonte == fonte, eventos.c.protocolo == l.protocolo)
                .values(**valores)
            )
            atualizados += 1
    if novos:
        conexao.execute(sa.insert(eventos), novos)
    return len(novos), atualizados


def empresas_dos_tickers(
    conexao: sa.Connection, tickers: Iterable[str]
) -> dict[str, tuple]:
    """ticker → (cnpj, empresa) para os tickers que têm cadastro na CVM."""
    lista = sorted(set(tickers))
    if not lista:
        return {}
    linhas = conexao.execute(
        sa.select(
            tickers_dos_emissores.c.ticker,
            tickers_dos_emissores.c.cnpj,
            tickers_dos_emissores.c.empresa,
        ).where(tickers_dos_emissores.c.ticker.in_(lista))
    )
    return {l.ticker: (l.cnpj, l.empresa) for l in linhas}


def tickers_das_empresas(
    conexao: sa.Connection, cnpjs: Iterable[str]
) -> dict[str, str]:
    """CNPJ (ou CIK) → um ticker da empresa (o primeiro em ordem alfabética: PETR3 antes de PETR4)."""
    pedidos = sorted(set(cnpjs))
    if not pedidos:
        return {}
    consulta = (
        sa.select(
            tickers_dos_emissores.c.cnpj, sa.func.min(tickers_dos_emissores.c.ticker)
        )
        .where(tickers_dos_emissores.c.cnpj.in_(pedidos))
        .group_by(tickers_dos_emissores.c.cnpj)
    )
    return dict(conexao.execute(consulta).all())


def eventos_dos_tickers(
    conexao: sa.Connection,
    tickers: Iterable[str],
    desde: date,
    temas: Iterable[str] | None = None,
    limite: int = 300,
) -> list[Evento]:
    """Os eventos das companhias desses tickers publicados desde `desde`, do mais novo ao mais
    velho. Um evento de empresa com dois tickers (PETR3 e PETR4) aparece uma vez, com o primeiro
    deles na ordem pedida."""
    pedidos = list(dict.fromkeys(tickers))
    empresas = empresas_dos_tickers(conexao, pedidos)
    if not empresas:
        return []
    ticker_do_cnpj: dict[str, str] = {}
    for (
        ticker
    ) in pedidos:  # na ordem pedida: o ticker que a pessoa acompanha vem primeiro
        if ticker in empresas:
            ticker_do_cnpj.setdefault(empresas[ticker][0], ticker)
    consulta = (
        sa.select(eventos)
        .where(
            eventos.c.cnpj.in_(list(ticker_do_cnpj)), eventos.c.publicado_em >= desde
        )
        .order_by(eventos.c.publicado_em.desc(), eventos.c.materialidade.desc())
        .limit(limite)
    )
    if temas is not None:
        consulta = consulta.where(eventos.c.tema.in_(list(temas)))
    return [
        Evento(
            ticker=ticker_do_cnpj[l.cnpj],
            empresa=l.empresa,
            rotulo=l.rotulo,
            tema=l.tema,
            materialidade=l.materialidade,
            assunto=l.assunto,
            referencia=l.referencia,
            publicado_em=l.publicado_em,
            link=l.link,
            fonte=l.fonte,
            protocolo=l.protocolo,
            versao=l.versao,
        )
        for l in conexao.execute(consulta)
    ]


def ultima_coleta(conexao: sa.Connection) -> datetime | None:
    """Quando os eventos foram coletados pela última vez (para a tela dizer a data-base)."""
    return conexao.execute(sa.select(sa.func.max(eventos.c.ingerido_em))).scalar()
