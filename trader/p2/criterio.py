"""O critério da Pesquisa 2 em código (pré-registro v0.1, seção 7). Todos os itens precisam passar.

Convenções fixadas aqui, antes de qualquer resultado:
- retornos diários líquidos da carteira, em dias úteis, anualizados com 252 (como na M2);
- avaliação de 01/01/1980 a 08/09/2023 (o aquecimento das regras usa os anos anteriores);
- **participação** de um mercado (A7) ou grupo (A8) = soma do retorno dele ÷ soma do retorno da
  carteira; se a carteira não ganhou nada, os dois itens reprovam;
- **A6** conta só os mercados que chegaram a ter posição;
- **A10**: as posições de todos os mercados são deslocadas juntas no tempo (1.000 sorteios,
  semente fixa) e a carteira é refeita com os mesmos custos;
- **A1/A9**: o Sharpe deflacionado estima a sorte pela dispersão dos Sharpes das configurações
  rodadas (K1, K2, B0, B1), como na M2. Consequência conhecida: se o candidato for muito melhor
  que as réguas, a dispersão cresce e a exigência também;
- **V1** (olhar o futuro): a mesma carteira usando a posição do próprio dia precisa render um Sharpe
  pelo menos **0,5 maior** que a normal; senão o teste está quebrado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import acaso
from trader import avaliacao
from trader.criterio import Item, Veredito
from trader.validacao import bootstrap_diferenca_de_sharpe

INICIO_DA_AVALIACAO = pd.Timestamp("1980-01-01")
FIM_DA_AVALIACAO = pd.Timestamp("2023-09-08")
DECADAS = (
    ("1980–89", "1980-01-01", "1989-12-31"),
    ("1990–99", "1990-01-01", "1999-12-31"),
    ("2000–09", "2000-01-01", "2009-12-31"),
    ("2010–23", "2010-01-01", "2023-09-08"),
)
DSR_MINIMO = 0.95  # A1
DECADAS_POSITIVAS_MINIMAS = 3  # A2 (inclusive a última)
T_MINIMO = 3.0  # A3
FRACAO_DE_ANOS_POSITIVOS_MINIMA = 0.60  # A4
FRACAO_DE_MERCADOS_POSITIVOS_MINIMA = 0.60  # A6
PARTICIPACAO_MAXIMA_DO_MERCADO = 0.25  # A7
PARTICIPACAO_MAXIMA_DO_GRUPO = 0.50  # A8
DSR_MINIMO_NO_ESTRESSE = 0.90  # A9
P_VALOR_MAXIMO_DO_ACASO = 0.05  # A10
GANHO_MINIMO_DO_FUTURO = 0.5  # V1
CONFIANCA_DO_MINTRL = 0.95  # C


def recortar_avaliacao[T: (pd.Series, pd.DataFrame)](dados: T) -> T:
    return dados.loc[
        (dados.index >= INICIO_DA_AVALIACAO) & (dados.index <= FIM_DA_AVALIACAO)
    ]


@dataclass
class Evidencia:
    """Tudo o que o critério precisa, já recortado no período de avaliação."""

    candidato: pd.Series  # K2, custos base
    por_mercado: pd.DataFrame  # contribuição diária de cada mercado (K2, base)
    grupo_do_mercado: dict[str, str]
    b1: pd.Series  # régua, custos base
    candidatos: pd.DataFrame  # K1, K2, B0, B1 (base), para o DSR
    candidatos_a: pd.DataFrame  # os mesmos no estresse A
    candidatos_b: pd.DataFrame  # os mesmos no estresse B
    tentativas_totais: int  # 101 da M2 + as da Pesquisa 2
    p_valor_do_acaso: float
    sharpe_olhando_o_futuro: float
    reexecucao_identica: bool
    dados_conforme_0014: bool = True
    extras: dict = field(default_factory=dict)


def _sharpe(r: pd.Series) -> float:
    return avaliacao.sharpe(r)


def _dsr(retorno: pd.Series, candidatos: pd.DataFrame, tentativas_totais: int) -> float:
    extras = max(0, tentativas_totais - candidatos.shape[1])
    return acaso.calcular_sharpe_deflacionado(
        retorno, candidatos, tentativas_extras=extras
    ).probabilidade


def _participacao_maxima(contribuicao: pd.DataFrame, total: float) -> tuple[float, str]:
    if total <= 0:
        return float("inf"), ""
    soma = contribuicao.sum()
    return float(soma.max() / total), str(soma.idxmax())


def avaliar(e: Evidencia) -> Veredito:
    r = e.candidato
    itens: list[Item] = []

    dsr = _dsr(r, e.candidatos, e.tentativas_totais)
    itens.append(
        Item(
            "A1",
            "Sharpe deflacionado (todas as tentativas)",
            dsr,
            f">= {DSR_MINIMO}",
            dsr >= DSR_MINIMO,
        )
    )

    por_decada = {nome: _sharpe(r.loc[ini:fim]) for nome, ini, fim in DECADAS}
    positivas = sum(v > 0 for v in por_decada.values())
    ultima_positiva = por_decada[DECADAS[-1][0]] > 0
    itens.append(
        Item(
            "A2",
            "décadas com Sharpe > 0 (inclusive 2010–23)",
            float(positivas),
            f">= {DECADAS_POSITIVAS_MINIMAS} de 4 e a última",
            positivas >= DECADAS_POSITIVAS_MINIMAS and ultima_positiva,
        )
    )

    t = avaliacao.t_estatistica(r)
    itens.append(
        Item(
            "A3", "t-estatística do retorno diário", t, f">= {T_MINIMO}", t >= T_MINIMO
        )
    )

    anos = avaliacao.fracao_de_anos_positivos(r)
    itens.append(
        Item(
            "A4",
            "anos civis com retorno > 0",
            anos,
            f">= {FRACAO_DE_ANOS_POSITIVOS_MINIMA}",
            anos >= FRACAO_DE_ANOS_POSITIVOS_MINIMA,
        )
    )

    contra_b1 = bootstrap_diferenca_de_sharpe(r, e.b1)
    itens.append(
        Item(
            "A5",
            "contra a B1: limite inferior de 90% da diferença de Sharpe",
            contra_b1["ic90_inferior"],
            "> 0",
            contra_b1["ic90_inferior"] > 0,
        )
    )

    operados = e.por_mercado.loc[:, (e.por_mercado != 0).any()]
    fracao = float((operados.sum() > 0).mean()) if operados.shape[1] else 0.0
    itens.append(
        Item(
            "A6",
            "mercados com contribuição positiva",
            fracao,
            f">= {FRACAO_DE_MERCADOS_POSITIVOS_MINIMA}",
            fracao >= FRACAO_DE_MERCADOS_POSITIVOS_MINIMA,
        )
    )

    total = float(r.sum())
    maior_mercado, qual = _participacao_maxima(e.por_mercado, total)
    itens.append(
        Item(
            "A7",
            f"maior participação de um mercado ({qual})",
            maior_mercado,
            f"<= {PARTICIPACAO_MAXIMA_DO_MERCADO}",
            maior_mercado <= PARTICIPACAO_MAXIMA_DO_MERCADO,
        )
    )
    por_grupo = e.por_mercado.T.groupby(e.grupo_do_mercado).sum().T
    maior_grupo, grupo = _participacao_maxima(por_grupo, total)
    itens.append(
        Item(
            "A8",
            f"maior participação de um grupo ({grupo})",
            maior_grupo,
            f"<= {PARTICIPACAO_MAXIMA_DO_GRUPO}",
            maior_grupo <= PARTICIPACAO_MAXIMA_DO_GRUPO,
        )
    )

    estresses = {}
    for nome, tabela in (("A", e.candidatos_a), ("B", e.candidatos_b)):
        sharpe = _sharpe(tabela["K2"])
        estresses[nome] = (sharpe, _dsr(tabela["K2"], tabela, e.tentativas_totais))
    passou_a9 = all(
        s > 0 and d >= DSR_MINIMO_NO_ESTRESSE for s, d in estresses.values()
    )
    itens.append(
        Item(
            "A9",
            "estresses A e B: Sharpe e DSR",
            min(s for s, _ in estresses.values()),
            "Sharpe > 0 e DSR >= 0.9 (DSR: "
            + ", ".join(f"{k} {d:.3f}" for k, (_, d) in estresses.items())
            + ")",
            passou_a9,
        )
    )

    itens.append(
        Item(
            "A10",
            "contra o acaso: p-valor",
            e.p_valor_do_acaso,
            f"<= {P_VALOR_MAXIMO_DO_ACASO}",
            e.p_valor_do_acaso <= P_VALOR_MAXIMO_DO_ACASO,
        )
    )

    infla = e.sharpe_olhando_o_futuro >= _sharpe(r) + GANHO_MINIMO_DO_FUTURO
    v_ok = infla and e.reexecucao_identica and e.dados_conforme_0014
    itens.append(
        Item(
            "V",
            "verificações (futuro infla, reexecução, dados)",
            e.sharpe_olhando_o_futuro,
            f"futuro >= normal + {GANHO_MINIMO_DO_FUTURO}; reexecução idêntica",
            v_ok,
        )
    )

    minimo = acaso.calcular_comprimento_minimo(r, CONFIANCA_DO_MINTRL)
    curto = not np.isfinite(minimo) or len(r) < minimo
    return Veredito(
        itens=itens,
        inconclusivo=curto and all(i.passou for i in itens),
        motivo_inconclusivo="amostra menor que o MinTRL" if curto else "",
    )


def p_valor_do_acaso(
    posicoes: pd.DataFrame,
    retornos: pd.DataFrame,
    custo_por_lado: pd.Series,
    margem_ao_ano: pd.Series,
    dias: pd.Series,
    sorteios: int = 1000,
    semente: int = 42,
) -> dict:
    """A10: desloca as posições de todos os mercados juntas no tempo e refaz a carteira."""
    r = retornos.fillna(0.0).to_numpy(dtype=float)
    p = posicoes.fillna(0.0).to_numpy(dtype=float)
    custo = custo_por_lado.reindex(posicoes.columns).to_numpy(dtype=float)
    margem = margem_ao_ano.reindex(posicoes.columns).to_numpy(dtype=float)
    fracao_do_ano = (dias.to_numpy(dtype=float) / 365.0)[:, None]

    def sharpe(desejada: np.ndarray) -> float:
        ontem = np.vstack([np.zeros((1, desejada.shape[1])), desejada[:-1]])
        giro = np.abs(np.diff(desejada, axis=0, prepend=0.0))
        diario = (
            ontem * r - giro * custo - np.abs(ontem) * margem * fracao_do_ano
        ).sum(axis=1)
        desvio = diario.std(ddof=1)
        return float(diario.mean() / desvio * np.sqrt(252)) if desvio > 0 else np.nan

    real = sharpe(p)
    n = len(p)
    folga = max(21, n // 10)
    deslocamentos = np.random.default_rng(semente).integers(
        folga, n - folga, size=sorteios
    )
    sorteados = np.array([sharpe(np.roll(p, int(k), axis=0)) for k in deslocamentos])
    sorteados = sorteados[~np.isnan(sorteados)]
    return {
        "sharpe_real": real,
        "percentil_95": float(np.percentile(sorteados, 95)),
        "p_valor": float((1 + (sorteados >= real).sum()) / (1 + len(sorteados))),
    }
