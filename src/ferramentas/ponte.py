"""A conta da ferramenta "Quanto daria? Foi sorte?" (ADR 0070): quanto um valor aplicado numa data
teria virado hoje em cada ativo, e se a data escolhida foi de sorte.

Cada ativo chega como uma **curva** (o valor de R$ 1 no começo de cada mês, em qualquer base) que
este módulo não busca (o `ponte_dados.py` busca). A data escolhida vale pelo mês dela. Daqui só saem **números soltos**: o valor final, o retorno, o
valor em poder de compra da data inicial e o resumo das janelas. Nunca a série (a ADR 0070 permite
mostrar o resultado, não os preços).

"Foi sorte?": para o mesmo prazo (da data escolhida até o último dia com dado), todas as datas de
início possíveis no histórico (meses de início). Em que posição a data da pessoa ficou, a pior, a mediana e a melhor.
As janelas se sobrepõem: não são sorteios independentes (a página diz isso). No CDI, o resultado
quase não depende da data; isso também é a lição.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

ATIVOS = ("cdi", "poupanca", "dolar", "parado", "ibovespa", "bitcoin")
ATIVOS_DO_YAHOO = ("ibovespa", "bitcoin")  # desligáveis pelo .env (ADR 0070, item 5)
NOMES = {
    "cdi": "CDI",
    "poupanca": "Poupança",
    "dolar": "Dólar",
    "parado": "Parado (só a inflação)",
    "ibovespa": "Ibovespa",
    "bitcoin": "Bitcoin",
}
FONTES = {
    "cdi": "Banco Central (CDI do mês, SGS 4391)",
    "poupanca": "Banco Central (rendimento do aniversário do dia 1, SGS 25 e 195)",
    "dolar": "Banco Central (dólar PTAX de venda do 1º dia útil do mês, SGS 1)",
    "parado": "Banco Central (IPCA, SGS 433)",
    "ibovespa": "Yahoo Finance (índice da B3, com os dividendos reinvestidos)",
    "bitcoin": "Yahoo Finance (BTC-USD, de corretora internacional) convertido pelo dólar PTAX do Banco Central",
}
SEM_JANELAS = ("parado",)  # dinheiro parado: toda data dá o mesmo
VALOR_MINIMO = 1.0
VALOR_MAXIMO = 10_000_000.0
DIAS_MINIMOS = 30  # a data inicial é de pelo menos 30 dias atrás
FOLGA_ANTES_DO_PRIMEIRO_DADO = 7  # dias


@dataclass(frozen=True)
class Janelas:
    quantas: int
    pior: float  # em reais, para o mesmo valor aplicado
    mediana: float
    melhor: float
    abaixo_da_sua: float  # fração das janelas que dariam menos que a data escolhida


@dataclass(frozen=True)
class ResultadoDoAtivo:
    ativo: str
    nome: str
    fonte: str
    inicio: date  # o primeiro dia com dado a partir da data pedida
    fim: date  # o último dia com dado
    valor_final: float
    retorno: float
    valor_real: (
        float  # o valor final em poder de compra da data inicial (descontado o IPCA)
    )
    janelas: Janelas | None


def conferir_pedido(desde: date, valor: float, hoje: date) -> None:
    """O valor entre R$ 1 e R$ 10 milhões; a data de pelo menos 30 dias atrás."""
    if not VALOR_MINIMO <= valor <= VALOR_MAXIMO:
        raise ValueError("Use um valor entre R$ 1 e R$ 10 milhões.")
    if desde > hoje - timedelta(days=DIAS_MINIMOS):
        raise ValueError("Escolha uma data de pelo menos 30 dias atrás.")


def janelas(curva: pd.Series, horizonte: int) -> np.ndarray:
    """Quanto R$ 1 vira em `horizonte` pontos da curva, para cada ponto de início possível."""
    valores = curva.to_numpy(dtype=float)
    inicios = len(valores) - horizonte
    return valores[horizonte : horizonte + inicios] / valores[:inicios]


def resultado_do_ativo(
    ativo: str, curva: pd.Series, desde: date, valor: float, fator_do_ipca: float
) -> ResultadoDoAtivo:
    """Quanto `valor` aplicado em `desde` virou no último dia da curva, e as janelas do mesmo prazo.
    `fator_do_ipca` é a inflação acumulada no período (1,25 = +25%)."""
    datas = pd.DatetimeIndex(curva.index)
    # um fim de semana ou feriado logo antes do 1º dado começa nele; antes disso, não há dado
    if pd.Timestamp(desde) < datas[0] - pd.Timedelta(days=FOLGA_ANTES_DO_PRIMEIRO_DADO):
        raise ValueError(f"Os dados de {NOMES[ativo]} começam em {datas[0]:%d/%m/%Y}.")
    posicao = int(datas.searchsorted(pd.Timestamp(desde)))
    horizonte = len(datas) - 1 - posicao
    if horizonte < 1:
        raise ValueError("Não há prazo entre a data escolhida e o último dado.")
    valores = curva.to_numpy(dtype=float)
    multiplo = valores[-1] / valores[posicao]
    valor_final = valor * multiplo
    resumo = None
    if ativo not in SEM_JANELAS:
        todas = janelas(curva, horizonte)
        resumo = Janelas(
            quantas=len(todas),
            pior=valor * float(todas.min()),
            mediana=valor * float(np.median(todas)),
            melhor=valor * float(todas.max()),
            abaixo_da_sua=float((todas < multiplo).mean()),
        )
    return ResultadoDoAtivo(
        ativo=ativo,
        nome=NOMES[ativo],
        fonte=FONTES[ativo],
        inicio=datas[posicao].date(),
        fim=datas[-1].date(),
        valor_final=valor_final,
        retorno=multiplo - 1,
        valor_real=valor_final / fator_do_ipca,
        janelas=resumo,
    )
