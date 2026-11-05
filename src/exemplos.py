"""Dados de exemplo guardados no projeto: o plano B para quando o Yahoo Finance falha.

São cópias de 5 anos de 13 tickers (inclui Bitcoin e dólar), tiradas em 09/10/2026 e guardadas em
`dados_de_exemplo/`. Servem para demonstrar o app sem internet e para não ficar sem tela quando
o Yahoo está fora do ar. Não são atualizadas: o app sempre avisa quando usa estes dados.
"""

import logging
from pathlib import Path

import pandas as pd

PASTA_DOS_EXEMPLOS = Path(__file__).resolve().parent.parent / "dados_de_exemplo"
COLUNAS = ["Open", "High", "Low", "Close", "Volume"]
PERIODO_TUDO = "max"  # todo o histórico que a fonte tiver (o nome do Yahoo)
# quanto cada período volta a partir do último dia; None = sem corte no começo
DESLOCAMENTO_DO_PERIODO: dict[str, pd.DateOffset | None] = {
    "6mo": pd.DateOffset(months=6),
    "1y": pd.DateOffset(years=1),
    "2y": pd.DateOffset(years=2),
    "5y": pd.DateOffset(years=5),
    "10y": pd.DateOffset(years=10),
    PERIODO_TUDO: None,
}

log = logging.getLogger(__name__)


def _caminho(ticker: str, pasta: Path) -> Path:
    return pasta / (ticker.replace("^", "_") + ".csv")


def tickers_de_exemplo(pasta: Path = PASTA_DOS_EXEMPLOS) -> list[str]:
    """Os tickers que têm arquivo de exemplo (na grafia do Yahoo)."""
    if not pasta.exists():
        return []
    return sorted(
        arquivo.stem.replace("_", "^", 1)
        if arquivo.stem.startswith("_")
        else arquivo.stem
        for arquivo in pasta.glob("*.csv")
    )


def carregar_exemplo(
    ticker: str, periodo: str = "2y", pasta: Path = PASTA_DOS_EXEMPLOS
) -> pd.DataFrame | None:
    """Os dados de exemplo do ticker no período, ou None se não houver arquivo.

    O resultado leva `attrs["origem"] == "exemplo"` e `attrs["ate"]` (último dia disponível).
    """
    caminho = _caminho(ticker, pasta)
    if not caminho.exists() or periodo not in DESLOCAMENTO_DO_PERIODO:
        return None
    try:
        dados = pd.read_csv(caminho, index_col="Data", parse_dates=["Data"])[COLUNAS]
    except (OSError, ValueError, KeyError) as erro:
        log.error("Arquivo de exemplo ilegível (%s): %s", caminho.name, erro)
        return None
    deslocamento = DESLOCAMENTO_DO_PERIODO[periodo]
    if deslocamento is not None:
        dados = dados.loc[dados.index > dados.index[-1] - deslocamento]
    dados.attrs["origem"] = "exemplo"
    dados.attrs["ate"] = dados.index[-1].strftime("%d/%m/%Y")
    return dados
