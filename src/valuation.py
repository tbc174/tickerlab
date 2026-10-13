"""Valuation sem preço-alvo (série 2 da base de ML, PR 5; ADRs 0032 e 0033).

- **Múltiplos contra o próprio histórico:** P/L e P/VP de cada ano, com o preço do último pregão do
  ano e o lucro e o patrimônio (dos controladores) por ação daquele ano; os percentis viram a régua
  do histórico do barato/justo/caro (`src/notas.py::preco`).
- **DCF com as premissas do usuário:** caixa livre de hoje crescendo a uma taxa por N anos, depois a
  perpetuidade, tudo descontado; menos a dívida líquida, dividido pelas ações. O número é do
  usuário: o TickerLab só faz a conta e mostra a **tabela de sensibilidade** (desconto × crescimento).
- **Valuation reverso:** o crescimento anual que o preço de hoje supõe, com as mesmas premissas
  (bissecção). Sem resposta (preço alto ou baixo demais para qualquer crescimento razoável): None.
"""

import math
from dataclasses import dataclass

import pandas as pd

from src.padroes import PERCENTIS

MINIMO_DE_ANOS = 3  # percentil do próprio histórico com menos que isso é ruído
CRESCIMENTO_MINIMO, CRESCIMENTO_MAXIMO = (
    -0.5,
    1.0,
)  # faixa da busca do valuation reverso
TOLERANCIA = 1e-7
PASSOS_MAXIMOS = 200


def _por_acao(valor: pd.Series, acoes: pd.Series) -> pd.Series:
    return valor / acoes.where(acoes > 0)


def _coluna(anual: pd.DataFrame, nome: str) -> pd.Series:
    """A coluna como números, ou vazia (NaN) se a empresa não tem essa conta."""
    if nome not in anual:
        return pd.Series(math.nan, index=anual.index, dtype=float)
    return anual[nome].astype(float)


def multiplos_do_historico(anual: pd.DataFrame, fechamentos: pd.Series) -> pd.DataFrame:
    """P/L e P/VP de cada ano (índice: ano), com o preço do último pregão até 31/12 daquele ano."""
    if anual.empty or fechamentos.empty:
        return pd.DataFrame(columns=["preco", "p_l", "p_vp"])
    fechamentos = fechamentos.sort_index()
    precos = {}
    for ano in anual.index:
        ate_o_fim = fechamentos[fechamentos.index <= pd.Timestamp(int(ano), 12, 31)]
        no_ano = ate_o_fim[ate_o_fim.index.year == int(ano)]
        precos[ano] = float(no_ano.iloc[-1]) if not no_ano.empty else math.nan
    preco = pd.Series(precos)
    lucro = _coluna(anual, "lucro_controladores")
    if lucro.isna().all():
        lucro = _coluna(anual, "lucro_liquido")
    pl = _coluna(anual, "patrimonio_liquido") - _coluna(anual, "minoritarios").fillna(0)
    acoes = _coluna(anual, "acoes_total") - _coluna(anual, "acoes_tesouraria").fillna(0)
    return pd.DataFrame(
        {
            "preco": preco,
            "p_l": preco / _por_acao(lucro, acoes),
            "p_vp": preco / _por_acao(pl, acoes),
        }
    )


def percentis_do_historico(
    serie: pd.Series, minimo: int = MINIMO_DE_ANOS
) -> dict[str, float] | None:
    """Os percentis dos múltiplos positivos do próprio histórico (None com menos de `minimo` anos)."""
    positivos = serie[(serie > 0) & serie.map(math.isfinite)].astype(float)
    if positivos.size < minimo:
        return None
    return {str(p): float(positivos.quantile(p / 100)) for p in PERCENTIS}


@dataclass(frozen=True)
class ResultadoDoDCF:
    fluxos: list[float]  # caixa livre de cada ano projetado (antes do desconto)
    valor_terminal: float  # na data do último ano projetado, antes do desconto
    valor_da_empresa: float  # tudo descontado a hoje
    valor_do_patrimonio: float  # empresa − dívida líquida
    valor_por_acao: float


def dcf(
    caixa_livre: float,
    crescimento: float,
    anos: int,
    desconto: float,
    perpetuidade: float,
    acoes: float,
    divida_liquida: float,
) -> ResultadoDoDCF:
    """Fluxo de caixa descontado com as premissas do usuário (taxas em fração: 0,10 = 10%)."""
    if desconto <= perpetuidade:
        raise ValueError(
            "O desconto precisa ser maior que o crescimento na perpetuidade (senão o valor é infinito)."
        )
    if acoes <= 0:
        raise ValueError("Quantidade de ações indisponível.")
    fluxos = [caixa_livre * (1 + crescimento) ** t for t in range(1, anos + 1)]
    presente = sum(f / (1 + desconto) ** t for t, f in enumerate(fluxos, start=1))
    terminal = fluxos[-1] * (1 + perpetuidade) / (desconto - perpetuidade)
    empresa = presente + terminal / (1 + desconto) ** anos
    patrimonio = empresa - divida_liquida
    return ResultadoDoDCF(fluxos, terminal, empresa, patrimonio, patrimonio / acoes)


def sensibilidade(
    caixa_livre: float,
    anos: int,
    perpetuidade: float,
    acoes: float,
    divida_liquida: float,
    descontos: tuple[float, ...],
    crescimentos: tuple[float, ...],
) -> pd.DataFrame:
    """Valor por ação para cada desconto (linhas) e crescimento (colunas); vazio onde não dá."""
    tabela = pd.DataFrame(
        index=list(descontos), columns=list(crescimentos), dtype=float
    )
    for desconto in descontos:
        for crescimento in crescimentos:
            if desconto > perpetuidade:
                tabela.loc[desconto, crescimento] = dcf(
                    caixa_livre,
                    crescimento,
                    anos,
                    desconto,
                    perpetuidade,
                    acoes,
                    divida_liquida,
                ).valor_por_acao
    return tabela


def crescimento_implicito(
    preco: float,
    caixa_livre: float,
    anos: int,
    desconto: float,
    perpetuidade: float,
    acoes: float,
    divida_liquida: float,
) -> float | None:
    """O crescimento anual que faz o DCF dar o preço de hoje (None se nenhum na faixa dá)."""

    def diferenca(crescimento: float) -> float:
        return (
            dcf(
                caixa_livre,
                crescimento,
                anos,
                desconto,
                perpetuidade,
                acoes,
                divida_liquida,
            ).valor_por_acao
            - preco
        )

    baixo, alto = CRESCIMENTO_MINIMO, CRESCIMENTO_MAXIMO
    if caixa_livre <= 0 or diferenca(baixo) > 0 or diferenca(alto) < 0:
        return None
    for _ in range(PASSOS_MAXIMOS):
        meio = (baixo + alto) / 2
        if diferenca(meio) > 0:
            alto = meio
        else:
            baixo = meio
        if alto - baixo < TOLERANCIA:
            break
    return (baixo + alto) / 2
