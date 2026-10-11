"""Custos por ativo do critério v0.1 (seção 3), em fração do valor negociado.

| Classe                                    | por lado (spread/2 + comissão + deslizamento) |
|-------------------------------------------|-----------------------------------------------|
| Forex G10                                 | 0,5 pb de meio spread + 0,5 pb de deslizamento |
| Forex emergente, dólar/real, metais, energia, agro | 3 pb                                  |
| Índices e ETFs                            | 2 pb                                          |
| Ações da B3                               | 5 pb                                          |
| Cripto                                    | 10 pb                                         |

**Carregamento (swap), versão v0.2 (11/10/2026):** com as taxas básicas dos bancos centrais (BIS,
`trader/juros.py`), o swap de ficar comprado é o **carry** do ativo menos uma margem de corretora
de **0,5% ao ano**; o de ficar vendido é o carry com sinal trocado, menos a mesma margem. No
estresse ×2, a margem dobra (o carry não, porque não é custo, é juro). Sem a tabela de taxas, cai
no carregamento simétrico de 2% ao ano da v0.1. Futuros contínuos (`=F`) não pagam.
"""

from __future__ import annotations

import pandas as pd

from trader.backtest import Custos
from trader.juros import carry_anual
from trader.universo import Ativo

VERSAO_DA_TABELA = "v0.2"
FOREX_G10 = {
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "EURJPY",
    "GBPJPY",
    "EURGBP",
    "AUDJPY",
}
POR_LADO = {  # custo por lado, quando não é forex G10
    "forex": 0.0003,  # emergentes (USDMXN, USDZAR)
    "cambio": 0.0003,
    "metais": 0.0003,
    "energia": 0.0003,
    "agro": 0.0003,
    "indices": 0.0002,
    "etfs": 0.0002,
    "acoes_b3": 0.0005,
    "cripto": 0.0010,
}
CARREGAMENTO_ANUAL = 0.02  # v0.1: pago dos dois lados quando não há taxas de juro
MARGEM_DO_SWAP = (
    0.005  # v0.2: margem da corretora sobre o carry, por ano, dos dois lados
)


def eh_futuro_continuo(ativo: Ativo) -> bool:
    return ativo.simbolo.endswith("=F")


def custos_do_ativo(
    ativo: Ativo,
    multiplicador: float = 1.0,
    taxas: pd.DataFrame | None = None,
    indice: pd.DatetimeIndex | None = None,
) -> Custos:
    """Os custos do ativo; `multiplicador=2` é o estresse "×2".

    Com `taxas` (de `trader.juros.carregar`) e o `indice` de datas, o swap segue o carry no tempo.
    """
    if multiplicador <= 0:
        raise ValueError("O multiplicador precisa ser positivo.")
    if ativo.papel != "operar":
        raise ValueError(f"{ativo.simbolo} é só atributo; não se opera.")
    swap_comprado: float | pd.Series
    swap_vendido: float | pd.Series
    if eh_futuro_continuo(ativo):
        swap_comprado = swap_vendido = 0.0
    elif taxas is not None and indice is not None:
        carry = carry_anual(ativo, indice, taxas).fillna(0.0)
        margem = MARGEM_DO_SWAP * multiplicador
        swap_comprado = carry - margem
        swap_vendido = -carry - margem
    else:
        swap_comprado = swap_vendido = -CARREGAMENTO_ANUAL * multiplicador
    if ativo.simbolo in FOREX_G10:
        return Custos(
            spread=0.0001 * multiplicador,
            deslizamento=0.00005 * multiplicador,
            swap_comprado_anual=swap_comprado,
            swap_vendido_anual=swap_vendido,
        )
    if ativo.classe not in POR_LADO:
        raise KeyError(f"Classe sem custo definido: {ativo.classe} ({ativo.simbolo}).")
    return Custos(
        comissao=POR_LADO[ativo.classe] * multiplicador,
        swap_comprado_anual=swap_comprado,
        swap_vendido_anual=swap_vendido,
    )
