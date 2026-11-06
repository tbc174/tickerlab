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

from src.banco.modelo import eventos, eventos_versoes, tickers_dos_emissores
from src.eventos import FONTE_IPE
from src.links_das_fontes import link_da_fonte
from src.negociacoes import FONTE_VLMO


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


def _nao_retirado(
    tabela: sa.Table, ate: datetime | None = None
) -> sa.ColumnElement[bool]:
    """Fora: a operação que a versão nova do documento VLMO tirou (achado 7c do Codex).

    Cada evento do VLMO é uma operação de um documento (empresa e mês); se a CVM reapresenta o
    documento sem ela, as outras sobem de versão e ela fica para trás. Nada é apagado: ela some
    da leitura, e "como estava em D" (`ate`, em `eventos_versoes`) continua mostrando o passado.
    """
    mais_nova = tabela.alias()
    retirado = sa.exists().where(
        mais_nova.c.fonte == tabela.c.fonte,
        mais_nova.c.cnpj == tabela.c.cnpj,
        mais_nova.c.referencia == tabela.c.referencia,
        mais_nova.c.versao > tabela.c.versao,
    )
    if ate is not None:
        retirado = retirado.where(mais_nova.c.registrado_em <= ate)
    return ~sa.and_(tabela.c.fonte == FONTE_VLMO, retirado)


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

    Devolve (novos, atualizados). Rodar duas vezes com o mesmo arquivo não muda nada. Cada
    versão também entra em `eventos_versoes` (Radar, PR 3): a substituída fica lá, marcada.
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
            _guardar_versao(conexao, fonte, l.protocolo, valores, agora)
            atualizados += 1
    if novos:
        conexao.execute(sa.insert(eventos), novos)
        conexao.execute(
            sa.insert(eventos_versoes),
            [_linha_da_versao(n["fonte"], n["protocolo"], n, agora) for n in novos],
        )
    return len(novos), atualizados


def _linha_da_versao(
    fonte: str, protocolo: str, valores: dict, agora: datetime
) -> dict:
    copia = {k: v for k, v in valores.items() if k not in ("id", "ingerido_em")}
    return {
        **copia,
        "fonte": fonte,
        "protocolo": protocolo,
        "registrado_em": agora,
    }


def _guardar_versao(
    conexao: sa.Connection, fonte: str, protocolo: str, valores: dict, agora: datetime
) -> None:
    """Marca a versão aberta como substituída e acrescenta a nova (nada é apagado)."""
    do_evento = (eventos_versoes.c.fonte == fonte) & (
        eventos_versoes.c.protocolo == protocolo
    )
    conexao.execute(
        sa.update(eventos_versoes)
        .where(do_evento, eventos_versoes.c.substituido_em.is_(None))
        .values(substituido_em=agora)
    )
    conexao.execute(
        sa.insert(eventos_versoes).values(
            **_linha_da_versao(fonte, protocolo, valores, agora)
        )
    )


def versoes_do_evento(
    conexao: sa.Connection, fonte: str, protocolo: str
) -> list[sa.Row]:
    """Todas as versões guardadas de um evento, da primeira para a mais nova."""
    return list(
        conexao.execute(
            sa.select(eventos_versoes)
            .where(
                eventos_versoes.c.fonte == fonte,
                eventos_versoes.c.protocolo == protocolo,
            )
            .order_by(eventos_versoes.c.versao)
        )
    )


def eventos_como_estavam_em(
    conexao: sa.Connection, momento: datetime, cnpj: str | None = None
) -> list[sa.Row]:
    """Os eventos como o TickerLab os conhecia em `momento` (a versão vigente naquela hora)."""
    consulta = sa.select(eventos_versoes).where(
        eventos_versoes.c.registrado_em <= momento,
        sa.or_(
            eventos_versoes.c.substituido_em.is_(None),
            eventos_versoes.c.substituido_em > momento,
        ),
        _nao_retirado(eventos_versoes, ate=momento),
    )
    if cnpj is not None:
        consulta = consulta.where(eventos_versoes.c.cnpj == cnpj)
    return list(
        conexao.execute(
            consulta.order_by(
                eventos_versoes.c.publicado_em.desc(), eventos_versoes.c.protocolo
            )
        )
    )


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
    coletados_entre: tuple[datetime, datetime] | None = None,
) -> list[Evento]:
    """Os eventos das companhias desses tickers publicados desde `desde`, do mais novo ao mais
    velho. Um evento de empresa com dois tickers (PETR3 e PETR4) aparece uma vez, com o primeiro
    deles na ordem pedida.

    `coletados_entre` (início, fim): só os coletados (ou reapresentados) depois do início e até o
    fim, como o Pulse pede ("desde a sua última visita")."""
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
            eventos.c.cnpj.in_(list(ticker_do_cnpj)),
            eventos.c.publicado_em >= desde,
            _nao_retirado(eventos),
        )
        .order_by(eventos.c.publicado_em.desc(), eventos.c.materialidade.desc())
        .limit(limite)
    )
    if temas is not None:
        consulta = consulta.where(eventos.c.tema.in_(list(temas)))
    if coletados_entre is not None:
        inicio, fim = coletados_entre
        consulta = consulta.where(
            eventos.c.ingerido_em > inicio, eventos.c.ingerido_em <= fim
        )
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
            link=link_da_fonte(l.link) or "",  # vazio = sem link (endereço não seguro)
            fonte=l.fonte,
            protocolo=l.protocolo,
            versao=l.versao,
        )
        for l in conexao.execute(consulta)
    ]


def ultima_coleta(conexao: sa.Connection) -> datetime | None:
    """Quando os eventos foram coletados pela última vez (para a tela dizer a data-base)."""
    return conexao.execute(sa.select(sa.func.max(eventos.c.ingerido_em))).scalar()
