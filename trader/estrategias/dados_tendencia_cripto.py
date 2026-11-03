"""Dados da ficha P0-1: BTC e ETH em reais, em dias corridos, com cache fora do Git.

Ficha de dados (a mesma série do começo ao fim, como o pré-registro pede):
- **Preços e volumes:** candles diários de BTCUSDT e ETHUSDT do Binance Vision
  (`data.binance.vision`, arquivos mensais em zip; fechamento e volume financeiro em USDT).
  Licença lida em 03/11/2026: uso interno (CC BY-NC-SA); esta pesquisa é interna.
- **Dólar:** PTAX de venda (SGS 1 do Banco Central, R$/US$) **da véspera**: o preço em reais de
  cada dia usa a última cotação conhecida antes daquele dia, para nenhum dia depender de um dado
  que ainda não existia no fechamento (sábado e domingo usam a de sexta).
- **Calendário:** todos os dias corridos entre o primeiro e o último candle; dia sem candle
  repete o preço anterior e não negocia (volume zero).
- **Volume para o impacto:** média dos 60 dias anteriores do volume em reais, deslocada um dia
  (só o que já era conhecido).

Os zips baixados são dado de fora: ficam na própria pasta, só são lidos (nunca executados) e
cada um tem o SHA-256 anotado em `sha256.json`.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from src import bcb, rede
from src import cdi as modulo_cdi
from trader.criterio_quant import FIM_DO_DESENVOLVIMENTO
from trader.estrategias import dados_p0_3
from trader.estrategias.tendencia_cripto import ATIVOS

PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
PASTA_DA_BINANCE = PASTA_DA_PESQUISA / "binance"
URL = "https://data.binance.vision/data/spot/monthly/klines/{par}/1d/{par}-1d-{mes}.zip"
PARES = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
PRIMEIRO_MES = "2017-08"  # os dois pares começam em 17/08/2017
INICIO_DO_DOLAR = pd.Timestamp("2017-08-01")
SERIE_DO_DOLAR = bcb.SERIES["dolar"]
DIAS_DO_VOLUME = 60
COLUNAS_DO_KLINE = (
    "abertura_ms",
    "abertura",
    "maxima",
    "minima",
    "fechamento",
    "volume_base",
    "fechamento_ms",
    "volume",  # em USDT (quote volume)
    "negocios",
    "compra_base",
    "compra_quote",
    "ignorar",
)
MILISSEGUNDOS = 1_000

Baixar = Callable[[str], bytes]


# --- Binance Vision ---------------------------------------------------------------------------------


def ler_kline_zip(conteudo: bytes) -> pd.DataFrame:
    """O csv dentro do zip: fechamento e volume financeiro (USDT) por dia (UTC), sem fuso."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        nome = next(n for n in z.namelist() if n.endswith(".csv"))
        tabela = pd.read_csv(z.open(nome), header=None, names=list(COLUNAS_DO_KLINE))
    # Arquivos mais novos trazem uma linha de cabeçalho: fica só o que é número.
    tabela = tabela[pd.to_numeric(tabela["abertura_ms"], errors="coerce").notna()]
    abertura = pd.to_numeric(tabela["abertura_ms"]).astype("int64")
    if (abertura > 10**14).any():  # microssegundos (formato de 2025 em diante)
        abertura = abertura // MILISSEGUNDOS
    dias = (
        pd.to_datetime(abertura, unit="ms", utc=True)
        .dt.tz_localize(None)
        .dt.normalize()
    )
    saida = pd.DataFrame(
        {
            "fechamento": pd.to_numeric(tabela["fechamento"]).to_numpy(float),
            "volume": pd.to_numeric(tabela["volume"]).to_numpy(float),
        },
        index=pd.DatetimeIndex(dias.to_numpy()),
    )
    return saida.sort_index()


def _baixar_da_internet(url: str) -> bytes:
    resposta = rede.get_com_agente(url, timeout=120)
    resposta.raise_for_status()
    return resposta.content


def baixar_par(
    par: str,
    meses: pd.PeriodIndex,
    pasta: Path = PASTA_DA_BINANCE,
    baixar: Baixar = _baixar_da_internet,
) -> int:
    """Grava um zip por mês em `pasta` (os que já existem ficam); devolve quantos baixou."""
    pasta.mkdir(parents=True, exist_ok=True)
    hashes_arquivo = pasta / "sha256.json"
    hashes = (
        json.loads(hashes_arquivo.read_text("utf-8")) if hashes_arquivo.exists() else {}
    )
    gravados = 0
    for mes in meses:
        nome = f"{par}-1d-{mes.strftime('%Y-%m')}.zip"
        destino = pasta / nome
        if destino.exists():
            continue
        conteudo = baixar(URL.format(par=par, mes=mes.strftime("%Y-%m")))
        ler_kline_zip(conteudo)  # confere que é um zip de candles antes de gravar
        destino.write_bytes(conteudo)
        hashes[nome] = hashlib.sha256(conteudo).hexdigest()
        gravados += 1
    if gravados:
        hashes_arquivo.write_text(json.dumps(hashes, indent=1, sort_keys=True), "utf-8")
    return gravados


