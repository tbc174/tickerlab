"""Séries mensais do Banco Central que as ferramentas do site usam: o CDI do mês e o rendimento da
poupança de quem depositou no dia 1, como `[["AAAA-MM", fração], ...]`, só com meses fechados.

- CDI do mês: SGS 4391 (o mês corrente vem parcial e fica de fora).
- Dólar do mês: a PTAX de venda (SGS 1) do 1º dia útil de cada mês (um nível, não um rendimento).
- Poupança: o BC não tem série mensal simples; as séries 25 (depósitos até 03/05/2012, regra antiga)
  e 195 (desde 04/05/2012, regra nova) dão o rendimento por data de aniversário. Fica o aniversário
  do dia 1 de cada mês: a 25 até mai/2012, a 195 de jun/2012 em diante. O mês corrente fica de fora
  (a poupança só credita no aniversário do mês seguinte).

Servem ao arquivo de dados das ferramentas (`scripts/exportar_dados_das_ferramentas.py`) e à
ferramenta "Quanto daria?" (`src/ferramentas/ponte_dados.py`).
"""

from datetime import date

import pandas as pd
import requests

from src import bcb

INICIO_DO_REAL = date(1994, 7, 1)  # o Plano Real: antes disso, outra moeda
POUPANCA = bcb.Serie(
    195, "Poupança: rentabilidade no mês (depósitos desde 04/05/2012)", "% no mês"
)
POUPANCA_ANTIGA = bcb.Serie(
    25, "Poupança: rentabilidade no mês (depósitos até 03/05/2012)", "% no mês"
)
FIM_DA_REGRA_ANTIGA = date(2012, 5, 31)
COMECO_DA_REGRA_NOVA = "2012-06"  # o 1º aniversário de dia 1 depois de 04/05/2012
CDI_NO_MES = bcb.Serie(4391, "CDI acumulado no mês", "% no mês")


def meses_fechados(serie: pd.Series, hoje: date) -> list[list]:
    """[["AAAA-MM", fração], ...] do aniversário (ou do mês) que cai no dia 1, sem o mês corrente."""
    corrente = f"{hoje:%Y-%m}"
    return [
        [f"{momento:%Y-%m}", float(valor) / 100]
        for momento, valor in serie.items()
        if momento.day == 1 and f"{momento:%Y-%m}" < corrente
    ]


def cdi_mensal(hoje: date, buscar: bcb.Buscar = requests.get) -> list[list]:
    serie = bcb.baixar_sgs(CDI_NO_MES, INICIO_DO_REAL, hoje, hoje, buscar)
    return meses_fechados(serie, hoje)


def poupanca_mensal(hoje: date, buscar: bcb.Buscar = requests.get) -> list[list]:
    """O rendimento de quem depositou no dia 1: regra antiga até mai/2012, regra nova depois."""
    antiga = bcb.baixar_sgs(
        POUPANCA_ANTIGA, INICIO_DO_REAL, FIM_DA_REGRA_ANTIGA, hoje, buscar
    )
    nova = bcb.baixar_sgs(POUPANCA, date(2012, 6, 1), hoje, hoje, buscar)
    meses = [m for m in meses_fechados(antiga, hoje) if m[0] < COMECO_DA_REGRA_NOVA]
    meses += [m for m in meses_fechados(nova, hoje) if m[0] >= COMECO_DA_REGRA_NOVA]
    return meses


def dolar_mensal(hoje: date, buscar: bcb.Buscar = requests.get) -> list[list]:
    """[["AAAA-MM", reais por dólar], ...]: a PTAX de venda (SGS 1) do 1º dia útil de cada mês."""
    serie = bcb.baixar_sgs(bcb.SERIES["dolar"], INICIO_DO_REAL, hoje, hoje, buscar)
    meses: dict[str, float] = {}
    for momento, valor in serie.items():
        meses.setdefault(
            f"{momento:%Y-%m}", float(valor)
        )  # a série vem em ordem: fica o 1º do mês
    return [[mes, valor] for mes, valor in meses.items()]
