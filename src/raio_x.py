"""O Raio-X do choque para qualquer pregão (plano `2026-10-28-raio-x-todo-dia`, PR 6; linha 444 da fila).

Leva para o código o estudo de 26/10/2026 (o circuit breaker do dia seguinte ao 2º turno), que saiu da
pasta privada: o tamanho da queda, os setores, a queda contra a dívida de cada empresa, os betas e os
choques anteriores do Ibovespa. Em dia de evento (`src/eventos_do_pregao.py`) o Raio-X sai como
rascunho, esperando o "pode" do Tiago.

Entradas (o gerador lê o acervo; aqui só se faz conta):

- `empresas`: a tabela do pregão (`pregao_do_dia.variacoes_das_empresas`), um papel por empresa;
- `balancos`: dívida líquida e EBITDA por CNPJ, com a data em que cada balanço ficou público
  (`divulgado_em`); só entra o que já era público na véspera;
- a série do Ibovespa (estatísticas do índice da B3) e, para os betas, os retornos de cada papel e
  de cada fator (Ibovespa, dólar, juros).

A saída é um `dict` de tipos simples, sem NaN (vazio vira None). Variações são frações. O Raio-X
descreve o que aconteceu no dia; não diz o que vem depois.
"""

import math
from datetime import date

import pandas as pd

from src import pregao_do_dia

# Queda de 30% ou mais num dia: a contagem que a página de 26/10 destacou (35 de 120 empresas).
QUEDA_FORTE = -0.30
MAIORES_QUEDAS = 12
MAIORES_ALTAS = 6
# Bancos, seguradoras e financeiras não têm EBITDA comparável: ficam fora da conta da dívida.
SETORES_FINANCEIROS = r"Banco|Intermedia|Seguro|Financ|Arrend"
CAIXA_MAIOR_QUE_A_DIVIDA = "Caixa maior que a dívida"
# (teto da dívida líquida / EBITDA, nome da faixa), em ordem; acima do último teto, a última faixa.
FAIXAS_DE_ALAVANCAGEM = (
    (1.0, "Até 1x"),
    (2.0, "1x a 2x"),
    (3.0, "2x a 3x"),
    (4.0, "3x a 4x"),
)
ACIMA_DE_4X = "Acima de 4x"
ORDEM_DAS_FAIXAS = (
    CAIXA_MAIOR_QUE_A_DIVIDA,
    *(nome for _, nome in FAIXAS_DE_ALAVANCAGEM),
    ACIMA_DE_4X,
)
# Para a dívida das empresas com caixa líquido entrar na correlação abaixo de qualquer alavancagem.
POSTO_DO_CAIXA_LIQUIDO = -1.0
# Correlação de postos com menos pontos que isto não diz nada.
MINIMO_PARA_CORRELACAO = 10
# Choque do Ibovespa: queda de 7% ou mais num dia (16 pregões de 2001 a 2020 na série da B3, em 5 anos).
QUEDA_DO_CHOQUE = -0.07
PREGOES_DEPOIS = {"1 mês": 21, "3 meses": 63, "6 meses": 126, "12 meses": 252}
# Beta: os pregões dos 12 meses até a véspera; com menos que isto, fica vazio.
MINIMO_DE_PREGOES = 120
JANELA_DO_BETA = pd.DateOffset(years=1)

FONTE_DO_BALANCO = "CVM, demonstrações financeiras (ITR e DFP) divulgadas até a véspera"
FONTES = {
    "acoes": pregao_do_dia.FONTE_DAS_ACOES,
    "setores": pregao_do_dia.FONTE_DOS_SETORES,
    "indice": pregao_do_dia.FONTE_DO_INDICE,
    "alavancagem": FONTE_DO_BALANCO,
}


def _numero(valor: float) -> float | None:
    return None if valor is None or math.isnan(valor) else float(valor)


def queda_do_dia(empresas: pd.DataFrame) -> dict[str, object]:
    """Quantas empresas líquidas, a mediana do dia e quantas subiram ou caíram `QUEDA_FORTE` ou mais."""
    variacao = pregao_do_dia.liquidas(empresas)["variacao"]
    return {
        "empresas": len(variacao),
        "mediana": _numero(variacao.median()),
        "subiram": int((variacao > 0).sum()),
        "cairam": int((variacao < 0).sum()),
        "quedas_fortes": int((variacao <= QUEDA_FORTE).sum()),
        "limite_da_queda_forte": QUEDA_FORTE,
    }


def setores_do_choque(
    empresas: pd.DataFrame, variacao_do_indice: float
) -> list[dict[str, object]]:
    """A mediana de cada setor contra o índice, do setor que mais caiu ao que menos caiu."""
    return sorted(
        pregao_do_dia.setores_contra_o_indice(empresas, variacao_do_indice),
        key=lambda setor: setor["mediana"],
    )


# --- a dívida ------------------------------------------------------------------------------------


def faixa_de_alavancagem(divida_liquida: float, ebitda: float) -> str | None:
    """A faixa da dívida líquida / EBITDA; None quando a conta não faz sentido (EBITDA zero ou
    negativo com dívida, ou número que falta)."""
    if math.isnan(divida_liquida) or math.isnan(ebitda):
        return None
    if divida_liquida < 0:
        return CAIXA_MAIOR_QUE_A_DIVIDA
    if ebitda <= 0:
        return None
    vezes = divida_liquida / ebitda
    return next(
        (nome for teto, nome in FAIXAS_DE_ALAVANCAGEM if vezes <= teto), ACIMA_DE_4X
    )


