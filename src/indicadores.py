"""Indicadores de análise de ações: retorno, médias móveis, volatilidade e drawdown."""

from typing import NamedTuple

import numpy as np
import pandas as pd

DIAS_POR_ANO = 252
NOMES_DOS_MESES = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
]


class PiorDrawdown(NamedTuple):
    """A pior queda do período: quanto caiu e as datas do topo, do fundo e da recuperação."""

    queda: float
    data_topo: pd.Timestamp | None
    data_fundo: pd.Timestamp | None
    data_recuperacao: pd.Timestamp | None  # None se ainda não voltou ao topo


def calcular_retorno_diario(fechamento: pd.Series) -> pd.Series:
    """Retorno percentual de cada dia em relação ao dia anterior (o primeiro dia fica vazio)."""
    return fechamento.pct_change()


def calcular_retorno_acumulado(retorno: pd.Series) -> pd.Series:
    """Retorno acumulado desde o início da série."""
    retorno_total = (1 + retorno).cumprod() - 1
    return retorno_total


def calcular_media_movel(fechamento: pd.Series, janela: int) -> pd.Series:
    """Média dos últimos `janela` dias."""
    mm = fechamento.rolling(window=janela).mean()
    return mm


def calcular_volatilidade_anual(retorno: pd.Series) -> float:
    """Desvio padrão dos retornos diários, anualizado."""
    vol_anual = retorno.std() * np.sqrt(DIAS_POR_ANO)
    return vol_anual


def calcular_drawdown(fechamento: pd.Series) -> pd.Series:
    """Queda de cada dia em relação ao maior preço visto até ali."""
    pico = fechamento.cummax()
    drawdown = fechamento / pico - 1
    return drawdown


def calcular_retorno_anualizado(retorno: pd.Series) -> float:
    """Retorno que o ativo teria em 1 ano se mantivesse o ritmo do período (composto)."""
    retorno = retorno.dropna()
    if retorno.empty:
        return float("nan")
    retorno_total = (1 + retorno).prod() - 1
    return (1 + retorno_total) ** (DIAS_POR_ANO / len(retorno)) - 1


def calcular_indice_sharpe(
    retorno: pd.Series, taxa_livre_de_risco: float = 0.0
) -> float:
    """Retorno anualizado acima da taxa livre de risco, por unidade de volatilidade anual."""
    volatilidade = calcular_volatilidade_anual(retorno)
    if np.isnan(volatilidade) or volatilidade == 0:
        return float("nan")  # sem oscilação não dá para dividir
    return (calcular_retorno_anualizado(retorno) - taxa_livre_de_risco) / volatilidade


def encontrar_melhor_dia(retorno: pd.Series) -> tuple[pd.Timestamp, float]:
    """Data e retorno do dia em que o ativo mais subiu."""
    retorno = retorno.dropna()
    if retorno.empty:
        raise ValueError("Série de retornos vazia: não há melhor dia.")
    return retorno.idxmax(), retorno.max()


def encontrar_pior_dia(retorno: pd.Series) -> tuple[pd.Timestamp, float]:
    """Data e retorno do dia em que o ativo mais caiu."""
    retorno = retorno.dropna()
    if retorno.empty:
        raise ValueError("Série de retornos vazia: não há pior dia.")
    return retorno.idxmin(), retorno.min()


def calcular_percentual_dias_positivos(retorno: pd.Series) -> float:
    """Fração dos dias (de 0 a 1) em que o ativo subiu. Dia parado não conta como alta."""
    retorno = retorno.dropna()
    if retorno.empty:
        return float("nan")
    return (retorno > 0).mean()


def calcular_var_historico(retorno: pd.Series, nivel: float = 0.95) -> float:
    """Perda diária que só foi superada em (1 - nivel) dos dias. Vem negativa (é uma perda)."""
    # o quantile ignora o NaN e devolve NaN se não houver nenhum dado
    return retorno.quantile(1 - nivel)


def calcular_volatilidade_movel(retorno: pd.Series, janela: int = 20) -> pd.Series:
    """Volatilidade anualizada calculada numa janela deslizante de `janela` dias."""
    if janela < 2:
        raise ValueError("A janela precisa ter pelo menos 2 dias.")
    return retorno.rolling(window=janela).std() * np.sqrt(DIAS_POR_ANO)