def carregar_par(par: str, pasta: Path = PASTA_DA_BINANCE) -> pd.DataFrame:
    """Todos os meses baixados de um par, em ordem."""
    arquivos = sorted(pasta.glob(f"{par}-1d-*.zip"))
    if not arquivos:
        raise FileNotFoundError(f"nenhum zip de {par} em {pasta}")
    tabela = pd.concat(ler_kline_zip(a.read_bytes()) for a in arquivos)
    return tabela[~tabela.index.duplicated(keep="last")].sort_index()


# --- dólar e preços em reais -----------------------------------------------------------------------


def carregar_dolar(
    inicio: pd.Timestamp = INICIO_DO_DOLAR,
    fim: pd.Timestamp = FIM_DO_DESENVOLVIMENTO,
    pasta: Path = PASTA_DA_PESQUISA,
) -> pd.Series:
    """PTAX de venda (SGS 1) por dia útil, com cache."""

    def baixar(comeco: pd.Timestamp, final: pd.Timestamp) -> pd.Series:
        return bcb.baixar_sgs(SERIE_DO_DOLAR, comeco.date(), final.date())

    return dados_p0_3.carregar_com_cache("dolar", inicio, fim, pasta, baixar)


def dolar_da_vespera(dolar: pd.Series, corridos: pd.DatetimeIndex) -> pd.Series:
    """Em cada dia corrido, a última cotação conhecida **antes** daquele dia."""
    cotacoes = dolar.sort_index().astype(float)
    tudo = cotacoes.reindex(cotacoes.index.union(corridos)).ffill()
    vespera = tudo.reindex(corridos - pd.Timedelta(days=1))
    return pd.Series(vespera.to_numpy(), index=corridos)


def montar_precos(
    tabelas: dict[str, pd.DataFrame], dolar: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preços e volumes em reais, em dias corridos, com o dólar da véspera.

    Dia sem candle repete o preço anterior e tem volume zero. Dia sem dólar da véspera é erro.
    """
    inicio = min(t.index.min() for t in tabelas.values())
    fim = max(t.index.max() for t in tabelas.values())
    corridos = pd.date_range(inicio, fim, freq="D")
    cambio = dolar_da_vespera(dolar, corridos)
    if cambio.isna().any():
        faltando = corridos[cambio.isna()][0]
        raise ValueError(f"sem dólar da véspera em {faltando.date()}")
    precos = pd.DataFrame(index=corridos, columns=list(ATIVOS), dtype=float)
    volumes = pd.DataFrame(index=corridos, columns=list(ATIVOS), dtype=float)
    for ativo in ATIVOS:
        tabela = tabelas[ativo].sort_index()
        precos[ativo] = tabela["fechamento"].reindex(corridos).ffill() * cambio
        volumes[ativo] = tabela["volume"].reindex(corridos).fillna(0.0) * cambio
    return precos, volumes


def volume_medio_conhecido(
    volumes: pd.DataFrame, dias: int = DIAS_DO_VOLUME
) -> pd.DataFrame:
    """Média dos `dias` anteriores (sem o dia), para o impacto só usar o que já era conhecido."""
    return volumes.rolling(dias, min_periods=1).mean().shift(1)


def carregar_cdi_corrido(
    corridos: pd.DatetimeIndex, pasta: Path = PASTA_DA_PESQUISA
) -> pd.Series:
    """O retorno do caixa em cada dia corrido (CDI nos dias úteis, zero no fim de semana)."""
    uteis = dados_p0_3.carregar_cdi(
        pd.Timestamp(corridos.min()), pd.Timestamp(corridos.max()), pasta
    )
    return modulo_cdi.retorno_diario_do_caixa(uteis, corridos)


def hash_da_tabela(tabela: pd.DataFrame) -> str:
    """Impressão digital dos dados que entraram (vai para a especificação da tentativa)."""
    bruto = np.ascontiguousarray(tabela.round(8).to_numpy(float)).tobytes()
    return hashlib.sha256(bruto).hexdigest()
