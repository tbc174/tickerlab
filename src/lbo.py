"""LBO determinístico: a compra alavancada com as premissas do usuário (protótipo A, M&A, do dossiê da
plataforma; B-25).

Quem usa declara tudo (`PremissasDoLbo`): o EBITDA e o múltiplo da compra e da venda, o EBITDA, a
depreciação, o capex e o capital de giro de cada ano, a alíquota, os custos, o caixa mínimo e as
dívidas (os mesmos `Instrumento` do simulador da B-23, `src/divida/simulador.py`). Nada é estimado
aqui. A conta, ano a ano:

- **fontes e usos:** usos = preço (EBITDA de entrada × múltiplo de entrada) + custos + caixa mínimo;
  fontes = dívidas + capital do acionista (o que falta);
- **dívida:** o fluxo de cada instrumento pelo simulador, somado por ano (juros, correção e
  amortização); o saldo que sobra na saída é pago com o dinheiro da venda;
- **fluxo ao acionista:** EBITDA − imposto − capex − capital de giro − juros pagos − amortização, com
  imposto = alíquota × (EBIT − juros − correção), zero quando negativo;
- **política:** `DISTRIBUI` (todo o fluxo vai ao acionista no ano) ou `ACUMULA` (fica no caixa, sem
  rendimento, até a saída); fluxo negativo usa o caixa acima do mínimo e o resto é aporte do acionista;
- **saída:** EBITDA do último ano × múltiplo de saída − dívida + caixa (zero se negativo: o acionista
  não paga a dívida que sobra); **TIR** do fluxo do acionista e **MOIC** = soma do recebido ÷ soma do
  investido.

É a conta das premissas declaradas: não diz quanto a empresa vale, nem se a compra é boa. Tipos
simples, sem Streamlit (a API e o app novo leem o mesmo `como_dict`).
"""

import math
from dataclasses import asdict, dataclass, field
from datetime import date

import numpy as np

from src.divida.curva_do_dia import CurvaDoDia
from src.divida.simulador import Instrumento, Simulacao, simular
from src.rastro import Rastro, datas_em_texto

VERSAO_DO_CALCULO = "lbo 1"  # sobe quando uma fórmula abaixo mudar
FONTE_DAS_PREMISSAS = "premissas declaradas"
DISTRIBUI, ACUMULA = "distribui", "acumula"
POLITICAS = (DISTRIBUI, ACUMULA)
MESES_POR_ANO = 12

# faixa da TIR (ao ano) e precisão: a raiz do polinômio é refinada até TOLERANCIA_DA_TIR
TIR_MINIMA, TIR_MAXIMA = -0.99, 10.0
TOLERANCIA_DA_TIR = 1e-12
TOLERANCIA_DA_RAIZ = (
    1e-9  # parte imaginária desprezível; raízes mais perto que isso são uma só
)
JANELA_DO_REFINO = 1e-6
SEM_TIR = "o fluxo do acionista não tem uma TIR única entre −99% e 1.000% ao ano"
SEM_INVESTIMENTO = "o acionista não investe nada (as dívidas cobrem todos os usos)"

FORMULAS = {
    "usos": "preço (EBITDA de entrada × múltiplo de entrada) + custos da transação + caixa mínimo",
    "capital_do_acionista": "usos − soma do principal das dívidas",
    "ebit": "EBITDA − depreciação",
    "despesa_financeira": "juros + correção monetária das dívidas no ano (simulador da B-23)",
    "imposto": "alíquota × (EBIT − despesa financeira), zero quando negativo",
    "fluxo_ao_acionista": (
        "EBITDA − imposto − capex − capital de giro − juros pagos − amortização"
    ),
    "distribuido": (
        "distribui: todo o fluxo do ano; acumula: zero, salvo o que falta além do caixa acima do "
        "mínimo (aporte, negativo)"
    ),
    "saida": (
        "EBITDA do último ano × múltiplo de saída − saldo das dívidas + caixa, zero se negativo"
    ),
    "tir": "a taxa que zera o valor presente do fluxo do acionista (ano 0 a N)",
    "moic": "soma dos fluxos recebidos pelo acionista ÷ soma dos investidos (ano 0 e aportes)",
}
LIMITES = (
    (
        "Todas as premissas são suas: o EBITDA, os múltiplos e as dívidas não são estimados nem "
        "conferidos pelo TickerLab. A conta não diz quanto a empresa vale nem se a compra é boa. "
        "Nada aqui é recomendação."
    ),
    (
        "Anos inteiros, fluxos no fim de cada ano; o caixa acumulado não rende; sem compensação de "
        "prejuízo fiscal, imposto sobre o ganho na venda, custos de saída, taxas de gestão ou "
        "dívida que vence antes da hora por covenant."
    ),
    (
        "A compra é do valor da empresa sem caixa e sem dívida: a dívida antiga se paga no preço. "
        "Na saída, o saldo que sobra das dívidas sai do dinheiro da venda."
    ),
)


