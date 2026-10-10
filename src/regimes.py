"""Regimes de mercado e disjuntor de drawdown.

- Regimes: classifica cada dia (volatilidade calma ou agitada; tendência de alta ou de baixa) só
  com o que já se sabia naquele dia, resume o desempenho em cada regime e permite filtrar uma
  estratégia para operar só em certos regimes.
- Variância gerida (Moreira & Muir, 2017): reduz a posição quando a variância recente está alta.
- Disjuntor de drawdown: se a própria estratégia cai mais de X% desde o topo, vai para o caixa
  por N dias. Mostra o custo de "se proteger": evita perdas, mas atrasa a volta.

Tudo usa só informação até o fechamento do dia (sem olhar o futuro). Os limites dos regimes são
calculados com o passado (percentil "expansivo"), nunca com a amostra inteira.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import indicadores as ind
from src import metricas
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest

SEM_HISTORICO = "Sem histórico"
REGIMES_DE_VOLATILIDADE = ("Calmo", "Agitado")
REGIMES_DE_TENDENCIA = ("Alta", "Baixa")
HISTORICO_MINIMO_DA_VOLATILIDADE = 60  # dias antes de o limite começar a existir


# --- Regimes ------------------------------------------------------------------------------


def classificar_regimes_de_volatilidade(
    fechamento: pd.Series, janela: int = 20, percentil: float = 0.5
) -> pd.Series:
    """ "Agitado" se a volatilidade recente passa do percentil histórico, senão "Calmo".

    O percentil é calculado só com os dias anteriores e o próprio dia (janela expansiva), então
    a classificação de hoje não depende do futuro.
    """
    if janela < 2:
        raise ValueError("A janela da volatilidade precisa ter pelo menos 2 dias.")
    if not 0 < percentil < 1:
        raise ValueError("O percentil deve ficar entre 0 e 1 (0,5 é a mediana).")
    volatilidade = fechamento.pct_change().rolling(janela).std()
    limite = volatilidade.expanding(
        min_periods=HISTORICO_MINIMO_DA_VOLATILIDADE
    ).quantile(percentil)
    regime = pd.Series(SEM_HISTORICO, index=fechamento.index, dtype=object)
    conhecido = limite.notna() & volatilidade.notna()
    regime[conhecido & (volatilidade > limite)] = "Agitado"
    regime[conhecido & (volatilidade <= limite)] = "Calmo"
    return regime


def classificar_regimes_de_tendencia(
    fechamento: pd.Series, janela: int = 200
) -> pd.Series:
    """ "Alta" se o fechamento está acima da média móvel, "Baixa" se está abaixo."""
    if janela < 2:
        raise ValueError("A janela da média precisa ter pelo menos 2 dias.")
    media = ind.calcular_media_movel(fechamento, janela)
    regime = pd.Series(SEM_HISTORICO, index=fechamento.index, dtype=object)
    regime[media.notna() & (fechamento > media)] = "Alta"
    regime[media.notna() & (fechamento <= media)] = "Baixa"
    return regime


def resumir_por_regime(
    retorno: pd.Series,
    regimes: pd.Series,
    taxa_livre_de_risco: float = 0.0,
    conhecido_na_vespera: bool = True,
) -> pd.DataFrame:
    """Uma linha por regime: dias, retorno e risco do ativo (ou da estratégia) nesses dias.

    Por padrão o regime que vale para o dia é o da véspera, que é o que dava para saber antes
    do pregão abrir. Usar o regime do próprio dia mistura causa e efeito (um dia de queda forte
    deixa o regime "agitado" justamente porque caiu).
    """
    if not retorno.index.equals(regimes.index):
        raise ValueError("Retornos e regimes precisam ter as mesmas datas.")
    rotulos = regimes.shift(1) if conhecido_na_vespera else regimes
    linhas = {}
    for nome in pd.unique(rotulos.dropna()):
        if nome == SEM_HISTORICO:
            continue
        r = retorno[rotulos == nome]
        if len(r) < 2:
            continue
        linhas[nome] = {
            "Dias": len(r),
            "% do tempo": len(r) / retorno.notna().sum(),
            "Retorno médio por dia": float(r.mean()),
            "Retorno anualizado": float(r.mean() * ind.DIAS_POR_ANO),
            "Volatilidade anual": ind.calcular_volatilidade_anual(r),
            "Índice de Sharpe": float(
                (r.mean() - taxa_livre_de_risco / ind.DIAS_POR_ANO)
                / r.std()
                * np.sqrt(ind.DIAS_POR_ANO)
            )
            if r.std() > 0
            else float("nan"),
            "Pior dia": float(r.min()),
        }
    if not linhas:
        raise ValueError("Poucos dias classificados para resumir os regimes.")
    return pd.DataFrame(linhas).T


def filtrar_por_regime(
    posicao_desejada: pd.Series, regimes: pd.Series, ficar_em: tuple[str, ...]
) -> pd.Series:
    """Mantém a posição só nos dias em que o regime está em `ficar_em`; nos outros, caixa."""
    if not posicao_desejada.index.equals(regimes.index):
        raise ValueError("Posição e regimes precisam ter as mesmas datas.")
    if not ficar_em:
        raise ValueError("Escolha pelo menos um regime para ficar comprado.")
    return posicao_desejada.where(regimes.isin(ficar_em), 0.0)


def gerir_pela_variancia(
    fechamento: pd.Series, posicao_desejada: pd.Series, janela: int = 21
) -> pd.Series:
    """Posição × (variância típica ÷ variância recente), no máximo 1 (sem alavancagem).

    A variância "típica" é a mediana dos dias anteriores. Quando o mercado está mais agitado que
    o normal, a exposição cai na proporção da variância; quando está calmo, fica cheia.
    """
    if janela < 2:
        raise ValueError("A janela da variância precisa ter pelo menos 2 dias.")
    variancia = fechamento.pct_change().rolling(janela).var()
    tipica = variancia.expanding(min_periods=HISTORICO_MINIMO_DA_VOLATILIDADE).median()
    fator = (tipica / variancia.where(variancia > 0)).clip(upper=1.0)
    return posicao_desejada * fator.fillna(0.0)


# --- Disjuntor de drawdown ----------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoDoDisjuntor:
    posicao: pd.Series  # posição desejada já com o disjuntor
    acionamentos: pd.DatetimeIndex  # dias em que o disjuntor disparou
    dias_parado: int  # quantos dias a decisão ficou travada em caixa


def aplicar_disjuntor_de_drawdown(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    limite: float,
    dias_de_pausa: int,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
) -> ResultadoDoDisjuntor:
    """Trava a estratégia em caixa por `dias_de_pausa` quando ela cai `limite` desde o topo.

    A queda é medida na curva da própria estratégia (já com custos), com a posição que de fato
    rendeu em cada dia. Quando a pausa termina, o topo é refeito a partir do patrimônio de
    então: senão o disjuntor dispararia de novo no dia seguinte, pela mesma queda antiga.
    """
    if not 0 < limite < 1:
        raise ValueError("O limite de queda deve ficar entre 0 e 1 (0,15 para 15%).")
    if dias_de_pausa < 1:
        raise ValueError("A pausa precisa ser de pelo menos 1 dia.")
    if custo_por_operacao < 0:
        raise ValueError("O custo por operação não pode ser negativo.")
    if not fechamento.index.equals(posicao_desejada.index):
        raise ValueError("Preços e posição precisam ter as mesmas datas.")

    retorno_do_ativo = fechamento.pct_change().fillna(0.0).to_numpy(dtype=float)
    desejada = posicao_desejada.to_numpy(dtype=float)
    protegida = np.zeros(len(desejada))
    patrimonio, topo = 1.0, 1.0
    pausa_restante = 0
    dias_parado = 0
    disparos = []
    anterior = 0.0  # posição que rendeu no dia anterior
    for dia in range(len(desejada)):
        # a posição que rende hoje é a decidida ontem
        em_posicao = protegida[dia - 1] if dia > 0 else 0.0
        mudanca = abs(em_posicao - anterior)
        patrimonio *= (
            1 + em_posicao * retorno_do_ativo[dia] - mudanca * custo_por_operacao
        )
        anterior = em_posicao
        topo = max(topo, patrimonio)

        if pausa_restante > 0:
            protegida[dia] = 0.0
            pausa_restante -= 1
            dias_parado += 1
            if pausa_restante == 0:
                topo = patrimonio  # volta a medir a queda a partir daqui
        elif patrimonio / topo - 1 <= -limite:
            protegida[dia] = 0.0
            pausa_restante = dias_de_pausa - 1
            dias_parado += 1
            disparos.append(fechamento.index[dia])
            if pausa_restante == 0:
                topo = patrimonio
        else:
            protegida[dia] = desejada[dia]
    return ResultadoDoDisjuntor(
        posicao=pd.Series(protegida, index=posicao_desejada.index),
        acionamentos=pd.DatetimeIndex(disparos),
        dias_parado=dias_parado,
    )


def varrer_disjuntor(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    limites: list[float],
    pausas: list[int],
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
    taxa_livre_de_risco: float = 0.0,
) -> pd.DataFrame:
    """Compara várias combinações de limite e pausa (e a estratégia sem disjuntor)."""
    linhas = []

    def _linha(rotulo: str, posicao: pd.Series, acionamentos: int) -> None:
        r = executar_backtest(fechamento, posicao, custo_por_operacao)
        linhas.append(
            {
                "Disjuntor": rotulo,
                "Retorno total": metricas.calcular_retorno_total(r.retorno),
                "Índice de Sharpe": ind.calcular_indice_sharpe(
                    r.retorno, taxa_livre_de_risco
                ),
                "Maior queda": float(ind.calcular_drawdown(r.curva_de_capital).min()),
                "Acionamentos": acionamentos,
            }
        )

    _linha("Sem disjuntor", posicao_desejada, 0)
    for limite in limites:
        for pausa in pausas:
            d = aplicar_disjuntor_de_drawdown(
                fechamento, posicao_desejada, limite, pausa, custo_por_operacao
            )
            _linha(
                f"Queda de {limite:.0%} · pausa de {pausa} dias".replace(".", ","),
                d.posicao,
                len(d.acionamentos),
            )
    return pd.DataFrame(linhas).set_index("Disjuntor")
