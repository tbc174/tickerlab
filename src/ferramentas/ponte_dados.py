"""As curvas da ferramenta "Quanto daria? Foi sorte?" (ADR 0070): o valor de R$ 1 no começo de cada
mês, em cada ativo, guardadas na memória até o dia seguinte.

- CDI, poupança, IPCA e dólar: do arquivo de dados abertos das ferramentas
  (`/dados/ferramentas.json`, gerado pelo cron do VPS a partir do Banco Central), e não do BC ao vivo:
  baixar 30 anos de séries diárias a cada dia é lento e cai quando o SGS oscila. O arquivo já
  guarda a parte anterior quando uma série falha.
- Parado: a curva constante (o dinheiro não rende; a inflação entra pelo `fator_do_ipca`).
- Ibovespa e bitcoin: Yahoo Finance, o histórico inteiro, um ponto por mês (o 1º pregão); o bitcoin
  em dólar vira reais pelo dólar do Banco Central do mesmo mês. **Só aqui o Yahoo entra numa página
  aberta**, e só o resultado sai (`src/ferramentas/ponte.py`), nunca a série.

Tudo mês a mês: a data que a pessoa escolhe vale pelo mês dela, e as janelas são os meses de início.
"""

import os
import threading
from collections.abc import Callable
from datetime import date, datetime

import pandas as pd
import requests

from src import dados as dados_de_mercado
from src.bcb import FUSO
from src.ferramentas import inflacao

ENDERECO_DOS_DADOS = os.environ.get(
    "TICKERLAB_DADOS_DAS_FERRAMENTAS", "https://tickerlab.com.br/dados/ferramentas.json"
)
TEMPO_LIMITE = 30
INICIO_DO_REAL = date(1994, 7, 1)
TICKERS = {"ibovespa": "^BVSP", "bitcoin": "BTC-USD"}
Buscar = Callable[..., requests.Response]


class CurvaIndisponivelError(Exception):
    """A curva de um ativo não veio hoje (o arquivo de dados ou o Yahoo fora do ar)."""


def curva_mensal(meses: list[list]) -> pd.Series:
    """De [["AAAA-MM", fração], ...] para o valor de R$ 1 no começo de cada mês (e do seguinte ao
    último): começa em 1 no 1º dia do primeiro mês."""
    if not meses:
        raise CurvaIndisponivelError("Série mensal vazia.")
    comecos = pd.to_datetime([f"{mes}-01" for mes, _ in meses])
    proximo = comecos[-1] + pd.offsets.MonthBegin(1)
    fatores = [1.0]
    for _, taxa in meses:
        fatores.append(fatores[-1] * (1 + taxa))
    return pd.Series(fatores, index=comecos.append(pd.DatetimeIndex([proximo])))


def niveis_mensais(meses: list[list]) -> pd.Series:
    """De [["AAAA-MM", valor], ...] (o valor do 1º dia útil do mês) para uma curva no dia 1."""
    if not meses:
        raise CurvaIndisponivelError("Série mensal vazia.")
    return pd.Series(
        [float(v) for _, v in meses],
        index=pd.to_datetime([f"{m}-01" for m, _ in meses]),
    )


def primeiro_pregao_de_cada_mes(fechamento: pd.Series) -> pd.Series:
    """O fechamento do 1º pregão de cada mês, datado no dia 1 (para casar com as outras curvas)."""
    mensal = fechamento.groupby(
        pd.DatetimeIndex(fechamento.index).to_period("M")
    ).first()
    return pd.Series(mensal.to_numpy(dtype=float), index=mensal.index.to_timestamp())


def fator_do_ipca(desde: date, meses: list[list]) -> float:
    """A inflação do mês de `desde` até o último IPCA divulgado (1,25 = +25%); 1 se não há mês."""
    inicio = f"{desde:%Y-%m}"
    ultimo = meses[-1][0]
    if inicio > ultimo:
        return 1.0
    return inflacao.corrigir(1.0, inicio, ultimo, meses).fator


