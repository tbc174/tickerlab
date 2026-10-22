"""Cascata de pagamentos (waterfall) determinística de uma securitização de recebíveis.

É a conta que o gestor de FIDC faz todo mês (Resolução CVM 175, Anexo II, art. 33): o caixa que
entrou é distribuído na ordem da estrutura, e a perda do mês abate as classes de baixo para cima.
Dinheiro em **centavos inteiros** (nada de ponto flutuante) e dado 100% sintético nos testes:
nenhum número aqui representa operação, oferta, rating ou condição de mercado real.

Regras do motor (escritas antes do código, ADR 0006; protótipo D do dossiê de 20/10/2026):

1. Em cada período, caixa disponível = reserva do período anterior + principal recebido + juros
   recebidos + recuperações.
2. Ordem de pagamento: despesas → juros das classes por senioridade → recomposição da reserva até o
   mínimo → principal (limitado ao principal recebido mais as recuperações: juros não amortizam) →
   turbo, se houver meta de sobrecolateralização → residual à classe mais subordinada.
3. A perda do período abate o saldo do pool; se o pool ficar menor que a soma das classes, a
   diferença abate o principal das classes de baixo para cima (alocação de perda).
4. Conservação de caixa: em todo período, reserva inicial + entradas == saídas + reserva final, ao
   centavo. O motor lança erro em vez de devolver resultado errado.

Regras da 0.2.0 (cada uma com teste escrito antes; ideia do securitization-lab, MIT, reescrita sem
copiar). Todas desligadas por padrão: sem elas o resultado é, ao centavo, o da 0.1.0.

5. **Mesma senioridade (pari passu):** classes com a mesma senioridade formam um grupo. O que não
   cobre o grupo inteiro é dividido pelos maiores restos: juros pelo devido, principal e perda pelo
   saldo. Vale sempre (a 0.1.0 recusava senioridade repetida).
6. **Juros não pagos acumulam** (`juros_acumulam`): o que faltou num mês fica em atraso, rende a
   taxa da classe e é devido no mês seguinte junto com os juros do mês, antes de qualquer principal.
   Fica desligado por padrão porque a cota sênior de FIDC tem meta de rentabilidade, não dívida; em
   CRI e CRA o juro é dívida e acumula.
7. **Principal pro rata** (`principal="pro_rata"`): o principal vai a todas as classes pelo saldo.
   **Gatilho de perda acumulada** (`gatilho_de_perda`): quando a perda acumulada passa (estritamente)
   da fração dada do pool original, o principal volta a sequencial e não volta mais. O gatilho olha a
   perda até o mês anterior: na data de pagamento, a perda do mês ainda não está fechada.
8. **Sobrecolateralização com turbo** (`meta_de_sobrecolateralizacao`): a soma das classes acima do
   grupo mais subordinado não pode passar de (1 - meta) × pool do fim do mês. Se passar, o caixa que
   iria ao residual amortiza essas classes de cima para baixo até a meta (o turbo). É a única saída do
   juro para o principal.

O que a versão 0.2.0 **não** faz: juros de mora, custo variável, indexador (hoje taxa mensal fixa),
gatilhos de caixa ou de inadimplência (só o de perda acumulada) e recomposição de perda já alocada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby

VERSAO_DO_CALCULO = "cascata 0.2.0"
CENTAVOS_POR_REAL = 100
SEQUENCIAL = "sequencial"
PRO_RATA = "pro_rata"


@dataclass(frozen=True)
class Classe:
    """Uma classe de cota ou tranche; senioridade 1 é a mais sênior (paga primeiro, perde por último)."""

    nome: str
    senioridade: int
    saldo_inicial: int  # centavos
    taxa_mensal: float  # fração ao mês: 0.01 = 1%


@dataclass(frozen=True)
class Regras:
    """As regras da 0.2.0 (itens 6 a 8 do módulo); o padrão desliga todas e reproduz a 0.1.0."""

    juros_acumulam: bool = False
    principal: str = SEQUENCIAL  # "sequencial" ou "pro_rata"
    gatilho_de_perda: float | None = None  # fração do pool original; None = sem gatilho
    meta_de_sobrecolateralizacao: float | None = (
        None  # fração do pool; None = sem turbo
    )

    def __post_init__(self) -> None:
        if self.principal not in (SEQUENCIAL, PRO_RATA):
            raise ValueError(f"regime de principal desconhecido: {self.principal}")
        if self.gatilho_de_perda is not None and not 0.0 < self.gatilho_de_perda <= 1.0:
            raise ValueError("gatilho de perda fora de (0, 1]")
        meta = self.meta_de_sobrecolateralizacao
        if meta is not None and not 0.0 <= meta < 1.0:
            raise ValueError("meta de sobrecolateralização fora de [0, 1)")


REGRAS_DA_0_1_0 = Regras()  # tudo desligado: o resultado da 0.1.0, ao centavo


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
    juros_devidos: dict[
        str, int
    ]  # do mês, mais o atraso corrigido quando os juros acumulam
    juros_pagos: dict[str, int]
    juros_em_atraso: dict[str, int]  # o que ficou devido para o mês seguinte
    reserva_final: int
    principal_pago: dict[str, int]  # inclui o turbo
    turbo_pago: dict[str, int]
    residual: int
    perda_alocada: dict[str, int]
    saldo_das_classes: dict[str, int]
    saldo_do_pool: int
    regime: str  # do principal neste período: "sequencial" ou "pro_rata"
    gatilho_disparado: bool
    versao_do_calculo: str = VERSAO_DO_CALCULO

    @property
    def saidas(self) -> int:
        """Tudo o que saiu do caixa no período: despesas, juros, principal (com o turbo) e residual."""
        return (
            self.despesas_pagas
            + sum(self.juros_pagos.values())
            + sum(self.principal_pago.values())
            + self.residual
        )


@dataclass
class Operacao:
    """A estrutura: classes, saldo do pool, reserva e regras. Guarda os saldos correntes enquanto roda."""

    classes: list[Classe]
    saldo_do_pool: int
    reserva_minima: int
    reserva_inicial: int = 0
    regras: Regras = REGRAS_DA_0_1_0
    saldos: dict[str, int] = field(default_factory=dict, init=False)
    atrasos: dict[str, int] = field(default_factory=dict, init=False)
    perda_acumulada: int = field(default=0, init=False)
    gatilho_disparado: bool = field(default=False, init=False)
    limite_do_gatilho: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        nomes = [c.nome for c in self.classes]
        if not nomes:
            raise ValueError("operação sem classes")
        if len(nomes) != len(set(nomes)):
            raise ValueError("classes com nome repetido")
        if any(c.saldo_inicial < 0 for c in self.classes):
            raise ValueError("classe com saldo negativo")
        if (
            self.saldo_do_pool < 0
            or self.reserva_minima < 0
            or self.reserva_inicial < 0
        ):
            raise ValueError("pool ou reserva negativos")
        self.saldos = {c.nome: c.saldo_inicial for c in self.classes}
        self.atrasos = {c.nome: 0 for c in self.classes}
        if self.regras.gatilho_de_perda is not None:
            self.limite_do_gatilho = int(
                self.saldo_do_pool * self.regras.gatilho_de_perda
            )

    @property
    def ordenadas(self) -> list[Classe]:
        """As classes da mais sênior para a mais subordinada."""
        return sorted(self.classes, key=lambda c: c.senioridade)

    @property
    def grupos(self) -> list[list[Classe]]:
        """As classes agrupadas por senioridade (pari passu), do grupo mais sênior ao mais subordinado."""
        return [
            list(g) for _, g in groupby(self.ordenadas, key=lambda c: c.senioridade)
        ]


def juros_devidos(classe: Classe, saldo: int) -> int:
    """Juros do mês sobre o saldo, arredondados para baixo ao centavo (regra fixa e declarada)."""
    return int(saldo * classe.taxa_mensal)


def ratear(valor: int, pesos: dict[str, int]) -> dict[str, int]:
    """Divide `valor` centavos na proporção dos pesos, fechando a soma pelos maiores restos.

    Empate de resto vai a quem vem antes nos pesos (a ordem da estrutura). Pesos todos zero: nada a dividir.
    """
    total = sum(pesos.values())
    if total == 0:
        return {nome: 0 for nome in pesos}
    partes = {nome: valor * peso // total for nome, peso in pesos.items()}
    sobra = valor - sum(partes.values())
    por_resto = sorted(
        enumerate(pesos.items()),
        key=lambda item: (-(valor * item[1][1] % total), item[0]),
    )
    for _, (nome, _) in por_resto[:sobra]:
        partes[nome] += 1
    return partes


def _pagar_por_senioridade(
    grupos: list[list[Classe]], caixa: int, devido: dict[str, int]
) -> tuple[dict[str, int], int]:
    """Paga grupo a grupo, do mais sênior ao mais subordinado; o grupo que o caixa não cobre divide pelo devido."""
    pago: dict[str, int] = {}
    for grupo in grupos:
        do_grupo = {c.nome: devido[c.nome] for c in grupo}
        total = sum(do_grupo.values())
        pago.update(do_grupo if caixa >= total else ratear(caixa, do_grupo))
        caixa -= min(caixa, total)
    return pago, caixa


def _pagar_pro_rata(op: Operacao, valor: int) -> dict[str, int]:
    """Principal a todas as classes pelo saldo; o que passa da soma dos saldos não é pago (vai ao residual)."""
    if valor >= sum(op.saldos.values()):
        return dict(op.saldos)
    return ratear(valor, op.saldos)


def _pagar_juros(
    op: Operacao, caixa: int
) -> tuple[dict[str, int], dict[str, int], int]:
    """Juros do mês, mais o atraso corrigido se a regra 6 estiver ligada; atualiza os atrasos da operação."""
    devido = {
        c.nome: juros_devidos(c, op.saldos[c.nome])
        + op.atrasos[c.nome]
        + juros_devidos(c, op.atrasos[c.nome])
        for c in op.classes
    }
    pago, caixa = _pagar_por_senioridade(op.grupos, caixa, devido)
    for nome, valor in devido.items():
        op.atrasos[nome] = valor - pago[nome] if op.regras.juros_acumulam else 0
    return devido, pago, caixa


def _regime_do_principal(op: Operacao) -> str:
    """Sequencial, pro rata ou sequencial porque o gatilho de perda disparou (e não volta)."""
    if op.limite_do_gatilho is not None and op.perda_acumulada > op.limite_do_gatilho:
        op.gatilho_disparado = True
    if op.regras.principal == SEQUENCIAL or op.gatilho_disparado:
        return SEQUENCIAL
    return PRO_RATA


def _turbo(op: Operacao, caixa: int, pool_do_fim_do_mes: int) -> dict[str, int]:
    """O excesso que amortiza as classes acima do grupo mais subordinado até a meta de sobrecolateralização."""
    meta = op.regras.meta_de_sobrecolateralizacao
    acima = op.grupos[:-1]
    if meta is None or not acima:
        return {c.nome: 0 for c in op.classes}
    notas = sum(op.saldos[c.nome] for grupo in acima for c in grupo)
    limite = pool_do_fim_do_mes - int(pool_do_fim_do_mes * meta)
    turbo, _ = _pagar_por_senioridade(
        acima, min(caixa, max(0, notas - limite)), op.saldos
    )
    return {c.nome: turbo.get(c.nome, 0) for c in op.classes}


def _alocar_perda(op: Operacao) -> dict[str, int]:
    """Se o pool ficou menor que a soma das classes, abate a diferença de baixo para cima (pari passu no grupo)."""
    perda_alocada = {c.nome: 0 for c in op.classes}
    excesso = sum(op.saldos.values()) - op.saldo_do_pool
    for grupo in reversed(op.grupos):
        if excesso <= 0:
            break
        do_grupo = {c.nome: op.saldos[c.nome] for c in grupo}
        total = sum(do_grupo.values())
        cortes = do_grupo if excesso >= total else ratear(excesso, do_grupo)
        for nome, corte in cortes.items():
            perda_alocada[nome] = corte
            op.saldos[nome] -= corte
        excesso -= min(excesso, total)
    return perda_alocada


def _amortizar(op: Operacao, pagos: dict[str, int]) -> None:
    for nome, pago in pagos.items():
        op.saldos[nome] -= pago


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

    devidos, juros_pagos, caixa = _pagar_juros(op, caixa)

    reserva_final = min(caixa, op.reserva_minima)
    caixa -= reserva_final

    # juros não amortizam: o principal só sai do principal recebido e das recuperações
    para_principal = min(caixa, p.principal_recebido + p.recuperacoes)
    regime = _regime_do_principal(op)
    if regime == PRO_RATA:
        principal_pago = _pagar_pro_rata(op, para_principal)
    else:
        principal_pago, _ = _pagar_por_senioridade(op.grupos, para_principal, op.saldos)
    _amortizar(op, principal_pago)
    caixa -= sum(principal_pago.values())

    op.saldo_do_pool = max(0, op.saldo_do_pool - p.principal_recebido - p.perda)
    turbo_pago = _turbo(op, caixa, op.saldo_do_pool)
    _amortizar(op, turbo_pago)
    caixa -= sum(turbo_pago.values())
    principal_pago = {
        nome: principal_pago[nome] + turbo_pago[nome] for nome in principal_pago
    }

    residual = (
        caixa  # o que sobrou, inclusive excesso de juros, vai à classe mais subordinada
    )

    perda_alocada = _alocar_perda(op)
    op.perda_acumulada += p.perda

    resultado = Resultado(
        periodo=numero,
        entradas=entradas,
        reserva_inicial=reserva,
        despesas_pagas=despesas_pagas,
        juros_devidos=devidos,
        juros_pagos=juros_pagos,
        juros_em_atraso=dict(op.atrasos),
        reserva_final=reserva_final,
        principal_pago=principal_pago,
        turbo_pago=turbo_pago,
        residual=residual,
        perda_alocada=perda_alocada,
        saldo_das_classes=dict(op.saldos),
        saldo_do_pool=op.saldo_do_pool,
        regime=regime,
        gatilho_disparado=op.gatilho_disparado,
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
