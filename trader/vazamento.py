"""Verificações de vazamento da seção 8 do critério (antes de aceitar qualquer número).

O pipeline de um candidato precisa saber rodar em três variantes e devolver a carteira:
- "normal": como será avaliado;
- "futuro": os atributos deslocados um dia PARA A FRENTE (olhando o futuro de propósito). Isso tem
  de **inflar** o resultado; se não inflar, o teste não está enxergando nada e não vale;
- "embaralhado": os rótulos de treino embaralhados;
- "proporcao": a referência da v0.2, o mesmo pipeline prevendo só a frequência de "sobe" do treino.
  Sortear os rótulos não muda essa frequência, então o embaralhado tende a ficar comprado em tudo,
  como a referência. Sem vazamento, o que ele aprende ALÉM dela é ruído: o Sharpe da diferença
  diária (embaralhado − proporção) não pode passar de +2 erros-padrão (critério v0.4: só o lado de
  render MAIS indica vazamento; render menos é o ruído do modelo sorteado pagando custo).
  (Na v0.1 a regra era "o embaralhado sozinho dá Sharpe ≈ 0", o que reprovava qualquer modelo com
  viés comprado sem haver vazamento; ver a seção 12 do critério.)
Além disso, rodar "normal" duas vezes com a mesma semente tem de dar o mesmo resultado.

`verificar(rodar)` devolve o dicionário que entra em `EvidenciaDoDesenvolvimento.vazamento`.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from trader import avaliacao

VARIANTES = ("normal", "futuro", "embaralhado", "proporcao")
FOLGA_MINIMA_DO_FUTURO = (
    0.5  # o "futuro" precisa render pelo menos 0,5 de Sharpe a mais
)
ERROS_PADRAO = 2.0


def erro_padrao_do_sharpe(retorno: pd.Series, dias_por_ano: int = 252) -> float:
    """Erro-padrão aproximado do Sharpe anual (Lo, 2002): √((1 + SR²/2) / anos)."""
    r = retorno.dropna()
    anos = len(r) / dias_por_ano
    if anos <= 0:
        return float("nan")
    sr = avaliacao.sharpe(r, dias_por_ano)
    if not np.isfinite(sr):  # série sem variação (ex.: diferença toda zero)
        sr = 0.0
    return float(np.sqrt((1 + 0.5 * sr**2) / anos))


def verificar(rodar: Callable[[str], pd.Series]) -> tuple[dict[str, bool], dict]:
    """Roda as variantes e devolve (aprovações, detalhes com os números)."""
    normal = rodar("normal")
    de_novo = rodar("normal")
    futuro = rodar("futuro")
    embaralhado = rodar("embaralhado")
    proporcao = rodar("proporcao")
    s_normal = avaliacao.sharpe(normal)
    s_futuro = avaliacao.sharpe(futuro)
    diferenca = (embaralhado - proporcao.reindex(embaralhado.index)).dropna()
    s_diferenca = avaliacao.sharpe(diferenca)
    if not np.isfinite(
        s_diferenca
    ):  # idênticos: diferença sem variação, nada além da proporção
        s_diferenca = 0.0
    limite = ERROS_PADRAO * erro_padrao_do_sharpe(diferenca)
    reprodutivel = normal.equals(de_novo)
    aprovacoes = {
        "futuro_inflou": bool(s_futuro >= s_normal + FOLGA_MINIMA_DO_FUTURO),
        # v0.4: unilateral. Vazamento só faz o embaralhado render MAIS que a referência; render
        # menos é ruído pagando custo (o LightGBM por classe, #21, reprovou por isso na v0.3)
        "embaralhado_nao_supera_a_proporcao": bool(s_diferenca <= limite),
        "reprodutivel": bool(reprodutivel),
    }
    detalhes = {
        "sharpe_normal": s_normal,
        "sharpe_futuro": s_futuro,
        "sharpe_embaralhado": avaliacao.sharpe(embaralhado),
        "sharpe_proporcao": avaliacao.sharpe(proporcao),
        "sharpe_da_diferenca": s_diferenca,
        "limite_da_diferenca": limite,
    }
    return aprovacoes, detalhes
