"""Baixa as séries gratuitas da Pesquisa 2 (FRED e Yahoo) e mede a qualidade de cada uma.

As funções que leem a internet são finas; o trabalho (ler o CSV, conferir a série) fica em funções
puras, testadas sem rede.
"""

from __future__ import annotations

import io
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PASTA_PADRAO = Path(__file__).resolve().parents[2] / "dados_p2"
URL_DO_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}"
NOME_SEGURO = re.compile(r"[A-Za-z0-9._=^\-]{1,40}")
TEMPO_LIMITE_EM_SEGUNDOS = 60
# Retorno diário maior que 10 desvios: provável erro de dado ou salto de rolagem do futuro.
DESVIOS_DE_UM_SALTO = 10


def ler_csv_do_fred(texto: str) -> pd.Series:
    """Converte o CSV do FRED (data, valor; "." quando falta) numa série sem valores vazios."""
    tabela = pd.read_csv(io.StringIO(texto))
    datas = pd.to_datetime(tabela.iloc[:, 0])
    valores = pd.to_numeric(tabela.iloc[:, 1], errors="coerce")
    serie = pd.Series(valores.to_numpy(), index=pd.DatetimeIndex(datas, name="Date"))
    return serie.dropna().sort_index()


def baixar_fred(serie: str) -> pd.Series:
    url = URL_DO_FRED.format(serie=serie)
    with urllib.request.urlopen(url, timeout=TEMPO_LIMITE_EM_SEGUNDOS) as resposta:
        return ler_csv_do_fred(resposta.read().decode("utf-8"))


def baixar_yahoo(simbolo: str) -> pd.Series:
    """Fechamento diário do Yahoo (ajustado por proventos quando houver)."""
    from trader.baixar_historico import baixar_yfinance

    return baixar_yfinance(simbolo)["Close"].rename(None)


def caminho_da_serie(fonte: str, serie: str, pasta: Path = PASTA_PADRAO) -> Path:
    if not NOME_SEGURO.fullmatch(serie):
        raise ValueError(f"Nome de série inválido: {serie!r}")
    return pasta / f"{fonte}_{serie.replace('^', 'IDX_')}.parquet"


def salvar_serie(
    serie: pd.Series, fonte: str, nome: str, pasta: Path = PASTA_PADRAO
) -> Path:
    caminho = caminho_da_serie(fonte, nome, pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    serie.rename("valor").to_frame().to_parquet(caminho)
    return caminho


def carregar_serie(
    fonte: str, nome: str, pasta: Path = PASTA_PADRAO
) -> pd.Series | None:
    caminho = caminho_da_serie(fonte, nome, pasta)
    return pd.read_parquet(caminho)["valor"] if caminho.exists() else None


@dataclass(frozen=True)
class QualidadeDaSerie:
    pontos: int
    inicio: pd.Timestamp | None
    fim: pd.Timestamp | None
    datas_repetidas: int
    valores_nao_positivos: (
        int  # só conta para preços (taxas de juros podem ser negativas)
    )
    maior_lacuna_em_dias: int
    saltos_suspeitos: int

    @property
    def aprovada(self) -> bool:
        return (
            self.pontos > 0
            and self.datas_repetidas == 0
            and self.valores_nao_positivos == 0
        )


def medir_qualidade(serie: pd.Series, e_preco: bool = True) -> QualidadeDaSerie:
    """Defeitos comuns: datas repetidas, preços ≤ 0, buracos longos e saltos improváveis."""
    if serie.empty:
        return QualidadeDaSerie(0, None, None, 0, 0, 0, 0)
    passos = serie.index.to_series().diff().dropna()
    return QualidadeDaSerie(
        pontos=len(serie),
        inicio=serie.index[0],
        fim=serie.index[-1],
        datas_repetidas=int(serie.index.duplicated().sum()),
        valores_nao_positivos=int((serie <= 0).sum()) if e_preco else 0,
        maior_lacuna_em_dias=int(passos.max().days) if not passos.empty else 0,
        saltos_suspeitos=_contar_saltos(serie) if e_preco else 0,
    )


def _contar_saltos(precos: pd.Series) -> int:
    positivos = precos[precos > 0]
    retornos = np.log(positivos).diff().dropna()
    if len(retornos) < 2:
        return 0
    desvio = retornos.std()
    return int((retornos.abs() > DESVIOS_DE_UM_SALTO * desvio).sum())
