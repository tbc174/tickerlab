"""A ficha "Foi sorte?": cinco checagens "passou / não passou" e um veredito (ADR 0037, D1 e D2).

A ficha junta, em linguagem simples, a validação que o backtest já faz (`validacao.py` e
`acaso.py`); nenhuma conta nova de estatística nasce aqui. Cada checagem responde uma pergunta:

1. Funcionou fora do período usado para escolher os parâmetros?
2. Sobrevive aos custos e ao imposto (rende mais que o CDI)?
3. Bate o acaso, contando as tentativas da pessoa?
4. Funciona com parâmetros vizinhos?
5. As quedas cabem no que a pessoa aguenta?

Os limites de cada checagem são constantes deste módulo, escritos antes de qualquer resultado
(o espírito da ADR 0006) e publicados na metodologia.
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from src.acaso import MIN_OPERACOES_PARA_MONTE_CARLO, simular_monte_carlo
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.imposto import aplicar_imposto

AVISO = "Vale para os dados do passado. Não é promessa de resultado nem recomendação."

PERGUNTA_FORA_DO_PERIODO = "Funcionou fora do período usado para escolher?"
PERGUNTA_VIZINHOS = "Funciona com parâmetros vizinhos?"
PERGUNTA_CUSTOS = "Sobrevive aos custos e ao imposto?"
PERGUNTA_QUEDAS = "As quedas cabem no que você aguenta?"

# Checagem 1: o Sharpe de fora precisa guardar pelo menos metade do de dentro
EFICIENCIA_MINIMA = 0.5
# Checagem 4: 2 de cada 3 vizinhos com Sharpe positivo, e a mediana deles com pelo menos metade
# do Sharpe da configuração escolhida (um pico isolado cercado de resultados fracos é sorte)
FRACAO_MINIMA_DE_VIZINHOS_POSITIVOS = 2 / 3
FRACAO_MINIMA_DA_MEDIANA = 0.5
# Checagem 5: a maior queda que a pessoa aguentaria, se ela não disser outra (fração)
TOLERANCIA_PADRAO_DE_QUEDA = 0.30
PIOR_CASO_COMUM = (
    0.05  # quantil das quedas do Monte Carlo: 95% das simulações caíram menos
)


class Situacao(Enum):
    PASSOU = "passou"
    NAO_PASSOU = "não passou"
    NAO_SE_APLICA = "não se aplica"  # não havia o que conferir (ex.: nada foi ajustado)
    SEM_MEDIDA = "não deu para medir"  # faltaram dados ou operações


class Resultado(Enum):
    PASSOU = "passou"
    NAO_PASSOU = "não passou"
    INCONCLUSIVO = "inconclusivo"


@dataclass(frozen=True)
class Checagem:
    pergunta: str
    situacao: Situacao
    explicacao: str  # uma frase em português, com os números que decidiram


@dataclass(frozen=True)
class Veredito:
    resultado: Resultado
    titulo: str
    texto: str  # sempre termina com o AVISO


@dataclass(frozen=True)
class Ficha:
    checagens: tuple[Checagem, ...]
    tentativas: int  # quantas variações entraram na conta da checagem 3

    @property
    def veredito(self) -> Veredito:
        """Passou só se nenhuma checagem falhou nem ficou sem medida ("não se aplica" não pesa)."""
        return montar_veredito(self.checagens)


def _perguntas(checagens: tuple[Checagem, ...], situacao: Situacao) -> str:
    return "; ".join(c.pergunta for c in checagens if c.situacao is situacao)


def montar_veredito(checagens: tuple[Checagem, ...]) -> Veredito:
    """O veredito da ficha a partir das checagens, com o texto que explica o porquê."""
    falhas = _perguntas(checagens, Situacao.NAO_PASSOU)
    if falhas:
        return Veredito(
            Resultado.NAO_PASSOU,
            "Não passou no teste contra a sorte",
            f"Não passou em: {falhas} Uma regra assim pode ter funcionado só no passado: "
            f"não coloque dinheiro nela por causa deste resultado. {AVISO}",
        )
    sem_medida = _perguntas(checagens, Situacao.SEM_MEDIDA)
    if sem_medida or not any(c.situacao is Situacao.PASSOU for c in checagens):
        return Veredito(
            Resultado.INCONCLUSIVO,
            "Inconclusivo",
            "Nenhuma checagem falhou, mas não deu para medir: "
            f"{sem_medida or 'nenhuma checagem se aplica'}. Com mais histórico ou mais "
            f"operações a ficha pode responder. {AVISO}",
        )
    return Veredito(
        Resultado.PASSOU,
        "Passou no teste contra a sorte",
        "Todas as checagens que se aplicam passaram: o resultado não parece ser só sorte. "
        f"{AVISO}",
    )


# --- Construtores das situações sem conta ------------------------------------------------


def nao_se_aplica(pergunta: str, motivo: str) -> Checagem:
    """Checagem que não tinha o que conferir (por exemplo, a regra não tem números para ajustar)."""
    return Checagem(pergunta, Situacao.NAO_SE_APLICA, motivo)


def sem_medida(pergunta: str, motivo: str) -> Checagem:
    """Checagem que não pôde ser feita (poucos dados, poucas operações)."""
    return Checagem(pergunta, Situacao.SEM_MEDIDA, motivo)


def _numero(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _porcentagem(valor: float) -> str:
    return f"{valor * 100:+.1f}%".replace(".", ",")


def _queda(valor: float) -> str:
    return f"{abs(valor) * 100:.0f}%"


def _situacao(passou: bool) -> Situacao:
    return Situacao.PASSOU if passou else Situacao.NAO_PASSOU


# --- Checagem 1: fora do período ---------------------------------------------------------


def checar_fora_do_periodo(
    sharpe_fora: float, sharpe_dentro: float, como: str
) -> Checagem:
    """Passa se o Sharpe fora do período de escolha é positivo e guarda pelo menos
    `EFICIENCIA_MINIMA` do Sharpe de dentro. `como`: "walk-forward" ou "treino e teste"."""
    if np.isnan(sharpe_fora):
        return Checagem(
            PERGUNTA_FORA_DO_PERIODO,
            Situacao.NAO_PASSOU,
            f"No {como}, a regra não operou fora do período de escolha.",
        )
    passou = (
        sharpe_fora > 0
        and sharpe_dentro > 0
        and sharpe_fora >= EFICIENCIA_MINIMA * sharpe_dentro
    )
    return Checagem(
        PERGUNTA_FORA_DO_PERIODO,
        _situacao(passou),
        f"No {como}, o Sharpe foi {_numero(sharpe_dentro)} no período usado para escolher "
        f"e {_numero(sharpe_fora)} fora dele.",
    )


# --- Checagem 4: parâmetros vizinhos -----------------------------------------------------


Valor = float | str  # valor de um parâmetro no mapa ("" quando só um parâmetro varia)


def _posicao_mais_proxima(rotulos: pd.Index, valor: Valor) -> int:
    exata = int(rotulos.get_indexer([valor])[0])  # -1 quando o valor não está na grade
    if exata >= 0:
        return exata
    distancias = np.abs(np.asarray(rotulos, dtype=float) - float(valor))
    return int(distancias.argmin())


def vizinhos(mapa: pd.DataFrame, escolhido: tuple[Valor, Valor]) -> list[float]:
    """Sharpes das casas em volta da escolhida no mapa de parâmetros (até 8; as inválidas saem).

    `mapa` vem de `validacao.montar_mapa_de_sharpe` (colunas = 1º parâmetro, linhas = 2º);
    `escolhido` = (valor do 1º, valor do 2º ou ""). Fora da grade, vale a casa mais próxima.
    """
    coluna = _posicao_mais_proxima(mapa.columns, escolhido[0])
    linha = _posicao_mais_proxima(mapa.index, escolhido[1])
    valores = mapa.to_numpy(dtype=float).copy()
    valores[linha, coluna] = np.nan  # a própria escolha não é vizinha dela
    bloco = valores[max(linha - 1, 0) : linha + 2, max(coluna - 1, 0) : coluna + 2]
    return [float(v) for v in bloco.ravel() if not np.isnan(v)]


def checar_vizinhos(
    mapa: pd.DataFrame, escolhido: tuple[Valor, Valor], sharpe_da_pessoa: float
) -> Checagem:
    """Passa se a configuração está numa região boa do mapa, não num pico isolado."""
    em_volta = vizinhos(mapa, escolhido)
    if not em_volta:
        return sem_medida(
            PERGUNTA_VIZINHOS, "Não há combinações vizinhas válidas para comparar."
        )
    positivos = sum(v > 0 for v in em_volta)
    mediana = float(np.median(em_volta))
    passou = (
        positivos >= FRACAO_MINIMA_DE_VIZINHOS_POSITIVOS * len(em_volta)
        and mediana >= FRACAO_MINIMA_DA_MEDIANA * sharpe_da_pessoa
    )
    return Checagem(
        PERGUNTA_VIZINHOS,
        _situacao(passou),
        f"{positivos} de {len(em_volta)} combinações vizinhas têm Sharpe "
        f"positivo; a mediana delas é {_numero(mediana)}, contra {_numero(sharpe_da_pessoa)} "
        "da sua configuração.",
    )


# --- Checagem 2: custos e imposto --------------------------------------------------------


def custo_da_checagem(custo_por_operacao: float) -> float:
    """O custo usado pela ficha: o da pessoa, mas nunca abaixo do padrão do app (fração)."""
    return max(custo_por_operacao, CUSTO_PADRAO_POR_OPERACAO)


def retorno_liquido(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    custo_por_operacao: float,
    capital_inicial: float,
) -> float:
    """Retorno total da regra depois dos custos e do imposto simplificado da B3 (fração)."""
    bruto = executar_backtest(fechamento, posicao_desejada, custo_por_operacao)
    liquido = aplicar_imposto(bruto, capital_inicial).resultado
    return float(liquido.curva_de_capital.iloc[-1] - 1)


def checar_custos_e_imposto(
    retorno_liquido_total: float, retorno_do_cdi: float | None
) -> Checagem:
    """Passa se, depois dos custos e do imposto, a regra rende mais que o CDI do mesmo período
    (sem o CDI, mais que zero). Os dois retornos são totais do período, em fração."""
    if retorno_do_cdi is None:
        return Checagem(
            PERGUNTA_CUSTOS,
            _situacao(retorno_liquido_total > 0),
            f"Depois dos custos e do imposto, a regra rendeu "
            f"{_porcentagem(retorno_liquido_total)}. Ficou sem o CDI para comparar, então a "
            "conta foi contra zero.",
        )
    return Checagem(
        PERGUNTA_CUSTOS,
        _situacao(retorno_liquido_total > retorno_do_cdi),
        f"Depois dos custos e do imposto, a regra rendeu {_porcentagem(retorno_liquido_total)}; "
        f"o CDI rendeu {_porcentagem(retorno_do_cdi)} no mesmo período.",
    )


# --- Checagem 5: quedas ------------------------------------------------------------------


def queda_no_pior_caso_comum(
    retornos_das_operacoes: pd.Series, curva_de_capital: pd.Series
) -> tuple[float, str]:
    """A maior queda (negativa) que se deve esperar e de onde ela veio.

    Com operações suficientes, o pior caso comum do Monte Carlo (as operações em outra ordem);
    com poucas, a maior queda que de fato aconteceu.
    """
    if len(retornos_das_operacoes.dropna()) >= MIN_OPERACOES_PARA_MONTE_CARLO:
        simulado = simular_monte_carlo(retornos_das_operacoes)
        queda = float(np.quantile(simulado.quedas_maximas, PIOR_CASO_COMUM))
        return queda, "no pior caso comum do Monte Carlo"
    real = float((curva_de_capital / curva_de_capital.cummax() - 1).min())
    return real, "na maior queda real (poucas operações para o Monte Carlo)"


def checar_quedas(queda: float, tolerancia: float, fonte: str) -> Checagem:
    """Passa se a queda (negativa) não passa da tolerância da pessoa (fração positiva)."""
    return Checagem(
        PERGUNTA_QUEDAS,
        _situacao(abs(queda) <= tolerancia),
        f"A queda chegou a {_queda(queda)} {fonte}; você disse aguentar até "
        f"{_queda(tolerancia)}.",
    )