def _mesmo_tamanho(nome: str, valores: tuple[float, ...], anos: int) -> None:
    if len(valores) != anos:
        raise ValueError(f"{nome} precisa de um valor por ano ({anos})")


@dataclass(frozen=True)
class PremissasDoLbo:
    """As premissas declaradas pelo usuário (reais; taxas em fração; um valor por ano de 1 a N)."""

    ebitda_de_entrada: float  # EBITDA dos 12 meses antes da compra
    multiplo_de_entrada: float  # EV/EBITDA pago
    multiplo_de_saida: float  # EV/EBITDA da venda, sobre o EBITDA do último ano
    ebitda: tuple[float, ...]  # ano 1 a N; N = anos até a saída
    depreciacao: tuple[float, ...]
    capex: tuple[float, ...]
    capital_de_giro: tuple[
        float, ...
    ]  # aumento da necessidade de capital de giro no ano
    aliquota: float  # IR e CSLL sobre o lucro antes do imposto (0,34 = 34%)
    custos_da_transacao: float = 0.0
    caixa_minimo: float = 0.0  # deixado na empresa na compra e mantido até a saída
    dividas: tuple[Instrumento, ...] = ()
    politica: str = ACUMULA

    def __post_init__(self) -> None:
        if not self.ebitda:
            raise ValueError("o LBO precisa de pelo menos um ano até a saída")
        for nome in ("depreciacao", "capex", "capital_de_giro"):
            _mesmo_tamanho(nome, getattr(self, nome), self.anos)
        if not (self.ebitda_de_entrada > 0 and self.multiplo_de_entrada > 0):
            raise ValueError("o EBITDA e o múltiplo de entrada precisam ser positivos")
        if not self.multiplo_de_saida > 0:
            raise ValueError("o múltiplo de saída precisa ser positivo")
        if not 0 <= self.aliquota < 1:
            raise ValueError("a alíquota precisa estar entre 0 e 100%")
        if self.custos_da_transacao < 0 or self.caixa_minimo < 0:
            raise ValueError("custos e caixa mínimo não podem ser negativos")
        if self.politica not in POLITICAS:
            raise ValueError(
                f"politica {self.politica!r} não existe; use uma de {POLITICAS}"
            )

    @property
    def anos(self) -> int:
        return len(self.ebitda)

    @classmethod
    def de_dict(cls, dados: dict) -> "PremissasDoLbo":
        """As premissas a partir do JSON da API (listas viram tuplas; dívidas, `Instrumento`)."""
        dados = dict(dados)
        dados["dividas"] = tuple(
            Instrumento.de_dict(d) for d in dados.get("dividas", ())
        )
        for nome in ("ebitda", "depreciacao", "capex", "capital_de_giro"):
            dados[nome] = tuple(float(v) for v in dados[nome])
        return cls(**dados)

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FontesEUsos:
    preco: float  # EBITDA de entrada × múltiplo de entrada
    custos_da_transacao: float
    caixa_minimo: float
    dividas: tuple[float, ...]  # o principal de cada instrumento
    capital_do_acionista: float

    @property
    def usos(self) -> float:
        return self.preco + self.custos_da_transacao + self.caixa_minimo

    @property
    def fontes(self) -> float:
        return math.fsum(self.dividas) + self.capital_do_acionista


@dataclass(frozen=True)
class AnoDoLbo:
    """Uma linha do LBO, em reais."""

    ano: int
    ebitda: float
    depreciacao: float
    ebit: float
    despesa_financeira: float  # juros + correção monetária
    imposto: float
    capex: float
    capital_de_giro: float
    juros_pagos: float
    amortizacao: float
    fluxo_ao_acionista: float
    distribuido: float  # pago ao acionista no ano (negativo: aporte)
    caixa_final: float
    divida_final: float


@dataclass(frozen=True)
class Saida:
    valor_da_empresa: float  # EBITDA do último ano × múltiplo de saída
    divida: float  # saldo das dívidas no fim do último ano
    caixa: float
    valor_do_acionista: float  # empresa − dívida + caixa, zero se negativo


