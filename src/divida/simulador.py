"""Simulador de um instrumento de dívida novo (protótipo B, DCM, do dossiê da plataforma; B-23).

Quem usa declara os termos (`Instrumento`: principal, indexador, taxa, prazo, carência, amortização)
e o simulador devolve o fluxo de juros e amortização período a período, com a curva de juros **como
era** no dia (`src/divida/curva_do_dia.py`):

- **pré:** juros do período = saldo × ((1 + taxa) ^ (meses ÷ 12) − 1);
- **CDI + spread:** o CDI de cada período é a taxa a termo da curva nominal entre o início e o fim
  do período; juros = saldo × ((1 + CDI a termo) × (1 + spread) ^ (meses ÷ 12) − 1);
- **IPCA + juro real:** o saldo é corrigido pela inflação implícita a termo do período antes dos
  juros e da amortização (como o valor nominal atualizado de uma debênture); juros = saldo
  corrigido × ((1 + juro real) ^ (meses ÷ 12) − 1).

Amortização depois da carência: **SAC** (o saldo, já corrigido, dividido pelos períodos que faltam:
parcela de principal constante), **Price** (parcela constante pela taxa do período sobre o que
falta) ou **bullet** (tudo no último período). Na carência, os juros são pagos ou capitalizados.

O prazo da curva passa do vértice mais longo? `ForaDaCurva`, nunca extrapolação. Nada aqui é opinião
de risco nem recomendação: é a conta dos termos declarados. Tipos simples, sem Streamlit.
"""

import math
from dataclasses import asdict, dataclass
from datetime import date

from src.divida.curva_do_dia import IMPLICITA, NOMINAL, CurvaDoDia
from src.rastro import Rastro, datas_em_texto

VERSAO_DO_SIMULADOR = "simulador 1"  # sobe quando uma fórmula abaixo mudar
PRE, CDI, IPCA = "pre", "cdi", "ipca"
INDEXADORES = (PRE, CDI, IPCA)
CURVA_DO_INDEXADOR = {CDI: NOMINAL, IPCA: IMPLICITA}
SAC, PRICE, BULLET = "sac", "price", "bullet"
AMORTIZACOES = (SAC, PRICE, BULLET)
PAGOS, CAPITALIZADOS = "pagos", "capitalizados"
JUROS_NA_CARENCIA = (PAGOS, CAPITALIZADOS)
MESES_POR_PERIODO = (1, 3, 6, 12)
MESES_POR_ANO = 12
FONTE_DOS_TERMOS = "termos declarados"  # a fonte do número que não usa a curva (o pré)

FORMULAS = {
    "indexador": (
        "CDI: taxa a termo da curva nominal no período; IPCA: inflação implícita a termo no "
        "período; pré: zero"
    ),
    "correcao_monetaria": "saldo inicial × IPCA a termo do período (zero no pré e no CDI)",
    "juros": (
        "(saldo inicial + correção) × taxa do período; taxa do período = (1 + taxa) ^ (meses ÷ 12) "
        "− 1 no pré e no IPCA (juro real), (1 + CDI a termo) × (1 + spread) ^ (meses ÷ 12) − 1 no CDI"
    ),
    "amortizacao": (
        "na carência, zero; SAC: (saldo inicial + correção) ÷ períodos que faltam; Price: parcela − "
        "juros, parcela = base × i ÷ (1 − (1 + i) ^ −n); bullet: tudo no último período"
    ),
    "parcela": "juros pagos + amortização",
    "saldo_final": "saldo inicial + correção + juros capitalizados − amortização",
}
LIMITES = (
    (
        "Os termos são os que você declarou: o simulador não diz se a taxa, o prazo ou a estrutura "
        "são adequados. Nada aqui é recomendação."
    ),
    (
        "O CDI projetado é a taxa a termo da curva dos títulos prefixados do Tesouro Direto, que "
        "tem um spread sobre o DI futuro da B3; o IPCA projetado é a inflação implícita entre os "
        "títulos prefixados e os IPCA+. São expectativas do mercado no dia, não previsões."
    ),
    (
        "O prazo conta em meses ÷ 12 (não em dias úteis ÷ 252, como a curva): a diferença é pequena "
        "num período, e o fluxo não depende do calendário. Sem tributos, custos de emissão nem "
        "arredondamento por título."
    ),
    (
        "Até o primeiro vértice da curva (6 meses), a taxa a termo é a desse vértice; depois do "
        "vértice mais longo não há curva, e o simulador para com erro em vez de extrapolar."
    ),
)


