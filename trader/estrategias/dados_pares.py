"""Dados da ficha P0-4 (pares): a mesma base da F-B3, sem a quantidade de ações, mais o setor.

| Tabela | Fonte | Situação em 03/11/2026 |
|---|---|---|
| preços, volume, cadastro, balanços, CDI | os de `dados_f_b3` (COTAHIST anual de 2009 a 2023 e preços ajustados) | **falta** o COTAHIST anual e os preços ajustados (fila, linha 577) |
| setores | `fca_geral/<ano>.parquet` do acervo (FCA da CVM: CNPJ, setor, `conhecido_em`) | pronto (2010 em diante) |

A ficha não usa a quantidade de ações (não há valor de mercado na regra), então não exige
`acoes_em_circulacao.parquet`. O setor entra ponto no tempo: cada linha do FCA vale a partir de
`conhecido_em` (`pares.setores_em`). Nada aqui baixa nada da internet.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trader.estrategias import dados_f_b3
from trader.estrategias.pares import COLUNAS_DOS_SETORES, Dados
from trader.holdout import FIM_DO_DESENVOLVIMENTO

PASTA_DA_FICHA = dados_f_b3.PASTA_DA_FICHA  # o COTAHIST anual é o mesmo da F-B3
PASTA_DO_ACERVO = dados_f_b3.PASTA_DO_ACERVO
PRIMEIRO_ANO_DO_FCA = 2010
ULTIMO_ANO = dados_f_b3.ULTIMO_ANO


def conferir_base(pasta: Path = PASTA_DA_FICHA) -> list[str]:
    """Os arquivos que faltam para a ficha rodar; lista vazia quando dá para rodar."""
    return dados_f_b3.conferir_base(pasta, com_acoes=False)


def setores_do_fca(pasta_do_acervo: Path = PASTA_DO_ACERVO) -> pd.DataFrame:
    """CNPJ, setor e `conhecido_em` de cada entrega do FCA, só o que ficou público no desenvolvimento."""
    pasta = pasta_do_acervo / "fca_geral"
    anos = range(PRIMEIRO_ANO_DO_FCA, ULTIMO_ANO + 1)
    arquivos = [pasta / f"{ano}.parquet" for ano in anos]
    tabelas = [
        pd.read_parquet(arquivo, columns=list(COLUNAS_DOS_SETORES))
        for arquivo in arquivos
        if arquivo.exists()
    ]
    if not tabelas:
        return pd.DataFrame(columns=list(COLUNAS_DOS_SETORES))
    setores = pd.concat(tabelas, ignore_index=True)
    setores["conhecido_em"] = pd.to_datetime(setores["conhecido_em"])
    setores = setores.dropna(subset=["setor", "conhecido_em"])
    setores = setores[setores["conhecido_em"] <= FIM_DO_DESENVOLVIMENTO]
    return setores.sort_values(["conhecido_em", "cnpj"], kind="stable").reset_index(
        drop=True
    )


def carregar_tabelas(
    pasta: Path = PASTA_DA_FICHA, pasta_do_acervo: Path = PASTA_DO_ACERVO
) -> Dados:
    """Monta `pares.Dados` só com o desenvolvimento; falha listando o que falta."""
    faltas = conferir_base(pasta)
    if faltas:
        raise FileNotFoundError(f"faltam na base da ficha P0-4: {', '.join(faltas)}")
    base = dados_f_b3.carregar_tabelas(pasta, pasta_do_acervo, com_acoes=False)
    return Dados(**base.__dict__, setores=setores_do_fca(pasta_do_acervo))
