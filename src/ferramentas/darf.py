"""DARF de ações: o imposto de um mês de operações na bolsa, e o que passa para o mês seguinte.

Só ações no mercado à vista (operações comuns e day trade). As regras, com a fonte oficial, ficam
em `src/regras_de_imposto.py`: 15% nas comuns e 20% no day trade; isento quando as vendas comuns de
ações no mês não passam de R$ 20.000 (o lucro isento não gasta o prejuízo acumulado); prejuízo
compensa lucro do mesmo tipo, no mês ou depois, sem prazo; o IR retido na fonte abate o imposto do
mês e o que sobra fica para os seguintes; DARF abaixo de R$ 10 não se paga e acumula.

Fica de fora: FII, ETF, BDR, opções, termo e futuros, que têm regras próprias, e custos que a pessoa
não descontou do resultado. Não substitui um contador.
"""

from dataclasses import dataclass

from src import regras_de_imposto as regras

ALIQUOTA_COMUM = float(regras.valor("aliquota_comum"))
ALIQUOTA_DAY_TRADE = float(regras.valor("aliquota_day_trade"))
ISENCAO_VENDAS_NO_MES = float(regras.valor("isencao_vendas_no_mes"))
DARF_MINIMO = float(regras.valor("darf_minimo"))
CODIGO_DO_DARF = str(regras.valor("codigo_do_darf"))
MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip


@dataclass(frozen=True)
class Mes:
    """As operações de um mês, já com os custos descontados do resultado (lucro + ou prejuízo −)."""

    vendas_comuns: float = 0  # total vendido em ações no mês, sem contar o day trade
    resultado_comum: float = 0
    resultado_day_trade: float = 0
    irrf_comum: float = 0  # o "dedo-duro" de 0,005% da nota de corretagem
    irrf_day_trade: float = 0  # o 1% retido sobre o ganho do day trade


@dataclass(frozen=True)
class Saldos:
    """O que vem dos meses anteriores (e o que passa para o seguinte)."""

    prejuizo_comum: float = 0
    prejuizo_day_trade: float = 0
    irrf_a_compensar: float = 0
    imposto_abaixo_do_minimo: float = 0


@dataclass(frozen=True)
class Apuracao:
    isento: bool
    base_comum: float
    base_day_trade: float
    imposto_comum: float
    imposto_day_trade: float
    irrf_usado: float
    darf: float  # a pagar neste mês (0 se isento, sem imposto ou abaixo de R$ 10)
    saldos_seguintes: Saldos


def _conferir(mes: Mes, saldos: Saldos) -> None:
    if mes.vendas_comuns < 0:
        raise ValueError("O total de vendas não pode ser negativo.")
    if mes.irrf_comum < 0 or mes.irrf_day_trade < 0 or saldos.irrf_a_compensar < 0:
        raise ValueError("O imposto retido não pode ser negativo.")
    if saldos.prejuizo_comum < 0 or saldos.prejuizo_day_trade < 0:
        raise ValueError("Informe o prejuízo a compensar como um valor positivo.")
    if not 0 <= saldos.imposto_abaixo_do_minimo < DARF_MINIMO:
        raise ValueError(
            f"O imposto acumulado abaixo de R$ {DARF_MINIMO:.0f} fica entre 0 e 10."
        )


def _compensar(resultado: float, prejuizo: float) -> tuple[float, float]:
    """(base tributável, prejuízo que sobra) de um resultado com o prejuízo acumulado."""
    if resultado < 0:
        return 0.0, prejuizo - resultado
    usado = min(prejuizo, resultado)
    return resultado - usado, prejuizo - usado


def apurar_mes(mes: Mes, saldos: Saldos) -> Apuracao:
    """O imposto do mês e os saldos que passam para o mês seguinte."""
    _conferir(mes, saldos)
    isento = mes.vendas_comuns <= ISENCAO_VENDAS_NO_MES and mes.resultado_comum > 0
    if isento:  # o lucro isento não gasta o prejuízo acumulado
        base_comum, prejuizo_comum = 0.0, saldos.prejuizo_comum
    else:
        base_comum, prejuizo_comum = _compensar(
            mes.resultado_comum, saldos.prejuizo_comum
        )
    base_dt, prejuizo_dt = _compensar(
        mes.resultado_day_trade, saldos.prejuizo_day_trade
    )
    imposto_comum = base_comum * ALIQUOTA_COMUM
    imposto_dt = base_dt * ALIQUOTA_DAY_TRADE
    irrf = saldos.irrf_a_compensar + mes.irrf_comum + mes.irrf_day_trade
    irrf_usado = min(imposto_comum + imposto_dt, irrf)
    devido = imposto_comum + imposto_dt - irrf_usado + saldos.imposto_abaixo_do_minimo
    paga = devido >= DARF_MINIMO
    return Apuracao(
        isento=isento,
        base_comum=base_comum,
        base_day_trade=base_dt,
        imposto_comum=imposto_comum,
        imposto_day_trade=imposto_dt,
        irrf_usado=irrf_usado,
        darf=devido if paga else 0.0,
        saldos_seguintes=Saldos(
            prejuizo_comum=prejuizo_comum,
            prejuizo_day_trade=prejuizo_dt,
            irrf_a_compensar=irrf - irrf_usado,
            imposto_abaixo_do_minimo=0.0 if paga else devido,
        ),
    )


def apurar_meses(meses: list[Mes], saldos: Saldos) -> list[Apuracao]:
    """Mês a mês, levando os saldos de um para o outro."""
    apuracoes = []
    for mes in meses:
        apuracoes.append(apurar_mes(mes, saldos))
        saldos = apuracoes[-1].saldos_seguintes
    return apuracoes


def vencimento(ano: int, mes: int) -> str:
    """O prazo do DARF das operações de `mes`/`ano`: o último dia útil do mês seguinte."""
    ano_seguinte, mes_seguinte = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return f"último dia útil de {MESES[mes_seguinte - 1]} de {ano_seguinte}"