def encontrar_pior_drawdown(fechamento: pd.Series) -> PiorDrawdown:
    """Acha a maior queda do topo ao fundo e diz quando começou e se já foi recuperada."""
    drawdown = calcular_drawdown(fechamento).dropna()
    if drawdown.empty:
        return PiorDrawdown(float("nan"), None, None, None)

    queda = float(drawdown.min())
    if queda == 0:  # o preço nunca ficou abaixo de um topo anterior
        return PiorDrawdown(0.0, None, None, None)

    data_fundo = drawdown.idxmin()
    antes = drawdown.loc[:data_fundo]
    data_topo = antes[antes == 0].index[-1]  # último dia no topo antes do fundo
    depois = drawdown.loc[data_fundo:]
    recuperou = depois[depois == 0]
    data_recuperacao = recuperou.index[0] if not recuperou.empty else None
    return PiorDrawdown(queda, data_topo, data_fundo, data_recuperacao)


def calcular_retorno_mensal(retorno: pd.Series) -> pd.Series:
    """Retorno de cada mês, juntando os retornos diários (juros compostos). Só meses com dados."""
    retorno = retorno.dropna()
    if retorno.empty:
        return pd.Series(dtype=float, index=pd.PeriodIndex([], freq="M"))
    meses = retorno.index.to_period("M")
    return (1 + retorno).groupby(meses).prod() - 1


def montar_tabela_retornos(retorno_mensal: pd.Series) -> pd.DataFrame:
    """Tabela com um ano por linha, os 12 meses em colunas e o total do ano em "Ano"."""
    if retorno_mensal.empty:
        return pd.DataFrame(columns=[*NOMES_DOS_MESES, "Ano"], dtype=float)
    longa = pd.DataFrame(
        {
            "ano": retorno_mensal.index.year,
            "mes": retorno_mensal.index.month,
            "retorno": retorno_mensal.to_numpy(),
        }
    )
    tabela = longa.pivot(index="ano", columns="mes", values="retorno")
    tabela = tabela.reindex(columns=range(1, 13))  # meses sem dados ficam vazios
    tabela.columns = NOMES_DOS_MESES
    tabela.index.name = None
    tabela["Ano"] = (1 + tabela).prod(axis=1) - 1  # o NaN conta como "mês sem dados"
    return tabela


def calcular_media_por_mes(tabela: pd.DataFrame) -> pd.Series:
    """Média do retorno de cada mês do calendário (todos os janeiros, todos os fevereiros...)."""
    return tabela[NOMES_DOS_MESES].mean()


def encontrar_melhor_e_pior_mes(
    retorno_mensal: pd.Series,
) -> tuple[tuple[pd.Period, float], tuple[pd.Period, float]]:
    """Devolve ((mês, retorno) do melhor mês, (mês, retorno) do pior mês)."""
    if retorno_mensal.empty:
        raise ValueError("Série de retornos mensais vazia: não há melhor nem pior mês.")
    melhor = (retorno_mensal.idxmax(), float(retorno_mensal.max()))
    pior = (retorno_mensal.idxmin(), float(retorno_mensal.min()))
    return melhor, pior


def calcular_media_movel_exponencial(fechamento: pd.Series, janela: int) -> pd.Series:
    """Média que dá mais peso aos dias recentes. Os primeiros dias, sem histórico, ficam vazios."""
    media = fechamento.ewm(span=janela, adjust=False).mean()
    return media.where(fechamento.expanding().count() >= janela)


def calcular_macd(
    fechamento: pd.Series, rapida: int = 12, lenta: int = 26, sinal: int = 9
) -> pd.DataFrame:
    """MACD: média exponencial rápida menos a lenta, sua linha de sinal e o histograma."""
    macd = calcular_media_movel_exponencial(
        fechamento, rapida
    ) - calcular_media_movel_exponencial(fechamento, lenta)
    linha_de_sinal = macd.ewm(span=sinal, adjust=False).mean().where(macd.notna())
    return pd.DataFrame(
        {"macd": macd, "sinal": linha_de_sinal, "histograma": macd - linha_de_sinal}
    )


