"""Coleta da base de cripto (série 1, PR 6): cada fonte baixa só o que falta e grava em Parquet.

Roda no servidor de casa (ADR 0031), chamada por `scripts/coletar_cripto.py`. Cada função recebe
`baixar(url) -> bytes`: no script, é o download embrulhado em `com_registro`, que guarda o arquivo
original no acervo e deixa a linha no registro de coletas (ADR 0024). Nos testes, um dublê.

As tabelas ficam em `<pasta>/<tabela>/<ano>.parquet`; acrescentar troca as linhas da mesma chave,
então rodar duas vezes não duplica. As fontes que refazem números antigos guardam **cada versão**
(a chave inclui `divulgado_em`): a Receita.
"""

import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from base.cripto.arquivos import acrescentar, ler_tabela
from base.cripto.atencao import (
    endereco_gdelt,
    endereco_wikipedia,
    juntar_gdelt,
    ler_gdelt,
    ler_wikipedia,
)
from base.cripto.cftc import endereco_do_ano, ler_tff
from base.cripto.diario import resumo_diario
from base.cripto.leitura import FonteDeBlocos, ler_ate_o_topo, ler_blocos, ler_parado
from base.cripto.precos import ler_kraken_arquivo, ler_kraken_rest, ler_mercado_bitcoin
from base.cripto.receita import (
    abrir_planilha,
    data_do_arquivo,
    divulgado_em,
    ler_por_criptoativo,
    ler_totais,
)

Baixar = Callable[[str], bytes]

INICIO_DO_MERCADO_BITCOIN = date(2014, 1, 1)
DIAS_POR_PEDIDO_AO_MERCADO_BITCOIN = 365
ENDERECO_DO_MERCADO_BITCOIN = "https://api.mercadobitcoin.net/api/v4/candles?symbol=BTC-BRL&resolution=1d&from={de}&to={ate}"
ENDERECO_DA_KRAKEN = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440"
# os futuros de Bitcoin da CME começaram em dezembro de 2017
PRIMEIRO_ANO_DA_CFTC = 2017
INICIO_DA_WIKIPEDIA = date(2015, 7, 1)
ARTIGO_DA_WIKIPEDIA = "Bitcoin"
# inglês: a atenção do mundo; português: a do Brasil (bem menos acessos)
PROJETOS_DA_WIKIPEDIA = ("en.wikipedia", "pt.wikipedia")
INICIO_DO_GDELT = date(2017, 1, 1)
TERMO_DO_GDELT = "bitcoin"
# o GDELT pede um pedido a cada 5 segundos; um a mais de folga
PAUSA_DO_GDELT_EM_SEGUNDOS = 6.0
# ~2 horas por noite (2 pedidos por dia, 6 s cada): a carga desde 2017 leva umas 6 noites
DIAS_DO_GDELT_POR_RODADA = 600
PAGINA_DA_RECEITA = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/"
    "declaracoes-e-demonstrativos/criptoativos"
)
# os de maior volume declarado (ago/2019 a jun/2026): as stablecoins mostram o cripto usado como
# "dólar digital"; BRZ é a stablecoin em reais
CRIPTOATIVOS_DA_RECEITA = ("BTC", "ETH", "USDT", "USDC", "BRZ")
LINK_DA_PLANILHA = re.compile(rb'href="([^"]+criptoativos_dados_abertos_\d{8}\.xls)"')


def coletar_mercado_bitcoin(pasta: Path, agora: datetime, baixar: Baixar) -> int:
    """Candles diários BTC-BRL desde o dia seguinte ao último guardado; devolve as linhas novas."""
    destino = pasta / "precos" / "mb"
    inicio = _dia_seguinte_ao_ultimo(destino, "dia", INICIO_DO_MERCADO_BITCOIN)
    hoje = agora.astimezone(UTC).date()
    novas = 0
    while inicio <= hoje:
        fim = min(inicio + timedelta(days=DIAS_POR_PEDIDO_AO_MERCADO_BITCOIN - 1), hoje)
        url = ENDERECO_DO_MERCADO_BITCOIN.format(
            de=_segundos(inicio), ate=_segundos(fim)
        )
        novas += _gravar_por_ano(
            destino, ler_mercado_bitcoin(baixar(url), agora), "dia"
        )
        inicio = fim + timedelta(days=1)
    return novas


def coletar_kraken(pasta: Path, agora: datetime, baixar: Baixar) -> int:
    """Os últimos 720 dias da Kraken (BTC/USD), até o último candle fechado."""
    tabela = ler_kraken_rest(baixar(ENDERECO_DA_KRAKEN), agora)
    return _gravar_por_ano(pasta / "precos" / "kraken", tabela, "dia")


def carregar_arquivo_kraken(pasta: Path, agora: datetime, conteudo_csv: bytes) -> int:
    """Carga única do histórico: o `XBTUSD_1440.csv` do arquivo OHLCVT da Kraken."""
    return _gravar_por_ano(
        pasta / "precos" / "kraken", ler_kraken_arquivo(conteudo_csv, agora), "dia"
    )


def coletar_cftc(pasta: Path, agora: datetime, baixar: Baixar) -> int:
    """Relatórios TFF: na primeira vez desde 2017; depois o ano anterior e o atual (correções)."""
    destino = pasta / "cftc"
    ano_atual = agora.year
    primeiro = (
        PRIMEIRO_ANO_DA_CFTC
        if ler_tabela(destino, "relatorio").empty
        else ano_atual - 1
    )
    novas = 0
    for ano in range(primeiro, ano_atual + 1):
        tabela = ler_tff(baixar(endereco_do_ano(ano)))
        novas += _gravar_por_ano(
            destino, tabela, "relatorio", ["relatorio", "contrato"]
        )
    return novas


