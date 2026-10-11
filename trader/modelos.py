"""Modelos da M2, com hiperparâmetros fixos e conservadores (critério v0.1, famílias H1 e H2).

Sinal financeiro é fraco: os modelos são regularizados de propósito (folhas grandes, árvores rasas,
penalidade L2). Cada combinação de parâmetros testada é uma tentativa no registro, então o padrão
é usar estes valores e mudar pouco.
"""

from __future__ import annotations

from typing import Any

from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from trader import redes

PADROES: dict[str, dict[str, Any]] = {
    "logistica": {"C": 0.1},
    "floresta": {
        "n_estimators": 300,
        "max_depth": 6,
        "min_samples_leaf": 500,
        "max_features": "sqrt",
    },
    "lightgbm": {
        "n_estimators": 300,
        "learning_rate": 0.03,
        "num_leaves": 15,
        "min_child_samples": 500,
        "subsample": 0.8,
        "subsample_freq": 1,
        "colsample_bytree": 0.8,
        "reg_lambda": 10.0,
    },
}
FAMILIA = {
    "logistica": "H1",
    "floresta": "H2",
    "lightgbm": "H2",
    "arima": "H5",
    **{t: "H4" for t in redes.TIPOS},
}
PADROES.update(redes.PADROES)  # H4: os parâmetros fixos de cada rede
# H5 não é um classificador: o ARIMA roda por ativo em `trader.arima` (aqui só os parâmetros)
PADROES["arima"] = {
    "p_max": 2,
    "q_max": 2,
    "d": 0,
    "constante": True,
    "escolha": "AIC so no treino",
    "entrada": "retorno_1d",
}


def parametros(tipo: str, ajustes: dict[str, Any] | None = None) -> dict[str, Any]:
    if tipo not in PADROES:
        raise ValueError(f"Modelo desconhecido: {tipo}. Use um de {list(PADROES)}.")
    return {**PADROES[tipo], **(ajustes or {})}


def criar(tipo: str, ajustes: dict[str, Any] | None = None, semente: int = 0) -> Any:  # noqa: ANN401 (cada biblioteca tem sua classe)
    """Um classificador do scikit-learn (com `fit` e `predict_proba`)."""
    p = parametros(tipo, ajustes)
    if tipo == "logistica":
        return make_pipeline(
            StandardScaler(), LogisticRegression(C=p["C"], max_iter=2000)
        )
    if tipo == "floresta":
        return RandomForestClassifier(**p, n_jobs=-1, random_state=semente)
    return LGBMClassifier(**p, random_state=semente, n_jobs=-1, verbose=-1)
