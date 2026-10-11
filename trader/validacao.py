"""Validação da M2: CPCV (validação cruzada purgada combinatória) e bootstrap em blocos.

Critério v0.1, seção 5A: 10 grupos de datas, 2 de teste por vez, expurgo e embargo de 21 pregões
→ C(10, 2) = 45 divisões e 9 caminhos de backtest.

**Como funciona o CPCV (López de Prado):** as datas do desenvolvimento são cortadas em 10 grupos
seguidos. Em cada divisão, 2 grupos são teste e os outros 8 são treino. Do treino saem:
- o **expurgo**: as datas logo ANTES de cada bloco de teste cujo rótulo (que olha até 21 pregões à
  frente) cairia dentro do teste;
- o **embargo**: as datas logo DEPOIS de cada bloco de teste, porque o que acontece no teste ainda
  "contamina" os dias seguintes (volatilidade, médias móveis).
Cada grupo é teste em 9 divisões. O caminho j junta, para cada grupo, a j-ésima divisão em que ele
foi teste: são 9 históricos completos fora da amostra, em vez de um só.

**Bootstrap em blocos:** para comparar dois Sharpes sem fingir que os dias são independentes,
sorteia blocos de 21 dias seguidos (os mesmos dias para as duas séries) e refaz a diferença
milhares de vezes. O intervalo de 90% vai do percentil 5 ao 95.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb

import numpy as np
import pandas as pd

N_GRUPOS = 10
K_TESTE = 2
EXPURGO = 21
EMBARGO = 21
BLOCO_DO_BOOTSTRAP = 21
SORTEIOS_DO_BOOTSTRAP = 5000


@dataclass(frozen=True)
class Divisao:
    numero: int
    grupos_de_teste: tuple[int, ...]
    treino: pd.DatetimeIndex
    teste: pd.DatetimeIndex


class CPCV:
    """Uso: `cpcv = CPCV(); for d in cpcv.divisoes(datas): treina em d.treino, testa em d.teste`."""

    def __init__(
        self,
        n_grupos: int = N_GRUPOS,
        k_teste: int = K_TESTE,
        expurgo: int = EXPURGO,
        embargo: int = EMBARGO,
    ) -> None:
        if not 1 <= k_teste < n_grupos:
            raise ValueError("Precisa de 1 <= grupos de teste < grupos.")
        if expurgo < 0 or embargo < 0:
            raise ValueError("Expurgo e embargo não podem ser negativos.")
        self.n_grupos, self.k_teste = n_grupos, k_teste
        self.expurgo, self.embargo = expurgo, embargo
        self._combinacoes = list(combinations(range(n_grupos), k_teste))

    @property
    def n_divisoes(self) -> int:
        return comb(self.n_grupos, self.k_teste)

    @property
    def n_caminhos(self) -> int:
        """Cada grupo é teste em C(N-1, k-1) divisões: esse é o número de caminhos."""
        return comb(self.n_grupos - 1, self.k_teste - 1)

    def grupos(self, datas: pd.DatetimeIndex) -> list[pd.DatetimeIndex]:
        datas = pd.DatetimeIndex(sorted(set(datas)))
        if len(datas) < self.n_grupos * (self.expurgo + self.embargo + 1):
            raise ValueError(
                "Poucas datas para esse número de grupos com expurgo e embargo."
            )
        return [datas[p] for p in np.array_split(np.arange(len(datas)), self.n_grupos)]

    def divisoes(self, datas: pd.DatetimeIndex) -> list[Divisao]:
        """As 45 divisões (treino e teste), com expurgo e embargo aplicados ao treino."""
        todas = pd.DatetimeIndex(sorted(set(datas)))
        grupos = self.grupos(todas)
        posicao = {d: i for i, d in enumerate(todas)}
        resultado = []
        for numero, combinacao in enumerate(self._combinacoes):
            teste = grupos[combinacao[0]].append([grupos[g] for g in combinacao[1:]])
            fora = np.zeros(len(todas), dtype=bool)
            for g in combinacao:
                inicio, fim = posicao[grupos[g][0]], posicao[grupos[g][-1]]
                fora[max(0, inicio - self.expurgo) : fim + 1 + self.embargo] = True
            treino = todas[~fora]
            resultado.append(Divisao(numero, combinacao, treino, teste.sort_values()))
        return resultado

    def caminhos(self) -> list[dict[int, int]]:
        """Para cada caminho, {grupo: número da divisão que fornece o teste desse grupo}."""
        por_grupo: dict[int, list[int]] = {g: [] for g in range(self.n_grupos)}
        for numero, combinacao in enumerate(self._combinacoes):
            for g in combinacao:
                por_grupo[g].append(numero)
        return [
            {g: por_grupo[g][j] for g in range(self.n_grupos)}
            for j in range(self.n_caminhos)
        ]

    def montar_caminhos(
        self, datas: pd.DatetimeIndex, retornos_por_divisao: dict[int, pd.Series]
    ) -> list[pd.Series]:
        """Junta os retornos fora da amostra de cada divisão nos 9 caminhos completos.

        `retornos_por_divisao[n]` traz o retorno da estratégia nas datas de teste da divisão n
        (pode ser a carteira inteira). Cada caminho cobre todas as datas uma vez só.
        """
        grupos = self.grupos(datas)
        faltando = set(range(self.n_divisoes)) - set(retornos_por_divisao)
        if faltando:
            raise ValueError(
                f"Faltam os retornos das divisões {sorted(faltando)[:5]}..."
            )
        caminhos = []
        for mapa in self.caminhos():
            pedacos = [
                retornos_por_divisao[mapa[g]].reindex(grupos[g])
                for g in range(self.n_grupos)
            ]
            caminhos.append(pd.concat(pedacos))
        return caminhos


def _sharpe(r: np.ndarray, dias_por_ano: int) -> float:
    desvio = r.std(ddof=1)
    return float(r.mean() / desvio * np.sqrt(dias_por_ano)) if desvio > 0 else np.nan


def bootstrap_diferenca_de_sharpe(
    candidato: pd.Series,
    referencia: pd.Series,
    bloco: int = BLOCO_DO_BOOTSTRAP,
    sorteios: int = SORTEIOS_DO_BOOTSTRAP,
    semente: int = 0,
    dias_por_ano: int = 252,
) -> dict:
    """Sharpe(candidato) - Sharpe(referência), com intervalo de 90% por bootstrap em blocos.

    Só usa as datas em que as duas séries existem; sorteia os MESMOS blocos para as duas.
    """
    juntos = pd.concat({"a": candidato, "b": referencia}, axis=1).dropna()
    n = len(juntos)
    if n < 2 * bloco:
        raise ValueError("Poucos dias em comum para o bootstrap.")
    a, b = juntos["a"].to_numpy(), juntos["b"].to_numpy()
    gerador = np.random.default_rng(semente)
    blocos_por_amostra = int(np.ceil(n / bloco))
    diferencas = np.empty(sorteios)
    for i in range(sorteios):
        inicios = gerador.integers(0, n, blocos_por_amostra)
        indices = ((inicios[:, None] + np.arange(bloco)) % n).ravel()[
            :n
        ]  # blocos circulares
        diferencas[i] = _sharpe(a[indices], dias_por_ano) - _sharpe(
            b[indices], dias_por_ano
        )
    diferencas = diferencas[~np.isnan(diferencas)]
    return {
        "diferenca": _sharpe(a, dias_por_ano) - _sharpe(b, dias_por_ano),
        "ic90_inferior": float(np.percentile(diferencas, 5)),
        "ic90_superior": float(np.percentile(diferencas, 95)),
        "fracao_menor_ou_igual_a_zero": float((diferencas <= 0).mean()),
        "dias": n,
        "sorteios": len(diferencas),
    }
