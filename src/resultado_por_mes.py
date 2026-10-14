"""O resultado realizado em cada mês, a partir da negociação da B3 (`src/negociacao_b3.py`).

Três passos, na ordem:

1. **Day trade:** num mesmo dia e num mesmo código, a quantidade de day trade é a menor entre a
   comprada e a vendida. O resultado sai pelos preços médios de compra e de venda do dia. O que
   sobra vira uma compra ou uma venda comum, pelo preço médio do dia (a regra usual da Receita).
2. **Operações comuns:** o mesmo custo médio da tela "Dividendos e custo médio"
   (`src/dividendos_e_custo.py`): cada venda dá o valor da venda menos o preço médio × quantidade.
   Desdobros, grupamentos, bonificações e amortizações só aparecem na movimentação: quando ela vem
   junto (`eventos`), entram na sequência do custo.
3. **Futuros:** o dia que zera dá o que entrou nas vendas menos o que saiu nas compras (o Valor da
   planilha já vem multiplicado pelo tamanho do contrato). O dia que não zera fica de fora: o
   ajuste diário de quem carrega a posição não vem na planilha.

Honestidade com os números: uma venda de ação comprada antes do período não vira lucro; o ativo
fica sem resultado, com o motivo. O resultado é bruto (a planilha não traz corretagem,
emolumentos nem o IR retido) e não é cálculo de imposto.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from src import dividendos_e_custo as dc
from src.dividendos_e_custo import Lancamento
from src.negociacao_b3 import NegociacaoB3, Negocio

# eventos da movimentação que mudam a quantidade ou o custo sem ser compra nem venda
EVENTOS_DO_CUSTO = (
    *dc.ENTRAM_SEM_CUSTO,
    *dc.SAEM_SEM_CUSTO,
    *dc.TIPOS_QUE_ABATEM_O_CUSTO,
)
MOTIVO_SEM_HISTORICO = (
    "A negociação começa depois da primeira compra (saíram mais ações do que entraram). "
    "Baixe a negociação desde a primeira compra para ver o resultado das vendas."
)
AVISO_SEM_A_MOVIMENTACAO = (
    "Sem a movimentação, desdobros, grupamentos, bonificações e amortizações não entram nas "
    "contas: se algum ativo teve um deles no período, o resultado dele pode não bater. Envie "
    "também a movimentação para incluí-los."
)
NOTA_DO_RESULTADO = (
    "Resultado realizado: o que entrou com as vendas menos o custo do que foi vendido, pelo preço "
    "médio. O day trade (compra e venda do mesmo ativo no mesmo dia) aparece separado. É bruto: "
    "a planilha da B3 não traz corretagem, emolumentos nem o IR retido na fonte. Não é cálculo "
    "de imposto nem recomendação; para declarar, confira com as notas de corretagem ou um "
    "contador."
)


@dataclass(frozen=True)
class Mes:
    ano: int
    mes: int
    acoes_comum: float = 0.0
    acoes_day_trade: float = 0.0
    fiis: float = 0.0  # FIIs e Fiagros, comum e day trade
    futuros: float = 0.0  # só day trade
    outros: float = 0.0  # ETFs e códigos 11 sem nome
    vendas_de_acoes: float = (
        0.0  # o que entrou com as vendas comuns de ações (sem day trade)
    )

    @property
    def total(self) -> float:
        return (
            self.acoes_comum
            + self.acoes_day_trade
            + self.fiis
            + self.futuros
            + self.outros
        )


@dataclass(frozen=True)
class ResultadoPorMes:
    meses: tuple[Mes, ...]  # do mais velho ao mais novo
    sem_resultado: tuple[tuple[str, str], ...]  # (código, motivo), pelo código
    avisos: tuple[str, ...] = field(default=())


@dataclass
class _Dia:
    """Os negócios de um código num dia, somados por lado."""

    qtd_compra: float = 0.0
    valor_compra: float = 0.0
    qtd_venda: float = 0.0
    valor_venda: float = 0.0

    def somar(self, negocio: Negocio) -> None:
        if negocio.compra:
            self.qtd_compra += negocio.quantidade
            self.valor_compra += negocio.valor
        else:
            self.qtd_venda += negocio.quantidade
            self.valor_venda += negocio.valor


# colunas de `Mes` onde entra o resultado de cada classe (comum, day trade)
_COLUNAS = {
    "acao": ("acoes_comum", "acoes_day_trade"),
    "fii": ("fiis", "fiis"),
    "outros": ("outros", "outros"),
}


class _Meses:
    def __init__(self) -> None:
        self._valores: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

    def somar(self, dia: date, coluna: str, valor: float) -> None:
        self._valores[(dia.year, dia.month)][coluna] += valor

    def tocar(self, dia: date) -> None:
        """Garante o mês na tabela, mesmo sem resultado (ex.: só compras)."""
        self._valores.setdefault((dia.year, dia.month), defaultdict(float))

    def tupla(self) -> tuple[Mes, ...]:
        return tuple(
            Mes(ano, mes, **dict(colunas))
            for (ano, mes), colunas in sorted(self._valores.items())
        )


def _futuros(dias: dict[tuple[date, str], _Dia], meses: _Meses) -> int:
    """Soma os dias de futuro que zeram; devolve quantos dias ficaram de fora."""
    de_fora = 0
    for (dia, _codigo), soma in dias.items():
        meses.tocar(dia)
        if abs(soma.qtd_compra - soma.qtd_venda) > 1e-9:
            de_fora += 1
            continue
        meses.somar(dia, "futuros", soma.valor_venda - soma.valor_compra)
    return de_fora


def _separar_day_trade(
    dias: dict[tuple[date, str], _Dia], classes: dict[str, str], meses: _Meses
) -> list[Lancamento]:
    """Soma o day trade de cada dia e devolve o que sobra como compra ou venda comum."""
    comuns = []
    for (dia, codigo), soma in sorted(dias.items()):
        meses.tocar(dia)
        coluna_comum, coluna_day_trade = _COLUNAS[classes[codigo]]
        medio_compra = soma.valor_compra / soma.qtd_compra if soma.qtd_compra else 0.0
        medio_venda = soma.valor_venda / soma.qtd_venda if soma.qtd_venda else 0.0
        day_trade = min(soma.qtd_compra, soma.qtd_venda)
        if day_trade:
            meses.somar(dia, coluna_day_trade, day_trade * (medio_venda - medio_compra))
        if sobra := soma.qtd_compra - day_trade:
            comuns.append(
                Lancamento(dia, codigo, "compra", sobra, sobra * medio_compra)
            )
        if sobra := soma.qtd_venda - day_trade:
            comuns.append(Lancamento(dia, codigo, "venda", sobra, sobra * medio_venda))
            if coluna_comum == "acoes_comum":
                meses.somar(dia, "vendas_de_acoes", sobra * medio_venda)
    return comuns


def resultado_por_mes(
    negociacao: NegociacaoB3, eventos: Sequence[Lancamento] | None = None
) -> ResultadoPorMes:
    """O resultado realizado de cada mês da negociação.

    `eventos` são os lançamentos da movimentação (`ler_movimentacao`); só os que mudam a
    quantidade ou o custo sem ser compra nem venda (desdobro, amortização...) são usados.
    None quando a movimentação não foi enviada: aí vem um aviso.
    """
    classes = {n.codigo: n.classe for n in negociacao.negocios}
    futuros: dict[tuple[date, str], _Dia] = defaultdict(_Dia)
    a_vista: dict[tuple[date, str], _Dia] = defaultdict(_Dia)
    for negocio in negociacao.negocios:
        destino = futuros if negocio.classe == "futuro" else a_vista
        destino[(negocio.data, negocio.codigo)].somar(negocio)
    meses = _Meses()
    futuros_de_fora = _futuros(futuros, meses)
    comuns = _separar_day_trade(a_vista, classes, meses)
    comuns += [
        e for e in eventos or () if e.tipo in EVENTOS_DO_CUSTO and e.codigo in classes
    ]
    sem_resultado = []
    for custo in dc.custo_medio(comuns):
        if not custo.completo:
            sem_resultado.append((custo.codigo, _motivo(custo.motivo)))
            continue
        coluna_comum = _COLUNAS[classes[custo.codigo]][0]
        for venda in custo.vendas:
            meses.somar(venda.data, coluna_comum, venda.resultado)
    avisos = []
    if futuros_de_fora:
        dias = "1 dia" if futuros_de_fora == 1 else f"{futuros_de_fora} dias"
        avisos.append(
            f"{dias} de futuros não zeraram a posição no próprio dia e ficaram de fora: o ajuste "
            "diário de quem carrega o contrato de um dia para outro não vem na planilha."
        )
    if eventos is None and any(c != "futuro" for c in classes.values()):
        avisos.append(AVISO_SEM_A_MOVIMENTACAO)
    return ResultadoPorMes(meses.tupla(), tuple(sem_resultado), tuple(avisos))


def _motivo(motivo: str | None) -> str:
    """O motivo do custo médio, dito em termos da negociação."""
    if motivo in (dc.MOTIVO_HISTORICO_INCOMPLETO, dc.MOTIVO_SEM_COMPRA):
        return MOTIVO_SEM_HISTORICO
    return motivo or MOTIVO_SEM_HISTORICO
