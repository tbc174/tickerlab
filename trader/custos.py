"""Custos por ativo do critério v0.1 (seção 3), em fração do valor negociado.

| Classe                                    | por lado (spread/2 + comissão + deslizamento) |
|-------------------------------------------|-----------------------------------------------|
| Forex G10                                 | 0,5 pb de meio spread + 0,5 pb de deslizamento |
| Forex emergente, dólar/real, metais, energia, agro | 3 pb                                  |
| Índices e ETFs                            | 2 pb                                          |
| Ações da B3                               | 5 pb                                          |
| Cripto                                    | 10 pb                                         |

**Carregamento (swap):** ainda não temos as taxas observadas. O critério manda assumir "o pior dos
dois lados"; sem as taxas, a implementação v0.1 usa um **custo simétrico de 2% ao ano sobre o valor
da posição, comprado ou vendido**, em tudo o que é à vista ou CFD. Futuros contínuos (`=F`) não pagam
(o carregamento já está no preço do futuro). **Limitação declarada:** o diferencial de juros entre
moedas (o "carry") não está modelado; isso distorce principalmente o dólar/real, o peso mexicano e o
rand, em que o diferencial chega a vários pontos por ano.
"""

from __future__ import annotations

from trader.backtest import Custos
from trader.universo import Ativo

VERSAO_DA_TABELA = "v0.1"
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
CARREGAMENTO_ANUAL = 0.02  # pago dos dois lados, sobre o valor da posição


def eh_futuro_continuo(ativo: Ativo) -> bool:
    return ativo.simbolo.endswith("=F")


def custos_do_ativo(ativo: Ativo, multiplicador: float = 1.0) -> Custos:
    """Os custos do ativo; `multiplicador=2` é o estresse "×2" (tudo dobrado, inclusive o swap)."""
    if multiplicador <= 0:
        raise ValueError("O multiplicador precisa ser positivo.")
    if ativo.papel != "operar":
        raise ValueError(f"{ativo.simbolo} é só atributo; não se opera.")
    swap = 0.0 if eh_futuro_continuo(ativo) else -CARREGAMENTO_ANUAL * multiplicador
    if ativo.simbolo in FOREX_G10:
        return Custos(
            spread=0.0001 * multiplicador,
            deslizamento=0.00005 * multiplicador,
            swap_comprado_anual=swap,
            swap_vendido_anual=swap,
        )
    if ativo.classe not in POR_LADO:
        raise KeyError(f"Classe sem custo definido: {ativo.classe} ({ativo.simbolo}).")
    return Custos(
        comissao=POR_LADO[ativo.classe] * multiplicador,
        swap_comprado_anual=swap,
        swap_vendido_anual=swap,
    )
