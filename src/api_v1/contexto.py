"""Os dados de um ativo para a API: o mesmo caminho da tela (`telas/comum.carregar_contexto`).

Preços pelo `baixar_dados` (cache em SQLite, Yahoo e, se ele falhar, o guardado), retorno diário e a
taxa livre de risco: a informada no pedido ou, sem ela, o CDI do período (zero se o Banco Central não
responder, como na tela).
"""

import threading
import time
from dataclasses import dataclass

import pandas as pd

from src import indicadores as ind
from src.analises import MIN_DIAS_PARA_ANALISE
from src.cdi import CDIIndisponivelError, baixar_cdi, calcular_taxa_anual_do_cdi
from src.dados import baixar_dados, normalizar_ticker

VALIDADE_DO_CDI = 24 * 3600  # segundos: o CDI só muda uma vez por dia útil


class PoucosDadosError(ValueError):
    """O período tem menos retornos do que o mínimo para os números dizerem alguma coisa."""


@dataclass(frozen=True)
class ContextoDoAtivo:
    ticker: str
    periodo: str
    dados: pd.DataFrame
    fechamento: pd.Series
    retorno: pd.Series
    taxa_livre_de_risco: float
    taxa_do_cdi: bool  # True: a taxa veio do CDI do período

    @property
    def origem(self) -> str:
        """De onde vieram os preços: "atual", "cache_antigo" (o Yahoo falhou) ou "exemplo"."""
        return str(self.dados.attrs.get("origem") or "atual")


def carregar_dados(ticker: str, periodo: str) -> pd.DataFrame:
    """Os preços do ativo (os testes trocam esta função pelos dados de exemplo)."""
    return baixar_dados(ticker, periodo)


_cdi_em_cache: dict[tuple[str, str], tuple[float, pd.Series]] = {}
_trava_do_cdi = threading.Lock()


def _cdi(inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.Series:
    chave = (inicio.date().isoformat(), fim.date().isoformat())
    with _trava_do_cdi:
        guardado = _cdi_em_cache.get(chave)
        if guardado and time.time() - guardado[0] < VALIDADE_DO_CDI:
            return guardado[1]
    serie = baixar_cdi(inicio, fim)
    with _trava_do_cdi:
        _cdi_em_cache[chave] = (time.time(), serie)
    return serie


def taxa_livre_de_risco(
    indice: pd.DatetimeIndex, taxa_informada: float | None
) -> tuple[float, bool]:
    """(taxa anual, veio do CDI?). Sem taxa informada, o CDI do período; se ele falhar, zero."""
    if taxa_informada is not None:
        return taxa_informada, False
    try:
        return calcular_taxa_anual_do_cdi(_cdi(indice[0], indice[-1]), indice), True
    except (CDIIndisponivelError, ValueError):
        return 0.0, False


def carregar_ativo(
    ticker: str, periodo: str, taxa_informada: float | None
) -> ContextoDoAtivo:
    """O ativo pronto para as análises. `DadosIndisponiveisError` ou `PoucosDadosError` se não der."""
    ticker = normalizar_ticker(ticker)
    dados = carregar_dados(ticker, periodo)
    fechamento = dados["Close"]
    retorno = ind.calcular_retorno_diario(fechamento)
    if retorno.dropna().size < MIN_DIAS_PARA_ANALISE:
        raise PoucosDadosError(
            f"Só há {retorno.dropna().size} dias de dados para {ticker}; são necessários "
            f"pelo menos {MIN_DIAS_PARA_ANALISE}. Tente um período mais longo."
        )
    taxa, do_cdi = taxa_livre_de_risco(pd.DatetimeIndex(dados.index), taxa_informada)
    return ContextoDoAtivo(ticker, periodo, dados, fechamento, retorno, taxa, do_cdi)
