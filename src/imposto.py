"""Imposto de renda simplificado sobre as operações do backtest (ações na B3, swing trade).

Regras usadas (simplificadas; NÃO são orientação tributária, confira na Receita Federal e na B3):
- 15% sobre o lucro líquido do mês;
- isento quando o total vendido no mês é de até R$ 20 mil;
- prejuízo de um mês abate o lucro dos meses seguintes;
- só operações já encerradas pagam imposto (lucro de operação aberta ainda não foi realizado);
- o imposto sai do capital no último dia de negociação do mês da venda.

Fica de fora: day trade (20%, sem isenção), IR retido na fonte, custos dedutíveis, dividendos e
ativos de fora do Brasil. O valor de cada operação usa a fração do capital que estava aplicada
no dia da entrada.
"""

from dataclasses import dataclass, replace

import pandas as pd

from src import regras_de_imposto
from src.backtest import ResultadoBacktest

# as regras com a fonte oficial ficam em src/regras_de_imposto.py (as mesmas das ferramentas do site)
ALIQUOTA_SWING_TRADE = float(regras_de_imposto.valor("aliquota_comum"))
ISENCAO_MENSAL_PADRAO = float(regras_de_imposto.valor("isencao_vendas_no_mes"))

COLUNAS_MENSAIS = [
    "Mês",
    "Lucro ou prejuízo (R$)",
    "Vendas (R$)",
    "Imposto (R$)",
    "Prejuízo a compensar (R$)",
]


@dataclass(frozen=True)
class ResultadoDoImposto:
    resultado: ResultadoBacktest  # o mesmo backtest, com retorno e capital já líquidos
    meses: pd.DataFrame  # uma linha por mês com vendas encerradas
    imposto_total: float  # em R$


def _dia_da_venda(posicao: pd.Series, saida: pd.Timestamp) -> pd.Timestamp:
    """A operação vai até `saida` (último dia com posição); a venda é no dia seguinte."""
    local = posicao.index.get_loc(saida)
    return posicao.index[min(local + 1, len(posicao) - 1)]


def aplicar_imposto(
    resultado: ResultadoBacktest,
    capital_inicial: float,
    aliquota: float = ALIQUOTA_SWING_TRADE,
    isencao_mensal: float = ISENCAO_MENSAL_PADRAO,
) -> ResultadoDoImposto:
    """Desconta o imposto das operações encerradas e devolve o backtest com retornos líquidos."""
    if capital_inicial <= 0:
        raise ValueError("O capital inicial deve ser maior que zero.")
    if not 0 <= aliquota < 1:
        raise ValueError("A alíquota deve ficar entre 0 e 1.")
    if isencao_mensal < 0:
        raise ValueError("A isenção mensal não pode ser negativa.")

    posicao = resultado.posicao
    operacoes = resultado.operacoes[~resultado.operacoes["aberta"]]
    liquido = resultado.retorno.copy()
    linhas = []
    prejuizo_a_compensar = 0.0

    if operacoes.empty:
        return ResultadoDoImposto(resultado, pd.DataFrame(columns=COLUNAS_MENSAIS), 0.0)

    vendas = pd.DataFrame(
        {
            "operacao": operacoes.index,
            "venda": [_dia_da_venda(posicao, s) for s in operacoes["saida"]],
        }
    )
    vendas["mes"] = vendas["venda"].dt.to_period("M")

    for mes, do_mes in vendas.groupby("mes", sort=True):
        lucro = volume = 0.0
        # o capital no dia da entrada já considera os impostos pagos antes
        capital = capital_inicial * (1 + liquido).cumprod()
        for _, linha in do_mes.iterrows():
            operacao = operacoes.loc[linha["operacao"]]
            local = capital.index.get_loc(operacao["entrada"])
            capital_antes = capital_inicial if local == 0 else capital.iloc[local - 1]
            aplicado = capital_antes * posicao.loc[operacao["entrada"]]
            lucro += aplicado * operacao["retorno"]
            volume += aplicado * (1 + operacao["retorno"])

        imposto = 0.0
        if volume <= isencao_mensal:
            if lucro < 0:
                prejuizo_a_compensar += -lucro
        else:
            liquido_do_mes = lucro - prejuizo_a_compensar
            if liquido_do_mes > 0:
                imposto = aliquota * liquido_do_mes
                prejuizo_a_compensar = 0.0
            else:
                prejuizo_a_compensar = -liquido_do_mes

        if imposto > 0:
            ultimo_dia = capital.index[capital.index.to_period("M") == mes][-1]
            capital_do_dia = capital.loc[ultimo_dia]
            # o imposto entra como uma "perda" no último dia do mês
            liquido.loc[ultimo_dia] = (1 + liquido.loc[ultimo_dia]) * (
                1 - imposto / capital_do_dia
            ) - 1
        linhas.append(
            {
                "Mês": str(mes),
                "Lucro ou prejuízo (R$)": lucro,
                "Vendas (R$)": volume,
                "Imposto (R$)": imposto,
                "Prejuízo a compensar (R$)": prejuizo_a_compensar,
            }
        )

    meses = pd.DataFrame(linhas, columns=COLUNAS_MENSAIS)
    novo = replace(resultado, retorno=liquido, curva_de_capital=(1 + liquido).cumprod())
    return ResultadoDoImposto(novo, meses, float(meses["Imposto (R$)"].sum()))
