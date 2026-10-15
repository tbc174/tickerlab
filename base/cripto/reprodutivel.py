"""Refazer a base de cripto a partir dos originais do acervo e comparar com a guardada (série 1;
exigências 3 e 9 do critério de pronto da base de cripto).

Cada arquivo baixado está no acervo (`bruto/<fonte>/...`, com o SHA-256 como nome) e tem uma linha
no registro de coletas com a hora do download. Refazer é ler cada original **com a hora em que foi
baixado** (um candle que estava aberto naquela hora não pode virar um dia fechado só porque o
refazer roda depois), **na ordem dos downloads** (quando dois originais têm a mesma chave, vale o
mais novo, como na coleta) e com os mesmos leitores. A rede do Bitcoin não sai do acervo: vem do
próprio nó, e a prova dela é a conferência da oferta (regra C7).

Comparar usa o hash do conteúdo (`ponto_no_tempo.hash_do_conteudo`), sem a hora da coleta e sem
depender de como os arquivos Parquet foram gravados.
"""

import io
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from base.cripto.arquivos import ler_tabela
from base.cripto.atencao import juntar_gdelt, ler_gdelt, ler_wikipedia
from base.cripto.cftc import ler_tff
from base.cripto.coleta import CRIPTOATIVOS_DA_RECEITA
from base.cripto.ponto_no_tempo import como_era_em, hash_do_conteudo
from base.cripto.precos import ler_kraken_arquivo, ler_kraken_rest, ler_mercado_bitcoin
from base.cripto.receita import (
    abrir_planilha,
    data_do_arquivo,
    ler_por_criptoativo,
    ler_totais,
)

# tabela (pasta dentro da base): a chave de cada linha
CHAVES = {
    "precos/kraken": ["dia"],
    "precos/mb": ["dia"],
    "cftc": ["relatorio", "contrato"],
    "wikipedia": ["projeto", "dia"],
    "gdelt": ["dia"],
    "receita/totais": ["mes", "divulgado_em"],
    "receita/criptoativo": ["mes", "criptoativo", "divulgado_em"],
}
# o começo de todo arquivo .xls antigo (formato OLE2); a página da Receita também fica no acervo
ASSINATURA_DO_XLS = bytes.fromhex("d0cf11e0a1b11ae1")
COLUNAS_QUE_NAO_SAO_CONTEUDO = ["coletado_em"]


@dataclass(frozen=True)
class Original:
    """Um arquivo do acervo, com o que o registro de coletas diz dele."""

    fonte: str  # o nome no registro de coletas (ex.: kraken-ohlc)
    url: str
    baixado_em: datetime
    conteudo: bytes


def refazer(originais: Iterable[Original]) -> dict[str, pd.DataFrame]:
    """As tabelas da base (menos a rede do Bitcoin) refeitas só a partir dos originais."""
    partes: dict[str, list[pd.DataFrame]] = defaultdict(list)
    gdelt: dict[str, dict[str, bytes]] = defaultdict(dict)
    for original in sorted(originais, key=lambda o: o.baixado_em):
        if original.fonte == "gdelt-cripto":
            periodo, modo = _periodo_e_modo_do_gdelt(original.url)
            gdelt[periodo][modo] = original.conteudo
            continue
        for tabela, linhas in _ler(original):
            partes[tabela].append(linhas)
    for par in gdelt.values():
        if {"timelinevolraw", "timelinetone"} <= par.keys():
            volume, tom = (
                ler_gdelt(par["timelinevolraw"]),
                ler_gdelt(par["timelinetone"]),
            )
            partes["gdelt"].append(juntar_gdelt(volume, tom))
    return {
        nome: _sem_repetir(pd.concat(linhas), CHAVES[nome])
        for nome, linhas in partes.items()
    }


def comparar(refeitas: dict[str, pd.DataFrame], pasta: Path) -> dict[str, bool]:
    """Para cada tabela refeita, se o conteúdo é igual ao da tabela guardada em `pasta`."""
    return {
        nome: _hash(_como_gravada(tabela), CHAVES[nome])
        == _hash(ler_tabela(pasta / nome, CHAVES[nome]), CHAVES[nome])
        for nome, tabela in refeitas.items()
    }


def nada_depois_de(tabelas: dict[str, pd.DataFrame], data: datetime) -> dict[str, bool]:
    """Para cada tabela, se a base montada "em `data`" não traz nada divulgado depois dela."""
    resultado = {}
    for nome, tabela in tabelas.items():
        if tabela["divulgado_em"].dt.tz is None:
            raise ValueError(
                f"A tabela {nome} tem divulgado_em sem fuso: não dá para cortar no tempo."
            )
        na_data = como_era_em(tabela, data)
        resultado[nome] = bool((na_data["divulgado_em"] <= pd.Timestamp(data)).all())
    return resultado


def _ler(original: Original) -> Iterator[tuple[str, pd.DataFrame]]:
    conteudo, quando = original.conteudo, original.baixado_em
    match original.fonte:
        case "kraken-ohlc":
            yield "precos/kraken", ler_kraken_rest(conteudo, quando)
        case "kraken-arquivo":
            yield "precos/kraken", ler_kraken_arquivo(conteudo, quando)
        case "mb-candles":
            yield "precos/mb", ler_mercado_bitcoin(conteudo, quando)
        case "cftc-tff":
            yield "cftc", ler_tff(conteudo)
        case "wiki-acessos":
            acessos = ler_wikipedia(conteudo)
            yield "wikipedia", acessos[acessos["divulgado_em"] <= pd.Timestamp(quando)]
        case "rfb-cripto" if conteudo.startswith(ASSINATURA_DO_XLS):
            yield from _ler_receita(conteudo, data_do_arquivo(original.url))
        case _:
            return


def _ler_receita(
    conteudo: bytes, data_no_nome: date
) -> Iterator[tuple[str, pd.DataFrame]]:
    abas = abrir_planilha(conteudo)
    yield "receita/totais", ler_totais(abas["Relatorio1"], data_no_nome)
    for criptoativo in CRIPTOATIVOS_DA_RECEITA:
        yield (
            "receita/criptoativo",
            ler_por_criptoativo(abas["Relatorio4"], data_no_nome, criptoativo),
        )


def _periodo_e_modo_do_gdelt(url: str) -> tuple[str, str]:
    """O período (início e fim) e o modo: a contagem e o tom do mesmo período formam um par."""
    pedido = parse_qs(urlparse(url).query)
    periodo = f"{pedido['startdatetime'][0]}-{pedido['enddatetime'][0]}"
    return periodo, pedido["mode"][0]


def _sem_repetir(tabela: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    """Como `arquivos.acrescentar`: a mesma chave fica com a linha mais nova."""
    return (
        tabela.drop_duplicates(chave, keep="last")
        .sort_values(chave)
        .reset_index(drop=True)
    )


def _como_gravada(tabela: pd.DataFrame) -> pd.DataFrame:
    """A tabela depois de passar pelo Parquet, para os tipos ficarem como os da guardada."""
    memoria = io.BytesIO()
    tabela.to_parquet(memoria, index=False)
    return pd.read_parquet(io.BytesIO(memoria.getvalue()))


def _hash(tabela: pd.DataFrame, chave: list[str]) -> str:
    if tabela.empty:
        return ""
    sem_coleta = tabela.drop(
        columns=[c for c in COLUNAS_QUE_NAO_SAO_CONTEUDO if c in tabela]
    )
    return hash_do_conteudo(sem_coleta[sorted(sem_coleta.columns)], chave)
