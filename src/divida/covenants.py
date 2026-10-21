"""Covenants preliminares do instrumento novo (protótipo B, DCM, do dossiê da plataforma; B-23).

Projeta, no fim de cada ano do instrumento, os dois indicadores que as regras da B-22
(`src/divida/capacidade.py`) declaram, com a dívida nova do simulador somada à de hoje:

- **alavancagem:** (dívida líquida de hoje + saldo da dívida nova no fim do ano) ÷ EBITDA;
- **cobertura:** base (EBITDA ou EBIT) ÷ (despesa financeira de hoje + juros e correção monetária
  da dívida nova no ano).

E diz, para cada ano, se a regra declarada (`Regras`: alavancagem máxima, cobertura mínima) é
cumprida. Os insumos são os da B-22, das demonstrações como eram no dia; o EBITDA, o EBIT, a
despesa financeira de hoje e o resto da dívida ficam como estão. Nada aqui é opinião de risco nem
recomendação: é a conta das regras que quem usa declarou. Tipos simples, sem Streamlit.
"""

import math
from dataclasses import asdict, dataclass
from datetime import date

from src.divida.capacidade import Insumo, Insumos, Regras
from src.divida.simulador import MESES_POR_ANO, Periodo, Simulacao
from src.rastro import DocumentoUsado, Rastro, datas_em_texto
from src.relatorio_empresa import FONTE_DA_CVM

VERSAO_DOS_COVENANTS = (
    "covenants preliminares 1"  # sobe quando uma fórmula abaixo mudar
)
FORMULA_DA_ALAVANCAGEM = (
    "(dívida líquida de hoje + saldo da dívida nova no fim do ano) ÷ EBITDA (12 meses)"
)
FORMULA_DA_COBERTURA = (
    "base (EBITDA ou EBIT, 12 meses) ÷ (despesa financeira de hoje + juros e correção "
    "monetária da dívida nova no ano)"
)
FALTA_INSUMO = "Falta {insumo}."
EBITDA_NAO_POSITIVO = (
    "EBITDA negativo ou zero: dívida líquida ÷ EBITDA não tem sentido."
)
SEM_DESPESA = "Sem despesa financeira no ano, a cobertura não tem divisor."
LIMITES = (
    (
        "As regras são as que você declarou, não um covenant recomendado: o TickerLab não diz "
        "qual alavancagem ou cobertura é adequada. Nada aqui é recomendação."
    ),
    (
        "Projeção preliminar: o EBITDA, o EBIT, a despesa financeira de hoje e o resto da dívida "
        "ficam como hoje; a dívida nova é tratada como gasta (não fica no caixa), e a amortização, "
        "como paga com caixa novo (o caixa de hoje não muda)."
    ),
    (
        "A despesa financeira de hoje é a linha inteira da DRE (juros, variação cambial, outras); "
        "a da dívida nova conta os juros (pagos ou capitalizados) e a correção monetária do ano."
    ),
    "Os covenants de cada escritura têm definições próprias: aqui vale a fórmula do rastro.",
)


@dataclass(frozen=True)
class IndicadorProjetado:
    """Um indicador num ano; `valor` None: não observado (ver `motivo`)."""

    valor: float | None  # em vezes
    limite: float | None  # a regra declarada (None: não declarada)
    cumpre: bool | None  # None: regra não declarada ou valor não observado
    rastro: Rastro
    motivo: str = ""


@dataclass(frozen=True)
class AnoProjetado:
    ano: int  # 1 = os primeiros 12 meses depois da emissão
    ate_o_mes: (
        int  # o último mês do ano que o instrumento tem (o último ano pode ser curto)
    )
    saldo_da_divida_nova: float  # em reais, no fim do ano
    despesa_da_divida_nova: float  # em reais, juros e correção no ano
    alavancagem: IndicadorProjetado
    cobertura: IndicadorProjetado


@dataclass(frozen=True)
class CovenantsPreliminares:
    como_era_em: date
    regras: Regras
    anos: tuple[AnoProjetado, ...]
    limites: tuple[str, ...] = LIMITES

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _documentos(
    insumos: tuple[Insumo, ...], simulacao: Simulacao
) -> list[DocumentoUsado]:
    vistos: dict[str, DocumentoUsado] = {}
    rastros = [i.rastro for i in insumos] + [simulacao.rastros["saldo_final"]]
    for rastro in rastros:
        for documento in rastro.documentos:
            vistos.setdefault(documento.nome, documento)
    return list(vistos.values())


