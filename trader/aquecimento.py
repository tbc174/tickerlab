"""Aquecimento dos indicadores separado da janela avaliada.

Um atributo de 252 pregões só vale alguma coisa depois de 252 pregões de história. Os dias antes
disso são o **aquecimento**: entram na conta do atributo, mas não na avaliação da tentativa. Como no
Vibe-Trading, quem roda declara **ou** quantos pregões aquecer **ou** a data em que a avaliação
começa, nunca os dois (`janela_avaliada`), para não existirem duas verdades sobre o mesmo início.

Duas conferências, para usar antes de um pré-registro:

- `cobertura_do_aquecimento`: para cada ativo, se há pregões suficientes antes do início da
  avaliação (um ativo que começa depois avalia dias ainda mal aquecidos);
- `dependem_do_comeco`: quais atributos mudam, dentro da janela avaliada, quando a série começa em
  outro dia. Janela finita converge (a média exponencial deixa um resto desprezível); memória
  expansiva (média desde o primeiro dia) nunca converge: o valor depende de onde o histórico começa.
  Na M2 é o caso de `tendencia` (a normalização de `baselines._normalizar`); não olha o futuro, mas
  dois ativos iguais com históricos de tamanhos diferentes recebem valores diferentes.

Nada aqui muda a M2: o módulo só lê índices e calcula atributos sobre os dados que receber.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

import pandas as pd

from trader.atributos import HORIZONTES

# maior janela dos atributos da M2: retorno de 252 pregões, razão de volatilidade e distâncias
# da máxima e da mínima (`trader/atributos.py`)
AQUECIMENTO_DOS_ATRIBUTOS_DA_M2 = max(*HORIZONTES, 252)
# diferença acima disto conta como "mudou": bem acima do resto da média exponencial depois do
# aquecimento (~1e-7) e bem abaixo de qualquer diferença que mude uma decisão
TOLERANCIA_DE_CONVERGENCIA = 1e-4
COLUNAS_DA_COBERTURA = [
    "simbolo",
    "primeiro_dia",
    "pregoes_antes_do_inicio",
    "cobre",
    "aquecido_desde",
]


def aquecimento_necessario(janelas: Iterable[int]) -> int:
    """Pregões de aquecimento para um conjunto de atributos: a maior janela entre eles."""
    janelas = list(janelas)
    if any(j < 0 for j in janelas):
        raise ValueError("Janela de atributo não pode ser negativa.")
    return max(janelas, default=0)


def janela_avaliada(
    indice: pd.Index, aquecimento: int | None = None, inicio: object = None
) -> pd.DatetimeIndex:
    """As datas que a avaliação conta: depois de `aquecimento` pregões, **ou** desde `inicio`.

    Declarar os dois (ou nenhum) é erro. Série curta demais para o aquecimento também.
    """
    datas = pd.DatetimeIndex(indice)
    if (aquecimento is None) == (inicio is None):
        raise ValueError(
            "Declare o aquecimento (em pregões) ou a data de início, nunca os dois."
        )
    if aquecimento is not None:
        if aquecimento < 0:
            raise ValueError("O aquecimento não pode ser negativo.")
        if aquecimento >= len(datas):
            raise ValueError(
                f"Série de {len(datas)} pregões não cobre o aquecimento de {aquecimento}."
            )
        return datas[aquecimento:]
    avaliadas = datas[datas >= pd.Timestamp(inicio)]  # type: ignore[arg-type]
    if avaliadas.empty:
        raise ValueError(f"Nenhum pregão a partir de {pd.Timestamp(inicio):%Y-%m-%d}.")  # type: ignore[arg-type]
    return avaliadas


def cobertura_do_aquecimento(
    indices: Mapping[str, pd.Index], inicio: object, aquecimento: int
) -> pd.DataFrame:
    """Para cada ativo: quantos pregões há antes de `inicio` e se cobrem o `aquecimento`.

    `aquecido_desde` é o primeiro dia em que o atributo mais longo já tem a janela inteira: quando
    vem depois de `inicio`, a avaliação desse ativo começa com dias mal aquecidos.
    """
    dia = pd.Timestamp(inicio)  # type: ignore[arg-type]
    linhas = []
    for simbolo, indice in indices.items():
        datas = pd.DatetimeIndex(indice).sort_values()
        antes = int((datas < dia).sum())
        linhas.append(
            {
                "simbolo": simbolo,
                "primeiro_dia": datas[0],
                "pregoes_antes_do_inicio": antes,
                "cobre": antes >= aquecimento,
                "aquecido_desde": datas[aquecimento]
                if aquecimento < len(datas)
                else pd.NaT,
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS_DA_COBERTURA)


def dependem_do_comeco(
    calcular: Callable[[pd.Series], pd.DataFrame],
    retorno: pd.Series,
    corte: int,
    aquecimento: int,
    tolerancia: float = TOLERANCIA_DE_CONVERGENCIA,
) -> list[str]:
    """Atributos que mudam na janela avaliada quando a série começa `corte` pregões mais tarde.

    Calcula os atributos com a série inteira e com a série sem os `corte` primeiros pregões, e
    compara nas datas depois do aquecimento da série cortada. Devolve as colunas que diferem mais que
    `tolerancia` (ou que estão vazias numa conta e cheias na outra).
    """
    if corte <= 0:
        raise ValueError("O corte precisa tirar pelo menos um pregão.")
    inteira = calcular(retorno)
    cortada = calcular(retorno.iloc[corte:])
    datas = janela_avaliada(cortada.index, aquecimento=aquecimento)
    a, b = inteira.loc[datas], cortada.loc[datas]
    mudaram = []
    for coluna in cortada.columns:
        diferenca = (a[coluna] - b[coluna]).abs().max()
        so_numa = (a[coluna].isna() != b[coluna].isna()).any()
        if so_numa or diferenca > tolerancia:
            mudaram.append(coluna)
    return mudaram
