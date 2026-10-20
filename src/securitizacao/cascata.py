"""Cascata de pagamentos (waterfall) determinística de uma securitização de recebíveis.

É a conta que o gestor de FIDC faz todo mês (Resolução CVM 175, Anexo II, art. 33): o caixa que
entrou é distribuído na ordem da estrutura, e a perda do mês abate as classes de baixo para cima.
Dinheiro em **centavos inteiros** (nada de ponto flutuante) e dado 100% sintético nos testes:
nenhum número aqui representa operação, oferta, rating ou condição de mercado real.

Regras do motor (escritas antes do código, ADR 0006; protótipo D do dossiê de 20/10/2026):

1. Em cada período, caixa disponível = reserva do período anterior + principal recebido + juros
   recebidos + recuperações.
2. Ordem de pagamento, sequencial: despesas → juros das classes por senioridade → recomposição da
   reserva até o mínimo → principal das classes por senioridade (limitado ao principal recebido mais
   as recuperações: juros não amortizam) → residual à classe mais subordinada.
3. A perda do período abate o saldo do pool; se o pool ficar menor que a soma das classes, a
   diferença abate o principal das classes de baixo para cima (alocação de perda).
4. Conservação de caixa: em todo período, reserva inicial + entradas == saídas + reserva final, ao
   centavo. O motor lança erro em vez de devolver resultado errado.

O que a versão 0.1.0 **não** faz (cada item vira teste antes do código): pro rata, gatilhos que
mudam o regime, juros de mora, custo variável, indexador (hoje taxa mensal fixa), duas classes na
mesma senioridade.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VERSAO_DO_CALCULO = "cascata 0.1.0"
CENTAVOS_POR_REAL = 100


@dataclass(frozen=True)
class Classe:
    """Uma classe de cota ou tranche; senioridade 1 é a mais sênior (paga primeiro, perde por último)."""

    nome: str
    senioridade: int
    saldo_inicial: int  # centavos
    taxa_mensal: float  # fração ao mês: 0.01 = 1%


@dataclass(frozen=True)
class Periodo:
    """Fluxo bruto do pool num mês, em centavos."""

    principal_recebido: int
    juros_recebidos: int
    recuperacoes: int
    perda: int  # inadimplência reconhecida no mês (abate o pool)
    despesas: int


@dataclass
class Resultado:
    """O que a cascata pagou num período e como ficaram os saldos (centavos)."""

    periodo: int
    entradas: int
    reserva_inicial: int
    despesas_pagas: int
    juros_pagos: dict[str, int]
    reserva_final: int
    principal_pago: dict[str, int]
    residual: int
    perda_alocada: dict[str, int]
    saldo_das_classes: dict[str, int]
    saldo_do_pool: int
    versao_do_calculo: str = VERSAO_DO_CALCULO

    @property
    def saidas(self) -> int:
        """Tudo o que saiu do caixa no período: despesas, juros, principal e residual."""
        return (
            self.despesas_pagas
            + sum(self.juros_pagos.values())
            + sum(self.principal_pago.values())
            + self.residual
        )


@dataclass
class Operacao:
    """A estrutura: classes, saldo do pool e reserva. Guarda os saldos correntes enquanto roda."""

    classes: list[Classe]
    saldo_do_pool: int
    reserva_minima: int
    reserva_inicial: int = 0
    saldos: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        nomes = [c.nome for c in self.classes]
        if not nomes:
            raise ValueError("operação sem classes")
        if len(nomes) != len(set(nomes)):
            raise ValueError("classes com nome repetido")
        senioridades = [c.senioridade for c in self.classes]
        if len(senioridades) != len(set(senioridades)):
            raise ValueError(
                "duas classes com a mesma senioridade (a versão 0.1.0 só é sequencial)"
            )
        if any(c.saldo_inicial < 0 for c in self.classes):
            raise ValueError("classe com saldo negativo")
        if (
            self.saldo_do_pool < 0
            or self.reserva_minima < 0
            or self.reserva_inicial < 0
        ):
            raise ValueError("pool ou reserva negativos")
        self.saldos = {c.nome: c.saldo_inicial for c in self.classes}

    @property
    def ordenadas(self) -> list[Classe]:
        """As classes da mais sênior para a mais subordinada."""
        return sorted(self.classes, key=lambda c: c.senioridade)


def juros_devidos(classe: Classe, saldo: int) -> int:
    """Juros do mês sobre o saldo, arredondados para baixo ao centavo (regra fixa e declarada)."""
    return int(saldo * classe.taxa_mensal)


def _pagar_por_senioridade(
    op: Operacao, caixa: int, devido: dict[str, int]
) -> tuple[dict[str, int], int]:
    """Paga a cada classe, da mais sênior para a mais subordinada, o devido ou o que sobrar."""
    pago: dict[str, int] = {}
    for c in op.ordenadas:
        pago[c.nome] = min(caixa, devido[c.nome])
        caixa -= pago[c.nome]
    return pago, caixa


def _alocar_perda(op: Operacao) -> dict[str, int]:
    """Se o pool ficou menor que a soma das classes, abate a diferença de baixo para cima."""
    perda_alocada = {c.nome: 0 for c in op.classes}
    excesso = sum(op.saldos.values()) - op.saldo_do_pool
    for c in reversed(op.ordenadas):
        if excesso <= 0:
            break
        corte = min(excesso, op.saldos[c.nome])
        perda_alocada[c.nome] = corte
        op.saldos[c.nome] -= corte
        excesso -= corte
    return perda_alocada


def rodar_periodo(
    op: Operacao, numero: int, p: Periodo, reserva: int
) -> tuple[Resultado, int]:
    """Aplica a cascata a um período; devolve o resultado e a reserva que passa ao período seguinte."""
    if (
        min(
            p.principal_recebido, p.juros_recebidos, p.recuperacoes, p.perda, p.despesas
        )
        < 0
    ):
        raise ValueError(f"fluxo negativo no período {numero}")
    entradas = p.principal_recebido + p.juros_recebidos + p.recuperacoes
    caixa = reserva + entradas

    despesas_pagas = min(caixa, p.despesas)
    caixa -= despesas_pagas

    juros = {c.nome: juros_devidos(c, op.saldos[c.nome]) for c in op.classes}
    juros_pagos, caixa = _pagar_por_senioridade(op, caixa, juros)

    reserva_final = min(caixa, op.reserva_minima)
    caixa -= reserva_final

    # juros não amortizam: o principal só sai do principal recebido e das recuperações
    para_principal = min(caixa, p.principal_recebido + p.recuperacoes)
    principal_pago, _ = _pagar_por_senioridade(op, para_principal, dict(op.saldos))
    for nome, pago in principal_pago.items():
        op.saldos[nome] -= pago
    caixa -= sum(principal_pago.values())

    residual = (
        caixa  # o que sobrou, inclusive excesso de juros, vai à classe mais subordinada
    )

    op.saldo_do_pool = max(0, op.saldo_do_pool - p.principal_recebido - p.perda)
    perda_alocada = _alocar_perda(op)

    resultado = Resultado(
        periodo=numero,
        entradas=entradas,
        reserva_inicial=reserva,
        despesas_pagas=despesas_pagas,
        juros_pagos=juros_pagos,
        reserva_final=reserva_final,
        principal_pago=principal_pago,
        residual=residual,
        perda_alocada=perda_alocada,
        saldo_das_classes=dict(op.saldos),
        saldo_do_pool=op.saldo_do_pool,
    )
    if reserva + entradas != resultado.saidas + reserva_final:
        raise AssertionError(
            f"caixa não conserva no período {numero}: "
            f"{reserva + entradas} != {resultado.saidas + reserva_final}"
        )
    return resultado, reserva_final


def rodar(op: Operacao, periodos: list[Periodo]) -> list[Resultado]:
    """Roda a cascata por todos os períodos; a mesma estrutura e os mesmos fluxos dão sempre o mesmo resultado."""
    reserva = op.reserva_inicial
    resultados: list[Resultado] = []
    for numero, p in enumerate(periodos, start=1):
        resultado, reserva = rodar_periodo(op, numero, p, reserva)
        resultados.append(resultado)
    return resultados


def reconciliar(reserva_inicial: int, resultados: list[Resultado]) -> dict[str, int]:
    """Totais para o relatório: tudo o que entrou é igual a tudo o que saiu mais a reserva que ficou."""
    entradas = reserva_inicial + sum(r.entradas for r in resultados)
    saidas = sum(r.saidas for r in resultados)
    reserva_final = resultados[-1].reserva_final if resultados else reserva_inicial
    return {
        "entradas": entradas,
        "saidas": saidas,
        "reserva_final": reserva_final,
        "diferenca": entradas - saidas - reserva_final,
    }