@dataclass(frozen=True)
class ResultadoDoLbo:
    premissas: PremissasDoLbo
    como_era_em: date
    fontes_e_usos: FontesEUsos
    anos: tuple[AnoDoLbo, ...]
    saida: Saida
    fluxos_do_acionista: tuple[float, ...]  # ano 0 a N (negativo: investido)
    tir: float | None
    moic: float | None
    rastros: dict[str, Rastro]
    motivo: str = ""  # por que a TIR ou o MOIC ficaram vazios
    limites: tuple[str, ...] = field(default=LIMITES)

    @property
    def investido(self) -> float:
        return -math.fsum(f for f in self.fluxos_do_acionista if f < 0)

    @property
    def recebido(self) -> float:
        return math.fsum(f for f in self.fluxos_do_acionista if f > 0)

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _fontes_e_usos(premissas: PremissasDoLbo) -> FontesEUsos:
    preco = premissas.ebitda_de_entrada * premissas.multiplo_de_entrada
    dividas = tuple(d.principal for d in premissas.dividas)
    usos = preco + premissas.custos_da_transacao + premissas.caixa_minimo
    return FontesEUsos(
        preco,
        premissas.custos_da_transacao,
        premissas.caixa_minimo,
        dividas,
        usos - math.fsum(dividas),
    )


@dataclass(frozen=True)
class _DividaNoAno:
    despesa_financeira: float = 0.0
    juros_pagos: float = 0.0
    amortizacao: float = 0.0
    saldo_final: float = 0.0


