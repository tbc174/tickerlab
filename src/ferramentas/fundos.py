"""Fundo de renda fixa pelo CDI, mês a mês: a taxa de administração, a de performance e o
come-cotas, para comparar com um CDB do mesmo prazo (`renda_fixa.comparar`).

- O fundo rende um percentual do CDI, pela mesma conta do CDB (a taxa de cada dia útil, 21 dias
  úteis por mês). A taxa de administração sai do patrimônio todo mês (1/12 da anual, composta).
- A taxa de performance é um percentual do que o fundo rendeu acima do CDI no semestre, cobrado a
  cada come-cotas e no resgate. Sem marca d'água: com o mesmo percentual do CDI o mês todo, o fundo
  bate o CDI em todo semestre ou em nenhum.
- Come-cotas (Lei 14.754/2023, art. 17): no último dia útil de maio e de novembro, 15% (longo
  prazo) ou 20% (curto prazo) do que rendeu desde o último. No resgate, o IR pela tabela do fundo
  sobre todo o ganho, menos o que o come-cotas já levou. O come-cotas do mês do resgate entra antes
  dele (o total de imposto é o mesmo).

O mês do come-cotas vem de `mes_inicial` (1 = a aplicação começa em janeiro). Os meses viram dias
corridos pela média (365/12) para a tabela do IR. Ficam de fora: o IOF (a partir de 30 dias é
zero), a compensação de prejuízo entre fundos, a taxa de saída e o prazo de cotização. As regras de
imposto vêm de `src/regras_de_imposto.py`.
"""

from dataclasses import dataclass

from src import regras_de_imposto as regras

PRAZO_MAXIMO = 120  # meses: 10 anos, o prazo máximo do CDB da comparação (renda_fixa)
MESES_DO_COME_COTAS = (5, 11)  # maio e novembro
DIAS_POR_MES = 365 / 12
DIAS_UTEIS_POR_ANO = 252
DIAS_UTEIS_POR_MES = DIAS_UTEIS_POR_ANO / 12


@dataclass(frozen=True)
class Resultado:
    patrimonio_final: float  # depois das taxas e do come-cotas, antes do IR do resgate
    taxa_de_administracao: float  # o total cobrado no prazo
    taxa_de_performance: float
    come_cotas: float
    vezes_do_come_cotas: int  # as vezes em que o come-cotas levou dinheiro
    ir_no_resgate: float
    liquido: float


def _conferir(
    valor: float, meses: int, cdi_ao_ano: float, percentual: float, taxas: list[float]
) -> None:
    if valor <= 0:
        raise ValueError("O valor aplicado precisa ser maior que zero.")
    if meses < 1 or meses > PRAZO_MAXIMO:
        raise ValueError(f"O prazo precisa estar entre 1 e {PRAZO_MAXIMO} meses.")
    if cdi_ao_ano <= -1:
        raise ValueError("O CDI precisa ser maior que -100% ao ano.")
    if percentual < 0:
        raise ValueError("O percentual do CDI não pode ser negativo.")
    if any(t < 0 or t >= 1 for t in taxas):
        raise ValueError("Cada taxa do fundo precisa estar entre 0% e 100%.")


def _rendimento_do_mes(cdi_ao_ano: float, percentual: float) -> float:
    diaria = ((1 + cdi_ao_ano) ** (1 / DIAS_UTEIS_POR_ANO) - 1) * percentual
    return (1 + diaria) ** DIAS_UTEIS_POR_MES - 1


def _mes_do_calendario(mes_inicial: int, mes: int) -> int:
    """O mês do ano (1 a 12) do `mes`-ésimo mês da aplicação (o primeiro é o 1)."""
    return (mes_inicial - 1 + mes - 1) % 12 + 1


@dataclass
class _Carteira:
    """O fundo durante a simulação: o patrimônio, as bases das taxas e o que já foi cobrado."""

    patrimonio: float
    base_do_ir: float  # o patrimônio depois do último come-cotas que levou dinheiro
    referencia: float  # o patrimônio do começo do semestre, corrigido pelo CDI
    administracao: float = 0.0
    performance: float = 0.0
    come_cotas: float = 0.0
    vezes: int = 0

    def render(self, rendimento: float, rendimento_do_cdi: float, fica: float) -> None:
        self.patrimonio *= 1 + rendimento
        self.referencia *= 1 + rendimento_do_cdi
        cobrada = self.patrimonio * (1 - fica)
        self.patrimonio -= cobrada
        self.administracao += cobrada

    def cobrar_performance(self, taxa: float) -> None:
        cobrada = taxa * max(self.patrimonio - self.referencia, 0.0)
        self.patrimonio -= cobrada
        self.performance += cobrada

    def reter_come_cotas(self, aliquota: float) -> None:
        retido = aliquota * max(self.patrimonio - self.base_do_ir, 0.0)
        if retido > 0:  # sem ganho, a perda fica para abater do próximo
            self.patrimonio -= retido
            self.come_cotas += retido
            self.vezes += 1
            self.base_do_ir = self.patrimonio


def simular(
    valor: float,
    meses: int,
    cdi_ao_ano: float,
    percentual_do_cdi: float,
    taxa_de_administracao: float,
    taxa_de_performance: float,
    longo_prazo: bool,
    mes_inicial: int,
) -> Resultado:
    """O fundo aplicado com `valor` por `meses` meses (percentuais e taxas em fração: 1,0 = 100% do
    CDI; 0,01 = 1% ao ano de administração; 0,2 = 20% de performance)."""
    _conferir(
        valor,
        meses,
        cdi_ao_ano,
        percentual_do_cdi,
        [taxa_de_administracao, taxa_de_performance],
    )
    if mes_inicial < 1 or mes_inicial > 12:
        raise ValueError("O mês inicial precisa estar entre 1 (janeiro) e 12.")
    rendimento = _rendimento_do_mes(cdi_ao_ano, percentual_do_cdi)
    rendimento_do_cdi = _rendimento_do_mes(cdi_ao_ano, 1.0)
    fica = (1 - taxa_de_administracao) ** (1 / 12)
    chave = "come_cotas_longo_prazo" if longo_prazo else "come_cotas_curto_prazo"
    aliquota_do_come_cotas = float(regras.valor(chave))
    carteira = _Carteira(valor, valor, valor)
    for mes in range(1, meses + 1):
        carteira.render(rendimento, rendimento_do_cdi, fica)
        e_come_cotas = _mes_do_calendario(mes_inicial, mes) in MESES_DO_COME_COTAS
        if e_come_cotas or mes == meses:
            carteira.cobrar_performance(taxa_de_performance)
            if e_come_cotas:
                carteira.reter_come_cotas(aliquota_do_come_cotas)
            carteira.referencia = carteira.patrimonio  # começa outro semestre
    return _resgatar(carteira, valor, meses, longo_prazo)


def _resgatar(
    carteira: _Carteira,
    valor: float,
    meses: int,
    longo_prazo: bool,
) -> Resultado:
    """O IR do resgate: a tabela do fundo sobre todo o ganho, menos o que o come-cotas já levou."""
    dias = round(meses * DIAS_POR_MES)
    ganho = carteira.patrimonio - valor + carteira.come_cotas
    ir_total = regras.aliquota_do_fundo(dias, longo_prazo) * max(ganho, 0.0)
    ir_no_resgate = max(ir_total - carteira.come_cotas, 0.0)
    return Resultado(
        carteira.patrimonio,
        carteira.administracao,
        carteira.performance,
        carteira.come_cotas,
        carteira.vezes,
        ir_no_resgate,
        carteira.patrimonio - ir_no_resgate,
    )
