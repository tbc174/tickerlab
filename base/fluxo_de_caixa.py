"""Conferência da demonstração do fluxo de caixa (série T1).

Para cada DFC (empresa, documento, versão, grupo e coluna), três perguntas:

- **Fecha?** O caixa do começo (6.05.01) mais o aumento ou a redução (6.05) dá o caixa do fim
  (6.05.02). É a regra dura: valeu em 100% dos DFP consolidados de 2023 e em 99,3% dos individuais
  (medido em 19/10/2026).
- **As atividades somam?** Operacional (6.01) + investimento (6.02) + financiamento (6.03) +
  variação cambial (6.04, quando há) = aumento ou redução (6.05). 100% dos consolidados de 2023.
- **Bate com o balanço?** O caixa do fim é o "Caixa e Equivalentes de Caixa" do ativo (1.01.01) na
  mesma data. É medida de qualidade, não regra: bancos e seguradoras chamam de "caixa" coisas
  diferentes nos dois quadros (85,8% dos consolidados e 90,7% dos individuais de 2023 batem). Sem a
  conta 1.01.01 no balanço, fica vazio.

A tolerância é de mil reais: uma unidade na escala em que quase todas as empresas informam (MIL),
para o arredondamento de cada linha não virar erro.
"""

import pandas as pd

TOLERANCIA = 1000.0  # reais
DFC = ("DFC_MI", "DFC_MD")
CAIXA_NO_BALANCO = "1.01.01"
SALDO_INICIAL, SALDO_FINAL, VARIACAO = "6.05.01", "6.05.02", "6.05"
ATIVIDADES = ("6.01", "6.02", "6.03", "6.04")
DOCUMENTO = ["cnpj", "documento", "referencia", "versao", "grupo", "ordem"]
COLUNAS_DA_CONFERENCIA = [
    *DOCUMENTO,
    "demonstracao",
    "inicio",
    "fim",
    "saldo_inicial",
    "saldo_final",
    "variacao",
    "soma_das_atividades",
    "caixa_no_balanco",
    "fecha",
    "soma_fecha",
    "bate_com_balanco",
]


def _perto(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a - b).abs() <= TOLERANCIA


def _coluna(tabela: pd.DataFrame, conta: str) -> pd.Series:
    """Os valores de uma conta; vazio quando nenhuma DFC a trouxe (a 6.04 é opcional)."""
    if conta in tabela:
        return tabela[conta]
    return pd.Series(float("nan"), index=tabela.index)


def _caixa_do_balanco(contas: pd.DataFrame) -> pd.DataFrame:
    caixa = contas[
        (contas["demonstracao"] == "BPA") & (contas["conta"] == CAIXA_NO_BALANCO)
    ]
    return caixa[[*DOCUMENTO, "fim", "valor"]].rename(
        columns={"valor": "caixa_no_balanco"}
    )


def conferir_dfc(contas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por DFC com os saldos, a soma das atividades e as três respostas.

    `contas`: no formato de `base/contas_cvm.py` (a DFC e, para bater, o BPA do mesmo documento).
    """
    dfc = contas[
        contas["demonstracao"].isin(DFC)
        & contas["conta"].isin([SALDO_INICIAL, SALDO_FINAL, VARIACAO, *ATIVIDADES])
    ]
    if dfc.empty:
        return pd.DataFrame(columns=COLUNAS_DA_CONFERENCIA)
    chave = [*DOCUMENTO, "demonstracao", "inicio", "fim"]
    tabela = (
        dfc.groupby([*chave, "conta"], dropna=False)["valor"]
        .first()
        .unstack("conta")
        .reset_index()
    )
    tabela["saldo_inicial"] = _coluna(tabela, SALDO_INICIAL)
    tabela["saldo_final"] = _coluna(tabela, SALDO_FINAL)
    tabela["variacao"] = _coluna(tabela, VARIACAO)
    tabela["soma_das_atividades"] = sum(
        _coluna(tabela, conta).fillna(0.0) for conta in ATIVIDADES
    )
    tabela = tabela.merge(_caixa_do_balanco(contas), on=[*DOCUMENTO, "fim"], how="left")
    tabela["fecha"] = _perto(
        tabela["saldo_inicial"] + tabela["variacao"], tabela["saldo_final"]
    )
    tabela["soma_fecha"] = _perto(tabela["soma_das_atividades"], tabela["variacao"])
    bate = _perto(tabela["saldo_final"], tabela["caixa_no_balanco"]).astype("boolean")
    tabela["bate_com_balanco"] = bate.mask(tabela["caixa_no_balanco"].isna())
    return tabela[COLUNAS_DA_CONFERENCIA].reset_index(drop=True)
