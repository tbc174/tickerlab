"""Proteções de risco: uma camada que se aplica por cima da posição de QUALQUER estratégia.

Stops (perda, ganho, móvel e por ATR), tamanho da posição por risco e alvo de volatilidade.
Tudo usa só informação até o fechamento do dia (sem olhar o futuro). O stop é conferido no
fechamento: se o preço fecha além do limite, a posição desejada do dia passa a ser zero e,
como em todo o motor, a saída acontece a partir do dia seguinte.

Depois de um stop, a proteção fica "armada": por padrão só volta a comprar quando a estratégia
primeiro pedir para sair e depois pedir para entrar de novo (um sinal novo). Sem isso, a
estratégia reentraria no dia seguinte, na mesma queda que acabou de ser cortada. Estratégias que
nunca mandam sair (como comprar e segurar) precisam de `dias_de_espera`: passado esse prazo,
se a estratégia ainda quer estar comprada, a proteção deixa entrar de novo.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import indicadores as ind


@dataclass(frozen=True)
class Protecoes:
    """O que ligar. `None` significa desligado. Percentuais são frações (0,08 = 8%)."""

    stop_loss: float | None = None  # sai se o preço cair tanto desde a entrada
    take_profit: float | None = None  # sai se o preço subir tanto desde a entrada
    stop_movel: float | None = (
        None  # sai se cair tanto desde a máxima depois da entrada
    )
    stop_atr: float | None = (
        None  # sai se cair N vezes o ATR da entrada abaixo do preço de entrada
    )
    janela_atr: int = 14
    risco_por_operacao: float | None = (
        None  # fração do capital que o stop de ATR pode custar
    )
    alvo_de_volatilidade: float | None = (
        None  # volatilidade anual desejada (0,15 = 15%)
    )
    janela_volatilidade: int = 20
    dias_de_espera: int | None = None  # None = só volta com um sinal novo da estratégia

    def alguma_ligada(self) -> bool:
        return any(
            valor is not None
            for valor in (
                self.stop_loss,
                self.take_profit,
                self.stop_movel,
                self.stop_atr,
                self.alvo_de_volatilidade,
            )
        )

    def validar(self) -> None:
        for nome in ("stop_loss", "stop_movel"):
            valor = getattr(self, nome)
            if valor is not None and not 0 < valor < 1:
                raise ValueError(
                    f"{nome} deve ficar entre 0 e 1 (por exemplo, 0,08 para 8%)."
                )
        for nome in ("take_profit", "stop_atr", "alvo_de_volatilidade"):
            valor = getattr(self, nome)
            if valor is not None and valor <= 0:
                raise ValueError(f"{nome} deve ser maior que zero.")
        if self.risco_por_operacao is not None:
            if not 0 < self.risco_por_operacao <= 1:
                raise ValueError("risco_por_operacao deve ficar entre 0 e 1.")
            if self.stop_atr is None:
                raise ValueError(
                    "O risco por operação precisa do stop por ATR para calcular o tamanho."
                )
        if self.dias_de_espera is not None and self.dias_de_espera < 1:
            raise ValueError("A espera depois de um stop deve ser de pelo menos 1 dia.")
        if self.janela_atr < 2 or self.janela_volatilidade < 2:
            raise ValueError("As janelas precisam ter pelo menos 2 dias.")


def _aplicar_stops(
    fechamento: np.ndarray,
    desejada: np.ndarray,
    atr: np.ndarray | None,
    protecoes: Protecoes,
) -> np.ndarray:
    """Percorre os dias em ordem, guardando o estado da operação em andamento."""
    protegida = np.zeros(len(fechamento))
    em_posicao = False
    bloqueada = False  # parou por um stop e espera um sinal novo da estratégia
    dias_bloqueada = 0
    entrada = maxima = nivel_do_atr = tamanho = 0.0

    for dia in range(len(fechamento)):
        quer = desejada[dia]
        preco = fechamento[dia]

        if bloqueada:
            dias_bloqueada += 1
            if quer == 0:  # a estratégia mandou sair: a proteção volta a ficar armada
                bloqueada = False
                continue
            espera = protecoes.dias_de_espera
            if espera is None or dias_bloqueada <= espera:
                continue
            bloqueada = False  # a espera acabou e a estratégia ainda quer comprar: tenta entrar hoje

        if not em_posicao:
            if quer > 0:
                if atr is not None and np.isnan(atr[dia]):
                    continue  # ainda sem ATR para calcular o stop: espera
                em_posicao = True
                entrada = maxima = preco
                tamanho = 1.0
                if atr is not None:
                    distancia = protecoes.stop_atr * atr[dia]
                    nivel_do_atr = entrada - distancia
                    if protecoes.risco_por_operacao is not None and distancia > 0:
                        tamanho = min(
                            1.0, protecoes.risco_por_operacao / (distancia / entrada)
                        )
                protegida[dia] = quer * tamanho
            continue

        if quer == 0:  # saída normal da estratégia
            em_posicao = False
            continue

        maxima = max(maxima, preco)
        bateu_stop = (
            (
                protecoes.stop_loss is not None
                and preco <= entrada * (1 - protecoes.stop_loss)
            )
            or (
                protecoes.take_profit is not None
                and preco >= entrada * (1 + protecoes.take_profit)
            )
            or (
                protecoes.stop_movel is not None
                and preco <= maxima * (1 - protecoes.stop_movel)
            )
            or (protecoes.stop_atr is not None and preco <= nivel_do_atr)
        )
        if bateu_stop:
            em_posicao = False
            bloqueada = True
            dias_bloqueada = 0
        else:
            protegida[dia] = quer * tamanho
    return protegida


def aplicar_protecoes(
    dados: pd.DataFrame, posicao_desejada: pd.Series, protecoes: Protecoes
) -> pd.Series:
    """Devolve a posição desejada já com os stops, o tamanho por risco e o alvo de volatilidade."""
    protecoes.validar()
    if not protecoes.alguma_ligada():
        return posicao_desejada.copy()

    atr = (
        ind.calcular_atr(dados, protecoes.janela_atr).to_numpy(dtype=float)
        if protecoes.stop_atr is not None
        else None
    )
    posicao = pd.Series(
        _aplicar_stops(
            dados["Close"].to_numpy(dtype=float),
            posicao_desejada.to_numpy(dtype=float),
            atr,
            protecoes,
        ),
        index=posicao_desejada.index,
    )

    if protecoes.alvo_de_volatilidade is not None:
        retorno = dados["Close"].pct_change()
        volatilidade = retorno.rolling(protecoes.janela_volatilidade).std() * np.sqrt(
            ind.DIAS_POR_ANO
        )
        fator = (protecoes.alvo_de_volatilidade / volatilidade).clip(
            upper=1.0
        )  # sem alavancagem
        posicao = posicao * fator.fillna(
            0.0
        )  # sem histórico de volatilidade: fica em caixa
    return posicao