def _rastro(formula: str, insumos: tuple[Insumo, ...], simulacao: Simulacao) -> Rastro:
    fonte_da_simulacao = simulacao.rastros["saldo_final"].fonte_id
    return Rastro.dos_documentos(
        formula,
        VERSAO_DOS_COVENANTS,
        FONTE_DA_CVM,
        _documentos(insumos, simulacao),
        (fonte_da_simulacao,),
    )


def _indicador(
    valor: float | None,
    limite: float | None,
    cumpre: bool | None,
    rastro: Rastro,
    motivo: str,
) -> IndicadorProjetado:
    if valor is None:
        return IndicadorProjetado(None, limite, None, rastro, motivo)
    return IndicadorProjetado(valor, limite, None if limite is None else cumpre, rastro)


def _falta(*insumos: Insumo) -> str:
    faltando = next((i for i in insumos if i.valor is None), None)
    if faltando is None:
        return ""
    return FALTA_INSUMO.format(insumo=faltando.nome.lower()) + (
        f" {faltando.motivo}" if faltando.motivo else ""
    )


def _alavancagem(
    insumos: Insumos, regras: Regras, saldo: float, simulacao: Simulacao
) -> IndicadorProjetado:
    usados = (insumos.ebitda, insumos.divida_liquida)
    rastro = _rastro(FORMULA_DA_ALAVANCAGEM, usados, simulacao)
    limite = regras.alavancagem_maxima
    if motivo := _falta(*usados):
        return _indicador(None, limite, None, rastro, motivo)
    ebitda, liquida = insumos.ebitda.valor, insumos.divida_liquida.valor
    assert ebitda is not None and liquida is not None
    if ebitda <= 0:
        return _indicador(None, limite, None, rastro, EBITDA_NAO_POSITIVO)
    valor = (liquida + saldo) / ebitda
    return _indicador(valor, limite, limite is not None and valor <= limite, rastro, "")


def _cobertura(
    insumos: Insumos, regras: Regras, despesa_nova: float, simulacao: Simulacao
) -> IndicadorProjetado:
    base = insumos.ebitda if regras.base_da_cobertura == "ebitda" else insumos.ebit
    usados = (base, insumos.despesa_financeira)
    rastro = _rastro(FORMULA_DA_COBERTURA, usados, simulacao)
    limite = regras.cobertura_minima
    if motivo := _falta(*usados):
        return _indicador(None, limite, None, rastro, motivo)
    assert base.valor is not None and insumos.despesa_financeira.valor is not None
    despesa = insumos.despesa_financeira.valor + despesa_nova
    if despesa <= 0:
        return _indicador(None, limite, None, rastro, SEM_DESPESA)
    valor = base.valor / despesa
    return _indicador(valor, limite, limite is not None and valor >= limite, rastro, "")


def _periodos_do_ano(simulacao: Simulacao, ano: int) -> list[Periodo]:
    inicio, fim = (ano - 1) * MESES_POR_ANO, ano * MESES_POR_ANO
    return [p for p in simulacao.periodos if inicio < p.mes <= fim]


def covenants_preliminares(
    simulacao: Simulacao, insumos: Insumos, regras: Regras
) -> CovenantsPreliminares:
    """Alavancagem e cobertura projetadas no fim de cada ano do instrumento, contra as regras."""
    prazo = simulacao.instrumento.prazo_meses
    anos = []
    for ano in range(1, math.ceil(prazo / MESES_POR_ANO) + 1):
        periodos = _periodos_do_ano(simulacao, ano)
        saldo = periodos[-1].saldo_final
        despesa = math.fsum(p.juros + p.correcao_monetaria for p in periodos)
        anos.append(
            AnoProjetado(
                ano=ano,
                ate_o_mes=periodos[-1].mes,
                saldo_da_divida_nova=saldo,
                despesa_da_divida_nova=despesa,
                alavancagem=_alavancagem(insumos, regras, saldo, simulacao),
                cobertura=_cobertura(insumos, regras, despesa, simulacao),
            )
        )
    return CovenantsPreliminares(simulacao.como_era_em, regras, tuple(anos))
