"""Mede um dia do IEX HIST: baixa o TOPS, monta as barras de 1 minuto do S&P 500 e confere.

    python -m scripts.medir_iex_um_dia --data 2026-10-09
    python -m scripts.medir_iex_um_dia --data 2026-10-09 --limite-gb 0.5   (só o começo do arquivo)

É a fase F2 do projeto de dados intradiários: decidir, com números, se o processamento cabe no
VPS ou vai para o notebook de casa. O arquivo (~9 GB comprimido) é lido enquanto baixa e não fica
no disco; só as barras são gravadas, em `dados/intradiario/iex/AAAA-MM-DD.parquet` (fora do Git).

Mede: GB baixados, tempo, velocidade, memória máxima, negócios lidos e guardados, cobertura dos
minutos e a diferença entre o último preço das barras e o fechamento oficial (Yahoo).
"""

import argparse
import gzip
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import BinaryIO

import pandas as pd
import psutil
import requests
import yfinance as yf

from src import catalogo, iex_tops
from src.barras_intradiarias import (
    cobertura_por_simbolo,
    conferir_fechamentos,
    montar_barras,
)

LISTA_DO_HIST = "https://iextrading.com/api/1.0/hist?date={data}"
PASTA_DAS_BARRAS = Path("dados/intradiario/iex")
FUSO_NY = "America/New_York"
BYTES_POR_GB = 1e9
INTERVALO_DA_MEMORIA_S = 2.0
TEMPO_LIMITE_S = 120


class LeituraContada:
    """Embrulha o fluxo da rede e conta os bytes comprimidos que chegaram."""

    def __init__(self, fluxo: BinaryIO) -> None:
        self.fluxo = fluxo
        self.lidos = 0

    def read(self, tamanho: int = -1) -> bytes:
        parte = self.fluxo.read(tamanho)
        self.lidos += len(parte)
        return parte


class LeituraComLimite:
    """Para de entregar dados descomprimidos quando a rede passa de `limite_bytes`.

    Parar do lado descomprimido (e não cortando o gzip) evita o erro de arquivo truncado e
    aproveita tudo o que já foi lido: serve para medir só o começo de um dia.
    """

    def __init__(
        self, fluxo: BinaryIO, contada: LeituraContada, limite_bytes: float
    ) -> None:
        self.fluxo = fluxo
        self.contada = contada
        self.limite_bytes = limite_bytes

    def read(self, tamanho: int = -1) -> bytes:
        if self.contada.lidos >= self.limite_bytes:
            return b""
        return self.fluxo.read(tamanho)