def _publicos_na_vespera(balancos: pd.DataFrame, vespera: date) -> pd.DataFrame:
    """O último balanço de cada CNPJ que já era público na véspera."""
    divulgado = pd.to_datetime(balancos["divulgado_em"])
    publicos = balancos[divulgado <= pd.Timestamp(vespera)]
    return publicos.sort_values("divulgado_em").drop_duplicates("cnpj", keep="last")


def _spearman(x: pd.Series, y: pd.Series) -> float | None:
    if len(x) < MINIMO_PARA_CORRELACAO:
        return None
    return _numero(x.rank().corr(y.rank()))


def queda_por_alavancagem(
    empresas: pd.DataFrame, balancos: pd.DataFrame, vespera: date
) -> dict[str, object]:
    """A mediana do dia por faixa de dívida líquida / EBITDA, só das empresas não financeiras, e a
    correlação de postos entre a alavancagem e a variação."""
    liquidas = pregao_do_dia.liquidas(empresas)
    nao_financeiras = liquidas[
        ~liquidas["setor"].str.contains(SETORES_FINANCEIROS, regex=True)
    ]
    juntas = nao_financeiras.merge(_publicos_na_vespera(balancos, vespera), on="cnpj")
    juntas = juntas.assign(
        faixa=[
            faixa_de_alavancagem(float(d), float(e))
            for d, e in zip(juntas["divida_liquida"], juntas["ebitda"], strict=True)
        ]
    ).dropna(subset=["faixa"])
    vezes = (juntas["divida_liquida"] / juntas["ebitda"]).where(
        juntas["divida_liquida"] >= 0, POSTO_DO_CAIXA_LIQUIDO
    )
    por_faixa = juntas.groupby("faixa")["variacao"].agg(["size", "median"])
    return {
        "empresas": len(juntas),
        "faixas": [
            {
                "faixa": faixa,
                "empresas": int(por_faixa.at[faixa, "size"]),
                "mediana": float(por_faixa.at[faixa, "median"]),
            }
            for faixa in ORDEM_DAS_FAIXAS
            if faixa in por_faixa.index
        ],
        "spearman": _spearman(vezes, juntas["variacao"]),
    }


# --- betas ---------------------------------------------------------------------------------------


def beta(retornos: pd.Series, fator: pd.Series, vespera: date) -> float | None:
    """Beta dos retornos diários do papel contra um fator (Ibovespa, dólar, juros), nos 12 meses até
    a véspera. O pregão estudado e os de depois não entram."""
    fim = pd.Timestamp(vespera)
    juntos = pd.DataFrame({"papel": retornos, "fator": fator}).dropna()
    juntos = juntos[(juntos.index > fim - JANELA_DO_BETA) & (juntos.index <= fim)]
    if len(juntos) <= MINIMO_DE_PREGOES:
        return None
    return _numero(juntos["papel"].cov(juntos["fator"]) / juntos["fator"].var())


# --- choques anteriores --------------------------------------------------------------------------


def choques_anteriores(
    ibovespa: pd.Series, dia: date, queda: float = QUEDA_DO_CHOQUE
) -> list[dict[str, object]]:
    """Os pregões antes de `dia` em que o Ibovespa caiu `queda` ou mais, e o que o índice fez depois
    de cada um. Só a série até `dia` entra: um prazo que passa de `dia` fica None."""
    serie = ibovespa.sort_index().loc[: pd.Timestamp(dia)].dropna()
    variacao = serie.pct_change()
    anteriores = variacao[(variacao <= queda) & (variacao.index < pd.Timestamp(dia))]
    choques = []
    for quando, tamanho in anteriores.items():
        i = serie.index.get_loc(quando)
        choques.append(
            {
                "dia": pd.Timestamp(quando).date().isoformat(),
                "queda": float(tamanho),
                "depois": {
                    prazo: (
                        float(serie.iloc[i + n] / serie.iloc[i] - 1)
                        if i + n < len(serie)
                        else None
                    )
                    for prazo, n in PREGOES_DEPOIS.items()
                },
            }
        )
    return choques


# --- o Raio-X ------------------------------------------------------------------------------------


def _variacao_do_indice(ibovespa: pd.Series, dia: date, vespera: date) -> float:
    return float(ibovespa[pd.Timestamp(dia)] / ibovespa[pd.Timestamp(vespera)] - 1)


def raio_x_do_pregao(
    dia: date,
    vespera: date,
    empresas: pd.DataFrame,
    ibovespa: pd.Series,
    balancos: pd.DataFrame | None = None,
) -> dict[str, object]:
    """O Raio-X do pregão `dia`, em tipos simples. Sem `balancos`, a parte da dívida fica None."""
    variacao_do_indice = _variacao_do_indice(ibovespa, dia, vespera)
    quedas = pregao_do_dia.maiores_altas_e_quedas(empresas, MAIORES_QUEDAS)["quedas"]
    altas = pregao_do_dia.maiores_altas_e_quedas(empresas, MAIORES_ALTAS)["altas"]
    return {
        "pregao": dia.isoformat(),
        "vespera": vespera.isoformat(),
        "ibovespa": {"variacao": variacao_do_indice},
        "queda": queda_do_dia(empresas),
        "setores": setores_do_choque(empresas, variacao_do_indice),
        "maiores": {"quedas": quedas, "altas": altas},
        "alavancagem": (
            None
            if balancos is None
            else queda_por_alavancagem(empresas, balancos, vespera)
        ),
        "choques_anteriores": choques_anteriores(ibovespa, dia),
        "fontes": {chave: {"fonte": fonte} for chave, fonte in FONTES.items()},
    }
