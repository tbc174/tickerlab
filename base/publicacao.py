"""Quando cada informe apareceu na CVM (`visto_em`), além do prazo (relatórios de cruzamentos 5 e 7,
16/10/2026; plano `projeto-acoes/planos/2026-10-16-fidc-cda-visto-em.md`).

O `disponivel_em` do CDA (competência + 90 dias ou fim do sigilo) e do informe de FIDC (competência +
45 dias) é a regra do prazo, não a data em que o dado apareceu: para quem entrega atrasado, a base
olharia o futuro (exigência 3 da ADR 0027). O arquivista guarda cada versão de cada arquivo com o dia
da baixada; daí sai, sem estado novo:

- `visto_em`: o dia (em São Paulo) da **primeira versão guardada que trouxe a chave** (fundo e
  competência). Se a chave já estava na primeira versão e nenhuma coleta anterior viu o arquivo
  faltando, não sabemos quando ela entrou: fica vazio (todo o passado, até 10/2026);
- `disponivel_em` continua sendo o prazo (o piso) e vira `max(prazo, visto_em)` quando há data vista.

Limite: revisão de um informe já visto não muda a data (vale a primeira vez que o fundo apareceu).
"""

import hashlib
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from src import acervo
from src.banco import coletas

VISTO_EM = "visto_em"
FUSO = ZoneInfo("America/Sao_Paulo")


def dia_da_coleta(baixado_em: datetime) -> pd.Timestamp:
    """O dia em São Paulo de uma baixada (o registro sem fuso, como no SQLite, é UTC)."""
    quando = pd.Timestamp(baixado_em)
    if quando.tzinfo is None:
        quando = quando.tz_localize("UTC")
    return quando.tz_convert(FUSO).tz_localize(None).normalize()


def primeiras_aparicoes(
    versoes: Iterable[tuple[pd.Timestamp, pd.DataFrame]],
    chave: Sequence[str],
    *,
    ausente_antes: bool,
) -> pd.DataFrame:
    """`chave` + `visto_em` de cada chave das versões (dia, chaves lidas), da mais antiga à mais nova.

    `ausente_antes`: uma coleta antes da primeira versão achou o arquivo faltando, então tudo o que
    a primeira versão traz apareceu nela.
    """
    vistas: list[pd.DataFrame] = []
    conhecidas: pd.DataFrame | None = None
    for numero, (dia, chaves) in enumerate(versoes):
        unicas = chaves[list(chave)].drop_duplicates()
        if conhecidas is not None:
            ja = unicas.merge(conhecidas, on=list(chave), how="left", indicator=True)
            unicas = unicas[(ja["_merge"] == "left_only").to_numpy()]
        quando = pd.NaT if numero == 0 and not ausente_antes else pd.Timestamp(dia)
        vistas.append(unicas.assign(**{VISTO_EM: quando}))
        conhecidas = unicas if conhecidas is None else pd.concat([conhecidas, unicas])
    if not vistas:
        return pd.DataFrame(columns=[*chave, VISTO_EM])
    saida = pd.concat(vistas, ignore_index=True)
    saida[VISTO_EM] = pd.to_datetime(saida[VISTO_EM])
    return saida


def uma_por_chave(vistos: pd.DataFrame, chave: Sequence[str]) -> pd.DataFrame:
    """Chave vista em mais de um arquivo: a primeira data; se num deles não sabemos, não sabemos."""
    agrupado = vistos.groupby(list(chave), dropna=False, sort=False)[VISTO_EM]
    primeira = agrupado.min()
    desconhecida = agrupado.apply(lambda datas: datas.isna().any())
    primeira[desconhecida] = pd.NaT
    return primeira.reset_index()


class Versao(NamedTuple):
    url: str
    sha256: str
    dia: (
        pd.Timestamp | None
    )  # o dia (São Paulo) em que o arquivista a baixou; None: sem registro
    caminho: str | None  # no acervo; None: só o conteúdo lido agora (acervo desligado)
    conteudo: bytes | None = None
    # uma coleta antes desta (a 1ª guardada do endereço) achou o arquivo faltando: o que ela traz
    # apareceu nela
    depois_de_ausente: bool = False


