"""Estratégias de negociação: cada uma recebe os dados e devolve a posição desejada (0 a 1).

O registro `ESTRATEGIAS` descreve cada estratégia (nome, grupo, parâmetros). A tela é gerada a
partir dele: para acrescentar uma estratégia nova basta escrever a função e registrá-la aqui.
A posição devolvida é a decisão do FIM do dia; o motor (`backtest.py`) aplica o `shift(1)`.

Regra para escrever uma estratégia: a posição de um dia só pode usar dados daquele dia e de dias
anteriores. Um teste automático confere isso para todas as estratégias do registro.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import indicadores as ind

TIPOS_DE_MEDIA = ("Simples", "Exponencial")


@dataclass(frozen=True)
class Parametro:
    """Um botão de ajuste de uma estratégia: um número (com limites) ou uma escolha (`opcoes`)."""

    nome: str  # nome do argumento da função
    rotulo: str  # texto mostrado na tela
    padrao: int | float | str
    minimo: int | float | None = None
    maximo: int | float | None = None
    passo: int | float = 1
    ajuda: str = ""
    opcoes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Estrategia:
    nome: str
    grupo: str
    funcao: Callable[..., pd.Series]
    parametros: tuple[Parametro, ...] = field(default_factory=tuple)

    def parametros_padrao(self) -> dict[str, int | float | str]:
        return {p.nome: p.padrao for p in self.parametros}


# --- Ajudantes ------------------------------------------------------------------------


def _media(fechamento: pd.Series, janela: int, tipo: str) -> pd.Series:
    if tipo == "Simples":
        return ind.calcular_media_movel(fechamento, janela)
    if tipo == "Exponencial":
        return ind.calcular_media_movel_exponencial(fechamento, janela)
    raise ValueError(f"Tipo de média desconhecido: {tipo}.")


def _manter_estado(entrada: pd.Series, saida: pd.Series) -> pd.Series:
    """Liga a posição quando há sinal de entrada e desliga quando há sinal de saída.

    Entre um sinal e outro a posição se mantém. Se os dois chegarem juntos, vale a saída.
    """
    estado = pd.Series(np.nan, index=entrada.index)
    estado[entrada] = 1.0
    estado[saida] = 0.0
    return estado.ffill().fillna(0.0)


# --- Funções de posição -------------------------------------------------------------


def posicao_comprar_e_segurar(dados: pd.DataFrame) -> pd.Series:
    """Compra no primeiro dia e nunca vende: a régua de todas as outras."""
    return pd.Series(1.0, index=dados.index)


def posicao_cruzamento_de_medias(
    dados: pd.DataFrame, curta: int = 20, longa: int = 50, tipo: str = "Simples"
) -> pd.Series:
    """Comprado enquanto a média curta está acima da longa; caixa caso contrário."""
    if curta >= longa:
        raise ValueError("A média curta precisa ser menor que a longa.")
    fechamento = dados["Close"]
    media_curta = _media(fechamento, curta, tipo)
    media_longa = _media(fechamento, longa, tipo)
    return (media_curta > media_longa).astype(float)  # NaN no começo vira False = caixa


def posicao_filtro_de_tendencia(dados: pd.DataFrame, janela: int = 200) -> pd.Series:
    """Comprado enquanto o preço está acima da sua média de `janela` dias."""
    fechamento = dados["Close"]
    return (fechamento > ind.calcular_media_movel(fechamento, janela)).astype(float)


def posicao_filtro_mensal(dados: pd.DataFrame, meses: int = 10) -> pd.Series:
    """Filtro de Faber: decide só no fim de cada mês, comparando o fechamento à média de `meses`.

    A decisão de um mês só vale a partir do mês SEGUINTE (o fechamento do mês só é conhecido
    no último pregão). Poucas operações, portanto poucos custos.
    """
    fechamento = dados["Close"]
    mes = fechamento.index.to_period("M")
    fechamento_do_mes = fechamento.groupby(mes).last()  # fechamento de cada mês
    media = fechamento_do_mes.rolling(meses).mean()
    sinal_do_mes = (fechamento_do_mes > media).astype(float)
    decisao_do_mes_anterior = sinal_do_mes.reindex(
        mes - 1
    )  # cada dia usa o mês anterior
    return pd.Series(decisao_do_mes_anterior.to_numpy(), index=fechamento.index).fillna(
        0.0
    )


def posicao_rompimento_de_canal(
    dados: pd.DataFrame, entrada: int = 20, saida: int = 10
) -> pd.Series:
    """Canal de Donchian (as "Tartarugas"): compra ao superar a máxima dos últimos `entrada`
    dias e vende ao perder a mínima dos últimos `saida` dias."""
    if saida >= entrada:
        raise ValueError("A janela de saída precisa ser menor que a de entrada.")
    fechamento = dados["Close"]
    maxima_anterior = dados["High"].rolling(entrada).max().shift(1)
    minima_anterior = dados["Low"].rolling(saida).min().shift(1)
    return _manter_estado(fechamento > maxima_anterior, fechamento < minima_anterior)


def posicao_macd(
    dados: pd.DataFrame, rapida: int = 12, lenta: int = 26, sinal: int = 9
) -> pd.Series:
    """Comprado enquanto a linha MACD está acima da sua linha de sinal."""
    if rapida >= lenta:
        raise ValueError("A média rápida precisa ser menor que a lenta.")
    macd = ind.calcular_macd(dados["Close"], rapida, lenta, sinal)
    return (macd["macd"] > macd["sinal"]).astype(float)


def posicao_momentum(
    dados: pd.DataFrame, janela: int = 252, pulo: int = 21
) -> pd.Series:
    """Momentum 12-1: comprado se o retorno de `janela` dias, pulando os `pulo` mais recentes,
    é positivo. O pulo evita a reversão de curtíssimo prazo."""
    fechamento = dados["Close"]
    retorno_passado = fechamento.shift(pulo) / fechamento.shift(pulo + janela) - 1
    return (retorno_passado > 0).astype(float)


def posicao_canal_de_keltner(
    dados: pd.DataFrame,
    janela_media: int = 20,
    janela_atr: int = 10,
    multiplicador: float = 2.0,
) -> pd.Series:
    """Compra quando o preço fecha acima da média exponencial + `multiplicador` x ATR
    (rompimento de força) e vende quando fecha de volta abaixo da média."""
    fechamento = dados["Close"]
    media = ind.calcular_media_movel_exponencial(fechamento, janela_media)
    faixa_superior = media + multiplicador * ind.calcular_atr(dados, janela_atr)
    return _manter_estado(fechamento > faixa_superior, fechamento < media)


# --- Registro -----------------------------------------------------------------------

ESTRATEGIAS: dict[str, Estrategia] = {
    estrategia.nome: estrategia
    for estrategia in (
        Estrategia("Comprar e segurar", "Referência", posicao_comprar_e_segurar),
        Estrategia(
            "Cruzamento de médias",
            "Tendência",
            posicao_cruzamento_de_medias,
            (
                Parametro("curta", "Média curta (dias)", 20, 5, 100, 1),
                Parametro("longa", "Média longa (dias)", 50, 10, 300, 5),
                Parametro(
                    "tipo",
                    "Tipo de média",
                    "Simples",
                    opcoes=TIPOS_DE_MEDIA,
                    ajuda="A exponencial dá mais peso aos dias recentes e reage mais rápido.",
                ),
            ),
        ),
        Estrategia(
            "Filtro de tendência",
            "Tendência",
            posicao_filtro_de_tendencia,
            (Parametro("janela", "Média de referência (dias)", 200, 20, 300, 5),),
        ),
        Estrategia(
            "Filtro mensal de 10 meses",
            "Tendência",
            posicao_filtro_mensal,
            (
                Parametro(
                    "meses",
                    "Média de (meses)",
                    10,
                    3,
                    24,
                    1,
                    ajuda="Decide só no fim de cada mês: poucas operações.",
                ),
            ),
        ),
        Estrategia(
            "Rompimento de canal (Donchian)",
            "Tendência",
            posicao_rompimento_de_canal,
            (
                Parametro("entrada", "Entrada: máxima de (dias)", 20, 10, 100, 5),
                Parametro("saida", "Saída: mínima de (dias)", 10, 5, 50, 5),
            ),
        ),
        Estrategia(
            "MACD",
            "Tendência",
            posicao_macd,
            (
                Parametro("rapida", "Média rápida", 12, 5, 30, 1),
                Parametro("lenta", "Média lenta", 26, 10, 60, 1),
                Parametro("sinal", "Linha de sinal", 9, 3, 20, 1),
            ),
        ),
        Estrategia(
            "Momentum 12-1",
            "Tendência",
            posicao_momentum,
            (
                Parametro("janela", "Janela do retorno (dias)", 252, 21, 504, 21),
                Parametro("pulo", "Pular os últimos (dias)", 21, 0, 63, 1),
            ),
        ),
        Estrategia(
            "Canal de Keltner",
            "Tendência",
            posicao_canal_de_keltner,
            (
                Parametro("janela_media", "Média exponencial (dias)", 20, 5, 60, 1),
                Parametro("janela_atr", "ATR (dias)", 10, 5, 30, 1),
                Parametro("multiplicador", "Multiplicador do ATR", 2.0, 0.5, 4.0, 0.5),
            ),
        ),
    )
}


def _conferir_parametro(parametro: Parametro, valor) -> None:
    if parametro.opcoes:
        if valor not in parametro.opcoes:
            raise ValueError(
                f"{parametro.rotulo} deve ser uma destas opções: {', '.join(parametro.opcoes)}."
            )
        return
    if not parametro.minimo <= valor <= parametro.maximo:
        raise ValueError(
            f"{parametro.rotulo} deve ficar entre {parametro.minimo} e {parametro.maximo}."
        )


def gerar_posicao(nome: str, dados: pd.DataFrame, **parametros) -> pd.Series:
    """Aplica a estratégia `nome`, conferindo os parâmetros contra os limites do registro."""
    if nome not in ESTRATEGIAS:
        raise ValueError(f"Estratégia desconhecida: {nome}.")
    estrategia = ESTRATEGIAS[nome]
    conhecidos = {p.nome: p for p in estrategia.parametros}
    desconhecidos = set(parametros) - set(conhecidos)
    if desconhecidos:
        raise ValueError(
            f"Parâmetros desconhecidos para {nome}: {sorted(desconhecidos)}."
        )
    valores = {**estrategia.parametros_padrao(), **parametros}
    for nome_do_parametro, valor in valores.items():
        _conferir_parametro(conhecidos[nome_do_parametro], valor)
    return estrategia.funcao(dados, **valores)