def coletar_wikipedia(pasta: Path, agora: datetime, baixar: Baixar) -> int:
    """Acessos diários ao artigo em cada projeto, do dia seguinte ao último guardado daquele
    projeto até o último dia que já vale."""
    destino = pasta / "wikipedia"
    guardado = ler_tabela(destino, ["projeto", "dia"])
    fim = agora.astimezone(UTC).date() - timedelta(days=2)
    novas = 0
    for projeto in PROJETOS_DA_WIKIPEDIA:
        do_projeto = (
            guardado[guardado["projeto"] == projeto] if not guardado.empty else guardado
        )
        inicio = (
            do_projeto["dia"].max() + timedelta(days=1)
            if not do_projeto.empty
            else INICIO_DA_WIKIPEDIA
        )
        if inicio > fim:
            continue
        url = endereco_wikipedia(ARTIGO_DA_WIKIPEDIA, inicio, fim, projeto)
        tabela = _ja_valem(ler_wikipedia(baixar(url)), agora)
        novas += _gravar_por_ano(destino, tabela, "dia", ["projeto", "dia"])
    return novas


def coletar_gdelt(
    pasta: Path,
    agora: datetime,
    baixar: Baixar,
    esperar: Callable[[float], None] = time.sleep,
) -> int:
    """Notícias sobre o Bitcoin, um dia por vez, com pausa entre os pedidos (limite do GDELT)."""
    destino = pasta / "gdelt"
    dia = _dia_seguinte_ao_ultimo(destino, "dia", INICIO_DO_GDELT)
    ultimo_que_vale = (agora.astimezone(UTC) - timedelta(days=1, hours=1)).date()
    novas = 0
    for _ in range(DIAS_DO_GDELT_POR_RODADA):
        if dia > ultimo_que_vale:
            break
        volume = _pedir_com_pausa(
            baixar, endereco_gdelt(TERMO_DO_GDELT, "timelinevolraw", dia), esperar
        )
        tom = _pedir_com_pausa(
            baixar, endereco_gdelt(TERMO_DO_GDELT, "timelinetone", dia), esperar
        )
        novas += _gravar_por_ano(
            destino, juntar_gdelt(ler_gdelt(volume), ler_gdelt(tom)), "dia"
        )
        dia += timedelta(days=1)
    return novas


def coletar_receita(pasta: Path, agora: datetime, baixar: Baixar) -> int:
    """A planilha mais nova da página da Receita, se ainda não foi guardada (cada versão fica)."""
    achado = LINK_DA_PLANILHA.search(baixar(PAGINA_DA_RECEITA))
    if achado is None:
        raise ValueError(
            "A página da Receita não tem mais o link da planilha de criptoativos."
        )
    url = achado.group(1).decode()
    data_no_nome = data_do_arquivo(url)
    totais_guardados = ler_tabela(pasta / "receita" / "totais", "mes")
    if (
        not totais_guardados.empty
        and (
            totais_guardados["divulgado_em"] == pd.Timestamp(divulgado_em(data_no_nome))
        ).any()
    ):
        return 0
    abas = abrir_planilha(baixar(url))
    totais = ler_totais(abas["Relatorio1"], data_no_nome)
    novas = _gravar_por_ano(
        pasta / "receita" / "totais", totais, "mes", ["mes", "divulgado_em"]
    )
    for criptoativo in CRIPTOATIVOS_DA_RECEITA:
        por_criptoativo = ler_por_criptoativo(
            abas["Relatorio4"], data_no_nome, criptoativo
        )
        novas += _gravar_por_ano(
            pasta / "receita" / "criptoativo",
            por_criptoativo,
            "mes",
            ["mes", "criptoativo", "divulgado_em"],
        )
    return novas


def coletar_no(pasta: Path, agora: datetime, no: FonteDeBlocos) -> int:
    """Lê o nó até o topo com 6 confirmações e refaz o resumo diário dos dias novos."""
    lidos = ler_ate_o_topo(no, pasta / "no", agora)
    if lidos:
        diario = resumo_diario(ler_blocos(pasta / "no"), ler_parado(pasta / "no"))
        _gravar_por_ano(pasta / "rede_diaria", diario, "dia")
    return lidos


def _pedir_com_pausa(
    baixar: Baixar, url: str, esperar: Callable[[float], None]
) -> bytes:
    conteudo = baixar(url)
    esperar(PAUSA_DO_GDELT_EM_SEGUNDOS)
    return conteudo


def _gravar_por_ano(
    destino: Path,
    tabela: pd.DataFrame,
    coluna_do_dia: str,
    chave: list[str] | None = None,
) -> int:
    if tabela.empty:
        return 0
    ano = tabela[coluna_do_dia].map(lambda dia: str(dia.year))
    return acrescentar(destino, tabela, ano, chave or [coluna_do_dia])


def _dia_seguinte_ao_ultimo(destino: Path, coluna: str, primeiro: date) -> date:
    guardado = ler_tabela(destino, coluna)
    if guardado.empty:
        return primeiro
    return guardado[coluna].max() + timedelta(days=1)


def _ja_valem(tabela: pd.DataFrame, agora: datetime) -> pd.DataFrame:
    return tabela[tabela["divulgado_em"] <= pd.Timestamp(agora)]


def _segundos(dia: date) -> int:
    return int(datetime(dia.year, dia.month, dia.day, tzinfo=UTC).timestamp())