def todas_as_versoes(
    conexao: sa.Connection, lidos: Sequence[tuple[str, bytes]]
) -> list[Versao]:
    """Cada versão guardada de cada arquivo lido, da mais antiga à mais nova (as origens da tabela).

    Sem nenhuma guardada (acervo desligado), só a que foi lida, sem dia."""
    versoes: list[Versao] = []
    for url, conteudo in lidos:
        guardadas = coletas.versoes_guardadas(conexao, url)
        if not guardadas:
            sha256 = hashlib.sha256(conteudo).hexdigest()
            versoes.append(Versao(url, sha256, None, None, conteudo))
            continue
        ausente = coletas.ausente_antes(conexao, url, guardadas[0].baixado_em)
        versoes += [
            Versao(
                url,
                v.sha256,
                dia_da_coleta(v.baixado_em),
                v.caminho,
                depois_de_ausente=numero == 0 and ausente,
            )
            for numero, v in enumerate(guardadas)
        ]
    return versoes


def _conteudo(versao: Versao) -> bytes:
    if versao.conteudo is not None:
        return versao.conteudo
    conteudo = acervo.ler_original(versao.caminho) if versao.caminho else None
    if conteudo is None:
        raise FileNotFoundError(
            f"versão {versao.sha256} de {versao.url} fora do acervo"
        )
    return conteudo


def vistos_nas_versoes(
    versoes: Sequence[Versao],
    ler_chaves: Callable[[bytes], pd.DataFrame],
    chave: Sequence[str],
) -> pd.DataFrame:
    """`chave` + `visto_em` pelas versões de cada arquivo, lidas uma de cada vez (o CDA tem ~25 MB
    por versão). Versão sem dia (acervo desligado) não dá data.

    Se nenhum arquivo tem mais de uma versão nem uma ausência vista antes, nada pode ter data: não lê
    nada (o CDA anual de 2022 tem 146 MB)."""
    datadas = [v for v in versoes if v.dia is not None]
    urls = [v.url for v in datadas]
    if not any(urls.count(v.url) > 1 or v.depois_de_ausente for v in datadas):
        return pd.DataFrame(columns=[*chave, VISTO_EM])
    partes = []
    for url in dict.fromkeys(v.url for v in versoes):
        do_arquivo = [v for v in versoes if v.url == url and v.dia is not None]
        if not do_arquivo:
            continue
        lidas = ((v.dia, ler_chaves(_conteudo(v))) for v in do_arquivo)
        partes.append(
            primeiras_aparicoes(
                lidas, chave, ausente_antes=do_arquivo[0].depois_de_ausente
            )
        )
    if not partes:
        return pd.DataFrame(columns=[*chave, VISTO_EM])
    return pd.concat(partes, ignore_index=True)


def com_visto_em(
    tabela: pd.DataFrame, vistos: pd.DataFrame, chave: Sequence[str]
) -> pd.DataFrame:
    """A tabela com `visto_em` e `disponivel_em = max(prazo, visto_em)` (o prazo é o piso)."""
    if vistos.empty:  # nada visto: só o prazo (sem juntar colunas de tipos diferentes)
        return tabela.assign(
            **{VISTO_EM: pd.Series(pd.NaT, index=tabela.index, dtype="datetime64[ns]")}
        )
    unicos = uma_por_chave(vistos, chave)
    saida = tabela.drop(columns=[VISTO_EM], errors="ignore").merge(
        unicos[[*chave, VISTO_EM]], on=list(chave), how="left"
    )
    saida[VISTO_EM] = pd.to_datetime(saida[VISTO_EM])
    saida["disponivel_em"] = saida[["disponivel_em", VISTO_EM]].max(axis=1)
    return saida
