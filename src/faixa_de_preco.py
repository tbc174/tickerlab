"""Mínima e máxima de 52 semanas e variação em 12 meses do preço da ação (linha 412 da fila).

Usa o fechamento SEM ajuste por proventos (`src.dados.baixar_fechamento_sem_ajuste`): o preço
ajustado, que o resto do app usa nos retornos, muda os preços antigos a cada dividendo, e a mínima
e a máxima deixariam de ser os preços que o mercado de fato viu. A série não é guardada."""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from src.configuracao import preco_no_relatorio_ligado
from src.dados import baixar_fechamento_sem_ajuste
from src.moedas import moeda_do_ticker

DIAS_DA_JANELA = 365
# Tolerância para achar o pregão de um ano antes (feriados e fins de semana).
DIAS_DE_FOLGA_DA_BASE = 7
FONTE_DA_FAIXA = "Yahoo Finance (fechamento diário sem ajuste por proventos)"


@dataclass(frozen=True)
class FaixaDePreco:
    minima: float
    data_da_minima: date
    maxima: float
    data_da_maxima: date
    variacao_12_meses: float | None  # fração: 0,10 é +10%; None sem um ano de histórico
    data_da_base: date  # o pregão de um ano antes, de onde sai a variação
    ate: date  # o último fechamento lido

    def texto(self) -> str:
        """O parágrafo da ficha: os números, de onde vêm, a data e qual preço a variação usa."""
        data = self.ate.strftime("%d/%m/%Y")
        faixa = (
            f"Em 52 semanas até {data}, a mínima de fechamento foi {_reais(self.minima)} "
            f"({self.data_da_minima:%d/%m/%Y}) e a máxima, {_reais(self.maxima)} "
            f"({self.data_da_maxima:%d/%m/%Y})."
        )
        if self.variacao_12_meses is None:
            variacao = " Ainda não há um ano de histórico para a variação em 12 meses."
        else:
            variacao = (
                f" A variação em 12 meses foi de {_percentual(self.variacao_12_meses)}, "
                f"do fechamento de {self.data_da_base:%d/%m/%Y} ao de {data}."
            )
        return (
            f"{faixa}{variacao} Preços sem ajuste por proventos, de {FONTE_DA_FAIXA}: a variação "
            "mostra só o preço da ação e não conta os proventos recebidos no período. "
            "Não é recomendação de investimento."
        )


def _reais(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _percentual(fracao: float) -> str:
    return f"{fracao * 100:+.1f}%".replace(".", ",")


def calcular_faixa_de_preco(
    fechamentos: pd.Series | None, ate: date | None = None
) -> FaixaDePreco | None:
    """A faixa de 52 semanas do fechamento sem ajuste, ou None sem série.

    `ate` corta o futuro: só entram fechamentos até essa data (inclusive)."""
    if fechamentos is None or fechamentos.empty:
        return None
    serie = fechamentos.dropna().sort_index()
    if ate is not None:
        serie = serie.loc[: pd.Timestamp(ate)]
    if serie.empty:
        return None
    ultimo = serie.index[-1]
    janela = serie.loc[serie.index > ultimo - timedelta(days=DIAS_DA_JANELA)]
    base = _fechamento_de_um_ano_antes(serie, ultimo)
    return FaixaDePreco(
        minima=float(janela.min()),
        data_da_minima=janela.idxmin().date(),
        maxima=float(janela.max()),
        data_da_maxima=janela.idxmax().date(),
        variacao_12_meses=None if base is None else float(serie.iloc[-1] / base[1] - 1),
        data_da_base=(base[0] if base else ultimo).date(),
        ate=ultimo.date(),
    )


def _fechamento_de_um_ano_antes(
    serie: pd.Series, ultimo: pd.Timestamp
) -> tuple[pd.Timestamp, float] | None:
    """(dia, fechamento) do último pregão até um ano antes; None se a série não chega lá."""
    alvo = ultimo - timedelta(days=DIAS_DA_JANELA)
    antes = serie.loc[:alvo]
    if antes.empty or alvo - antes.index[-1] > timedelta(days=DIAS_DE_FOLGA_DA_BASE):
        return None
    return antes.index[-1], float(antes.iloc[-1])


def faixa_de_preco_do_ticker(ticker: str) -> FaixaDePreco | None:
    """A faixa da ficha: vazia fora da B3, sem cotação ou com a trava do preço desligada
    (`TICKERLAB_PRECO_NO_RELATORIO=0`), que nem pergunta ao Yahoo."""
    if moeda_do_ticker(ticker) != "BRL" or not preco_no_relatorio_ligado():
        return None
    return calcular_faixa_de_preco(baixar_fechamento_sem_ajuste(ticker))