def calcular_atr(dados: pd.DataFrame, janela: int = 14) -> pd.Series:
    """ATR: o tamanho médio do movimento diário (máxima, mínima e o fechamento anterior).

    Usa a suavização de Wilder. Os primeiros dias, sem histórico, ficam vazios.
    """
    fechamento_anterior = dados["Close"].shift(1)
    amplitudes = pd.concat(
        [
            dados["High"] - dados["Low"],
            (dados["High"] - fechamento_anterior).abs(),
            (dados["Low"] - fechamento_anterior).abs(),
        ],
        axis=1,
    )
    amplitude_verdadeira = amplitudes.max(axis=1)
    atr = amplitude_verdadeira.ewm(alpha=1 / janela, adjust=False).mean()
    return atr.where(amplitude_verdadeira.expanding().count() >= janela)


def calcular_rsi(fechamento: pd.Series, janela: int = 14) -> pd.Series:
    """Índice de Força Relativa (0 a 100), com a suavização de Wilder.

    RSI = 100 - 100 / (1 + RS), com RS = ganho médio / perda média. Perto de 0 o preço caiu
    quase todos os dias; perto de 100, subiu quase todos. Os primeiros dias ficam vazios.
    """
    variacao = fechamento.diff()
    ganho = variacao.clip(lower=0)
    perda = (-variacao).clip(lower=0)
    ganho_medio = ganho.ewm(alpha=1 / janela, adjust=False).mean()
    perda_media = perda.ewm(alpha=1 / janela, adjust=False).mean()
    forca_relativa = ganho_medio / perda_media
    rsi = 100 - 100 / (1 + forca_relativa)
    rsi = rsi.where(perda_media > 0, 100.0)  # sem perdas: 100
    rsi = rsi.where((ganho_medio > 0) | (perda_media > 0), 50.0)  # preço parado: neutro
    return rsi.where(variacao.expanding().count() >= janela)


def calcular_bandas_de_bollinger(
    fechamento: pd.Series, janela: int = 20, desvios: float = 2.0
) -> pd.DataFrame:
    """Média móvel com uma faixa de `desvios` desvios-padrão para cima e para baixo.

    Também devolve o %b (0 na banda inferior, 1 na superior) e a largura relativa da faixa.
    """
    media = fechamento.rolling(janela).mean()
    desvio = fechamento.rolling(janela).std(ddof=0)
    superior = media + desvios * desvio
    inferior = media - desvios * desvio
    largura_da_faixa = (superior - inferior).where(superior != inferior)
    return pd.DataFrame(
        {
            "media": media,
            "superior": superior,
            "inferior": inferior,
            "percentual_b": (fechamento - inferior) / largura_da_faixa,
            "largura": largura_da_faixa / media,
        }
    )


def calcular_zscore(fechamento: pd.Series, janela: int = 20) -> pd.Series:
    """A que distância, em desvios-padrão, o preço está da sua média dos últimos `janela` dias."""
    media = fechamento.rolling(janela).mean()
    desvio = fechamento.rolling(janela).std(ddof=0)
    return (fechamento - media) / desvio.where(desvio > 0)


# --- Research, etapa 6: indicadores novos -------------------------------------------------------
def calcular_cvar_historico(retorno: pd.Series, nivel: float = 0.95) -> float:
    """CVaR (perda média nos piores dias): a média dos retornos iguais ou piores que o VaR.

    Responde "quando o dia é ruim, quanto se perde em média?". Vem negativo. Como o VaR, é uma
    estimativa feita com o passado, não um limite de perda.
    """
    retorno = retorno.dropna()
    if retorno.empty:
        return float("nan")
    corte = retorno.quantile(1 - nivel)
    return float(retorno[retorno <= corte].mean())


def _diferenca_ativa(retorno: pd.Series, referencia: pd.Series) -> pd.Series:
    """Retorno do ativo menos o do índice, só nos dias em que os dois têm retorno."""
    juntos = pd.concat([retorno, referencia], axis=1, join="inner").dropna()
    return juntos.iloc[:, 0] - juntos.iloc[:, 1]


