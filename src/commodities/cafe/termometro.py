"""Termômetro da CONAB: quanto o 1º levantamento da safra errou em relação ao 4º (o final).

A CONAB "costuma dar uma erradinha, mas não pode ser desconsiderada": aqui o erro vira número, por
tipo (arábica e conilon nunca se misturam). Erro positivo = o 1º levantamento previu mais que o final.
Funções puras sobre a tabela `conab_cafe`; sem tela e sem API (licença CC BY-ND 3.0 da CONAB).
"""

from datetime import date

import pandas as pd

from src.commodities.cafe.pontos import PontoDaSafra, levantamentos_ate

PRIMEIRO, FINAL = 1, 4
SAFRAS_DO_VIES = 10  # "viés médio dos últimos 10 anos"
MINIMO_DE_SAFRAS_DO_VIES = 3  # abaixo disso a média é anedota, não viés
PCT, MIL_SACAS = "% do final", "mil sacas de 60 kg"


def _primeiro_e_final(
    tabela: pd.DataFrame, tipo: str, uf: str, ate: date | None
) -> pd.DataFrame:
    """Uma linha por safra que já tem o 4º levantamento: colunas `primeiro` e `final` (mil sacas)."""
    por_levantamento = levantamentos_ate(tabela, tipo, uf, ate).pivot(
        index="safra", columns="levantamento", values="producao_mil_sacas"
    )
    if PRIMEIRO not in por_levantamento or FINAL not in por_levantamento:
        return pd.DataFrame(columns=["primeiro", "final"], dtype=float)
    pares = por_levantamento[[PRIMEIRO, FINAL]].dropna()
    pares.columns = ["primeiro", "final"]
    return pares[pares["final"] != 0]


def erro_do_primeiro_levantamento(
    tabela: pd.DataFrame, tipo: str, uf: str = "BRASIL", ate: date | None = None
) -> list[PontoDaSafra]:
    """Por safra concluída (com o 4º levantamento até `ate`): o erro do 1º, em % e em mil sacas."""
    pontos: list[PontoDaSafra] = []
    for safra, linha in _primeiro_e_final(tabela, tipo, uf, ate).iterrows():
        erro = float(linha["primeiro"] - linha["final"])
        pontos.append(
            PontoDaSafra(
                int(safra),
                tipo,
                uf,
                "erro_1o_levantamento_pct",
                100 * erro / float(linha["final"]),
                PCT,
                levantamento=PRIMEIRO,
            )
        )
        pontos.append(
            PontoDaSafra(
                int(safra),
                tipo,
                uf,
                "erro_1o_levantamento_mil_sacas",
                erro,
                MIL_SACAS,
                levantamento=PRIMEIRO,
            )
        )
    return pontos


def vies_medio(
    tabela: pd.DataFrame, tipo: str, uf: str = "BRASIL", ate: date | None = None
) -> list[PontoDaSafra]:
    """Um ponto: a média do erro (%) do 1º levantamento nas últimas 10 safras concluídas.

    Vazio se há menos de três safras concluídas. Positivo = a CONAB costuma começar alta demais.
    """
    erros = [
        p
        for p in erro_do_primeiro_levantamento(tabela, tipo, uf, ate)
        if p.serie == "erro_1o_levantamento_pct"
    ][-SAFRAS_DO_VIES:]
    if len(erros) < MINIMO_DE_SAFRAS_DO_VIES:
        return []
    media = sum(p.valor for p in erros) / len(erros)
    return [
        PontoDaSafra(erros[-1].safra, tipo, uf, "vies_medio_10_safras_pct", media, PCT)
    ]
