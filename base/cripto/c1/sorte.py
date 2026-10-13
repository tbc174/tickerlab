"""Teste contra a sorte do modelo C-1 (pré-registro v2, seção 8; ADR 0035).

O candidato **passa** só se cumprir as quatro condições, todas no período avaliado:

1. ganho sobre a régua (R2) maior que zero, com Diebold-Mariano unilateral (Newey-West de 30
   defasagens) e p < 0,05 **depois da correção de Holm** pelo número de tentativas do registro;
2. **embaralhamento em blocos:** as entradas que não são preço, embaralhadas em blocos de 90 dias,
   com o modelo refeito; o ganho real fica acima do percentil 95 dos ganhos embaralhados;
3. **estabilidade:** ganho positivo em pelo menos 2/3 dos anos (2 dos 3 do lacrado);
4. **calibração:** erro médio de calibração de no máximo 0,05.

O ganho é o *Brier skill score*: 1 − Brier do candidato / Brier da régua.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from base.cripto.c1.avaliacao import (
    Modelo,
    ResultadoWalkForward,
    calibracao,
    estabilidade_por_ano,
    walk_forward,
)
from base.cripto.c1.candidatos import COLUNAS_DE_VOLATILIDADE
from base.cripto.c1.entradas import COLUNAS, COLUNAS_DE_PRECO
from base.cripto.c1.medidas import brier, brier_por_linha

DEFASAGENS_DE_NEWEY_WEST = 30
NIVEL = 0.05
DIAS_DO_BLOCO = 90
PERCENTIL_DO_EMBARALHAMENTO = 95
FRACAO_MINIMA_DE_ANOS = 2 / 3
CALIBRACAO_MAXIMA = 0.05
# o embaralhamento mexe só no que não é preço (o preço é o que a régua já usa)
COLUNAS_EMBARALHADAS = [
    c for c in COLUNAS if c not in COLUNAS_DE_PRECO + COLUNAS_DE_VOLATILIDADE
]


@dataclass
class Veredito:
    """O resultado do teste contra a sorte, condição por condição."""

    ganho: float
    p_diebold_mariano: float
    p_com_holm: float
    percentil_do_embaralhamento: float
    ganho_por_ano: dict[int, float]
    erro_de_calibracao: float
    condicoes: dict[str, bool]

    @property
    def passou(self) -> bool:
        return all(self.condicoes.values())


def diebold_mariano(
    perda_do_candidato: np.ndarray,
    perda_da_regua: np.ndarray,
    defasagens: int = DEFASAGENS_DE_NEWEY_WEST,
) -> tuple[float, float]:
    """Estatística e p unilateral de "o candidato erra menos que a régua" (variância de Newey-West)."""
    diferenca = np.asarray(perda_do_candidato, dtype=float) - np.asarray(
        perda_da_regua, dtype=float
    )
    n = len(diferenca)
    centrado = diferenca - diferenca.mean()
    variancia = centrado @ centrado / n
    for defasagem in range(1, defasagens + 1):
        peso = 1 - defasagem / (defasagens + 1)
        variancia += 2 * peso * (centrado[defasagem:] @ centrado[:-defasagem]) / n
    estatistica = diferenca.mean() / np.sqrt(variancia / n)
    return float(estatistica), float(norm.cdf(estatistica))


def holm(p_valores: Sequence[float]) -> list[float]:
    """Os p corrigidos por Holm, na mesma ordem dos originais."""
    m = len(p_valores)
    ordem = np.argsort(p_valores)
    corrigidos = np.empty(m)
    maior_ate_aqui = 0.0
    for posicao, indice in enumerate(ordem):
        maior_ate_aqui = max(
            maior_ate_aqui, min(1.0, (m - posicao) * p_valores[indice])
        )
        corrigidos[indice] = maior_ate_aqui
    return corrigidos.tolist()


def embaralhar_em_blocos(
    quadro: pd.DataFrame,
    colunas: Sequence[str],
    tamanho_do_bloco: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """As `colunas` com os blocos de dias trocados de lugar (a ordem dentro do bloco fica)."""
    n = len(quadro)
    blocos = [
        np.arange(i, min(i + tamanho_do_bloco, n))
        for i in range(0, n, tamanho_do_bloco)
    ]
    nova_ordem = np.concatenate([blocos[i] for i in rng.permutation(len(blocos))])
    embaralhado = quadro.copy()
    embaralhado[list(colunas)] = quadro[list(colunas)].to_numpy()[nova_ordem]
    return embaralhado


def ganho(
    probabilidades: pd.DataFrame, da_regua: pd.DataFrame, classes: pd.Series
) -> float:
    """Brier skill score do candidato sobre a régua (maior que zero = melhor que a régua)."""
    return 1 - brier(probabilidades.to_numpy(), classes.to_numpy()) / brier(
        da_regua.to_numpy(), classes.to_numpy()
    )


def veredito(
    resultado: ResultadoWalkForward,
    candidato: str,
    regua: str,
    p_das_outras_tentativas: Sequence[float],
    quadro: pd.DataFrame,
    classes: pd.Series,
    fabrica_do_candidato: Callable[[], Modelo],
    rodadas: int,
    rng: np.random.Generator,
) -> Veredito:
    """As quatro condições da seção 8 do pré-registro para um candidato."""
    reais = resultado.classes
    do_candidato, da_regua = (
        resultado.probabilidades[candidato],
        resultado.probabilidades[regua],
    )
    perda_do_candidato = brier_por_linha(do_candidato.to_numpy(), reais.to_numpy())
    perda_da_regua = brier_por_linha(da_regua.to_numpy(), reais.to_numpy())

    ganho_real = ganho(do_candidato, da_regua, reais)
    _, p = diebold_mariano(perda_do_candidato, perda_da_regua)
    p_com_holm = holm([*p_das_outras_tentativas, p])[-1]
    embaralhados = _ganhos_embaralhados(
        resultado, quadro, classes, fabrica_do_candidato, da_regua, rodadas, rng
    )
    percentil = float(np.percentile(embaralhados, PERCENTIL_DO_EMBARALHAMENTO))
    por_ano = estabilidade_por_ano(
        pd.Series(perda_da_regua - perda_do_candidato, index=reais.index)
    )
    erro = calibracao(do_candidato.to_numpy(), reais.to_numpy())
    condicoes = {
        "ganho_com_holm": ganho_real > 0 and p_com_holm < NIVEL,
        "acima_do_embaralhamento": ganho_real > percentil,
        "estavel_nos_anos": np.mean([v > 0 for v in por_ano.values()])
        >= FRACAO_MINIMA_DE_ANOS,
        "calibrado": erro <= CALIBRACAO_MAXIMA,
    }
    return Veredito(ganho_real, p, p_com_holm, percentil, por_ano, erro, condicoes)


def _ganhos_embaralhados(
    resultado: ResultadoWalkForward,
    quadro: pd.DataFrame,
    classes: pd.Series,
    fabrica: Callable[[], Modelo],
    da_regua: pd.DataFrame,
    rodadas: int,
    rng: np.random.Generator,
) -> list[float]:
    assert resultado.inicio is not None and resultado.fim is not None
    ganhos = []
    for _ in range(rodadas):
        embaralhado = embaralhar_em_blocos(
            quadro, COLUNAS_EMBARALHADAS, DIAS_DO_BLOCO, rng
        )
        refeito = walk_forward(
            embaralhado,
            classes,
            {"candidato": fabrica},
            resultado.inicio,
            resultado.fim,
            resultado.meses_entre_treinos,
        )
        ganhos.append(
            ganho(refeito.probabilidades["candidato"], da_regua, refeito.classes)
        )
    return ganhos
