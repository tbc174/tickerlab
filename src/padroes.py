"""Padrões por setor "como estavam na data" (série 2 da base de ML, PR 4; ADR 0033).

As notas (ótimo a péssimo) comparam o número da empresa com o padrão do grupo dela: os percentis do
indicador entre as empresas do mesmo grupo (`src/setores.py`), numa data de corte. Regras:

- **Só o que era público na data de corte:** de cada documento entra a maior versão entregue à
  CVM até o corte (`recebido_em`). Se o banco só tem uma versão entregue depois (uma reapresentação
  posterior), o documento fica de fora daquele corte: falta um ponto, mas o futuro não vaza.
- **Os mesmos cálculos da tela:** cada indicador sai de `src/fundamentos.py` e
  `src/fundamentalista.py`, e a nota compara com o mesmo número que a pessoa vê.
- **Número em conferência fica fora:** empresa com achado aberto que afeta o balanço inteiro (R1,
  R3, R4, R10) não entra no padrão daquele corte.
- **Mercado:** além de cada grupo, um padrão de todas as não financeiras, usado quando o grupo tem
  poucas empresas (`setores.grupo_para_comparar`).
"""

import math

import pandas as pd

from src import fundamentalista, fundamentos
from src.banco.demonstracoes import DadosDaEmpresa
from src.setores import MERCADO, SEM_GRUPO

VERSAO_DOS_PADROES = "1"  # sobe quando um indicador ou o método mudar
PERCENTIS = (10, 20, 25, 33, 40, 50, 60, 67, 75, 80, 90)
REGRAS_QUE_TIRAM_DO_PADRAO = ("R1", "R3", "R4", "R10")
CHAVE_DO_DOCUMENTO = ["cnpj", "documento", "referencia"]

# indicador → (nome, maior é melhor?)
INDICADORES: dict[str, tuple[str, bool]] = {
    "margem_bruta": ("Margem bruta", True),
    "margem_ebit": ("Margem EBIT", True),
    "margem_liquida": ("Margem líquida", True),
    "roe": ("ROE", True),
    "roic": ("ROIC", True),
    "conversao_de_caixa": ("Caixa operacional / lucro", True),
    "divida_sobre_pl": ("Dívida líquida / patrimônio", False),
    "crescimento_receita": ("Crescimento da receita", True),
    "crescimento_lucro": ("Crescimento do lucro", True),
    "dupont_giro": ("Giro do ativo", True),
    "ciclo_de_caixa": ("Ciclo de caixa", False),
    "cobertura_de_juros": ("Cobertura de juros", True),
}
# a unidade de cada indicador (para escrever o número e o padrão na nota)
UNIDADES: dict[str, str] = {
    **{
        chave: fundamentos.FRACAO
        for chave in (
            "margem_bruta", "margem_ebit", "margem_liquida", "roe", "roic",
            "crescimento_receita", "crescimento_lucro",
        )
    },
    **{
        chave: fundamentos.VEZES
        for chave in ("conversao_de_caixa", "divida_sobre_pl", "dupont_giro", "cobertura_de_juros")
    },
    "ciclo_de_caixa": fundamentalista.DIAS,
}  # fmt: skip
_DOCUMENTOS_VAZIOS = pd.DataFrame(
    columns=["documento", "referencia", "versao", "empresa", "recebido_em", "link"]
)


def contas_como_estavam(
    contas: pd.DataFrame, documentos: pd.DataFrame, data: pd.Timestamp
) -> pd.DataFrame:
    """As contas de cada documento na maior versão entregue à CVM até `data`.

    `contas`: as versões guardadas (cnpj, documento, referencia, versao, periodo, ...);
    `documentos`: cnpj, documento, referencia, versao, recebido_em de cada versão.
    """
    entregues = documentos[pd.to_datetime(documentos["recebido_em"]) <= data]
    if entregues.empty:
        return contas.iloc[0:0]
    versao = entregues.groupby(CHAVE_DO_DOCUMENTO)["versao"].max().reset_index()
    return (
        contas.merge(versao, on=[*CHAVE_DO_DOCUMENTO, "versao"])
        .drop_duplicates()
        .reset_index(drop=True)
    )


def indicadores_da_empresa(contas: pd.DataFrame, setor: str) -> dict[str, float | None]:
    """Os indicadores com padrão de uma empresa, pelas mesmas funções da tela."""
    dados = DadosDaEmpresa(contas=contas, documentos=_DOCUMENTOS_VAZIOS, setor=setor)
    resultado = fundamentos.calcular(dados, None)
    extra = fundamentalista.calcular(dados)
    valores = {}
    for chave in INDICADORES:
        indicador = resultado.indicadores.get(chave) or extra.indicadores.get(chave)
        valores[chave] = indicador.valor if indicador else None
    return valores


def _valido(valor: object) -> bool:
    return isinstance(valor, int | float) and math.isfinite(valor)


def _percentis(serie: pd.Series) -> dict[str, float]:
    return {str(p): float(serie.quantile(p / 100)) for p in PERCENTIS}


def calcular_padroes(
    valores: pd.DataFrame, excluidas: set[str] | frozenset[str] = frozenset()
) -> pd.DataFrame:
    """Percentis por grupo e indicador, e o do mercado (todas as não financeiras).

    `valores`: cnpj, grupo, indicador, valor. `excluidas`: empresas com número em conferência.
    Colunas: grupo, indicador, empresas, percentis ({"10": ..., "50": ..., "90": ...}).
    """
    validos = valores[
        ~valores["cnpj"].isin(excluidas) & valores["valor"].map(_valido)
    ].copy()
    validos = validos[validos["grupo"] != SEM_GRUPO]
    mercado = validos[validos["grupo"] != "financeiro"].assign(grupo=MERCADO)
    linhas = []
    for (grupo, indicador), parte in pd.concat([validos, mercado]).groupby(
        ["grupo", "indicador"]
    ):
        serie = parte["valor"].astype(float)
        linhas.append(
            {
                "grupo": grupo,
                "indicador": indicador,
                "empresas": int(serie.size),
                "percentis": _percentis(serie),
            }
        )
    return pd.DataFrame(linhas, columns=["grupo", "indicador", "empresas", "percentis"])