def _ano_do_periodo(mes: int) -> int:
    return -(-mes // MESES_POR_ANO)  # o mês 12 é do ano 1; o 13, do ano 2


def _divida_por_ano(simulacoes: list[Simulacao], anos: int) -> list[_DividaNoAno]:
    """Juros, correção, amortização e saldo de todas as dívidas, somados por ano de 1 a `anos`."""
    por_ano = []
    for ano in range(1, anos + 1):
        periodos = [
            p for s in simulacoes for p in s.periodos if _ano_do_periodo(p.mes) == ano
        ]
        saldos = [
            next(
                (
                    p.saldo_final
                    for p in reversed(s.periodos)
                    if p.mes <= ano * MESES_POR_ANO
                ),
                s.instrumento.principal,
            )
            for s in simulacoes
        ]
        por_ano.append(
            _DividaNoAno(
                despesa_financeira=math.fsum(
                    p.juros + p.correcao_monetaria for p in periodos
                ),
                juros_pagos=math.fsum(p.juros_pagos for p in periodos),
                amortizacao=math.fsum(p.amortizacao for p in periodos),
                saldo_final=math.fsum(saldos),
            )
        )
    return por_ano


def _anos(premissas: PremissasDoLbo, dividas: list[_DividaNoAno]) -> list[AnoDoLbo]:
    linhas, caixa = [], premissas.caixa_minimo
    for i, divida in enumerate(dividas):
        ebitda, depreciacao = premissas.ebitda[i], premissas.depreciacao[i]
        ebit = ebitda - depreciacao
        imposto = premissas.aliquota * max(ebit - divida.despesa_financeira, 0.0)
        capex, giro = premissas.capex[i], premissas.capital_de_giro[i]
        fluxo = (
            ebitda - imposto - capex - giro - divida.juros_pagos - divida.amortizacao
        )
        excedente = caixa - premissas.caixa_minimo + fluxo
        distribui = premissas.politica == DISTRIBUI or excedente < 0
        distribuido = excedente if distribui else 0.0
        caixa = premissas.caixa_minimo + excedente - distribuido
        linhas.append(
            AnoDoLbo(
                ano=i + 1,
                ebitda=ebitda,
                depreciacao=depreciacao,
                ebit=ebit,
                despesa_financeira=divida.despesa_financeira,
                imposto=imposto,
                capex=capex,
                capital_de_giro=giro,
                juros_pagos=divida.juros_pagos,
                amortizacao=divida.amortizacao,
                fluxo_ao_acionista=fluxo,
                distribuido=distribuido,
                caixa_final=caixa,
                divida_final=divida.saldo_final,
            )
        )
    return linhas


def _saida(premissas: PremissasDoLbo, ultimo: AnoDoLbo) -> Saida:
    empresa = premissas.ebitda[-1] * premissas.multiplo_de_saida
    acionista = max(empresa - ultimo.divida_final + ultimo.caixa_final, 0.0)
    return Saida(empresa, ultimo.divida_final, ultimo.caixa_final, acionista)


def valor_presente(fluxos: tuple[float, ...], taxa: float) -> float:
    """Soma dos fluxos (ano 0 a N) descontados à `taxa` ao ano."""
    return math.fsum(f / (1 + taxa) ** t for t, f in enumerate(fluxos))


def _refinar(fluxos: tuple[float, ...], taxa: float) -> float:
    """A raiz achada pelo polinômio, refinada por bisseção num intervalo pequeno em volta dela."""
    baixo, alto = max(taxa - JANELA_DO_REFINO, TIR_MINIMA), taxa + JANELA_DO_REFINO
    vp_baixo = valor_presente(fluxos, baixo)
    if (vp_baixo > 0) == (valor_presente(fluxos, alto) > 0):
        return taxa  # raiz dupla ou na borda: fica a do polinômio
    while alto - baixo > TOLERANCIA_DA_TIR:
        meio = (baixo + alto) / 2
        vp_meio = valor_presente(fluxos, meio)
        if (vp_meio > 0) == (vp_baixo > 0):
            baixo, vp_baixo = meio, vp_meio
        else:
            alto = meio
    return (baixo + alto) / 2


def tir(fluxos: tuple[float, ...]) -> float | None:
    """A TIR do fluxo (ano 0 a N), ou None se não há exatamente uma entre −99% e 1.000% ao ano.

    O valor presente é um polinômio em x = 1 ÷ (1 + taxa): Σ fluxo_t × x^t. As raízes reais positivas
    dele são todas as TIRs; fluxo com duas (aporte no meio) fica sem, em vez de escolher uma."""
    if not any(fluxos):
        return None
    raizes = np.roots(list(reversed(fluxos)))  # do maior grau para o menor
    taxas = sorted(
        1 / x.real - 1
        for x in raizes
        if abs(x.imag) < TOLERANCIA_DA_RAIZ
        and x.real > 0
        and TIR_MINIMA <= 1 / x.real - 1 <= TIR_MAXIMA
    )
    distintas = [
        t
        for i, t in enumerate(taxas)
        if i == 0 or t - taxas[i - 1] > TOLERANCIA_DA_RAIZ
    ]
    return _refinar(fluxos, distintas[0]) if len(distintas) == 1 else None


def _rastros(simulacoes: list[Simulacao], como_era_em: date) -> dict[str, Rastro]:
    rastros = {
        nome: Rastro(formula, VERSAO_DO_CALCULO, FONTE_DAS_PREMISSAS, como_era_em)
        for nome, formula in FORMULAS.items()
    }
    # juros, amortização e saldo vêm do simulador (com a curva do dia, quando o indexador a usa)
    for coluna in ("juros", "amortizacao", "saldo_final"):
        de_cada = [s.rastros[coluna] for s in simulacoes if coluna in s.rastros]
        if de_cada:
            rastros[coluna] = de_cada[0]
    return rastros


def lbo(
    premissas: PremissasDoLbo, como_era_em: date, curva: CurvaDoDia | None = None
) -> ResultadoDoLbo:
    """O LBO das premissas, com a compra em `como_era_em` (a curva, se uma dívida a usa, já lida como
    era nesse dia: `src/divida/curva_do_dia.py`)."""
    fontes_e_usos = _fontes_e_usos(premissas)
    if fontes_e_usos.capital_do_acionista < 0:
        raise ValueError("as dívidas passam dos usos: o acionista receberia na compra")
    simulacoes = [simular(d, curva, como_era_em) for d in premissas.dividas]
    anos = _anos(premissas, _divida_por_ano(simulacoes, premissas.anos))
    saida = _saida(premissas, anos[-1])
    fluxos = (
        [-fontes_e_usos.capital_do_acionista]
        + [a.distribuido for a in anos[:-1]]
        + [anos[-1].distribuido + saida.valor_do_acionista]
    )
    investido = -math.fsum(f for f in fluxos if f < 0)
    recebido = math.fsum(f for f in fluxos if f > 0)
    taxa = tir(tuple(fluxos)) if investido > 0 else None
    motivo = (
        SEM_INVESTIMENTO if investido <= 0 else ("" if taxa is not None else SEM_TIR)
    )
    return ResultadoDoLbo(
        premissas=premissas,
        como_era_em=como_era_em,
        fontes_e_usos=fontes_e_usos,
        anos=tuple(anos),
        saida=saida,
        fluxos_do_acionista=tuple(fluxos),
        tir=taxa,
        moic=recebido / investido if investido > 0 else None,
        rastros=_rastros(simulacoes, como_era_em),
        motivo=motivo,
    )