@dataclass(frozen=True)
class Instrumento:
    """Os termos declarados do instrumento novo (tipos simples, para a API)."""

    principal: float  # em reais
    indexador: str  # PRE, CDI ou IPCA
    taxa: (
        float  # fração ao ano: a taxa (pré), o spread sobre o CDI ou o juro real (IPCA)
    )
    prazo_meses: int
    amortizacao: str  # SAC, PRICE ou BULLET
    carencia_meses: int = 0  # meses sem amortização no começo (SAC e Price)
    meses_por_periodo: int = 1  # um de MESES_POR_PERIODO
    juros_na_carencia: str = PAGOS  # PAGOS ou CAPITALIZADOS

    def __post_init__(self) -> None:
        self._conferir_escolhas()
        if not self.principal > 0:
            raise ValueError("o principal precisa ser positivo")
        if not self.taxa > -1:
            raise ValueError("a taxa precisa ser maior que −100% ao ano")
        if self.prazo_meses <= 0 or self.prazo_meses % self.meses_por_periodo:
            raise ValueError("o prazo precisa ser um número inteiro de períodos")
        if self.carencia_meses < 0 or self.carencia_meses % self.meses_por_periodo:
            raise ValueError("a carência precisa ser um número inteiro de períodos")
        if self.amortizacao == BULLET and self.carencia_meses:
            raise ValueError(
                "o bullet já não amortiza antes do vencimento: sem carência"
            )
        if self.carencia_meses >= self.prazo_meses:
            raise ValueError("a carência precisa acabar antes do vencimento")

    def _conferir_escolhas(self) -> None:
        escolhas = (
            ("indexador", self.indexador, INDEXADORES),
            ("amortizacao", self.amortizacao, AMORTIZACOES),
            ("juros_na_carencia", self.juros_na_carencia, JUROS_NA_CARENCIA),
            ("meses_por_periodo", self.meses_por_periodo, MESES_POR_PERIODO),
        )
        for nome, valor, validos in escolhas:
            if valor not in validos:
                raise ValueError(f"{nome} {valor!r} não existe; use um de {validos}")

    @property
    def periodos(self) -> int:
        return self.prazo_meses // self.meses_por_periodo

    @property
    def periodos_de_carencia(self) -> int:
        return self.carencia_meses // self.meses_por_periodo

    @classmethod
    def de_dict(cls, dados: dict) -> "Instrumento":
        """Os termos a partir do JSON da API (campos que não existem levantam erro)."""
        return cls(**dados)

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Periodo:
    """Uma linha do fluxo, em reais (as taxas em fração do período, não ao ano)."""

    numero: int  # 1 a n
    mes: int  # meses desde a emissão no fim do período
    indexador_do_periodo: float  # CDI ou IPCA a termo no período; zero no pré
    taxa_do_periodo: float  # a taxa dos juros no período
    saldo_inicial: float
    correcao_monetaria: float
    juros: float
    juros_pagos: float
    amortizacao: float
    parcela: float
    saldo_final: float


@dataclass(frozen=True)
class Simulacao:
    """O fluxo do instrumento, com a curva usada e o rastro de cada coluna do fluxo."""

    instrumento: Instrumento
    como_era_em: date
    curva_de: date | None  # o dia da curva usada (None no pré, que não usa curva)
    periodos: tuple[Periodo, ...]
    rastros: dict[str, Rastro]  # coluna do `Periodo` → rastro (fórmula em `FORMULAS`)
    limites: tuple[str, ...] = LIMITES

    def total(self, coluna: str) -> float:
        """A soma de uma coluna do fluxo (juros, amortização, parcela, correção)."""
        return math.fsum(getattr(p, coluna) for p in self.periodos)

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _anos(meses: int) -> float:
    return meses / MESES_POR_ANO


def _composta(taxa_ao_ano: float, meses: int) -> float:
    """A taxa ao ano levada a `meses` meses, em juros compostos."""
    return math.expm1(math.log1p(taxa_ao_ano) * _anos(meses))