def _parte(arquivo: dict, chave: str) -> list[list]:
    try:
        return arquivo[chave]["meses"]
    except (KeyError, TypeError) as erro:
        raise CurvaIndisponivelError(f"O arquivo de dados não tem {chave}.") from erro


def curvas_do_banco_central(arquivo: dict) -> dict[str, pd.Series]:
    """CDI, poupança, parado e (se o arquivo já tiver) o dólar, do arquivo de dados das ferramentas.
    Sem o dólar mês a mês (o cron ainda não o gerou), ele e o bitcoin ficam de fora."""
    cdi = curva_mensal(_parte(arquivo, "cdi_mensal"))
    curvas = {
        "cdi": cdi,
        "poupanca": curva_mensal(_parte(arquivo, "poupanca_mensal")),
        "parado": pd.Series(1.0, index=cdi.index),
    }
    if "dolar_mensal" in arquivo:
        curvas["dolar"] = niveis_mensais(_parte(arquivo, "dolar_mensal"))
    return curvas


def curva_do_yahoo(ativo: str, dolar: pd.Series) -> pd.Series:
    """Ibovespa (em reais) ou bitcoin (em dólar, vezes o dólar do BC do mesmo mês), mês a mês."""
    historico = dados_de_mercado.baixar_historico_completo(TICKERS[ativo])["Close"]
    mensal = primeiro_pregao_de_cada_mes(historico)
    # antes do Plano Real, os números do Yahoo são da hiperinflação (outra moeda)
    mensal = mensal[mensal.index >= pd.Timestamp(INICIO_DO_REAL)]
    if ativo == "bitcoin":
        mensal = (mensal * dolar.reindex(mensal.index)).dropna()
    if len(mensal) < 2:
        raise CurvaIndisponivelError(f"Poucos meses de {ativo}.")
    return mensal


class CacheDoDia:
    """Guarda o que deu certo até o dia seguinte; a falha não fica guardada."""

    def __init__(self) -> None:
        self._guardado: dict[str, tuple[object, object]] = {}
        self._trava = threading.Lock()

    def obter[T](self, chave: str, dia: object, fazer: Callable[[], T]) -> T:
        """O guardado em `chave` se for do mesmo `dia` (ou da mesma hora, para o arquivo)."""
        with self._trava:
            guardado = self._guardado.get(chave)
            if guardado is not None and guardado[0] == dia:
                return guardado[1]  # type: ignore[return-value]
        valor = fazer()  # fora da trava: uma busca lenta não segura as outras
        with self._trava:
            self._guardado[chave] = (dia, valor)
        return valor


CACHE = CacheDoDia()


def baixar_arquivo(buscar: Buscar = requests.get) -> dict:
    try:
        resposta = buscar(ENDERECO_DOS_DADOS, timeout=TEMPO_LIMITE)
        resposta.raise_for_status()
        return resposta.json()
    except (requests.RequestException, ValueError) as erro:
        raise CurvaIndisponivelError(
            "Sem o arquivo de dados das ferramentas agora."
        ) from erro


def _hora_agora() -> int:
    return datetime.now(FUSO).hour


def obter_arquivo(hoje: date, buscar: Buscar = requests.get) -> dict:
    """O arquivo de dados, buscado de novo a cada hora: o cron do VPS o atualiza duas vezes por dia
    (9h10 e 13h40), e guardar o do dia inteiro prenderia a rota nos dados da madrugada."""
    return CACHE.obter("arquivo", (hoje, _hora_agora()), lambda: baixar_arquivo(buscar))


def obter_curva_do_yahoo(ativo: str, hoje: date, dolar: pd.Series) -> pd.Series:
    def buscar_agora() -> pd.Series:
        try:
            return curva_do_yahoo(ativo, dolar)
        except (dados_de_mercado.DadosIndisponiveisError, ValueError, KeyError) as erro:
            raise CurvaIndisponivelError(f"{ativo}: {erro}") from erro

    return CACHE.obter(ativo, hoje, buscar_agora)
