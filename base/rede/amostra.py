"""Precisão da resolução medida por amostra conferida (ADR 0077, item 4; plano da série, tarefa 2.7).

Para cada regra, `POR_REGRA` identificadores sorteados com semente fixa (a mesma montagem dá a mesma
amostra, em qualquer ordem). Claude confere todos contra os originais; o Tiago confere
`DO_TIAGO_POR_REGRA` da mesma amostra (Q2 do plano, "Claude 200, Tiago 20", 15/10/2026), e o que ele
marca errado conta como errado. O resultado fica em `base/conferidas/resolucao_amostra.csv`; uma regra
abaixo do corte (99% nas regras por código) quebra o teste. Critério de corte de custo da ADR: se a
conferência passar de 2 h/semana do Tiago, congelar a regra 6 e a API externa até haver cliente.

A **cobertura por valor** (meta 95%, como a do painel dos fundos) diz quanto do valor das carteiras
dos fundos tem emissor ligado a uma entidade da rede.
"""

from pathlib import Path

import pandas as pd

POR_REGRA = 200
DO_TIAGO_POR_REGRA = 20
SEMENTE = 77  # ADR 0077
CORTE_DAS_REGRAS_POR_CODIGO = 0.99
META_DE_COBERTURA = 0.95
CERTO, ERRADO = "certo", "errado"
TABELA_CONFERIDA = (
    Path(__file__).resolve().parent.parent / "conferidas" / "resolucao_amostra.csv"
)
CHAVE = ["regra", "id_entidade", "sistema", "valor"]
COLUNAS_DA_CONFERIDA = (
    *CHAVE, "conferencia_claude", "conferencia_tiago", "observacao", "conferido_com",
    "conferido_em",
)  # fmt: skip


def _por_regra(tabela: pd.DataFrame, quantos: int) -> pd.DataFrame:
    """Até `quantos` linhas de cada regra (todas, se tem menos), sempre as mesmas (semente fixa)."""
    ordenada = tabela.sort_values(CHAVE, kind="stable").reset_index(drop=True)
    partes = [
        grupo.sample(n=min(quantos, len(grupo)), random_state=SEMENTE)
        for _, grupo in ordenada.groupby("regra", sort=True)
    ]
    if not partes:
        return tabela.iloc[0:0]
    return pd.concat(partes).sort_values(CHAVE).reset_index(drop=True)


def sortear(identificadores: pd.DataFrame) -> pd.DataFrame:
    """A amostra a conferir: até `POR_REGRA` identificadores de cada regra, em qualquer ordem."""
    return _por_regra(identificadores, POR_REGRA)


def para_o_tiago(sorteada: pd.DataFrame) -> pd.DataFrame:
    """`DO_TIAGO_POR_REGRA` linhas de cada regra, sorteadas da própria amostra."""
    return _por_regra(sorteada, DO_TIAGO_POR_REGRA)


def tabela_conferida(caminho: Path = TABELA_CONFERIDA) -> pd.DataFrame:
    return pd.read_csv(
        caminho, sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
    )


def precisao(conferida: pd.DataFrame) -> dict[int, float]:
    """Fração certa por regra; o "errado" do Tiago vale sobre o "certo" do Claude."""
    errado = (conferida["conferencia_claude"] == ERRADO) | (
        conferida["conferencia_tiago"] == ERRADO
    )
    por_regra = (~errado).groupby(conferida["regra"].astype(int)).mean()
    return {int(regra): round(float(fracao), 6) for regra, fracao in por_regra.items()}


def regras_abaixo_do_corte(conferida: pd.DataFrame) -> list[int]:
    return [
        r for r, p in precisao(conferida).items() if p < CORTE_DAS_REGRAS_POR_CODIGO
    ]


def cobertura_por_valor(posicoes: pd.DataFrame, identificadores: pd.DataFrame) -> float:
    """Fração do valor das posições (`emissor`, `valor`) cujo emissor está na rede."""
    emissores = identificadores.loc[identificadores["sistema"] == "emissor", "valor"]
    total = float(posicoes["valor"].sum())
    if total == 0:
        return 0.0
    return float(
        posicoes.loc[posicoes["emissor"].isin(emissores), "valor"].sum() / total
    )