def calcular_tracking_error(retorno: pd.Series, referencia: pd.Series) -> float:
    """Tracking error anualizado: o quanto o ativo se descola do índice (desvio da diferença)."""
    diferenca = _diferenca_ativa(retorno, referencia)
    if len(diferenca) < 2:
        return float("nan")
    return float(diferenca.std() * np.sqrt(DIAS_POR_ANO))


def calcular_information_ratio(retorno: pd.Series, referencia: pd.Series) -> float:
    """Information Ratio: quanto o ativo rendeu acima do índice por unidade de tracking error.

    Média anualizada da diferença diária ÷ tracking error. Positivo: rendeu mais que o índice com
    aquele descolamento; perto de zero: o descolamento não rendeu nada a mais.
    """
    diferenca = _diferenca_ativa(retorno, referencia)
    erro = calcular_tracking_error(retorno, referencia)
    if len(diferenca) < 2 or not erro:
        return float("nan")
    return float(diferenca.mean() * DIAS_POR_ANO / erro)


def calcular_adx(dados: pd.DataFrame, janela: int = 14) -> pd.DataFrame:
    """ADX (força da tendência, de 0 a 100) e as direções +DI e -DI, com a suavização de Wilder.

    O ADX não diz se a tendência é de alta ou de baixa (isso é o +DI contra o -DI), só se ela é
    forte: abaixo de ~20 o preço anda de lado; acima de ~25, há tendência. Os primeiros dias ficam
    vazios (o ADX precisa de duas janelas de histórico).
    """
    alta = dados["High"].diff()
    baixa = -dados["Low"].diff()
    mais = alta.where((alta > baixa) & (alta > 0), 0.0)
    menos = baixa.where((baixa > alta) & (baixa > 0), 0.0)
    atr = calcular_atr(dados, janela)
    suavizar = {"alpha": 1 / janela, "adjust": False}
    mais_di = 100 * mais.ewm(**suavizar).mean() / atr
    menos_di = 100 * menos.ewm(**suavizar).mean() / atr
    soma = (mais_di + menos_di).where(lambda s: s > 0)
    dx = 100 * (mais_di - menos_di).abs() / soma
    adx = dx.ewm(**suavizar).mean()
    adx = adx.where(dx.expanding().count() >= janela)
    return pd.DataFrame({"adx": adx, "mais_di": mais_di, "menos_di": menos_di})


def calcular_obv(dados: pd.DataFrame) -> pd.Series:
    """OBV (saldo de volume): soma o volume dos dias de alta e subtrai o dos dias de queda.

    O nível em si não importa (depende de onde começa); o que se lê é a direção: OBV subindo com
    o preço parado indica volume maior nos dias de alta.
    """
    variacao = np.sign(dados["Close"].diff()).fillna(0.0)
    return (variacao * dados["Volume"]).cumsum()


def calcular_volume_relativo(dados: pd.DataFrame, janela: int = 20) -> pd.Series:
    """Volume do dia ÷ média dos `janela` dias anteriores (1 = normal; 2 = o dobro do normal)."""
    media_anterior = dados["Volume"].rolling(janela).mean().shift(1)
    return dados["Volume"] / media_anterior.where(media_anterior > 0)


def para_semanal(dados: pd.DataFrame) -> pd.DataFrame:
    """Barras semanais (semana terminando na sexta) a partir das diárias: abertura da primeira,
    máxima e mínima da semana, fechamento do último pregão e volume somado.

    A data de cada barra é a do **último pregão** da semana (não a sexta "de calendário"), para
    nenhuma barra parecer existir antes de o pregão acontecer.
    """
    regras = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    colunas = {c: f for c, f in regras.items() if c in dados.columns}
    semanas = dados[list(colunas)].groupby(pd.Grouper(freq="W-FRI"))
    barras = semanas.agg(colunas)
    ultimo_pregao = semanas.apply(lambda g: g.index.max() if len(g) else pd.NaT)
    barras.index = pd.DatetimeIndex(ultimo_pregao, name=dados.index.name)
    barras = barras[barras.index.notna()].dropna(subset=["Close"])
    barras.attrs = dict(dados.attrs)
    return barras


def curva_de_capital(retorno: pd.Series) -> pd.Series:
    """Quanto vale cada R$ 1 investido no começo, dia a dia (os retornos compostos)."""
    return (1 + retorno).cumprod()
