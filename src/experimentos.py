"""Experimentos educacionais: perguntas clássicas respondidas com os dados do ativo escolhido.

- Aporte único × aportes mensais (DCA): qual vence, e quantas vezes?
- Rebalanceamento: nunca, todo mês ou só quando os pesos se afastam de uma faixa.
- Retorno da noite × retorno do dia.
- Virada do mês: ficar comprado só em torno da troca de mês.

Nada aqui é uma regra de negociação pronta: são formas de olhar os dados. Os resultados valem
para o ativo e o período escolhidos, não para o mercado em geral.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import indicadores as ind
from src.backtest import (
    CUSTO_PADRAO_POR_OPERACAO,
    ResultadoBacktest,
    executar_backtest,
)
from src.carteiras import dias_de_decisao

DIAS_POR_MES = 21  # dias úteis aproximados em um mês


# --- Aporte único × aportes mensais (DCA) -------------------------------------------------


def simular_aporte_unico_e_dca(
    fechamento: pd.Series,
    total: float,
    parcelas: int,
    intervalo: int = DIAS_POR_MES,
) -> pd.DataFrame:
    """Patrimônio dia a dia de quem investe `total` de uma vez e de quem divide em parcelas.

    As parcelas são iguais e compradas a cada `intervalo` dias; o dinheiro que ainda não
    entrou fica parado, sem render (para o experimento ser simples). Termina com as duas
    estratégias totalmente investidas.
    """
    _conferir_parcelas(len(fechamento), parcelas, intervalo)
    if total <= 0:
        raise ValueError("O valor total deve ser maior que zero.")
    preco = fechamento.to_numpy(dtype=float)
    unico = total * preco / preco[0]

    cotas = np.zeros(len(preco))
    caixa = np.full(len(preco), float(total))
    parcela = total / parcelas
    for k in range(parcelas):
        dia = k * intervalo
        cotas[dia:] += parcela / preco[dia]
        caixa[dia:] -= parcela
    parcelado = caixa + cotas * preco
    return pd.DataFrame(
        {"Aporte único": unico, "Parcelado": parcelado}, index=fechamento.index
    )


def _conferir_parcelas(n_dias: int, parcelas: int, intervalo: int) -> None:
    if parcelas < 2:
        raise ValueError("Use pelo menos 2 parcelas.")
    if intervalo < 1:
        raise ValueError("O intervalo entre parcelas deve ser de pelo menos 1 dia.")
    if (parcelas - 1) * intervalo >= n_dias:
        raise ValueError("Não há dias suficientes para comprar todas as parcelas.")


def comparar_janelas(
    fechamento: pd.Series,
    parcelas: int,
    horizonte: int,
    intervalo: int = DIAS_POR_MES,
) -> pd.DataFrame:
    """Para cada dia de início possível, quanto R$ 1 vira depois de `horizonte` dias em cada jeito.

    Colunas: "Aporte único", "Parcelado" (múltiplos do valor investido, 1,10 = +10%) e
    "Diferença" (único menos parcelado). As janelas se sobrepõem: não são sorteios independentes.
    """
    _conferir_parcelas(horizonte + 1, parcelas, intervalo)
    n = len(fechamento)
    if horizonte >= n:
        raise ValueError("O horizonte é maior que o histórico.")
    preco = fechamento.to_numpy(dtype=float)
    inicios = n - horizonte
    final = preco[horizonte : horizonte + inicios]
    unico = final / preco[:inicios]
    inverso = np.zeros(inicios)
    for k in range(parcelas):
        inverso += 1 / preco[k * intervalo : k * intervalo + inicios]
    parcelado = final * inverso / parcelas
    return pd.DataFrame(
        {
            "Aporte único": unico,
            "Parcelado": parcelado,
            "Diferença": unico - parcelado,
        },
        index=fechamento.index[:inicios],
    )


def resumir_janelas(janelas: pd.DataFrame) -> dict[str, float]:
    """Números que contam a história das janelas: quem vence, por quanto e no pior caso."""
    if janelas.empty:
        raise ValueError("Não há janelas para resumir.")
    return {
        "Janelas": float(len(janelas)),
        "Aporte único vence": float((janelas["Diferença"] > 0).mean()),
        "Diferença mediana": float(janelas["Diferença"].median()),
        "Pior caso do aporte único": float(janelas["Aporte único"].min() - 1),
        "Pior caso do parcelado": float(janelas["Parcelado"].min() - 1),
        "Mediana do aporte único": float(janelas["Aporte único"].median() - 1),
        "Mediana do parcelado": float(janelas["Parcelado"].median() - 1),
    }


# --- Rebalanceamento por faixas -----------------------------------------------------------

REGRAS_DE_REBALANCEAMENTO = ("Nunca", "Todo mês", "Por faixa")


@dataclass(frozen=True)
class ResultadoRebalanceamento:
    retorno: pd.Series
    curva_de_capital: pd.Series
    rebalanceamentos: int
    giro: float  # soma do que foi comprado e vendido, em frações do capital


def simular_rebalanceamento(
    fechamentos: pd.DataFrame,
    peso_do_primeiro: float = 0.5,
    regra: str = "Por faixa",
    faixa: float = 0.05,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
) -> ResultadoRebalanceamento:
    """Carteira de dois ativos com pesos-alvo fixos e uma regra para voltar a eles.

    Compra tudo no primeiro dia. No fim de cada dia confere a regra e, se for o caso, rebalanceia
    ao preço de fechamento (o novo peso vale a partir do dia seguinte). Os custos incidem
    sobre o valor negociado.
    """
    if fechamentos.shape[1] != 2:
        raise ValueError("O rebalanceamento usa exatamente dois ativos.")
    if regra not in REGRAS_DE_REBALANCEAMENTO:
        raise ValueError(f"Regra desconhecida: {regra}.")
    if not 0 < peso_do_primeiro < 1:
        raise ValueError("O peso do primeiro ativo deve ficar entre 0 e 1.")
    if not 0 < faixa < 1:
        raise ValueError("A faixa deve ficar entre 0 e 1.")
    if custo_por_operacao < 0:
        raise ValueError("O custo por operação não pode ser negativo.")
    if len(fechamentos) < 2:
        raise ValueError("Não há preços para simular.")

    alvo = np.array([peso_do_primeiro, 1 - peso_do_primeiro])
    retornos = fechamentos.pct_change().fillna(0.0).to_numpy(dtype=float)
    fim_de_mes = fechamentos.index.isin(dias_de_decisao(fechamentos.index))

    retorno = np.zeros(len(fechamentos))
    retorno[0] = -custo_por_operacao  # a compra inicial de 100% do capital
    pesos = alvo.copy()
    rebalanceamentos, giro = 0, 1.0
    for dia in range(1, len(fechamentos)):
        crescimento = 1 + pesos @ retornos[dia]
        pesos = pesos * (1 + retornos[dia]) / crescimento
        custo = 0.0
        precisa = (regra == "Todo mês" and fim_de_mes[dia]) or (
            regra == "Por faixa" and abs(pesos[0] - alvo[0]) > faixa
        )
        if precisa:
            negociado = np.abs(alvo - pesos).sum()
            custo = negociado * custo_por_operacao
            giro += negociado
            rebalanceamentos += 1
            pesos = alvo.copy()
        retorno[dia] = crescimento - 1 - custo

    serie = pd.Series(retorno, index=fechamentos.index)
    return ResultadoRebalanceamento(
        serie, (1 + serie).cumprod(), rebalanceamentos, float(giro)
    )


# --- Retorno da noite × retorno do dia ----------------------------------------------------


def separar_noite_e_dia(dados: pd.DataFrame) -> pd.DataFrame:
    """Divide o retorno de cada dia em "Noite" (fechamento de ontem até a abertura de hoje) e
    "Dia" (abertura até o fechamento). Compostos, dão o retorno total: (1+noite)(1+dia) = 1+retorno.
    """
    for coluna in ("Open", "Close"):
        if coluna not in dados.columns:
            raise ValueError(
                f"Faltam os preços de {coluna} para separar a noite e o dia."
            )
    abertura = dados["Open"].where(dados["Open"] > 0)
    fechamento = dados["Close"]
    tabela = pd.DataFrame(
        {
            "Noite": abertura / fechamento.shift(1) - 1,
            "Dia": fechamento / abertura - 1,
        }
    ).dropna()
    if len(tabela) < 2:
        raise ValueError(
            "Poucos dias com preço de abertura para separar a noite e o dia."
        )
    return tabela


def resumir_noite_e_dia(
    partes: pd.DataFrame, taxa_livre_de_risco: float = 0.0
) -> pd.DataFrame:
    """Uma linha por parte (Noite, Dia, Total): retorno composto, média diária, Sharpe e acertos."""
    total = (1 + partes["Noite"]) * (1 + partes["Dia"]) - 1
    linhas = {}
    for rotulo, serie in (
        ("Noite", partes["Noite"]),
        ("Dia", partes["Dia"]),
        ("Total", total),
    ):
        linhas[rotulo] = {
            "Retorno total": float((1 + serie).prod() - 1),
            "Média por dia": float(serie.mean()),
            "Índice de Sharpe": ind.calcular_indice_sharpe(serie, taxa_livre_de_risco),
            "Dias de alta": float((serie > 0).mean()),
        }
    return pd.DataFrame(linhas).T


def calcular_retorno_da_noite_com_custo(
    partes: pd.DataFrame, custo_por_operacao: float
) -> pd.Series:
    """Retorno de quem só fica comprado à noite: compra no fechamento, vende na abertura.

    Cada dia tem uma compra e uma venda, então o custo é cobrado duas vezes por dia.
    """
    if custo_por_operacao < 0:
        raise ValueError("O custo por operação não pode ser negativo.")
    return (1 + partes["Noite"]) * (1 - custo_por_operacao) ** 2 - 1


# --- Virada do mês ------------------------------------------------------------------------


def curvas_da_noite_e_do_dia(
    partes: pd.DataFrame, noite_com_custos: pd.Series
) -> dict[str, pd.Series]:
    """As quatro curvas de capital do experimento (R$ 1 no começo): o dia inteiro, só a noite,
    só o dia e só a noite pagando os custos de entrar e sair todo dia."""
    # a mesma ordem de contas de antes: muda o arredondamento na 16ª casa, não o número
    return {
        "Total (comprar e segurar)": (
            1 + (1 + partes["Noite"]) * (1 + partes["Dia"]) - 1
        ).cumprod(),
        "Só a noite": (1 + partes["Noite"]).cumprod(),
        "Só o dia": (1 + partes["Dia"]).cumprod(),
        "Só a noite, com custos": (1 + noite_com_custos).cumprod(),
    }


def marcar_virada_do_mes(
    indice: pd.DatetimeIndex, dias_antes: int = 1, dias_depois: int = 3
) -> pd.Series:
    """Verdadeiro nos últimos `dias_antes` pregões de cada mês e nos primeiros `dias_depois`.

    Meses cortados pelo início ou pelo fim dos dados não contam o lado que falta.
    """
    if dias_antes < 0 or dias_depois < 0 or dias_antes + dias_depois < 1:
        raise ValueError("Escolha pelo menos um dia na virada do mês.")
    if dias_antes + dias_depois > 15:
        raise ValueError("A virada do mês não pode passar de 15 dias.")
    meses = pd.Series(indice.to_period("M"), index=indice)
    posicao_no_mes = meses.groupby(meses).cumcount()
    posicao_do_fim = meses.groupby(meses).cumcount(ascending=False)
    primeiro_mes, ultimo_mes = meses.iloc[0], meses.iloc[-1]
    comeca_no_inicio = indice[0].day <= 5  # senão o primeiro mês chegou pela metade
    depois = (posicao_no_mes < dias_depois) & (
        (meses != primeiro_mes) | comeca_no_inicio
    )
    antes = (posicao_do_fim < dias_antes) & (meses != ultimo_mes)
    return (antes | depois).rename("virada")


def simular_virada_do_mes(
    fechamento: pd.Series,
    dias_antes: int = 1,
    dias_depois: int = 3,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
) -> tuple[ResultadoBacktest, pd.Series]:
    """Fica comprado só nos dias da virada do mês. Devolve o backtest e a máscara dos dias.

    O calendário é conhecido de antemão, então a posição de amanhã pode ser decidida hoje.
    """
    marcados = marcar_virada_do_mes(fechamento.index, dias_antes, dias_depois)
    desejada = posicao_da_virada(marcados)
    return executar_backtest(fechamento, desejada, custo_por_operacao), marcados


def posicao_da_virada(marcados: pd.Series) -> pd.Series:
    """A posição de cada dia (1 comprado, 0 fora): comprado hoje se amanhã é dia da virada.

    O calendário é conhecido de antemão, então a marca de amanhã já se sabe hoje (nenhum preço
    do futuro entra). Depois do último dia não há marca: fora.
    """
    return marcados.shift(-1, fill_value=False).astype(float)


def comparar_dentro_e_fora(
    retorno_do_ativo: pd.Series, marcados: pd.Series
) -> dict[str, float]:
    """Média diária dentro e fora da virada, e quanto do retorno composto veio de cada parte."""
    marcados = marcados.reindex(retorno_do_ativo.index, fill_value=False)
    dentro, fora = retorno_do_ativo[marcados], retorno_do_ativo[~marcados]
    if dentro.empty or fora.empty:
        raise ValueError("Não há dias suficientes dentro e fora da virada do mês.")
    return {
        "Dias dentro": float(len(dentro)),
        "Dias fora": float(len(fora)),
        "Média por dia (dentro)": float(dentro.mean()),
        "Média por dia (fora)": float(fora.mean()),
        "Retorno composto (dentro)": float((1 + dentro).prod() - 1),
        "Retorno composto (fora)": float((1 + fora).prod() - 1),
    }