class MedidorDeMemoria(threading.Thread):
    """Anota a maior memória usada pelo processo enquanto o dia é lido."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.maxima_bytes = 0
        self.parar = threading.Event()

    def run(self) -> None:
        processo = psutil.Process()
        while not self.parar.wait(INTERVALO_DA_MEMORIA_S):
            self.maxima_bytes = max(self.maxima_bytes, processo.memory_info().rss)


def endereco_do_tops(data: date) -> tuple[str, int]:
    """O link do arquivo TOPS do dia e o tamanho dele em bytes (comprimido)."""
    resposta = requests.get(
        LISTA_DO_HIST.format(data=data.strftime("%Y%m%d")), timeout=TEMPO_LIMITE_S
    )
    resposta.raise_for_status()
    tops = [item for item in resposta.json() if item["feed"] == "TOPS"]
    if not tops:
        raise SystemExit(
            f"A IEX não tem o TOPS de {data} (fim de semana, feriado ou ainda não saiu)."
        )
    return tops[0]["link"], int(tops[0]["size"])


def simbolos_do_sp500() -> dict[str, str]:
    """Símbolo da IEX ("BRK.B") → símbolo do Yahoo ("BRK-B"), para as ações dos EUA do catálogo."""
    tabela = catalogo.carregar()
    acoes = tabela[(tabela["bolsa"] == "EUA") & (tabela["tipo"] == "Ação")]
    return {simbolo.replace("-", "."): simbolo for simbolo in acoes.index}


def ler_o_dia(link: str, simbolos: set[str], limite_gb: float | None) -> tuple:
    """Baixa e lê o TOPS; devolve os negócios, os bytes baixados, o tempo e a memória máxima."""
    medidor = MedidorDeMemoria()
    medidor.start()
    inicio = time.perf_counter()
    with requests.get(link, stream=True, timeout=TEMPO_LIMITE_S) as resposta:
        resposta.raise_for_status()
        contada = LeituraContada(resposta.raw)
        with gzip.GzipFile(fileobj=contada) as descomprimido:
            fluxo = descomprimido
            if limite_gb:
                fluxo = LeituraComLimite(
                    descomprimido, contada, limite_gb * BYTES_POR_GB
                )
            dia = iex_tops.coletar_negocios(iex_tops.pacotes_do_pcapng(fluxo), simbolos)
    segundos = time.perf_counter() - inicio
    medidor.parar.set()
    return dia, contada.lidos, segundos, medidor.maxima_bytes


def fechamentos_do_yahoo(data: date, para_yahoo: dict[str, str]) -> pd.Series:
    """Fechamento oficial (não ajustado) do dia, com o símbolo da IEX no índice."""
    precos = yf.download(
        list(para_yahoo.values()),
        start=data.isoformat(),
        end=(data + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        progress=False,
    )["Close"]
    linha = precos.iloc[0] if not precos.empty else pd.Series(dtype=float)
    para_iex = {yahoo: iex for iex, yahoo in para_yahoo.items()}
    return linha.rename(index=para_iex).dropna()


def relatorio(
    dia: iex_tops.NegociosDoDia, barras: pd.DataFrame, conferencia: pd.DataFrame
) -> None:
    cobertura = cobertura_por_simbolo(barras)
    diferenca = conferencia["diferenca"].abs()
    print(f"pacotes lidos: {dia.pacotes_lidos:,}")
    print(
        f"negócios do S&P 500 vistos: {dia.negocios_vistos:,} (pregão regular guardado: {len(dia.preco):,})"
    )
    print(f"cancelamentos: {len(dia.cancelados)}")
    print(f"barras: {len(barras):,} de {barras['simbolo'].nunique()} símbolos")
    print(
        "cobertura dos 390 minutos: mediana "
        f"{cobertura.median():.0%}, 10% piores abaixo de {cobertura.quantile(0.1):.0%}, "
        f"símbolos com 90% ou mais: {(cobertura >= 0.9).mean():.0%}"
    )
    print(
        f"último preço x fechamento oficial ({len(conferencia)} símbolos): mediana "
        f"{diferenca.median():.3%}, 95% abaixo de {diferenca.quantile(0.95):.3%}, "
        f"maior {diferenca.max():.3%} ({diferenca.idxmax() if len(diferenca) else '-'})"
    )


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--data", type=date.fromisoformat, required=True)
    argumentos.add_argument("--limite-gb", type=float, default=None)
    opcoes = argumentos.parse_args()

    link, tamanho = endereco_do_tops(opcoes.data)
    para_yahoo = simbolos_do_sp500()
    print(
        f"TOPS de {opcoes.data}: {tamanho / BYTES_POR_GB:.2f} GB; {len(para_yahoo)} ações"
    )
    dia, baixados, segundos, memoria = ler_o_dia(
        link, set(para_yahoo), opcoes.limite_gb
    )
    print(
        f"baixado: {baixados / BYTES_POR_GB:.2f} GB em {segundos / 60:.1f} min "
        f"({baixados / segundos / 1e6:.0f} MB/s); memória máxima {memoria / 1e9:.2f} GB"
    )

    barras = montar_barras(iex_tops.tabela_de_negocios(dia), FUSO_NY)
    PASTA_DAS_BARRAS.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA_DAS_BARRAS / f"{opcoes.data.isoformat()}.parquet"
    barras.to_parquet(arquivo, index=False)
    print(f"gravado: {arquivo} ({arquivo.stat().st_size / 1e6:.1f} MB)")

    conferencia = conferir_fechamentos(
        barras, fechamentos_do_yahoo(opcoes.data, para_yahoo)
    )
    relatorio(dia, barras, conferencia)


if __name__ == "__main__":
    main()
