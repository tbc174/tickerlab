"""Comparação entre ativos: escolhe a lista, alinha as datas, põe tudo na base 100 e resume."""

import re

import pandas as pd

from src import indicadores as ind
from src.dados import normalizar_ticker

MAX_ATIVOS = 5  # contando o ativo principal; evita sobrecarregar o Yahoo
ATALHOS = {
    "Ibovespa": "^BVSP",
    "S&P 500": "^GSPC",
    "Bitcoin": "BTC-USD",
    "Dólar (em reais)": "USDBRL=X",
}
ATALHOS_PADRAO = ["Ibovespa", "S&P 500"]
NOMES_AMIGAVEIS = {ticker: nome for nome, ticker in ATALHOS.items()}
COLUNAS_DA_TABELA = [
    "Retorno total",
    "Retorno anualizado",
    "Volatilidade anual",
    "Maior queda",
    "Índice de Sharpe",
]
# como cada coluna aparece (src/formatos.py): a tela do Streamlit e o app em React
FORMATO_DAS_COLUNAS = {
    "Retorno total": "pct_com_sinal",
    "Retorno anualizado": "pct_com_sinal",
    "Volatilidade anual": "pct",
    "Maior queda": "pct",
    "Índice de Sharpe": "decimal",
}
AVISO_DO_LIMITE = (
    "O limite é de {maximo} ativos por comparação. Ficaram de fora: {fora}."
)
AVISO_SEM_DADOS = (
    "Não encontrei dados para: {sem_dados}. Eles ficaram de fora da comparação."
)
_SEPARADORES = re.compile(r"[,;\s]+")


def interpretar_tickers(texto: str) -> list[str]:
    """Lê uma lista digitada ("vale3, aapl;btc-usd") e devolve os tickers normalizados, sem repetir."""
    tickers: list[str] = []
    for pedaco in _SEPARADORES.split(texto or ""):
        ticker = normalizar_ticker(pedaco)
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def escolher_ativos(
    principal: str,
    atalhos: list[str],
    texto_extra: str = "",
    maximo: int = MAX_ATIVOS,
) -> tuple[list[str], list[str]]:
    """Monta a lista final: principal primeiro, depois atalhos e extras, sem repetir.

    Devolve (usados, ignorados). O que passar do `maximo` vai para os ignorados, para o app avisar.
    """
    candidatos = [principal, *atalhos, *interpretar_tickers(texto_extra)]
    usados: list[str] = []
    ignorados: list[str] = []
    for candidato in candidatos:
        ticker = normalizar_ticker(candidato)
        if not ticker or ticker in usados or ticker in ignorados:
            continue
        (usados if len(usados) < maximo else ignorados).append(ticker)
    return usados, ignorados


def _limpar_serie(serie: pd.Series) -> pd.Series:
    """Deixa a série com datas simples (sem fuso nem hora), sem datas repetidas e sem vazios."""
    serie = serie.dropna()
    datas = pd.DatetimeIndex(pd.to_datetime(serie.index))
    if datas.tz is not None:
        datas = datas.tz_localize(None)
    limpa = pd.Series(serie.to_numpy(), index=datas.normalize())
    return limpa[~limpa.index.duplicated(keep="last")]


def alinhar_fechamentos(
    fechamentos: dict[str, pd.Series],
) -> tuple[pd.DataFrame, int]:
    """Junta os fechamentos usando só os dias em que TODOS os ativos têm preço.

    Feriados diferentes (B3 x EUA) fazem alguns dias existirem para um ativo e não para outro;
    esses dias são descartados em vez de preenchidos, para não inventar preços.
    Devolve (tabela com uma coluna por ativo, quantidade de dias descartados).
    """
    if not fechamentos:
        raise ValueError("Nenhum ativo para alinhar.")
    todos = pd.concat(
        {t: _limpar_serie(s) for t, s in fechamentos.items()}, axis=1, sort=True
    )
    alinhado = todos.dropna().sort_index()
    return alinhado, len(todos) - len(alinhado)


def rebasear_para_100(alinhado: pd.DataFrame) -> pd.DataFrame:
    """Faz todos os ativos começarem em 100, para comparar desempenho mesmo com moedas diferentes."""
    if alinhado.empty:
        raise ValueError("Não há dias em comum para comparar.")
    return alinhado / alinhado.iloc[0] * 100


def montar_tabela_comparativa(
    alinhado: pd.DataFrame, taxa_livre_de_risco: float = 0.0
) -> pd.DataFrame:
    """Uma linha por ativo, com os números principais calculados nos mesmos dias para todos."""
    linhas = {}
    for ticker in alinhado.columns:
        fechamento = alinhado[ticker]
        retorno = ind.calcular_retorno_diario(fechamento)
        linhas[ticker] = {
            "Retorno total": fechamento.iloc[-1] / fechamento.iloc[0] - 1,
            "Retorno anualizado": ind.retorno_anualizado_para_mostrar(retorno),
            "Volatilidade anual": ind.calcular_volatilidade_anual(retorno),
            "Maior queda": ind.calcular_drawdown(fechamento).min(),
            "Índice de Sharpe": ind.calcular_indice_sharpe(
                retorno, taxa_livre_de_risco
            ),
        }
    if not linhas:
        return pd.DataFrame(columns=COLUNAS_DA_TABELA, dtype=float)
    return pd.DataFrame(linhas).T[COLUNAS_DA_TABELA]
