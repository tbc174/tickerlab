"""Alvo e faixas do modelo C-1 (pré-registro v2, seção 2).

- **Previsão no dia D**, com o que existia às 00:00 UTC de D: o último fechamento conhecido é o de
  D−1.
- **Alvo:** a volatilidade realizada de D+1 a D+30 (desvio padrão dos 30 retornos log diários). O
  retorno do próprio dia D fica fora: um dia de folga, sem vazamento.
- **Faixas:** calmo, normal e agitado, pelos terços da volatilidade de 30 dias nos 1.095 dias
  anteriores a D (as janelas que terminam até D−1). Só o passado entra nos limites.
"""

import numpy as np
import pandas as pd

DIAS_DO_ALVO = 30
DIAS_DAS_FAIXAS = 1_095
CALMO, NORMAL, AGITADO = 0, 1, 2


def retornos_log(fechamento: pd.Series) -> pd.Series:
    """Retornos log diários, num índice de dias corridos: um dia sem preço vira buraco (NaN), e o
    retorno nunca junta dois dias."""
    indice = pd.to_datetime(pd.Index(fechamento.index))
    diario = pd.Series(fechamento.to_numpy(dtype=float), index=indice).asfreq("D")
    retornos = np.log(diario / diario.shift(1))
    retornos.index = retornos.index.date
    return retornos


def volatilidade_realizada(retornos: pd.Series, janela: int) -> pd.Series:
    """Desvio padrão dos `janela` retornos que terminam no dia (inclusive); só com a janela cheia."""
    return retornos.rolling(janela, min_periods=janela).std()


def alvo_30_dias(retornos: pd.Series) -> pd.Series:
    """No dia D: a volatilidade dos retornos de D+1 a D+30 (a janela de 30 que termina em D+30)."""
    return volatilidade_realizada(retornos, DIAS_DO_ALVO).shift(-DIAS_DO_ALVO)


def faixas(retornos: pd.Series) -> pd.DataFrame:
    """No dia D: os limites `inferior` e `superior` (terços) da volatilidade de 30 dias nas janelas
    que terminam de D−1.095 a D−1."""
    historico = volatilidade_realizada(retornos, DIAS_DO_ALVO).shift(1)
    janela = historico.rolling(DIAS_DAS_FAIXAS, min_periods=DIAS_DAS_FAIXAS)
    return pd.DataFrame(
        {"inferior": janela.quantile(1 / 3), "superior": janela.quantile(2 / 3)}
    )


def classe_do_alvo(alvo: pd.Series, limites: pd.DataFrame) -> pd.Series:
    """0 = calmo (abaixo do 1º terço), 1 = normal, 2 = agitado (acima do 2º); NaN sem alvo ou limite."""
    classe = pd.Series(np.nan, index=alvo.index)
    sabido = alvo.notna() & limites["inferior"].notna() & limites["superior"].notna()
    classe[sabido & (alvo < limites["inferior"])] = CALMO
    classe[sabido & (alvo >= limites["inferior"]) & (alvo < limites["superior"])] = (
        NORMAL
    )
    classe[sabido & (alvo >= limites["superior"])] = AGITADO
    return classe