def _indexador_e_taxa(
    instrumento: Instrumento, curva: CurvaDoDia | None, numero: int
) -> tuple[float, float]:
    """(indexador a termo, taxa dos juros) do período `numero`, em fração do período."""
    meses = instrumento.meses_por_periodo
    taxa = _composta(instrumento.taxa, meses)
    if instrumento.indexador == PRE:
        return 0.0, taxa
    assert curva is not None
    nome_da_curva = CURVA_DO_INDEXADOR[instrumento.indexador]
    inicio, fim = _anos((numero - 1) * meses), _anos(numero * meses)
    indexador = curva.a_termo(nome_da_curva, inicio, fim)
    if instrumento.indexador == CDI:
        return indexador, (1 + indexador) * (1 + taxa) - 1
    return indexador, taxa


def _price(base: float, taxa: float, restantes: int) -> float:
    """A parcela constante que paga `base` em `restantes` períodos à taxa do período."""
    if taxa == 0:
        return base / restantes
    # 1 − (1 + i) ^ −n por expm1 e log1p: com taxa perto de zero, a conta direta perde os dígitos
    return base * taxa / -math.expm1(-restantes * math.log1p(taxa))


def _amortizacao(
    instrumento: Instrumento, numero: int, base: float, taxa: float
) -> float:
    """A amortização do período `numero` (já fora da carência) sobre o saldo corrigido `base`."""
    restantes = instrumento.periodos - numero + 1
    if numero == instrumento.periodos:
        return base  # no último período, o que sobra (sem resto de ponto flutuante)
    if instrumento.amortizacao == SAC:
        return base / restantes
    if instrumento.amortizacao == PRICE:
        return _price(base, taxa, restantes) - base * taxa
    return 0.0  # bullet


def _periodo(
    instrumento: Instrumento, curva: CurvaDoDia | None, numero: int, saldo: float
) -> Periodo:
    indexador, taxa = _indexador_e_taxa(instrumento, curva, numero)
    correcao = saldo * indexador if instrumento.indexador == IPCA else 0.0
    base = saldo + correcao
    juros = base * taxa
    if numero <= instrumento.periodos_de_carencia:
        capitaliza = instrumento.juros_na_carencia == CAPITALIZADOS
        pagos, amortizacao = (0.0 if capitaliza else juros), 0.0
    else:
        pagos, amortizacao = juros, _amortizacao(instrumento, numero, base, taxa)
    return Periodo(
        numero=numero,
        mes=numero * instrumento.meses_por_periodo,
        indexador_do_periodo=indexador,
        taxa_do_periodo=taxa,
        saldo_inicial=saldo,
        correcao_monetaria=correcao,
        juros=juros,
        juros_pagos=pagos,
        amortizacao=amortizacao,
        parcela=pagos + amortizacao,
        saldo_final=base + (juros - pagos) - amortizacao,
    )


def _rastros(
    instrumento: Instrumento, curva: CurvaDoDia | None, como_era_em: date
) -> dict[str, Rastro]:
    if instrumento.indexador == PRE or curva is None:
        fonte, publicado_em, documentos = FONTE_DOS_TERMOS, como_era_em, ()
    else:
        fonte, publicado_em = curva.rastro.fonte_id, curva.rastro.publicado_em
        documentos = curva.rastro.documentos
    return {
        coluna: Rastro(formula, VERSAO_DO_SIMULADOR, fonte, publicado_em, documentos)
        for coluna, formula in FORMULAS.items()
    }


def simular(
    instrumento: Instrumento, curva: CurvaDoDia | None, como_era_em: date
) -> Simulacao:
    """O fluxo do instrumento emitido em `como_era_em`, com a curva já lida como era nesse dia.

    O pré não usa a curva (pode vir None); o CDI e o IPCA sem curva levantam `ValueError`, e com o
    prazo além do vértice mais longo, `ForaDaCurva`."""
    if instrumento.indexador != PRE and curva is None:
        raise ValueError(f"o indexador {instrumento.indexador} precisa da curva do dia")
    periodos, saldo = [], instrumento.principal
    for numero in range(1, instrumento.periodos + 1):
        periodo = _periodo(instrumento, curva, numero, saldo)
        periodos.append(periodo)
        saldo = periodo.saldo_final
    return Simulacao(
        instrumento=instrumento,
        como_era_em=como_era_em,
        curva_de=None
        if instrumento.indexador == PRE or curva is None
        else curva.data_base,
        periodos=tuple(periodos),
        rastros=_rastros(instrumento, curva, como_era_em),
    )
