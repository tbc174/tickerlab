"""A comparação da camada A3: a nota do dia contra os preços dos 12 meses seguintes.

Só entram preços posteriores ao registro: a carteira de uma rodada entra no fechamento do pregão
seguinte ao dia registrado (critérios, seção 5) e sai no primeiro pregão a 12 meses ou mais da
entrada (seção 7). Nada do dia do registro nem de antes muda o resultado (há teste).

Os preços são os de fechamento que o chamador passar. Enquanto o ajuste por proventos não estiver
conferido, a comparação é "a confirmar" (critérios, seção 9); uma ação que sair da bolsa na janela
fica com o último preço que teve.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from trader import custos_br
from trader.agentes import criterios
from trader.freios import Freio, aplicar_freio

CAPITAL = 100_000.0  # reais da carteira em papel: só pesa na corretagem fixa por ordem
CLASSE = "acoes"


def _entrada(indice: pd.Index, data: str) -> pd.Timestamp | None:
    depois = indice[indice > pd.Timestamp(data)]
    return depois[0] if len(depois) else None


def janela(indice: pd.Index, data: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Entrada e saída da rodada registrada em `data`; None se os 12 meses ainda não fecharam."""
    entrada = _entrada(indice, data)
    if entrada is None:
        return None
    alvo = entrada + pd.DateOffset(months=criterios.MESES_DA_COMPARACAO)
    depois = indice[indice >= alvo]
    return (entrada, depois[0]) if len(depois) else None


def _precos(
    fechamento: pd.DataFrame, tickers: Iterable[str], ate: pd.Timestamp
) -> pd.DataFrame:
    tickers = list(tickers)
    faltando = sorted(set(tickers) - set(fechamento.columns))
    if faltando:
        raise KeyError(f"sem preço para {', '.join(faltando)}")
    return fechamento.loc[:ate, tickers].ffill()


def _cdi_acumulado(cdi: pd.Series, dias: pd.Index) -> float:
    alinhado = cdi.reindex(dias)
    if alinhado.isna().any():
        raise ValueError(f"CDI faltando em {alinhado.index[alinhado.isna()][0].date()}")
    return float((1 + alinhado).prod() - 1)


def _correlacao(notas: pd.Series, retornos: pd.Series) -> float | None:
    """Spearman sem o SciPy: Pearson das posições."""
    valor = notas.rank().corr(retornos.rank())
    return None if pd.isna(valor) else float(valor)


def comparar(
    linha: dict,
    fechamento: pd.DataFrame,
    cdi: pd.Series,
    ibovespa: pd.Series | None = None,
) -> dict | None:
    """Retornos da janela: as escolhidas (resto em CDI), a cesta das candidatas, o CDI e o Ibovespa."""
    datas = janela(fechamento.index, linha["data"])
    if datas is None:
        return None
    entrada, saida = datas
    notas = pd.Series(
        {a["ticker"]: a["nota_final"] for a in linha["avaliacoes"]}, dtype=float
    )
    precos = _precos(fechamento, notas.index, saida)
    retornos = precos.loc[saida] / precos.loc[entrada] - 1
    dias = fechamento.index[(fechamento.index > entrada) & (fechamento.index <= saida)]
    cdi_da_janela = _cdi_acumulado(cdi, dias)
    pesos = linha["escolhidas"]
    escolhidas = sum(peso * retornos[t] for t, peso in pesos.items())
    escolhidas += (1 - sum(pesos.values())) * cdi_da_janela
    return {
        "entrada": entrada.date().isoformat(),
        "saida": saida.date().isoformat(),
        "escolhidas": float(escolhidas),
        "cesta": float(retornos.mean()),
        "cdi": cdi_da_janela,
        "ibovespa": (
            None if ibovespa is None else float(ibovespa[saida] / ibovespa[entrada] - 1)
        ),
        "correlacao": _correlacao(notas, retornos),
    }


# --- a carteira em papel, rodada após rodada -----------------------------------------------------


def _custo(
    posicoes: dict[str, float], alvo: dict[str, float], custos: custos_br.CustosBR
) -> float:
    tickers = set(posicoes) | set(alvo)
    negociado = (abs(alvo.get(t, 0.0) - posicoes.get(t, 0.0)) for t in tickers)
    return sum(
        custos_br.custo_de_negociar(valor, CLASSE, custos=custos)
        for valor in negociado
        if valor > 0
    )


def carteira_em_papel(
    linhas: Iterable[dict],
    fechamento: pd.DataFrame,
    cdi: pd.Series,
    custos: custos_br.CustosBR = custos_br.PADRAO,
) -> Freio:
    """O retorno diário da camada: cada rodada troca a carteira na entrada dela, com custos e freio.

    Entre as trocas a carteira fica parada (as ações andam com o preço, o resto rende CDI). No dia da
    troca o custo das ordens sai do valor; o freio de 40% vale sobre a série inteira.
    """
    entradas: dict[pd.Timestamp, dict[str, float]] = {}
    for linha in sorted(linhas, key=lambda item: item["data"]):
        entrada = _entrada(fechamento.index, linha["data"])
        if entrada is not None:
            entradas[entrada] = dict(linha["escolhidas"])
    if not entradas:
        raise ValueError("nenhuma rodada entrou na carteira ainda")
    tickers = sorted({t for pesos in entradas.values() for t in pesos})
    inicio = min(entradas)
    dias = fechamento.index[fechamento.index >= inicio]
    precos = _precos(fechamento, tickers, dias[-1]).loc[inicio:]
    cdi_do_dia = cdi.reindex(dias)
    if cdi_do_dia.isna().any():
        raise ValueError(
            f"CDI faltando em {cdi_do_dia.index[cdi_do_dia.isna()][0].date()}"
        )
    posicoes: dict[str, float] = {}
    caixa = CAPITAL
    retornos = []
    anterior = precos.iloc[0]
    for dia in dias:
        valor_antes = caixa + sum(posicoes.values())
        posicoes = {t: v * precos.at[dia, t] / anterior[t] for t, v in posicoes.items()}
        if dia != inicio:
            caixa *= 1 + cdi_do_dia[dia]
        anterior = precos.loc[dia]
        if dia in entradas:
            valor = caixa + sum(posicoes.values())
            alvo = {t: peso * valor for t, peso in entradas[dia].items()}
            valor -= _custo(posicoes, alvo, custos)
            posicoes = {t: peso * valor for t, peso in entradas[dia].items()}
            caixa = valor - sum(posicoes.values())
        retornos.append((caixa + sum(posicoes.values())) / valor_antes - 1)
    retorno = pd.Series(retornos, index=dias, name="agentes")
    return aplicar_freio(retorno, cdi, criterios.FREIO)
