"""Tabela `conab_cafe` pequena, montada à mão, para os testes dos derivados do café."""

import pandas as pd

DIAS = {1: "02-05", 2: "05-21", 3: "09-24", 4: "12-04"}


def tabela(
    producoes: dict[int, dict[int, float]], tipo="arabica", uf="BRASIL"
) -> pd.DataFrame:
    """`producoes[safra][levantamento]` em mil sacas; o levantamento 1 sai em fev da própria safra."""
    linhas = [
        {
            "safra": safra, "levantamento": lev, "tipo": tipo, "uf": uf,
            "area_formacao_ha": None, "area_producao_ha": None, "produtividade_sc_ha": None,
            "producao_mil_sacas": valor,
            "divulgado_em": pd.Timestamp(f"{safra}-{DIAS[lev]}"),
        }
        for safra, levs in producoes.items()
        for lev, valor in levs.items()
    ]  # fmt: skip
    return pd.DataFrame(linhas)
