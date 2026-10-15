"""Preço médio de ações e FIIs, operação por operação: as mesmas regras do custo médio do app
(`src/dividendos_e_custo.py`), para quem digita as próprias notas no site.

- Compra: o custo soma a quantidade × o preço **mais a corretagem e as taxas** (a Receita manda
  somar essas despesas ao custo de aquisição).
- Venda: **não muda o preço médio**; o resultado é o que entrou (menos as taxas da venda) menos o
  preço médio × a quantidade vendida. Vender tudo zera, e a próxima compra recomeça a média.
- Bonificação: as ações novas entram com o valor que a empresa atribuiu a cada uma (`preco`).
- Desdobro e grupamento: só a quantidade muda; o custo total fica.
- Amortização (FII): devolve parte do capital; o custo cai `preco` por cota (sem passar de zero) e a
  quantidade fica.

Não é cálculo de imposto nem recomendação.
"""

from dataclasses import dataclass

TIPOS = ("compra", "venda", "bonificacao", "desdobro", "grupamento", "amortizacao")
_QUASE_ZERO = 1e-9


@dataclass(frozen=True)
class Operacao:
    tipo: str
    quantidade: float
    preco: float = (
        0.0  # por ação; na bonificação, o valor atribuído; na amortização, por cota
    )
    custos: float = 0.0  # corretagem e taxas da operação, em reais


@dataclass(frozen=True)
class Linha:
    tipo: str
    quantidade: float  # depois da operação
    custo_total: float
    preco_medio: float | None  # None sem ações
    resultado: float | None  # só na venda: lucro (+) ou prejuízo (−)


def calcular(operacoes: list[Operacao]) -> list[Linha]:
    """A posição depois de cada operação, na ordem em que foram feitas."""
    quantidade = custo = 0.0
    linhas: list[Linha] = []
    for op in operacoes:
        if op.tipo not in TIPOS:
            raise ValueError(f"Operação de tipo desconhecido: {op.tipo!r}")
        if op.quantidade < 0 or op.preco < 0 or op.custos < 0:
            raise ValueError("Quantidade, preço e custos não podem ser negativos.")
        resultado = None
        if op.tipo == "compra":
            quantidade += op.quantidade
            custo += op.quantidade * op.preco + op.custos
        elif op.tipo == "bonificacao":
            quantidade += op.quantidade
            custo += op.quantidade * op.preco
        elif op.tipo == "desdobro":
            quantidade += op.quantidade
        elif op.tipo == "amortizacao":
            custo = max(custo - op.preco * quantidade, 0.0)
        else:  # venda ou grupamento: saem ações
            if op.quantidade > quantidade + _QUASE_ZERO:
                raise ValueError("Saem mais ações do que há na posição.")
            if op.tipo == "venda":
                custo_da_venda = custo / quantidade * op.quantidade
                resultado = op.quantidade * op.preco - op.custos - custo_da_venda
                custo -= custo_da_venda
            quantidade -= op.quantidade
            if quantidade <= _QUASE_ZERO:
                quantidade = custo = (
                    0.0  # vendeu tudo: a próxima compra recomeça a média
                )
        medio = custo / quantidade if quantidade > _QUASE_ZERO else None
        linhas.append(Linha(op.tipo, quantidade, custo, medio, resultado))
    return linhas
