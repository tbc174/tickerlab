"""Análise de viabilidade: antes de treinar qualquer modelo, os dados aguentam uma estratégia?

Ideia tirada do `machine-learning-for-trading` (3ª ed.). Nada aqui ajusta modelo ou faz previsão:
- **movimento contra custo:** em que fração dos dias (e das semanas, e dos meses) o preço anda mais
  do que custa entrar e sair. Se quase nunca anda, nenhum modelo salva;
- **autocorrelação dentro de cada ativo:** o retorno de hoje diz algo do de amanhã?
- **apostas independentes:** 70 ativos correlacionados valem bem menos que 70 apostas. A conta usa
  os autovalores da matriz de correlação dos retornos semanais (semanal para não sofrer com
  bolsas que fecham em horários diferentes): N efetivo = (Σλ)² / Σλ².
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trader.avaliacao import para_dias_uteis

HORIZONTES = {"1d": 1, "5d": 5, "21d": 21}
MINIMO_DE_SEMANAS_EM_COMUM = 104  # 2 anos


def _retorno_em_blocos(retorno: pd.Series, dias: int) -> pd.Series:
    """Retornos compostos em blocos SEM sobreposição de `dias` linhas."""
    grupos = np.arange(len(retorno)) // dias
    compostos = (1 + retorno).groupby(grupos).prod() - 1
    completos = pd.Series(grupos).value_counts().sort_index() == dias
    return compostos[completos.to_numpy()]


def linha_de_viabilidade(retorno: pd.Series, custo_ida_e_volta: float) -> dict:
    """Números de um ativo. `custo_ida_e_volta` em fração (0,0002 = 2 pb)."""
    r = retorno.dropna()
    linha: dict[str, float] = {
        "dias": float(len(r)),
        "volatilidade_diaria": float(r.std()) if len(r) > 1 else float("nan"),
        "custo_ida_e_volta_pb": custo_ida_e_volta * 1e4,
        "autocorrelacao_1d": float(r.autocorr(1)) if len(r) > 2 else float("nan"),
    }
    for nome, dias in HORIZONTES.items():
        blocos = _retorno_em_blocos(r, dias) if dias > 1 else r
        linha[f"movimento_maior_que_custo_{nome}"] = (
            float((blocos.abs() > custo_ida_e_volta).mean())
            if len(blocos)
            else float("nan")
        )
    semanal = _retorno_em_blocos(r, 5)
    linha["autocorrelacao_semanal"] = (
        float(semanal.autocorr(1)) if len(semanal) > 2 else float("nan")
    )
    return linha


def retornos_semanais(retornos: dict[str, pd.Series]) -> pd.DataFrame:
    """Uma coluna por ativo, semana terminando na sexta (fim de semana do cripto já incluído)."""
    semanais = {
        nome: (1 + para_dias_uteis(r)).resample("W-FRI").prod() - 1
        for nome, r in retornos.items()
    }
    tabela = pd.concat(semanais, axis=1, sort=True)
    # semanas sem nenhum dado do ativo viram vazio, não zero
    contagem = pd.concat(
        {
            nome: para_dias_uteis(r).resample("W-FRI").count()
            for nome, r in retornos.items()
        },
        axis=1,
        sort=True,
    )
    return tabela.where(contagem > 0)


def apostas_independentes(semanais: pd.DataFrame) -> dict:
    """N efetivo de apostas e a correlação média entre os ativos."""
    correlacao = semanais.corr(min_periods=MINIMO_DE_SEMANAS_EM_COMUM)
    n = len(correlacao)
    if n == 0:
        return {
            "ativos": 0,
            "apostas_independentes": float("nan"),
            "correlacao_media": float("nan"),
        }
    preenchida = np.array(correlacao.fillna(0.0).to_numpy(), dtype=float, copy=True)
    np.fill_diagonal(preenchida, 1.0)
    autovalores = np.clip(np.linalg.eigvalsh(preenchida), 0, None)
    efetivo = autovalores.sum() ** 2 / (autovalores**2).sum()
    fora_da_diagonal = correlacao.where(~np.eye(n, dtype=bool)).stack()
    return {
        "ativos": n,
        "apostas_independentes": float(efetivo),
        "correlacao_media": float(fora_da_diagonal.mean())
        if len(fora_da_diagonal)
        else float("nan"),
        "pares_sem_dados_em_comum": int(correlacao.isna().sum().sum() // 2),
    }
