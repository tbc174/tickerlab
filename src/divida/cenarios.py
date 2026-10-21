"""Cenários de curva para o simulador de instrumento (protótipo B, DCM, do dossiê; B-23).

Um cenário muda os vértices da curva do dia e simula de novo o mesmo instrumento:

- **choque paralelo:** soma o mesmo número de pontos-base a todos os vértices;
- **inclinação:** soma zero no vértice mais curto, o choque inteiro no mais longo e, no meio, a
  proporção do prazo (a curva gira em torno do vértice mais curto).

O choque vale para as duas curvas (nominal e implícita) do mesmo jeito: no CDI ele muda o CDI
projetado; no IPCA, a inflação projetada. O pré não usa a curva, e todos os cenários dão o mesmo
fluxo. Os cenários são hipóteses de quem usa, não previsões; nada aqui é recomendação.
"""

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

from src.divida.curva_do_dia import CurvaDoDia
from src.divida.simulador import PRE, Instrumento, Simulacao, simular
from src.rastro import Rastro, datas_em_texto

VERSAO_DOS_CENARIOS = "cenarios de curva 1"  # sobe quando o choque abaixo mudar
PONTOS_BASE = 10_000  # 1 ponto-base = 0,01% ao ano
FORMULA_DO_CHOQUE = (
    "taxa do vértice + (paralelo + inclinação × (prazo − prazo mais curto) ÷ (prazo mais longo − "
    "prazo mais curto)) ÷ 10.000, nas curvas nominal e implícita"
)
TAXA_IMPOSSIVEL = "O choque deixa a curva {curva} com taxa de −100% ao ano ou menos."
PRE_NAO_USA_A_CURVA = "O pré não usa a curva: todos os cenários dão o mesmo fluxo."


@dataclass(frozen=True)
class CenarioDeCurva:
    nome: str
    paralelo_pb: int = 0  # pontos-base somados a todos os vértices
    inclinacao_pb: int = 0  # pontos-base no vértice mais longo (zero no mais curto)


CENARIOS_PADRAO = (
    CenarioDeCurva("curva do dia"),
    CenarioDeCurva("+100 pb", paralelo_pb=100),
    CenarioDeCurva("−100 pb", paralelo_pb=-100),
    CenarioDeCurva("mais inclinada (+100 pb no longo)", inclinacao_pb=100),
    CenarioDeCurva("menos inclinada (−100 pb no longo)", inclinacao_pb=-100),
)


@dataclass(frozen=True)
class ResultadoDoCenario:
    """O fluxo do instrumento num cenário e os totais dele, em reais."""

    cenario: CenarioDeCurva
    simulacao: Simulacao
    total_de_juros: float
    total_de_correcao: float
    total_das_parcelas: float
    maior_parcela: float
    rastro: Rastro


@dataclass(frozen=True)
class TabelaDeCenarios:
    instrumento: Instrumento
    resultados: tuple[ResultadoDoCenario, ...]
    aviso: str = ""

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _choque_no_prazo(
    cenario: CenarioDeCurva, prazo: float, curto: float, longo: float
) -> float:
    """O choque, em fração ao ano, no vértice de `prazo`."""
    proporcao = 0.0 if longo == curto else (prazo - curto) / (longo - curto)
    return (cenario.paralelo_pb + cenario.inclinacao_pb * proporcao) / PONTOS_BASE


def _chocados(
    vertices: tuple[tuple[float, float], ...], cenario: CenarioDeCurva, curva: str
) -> tuple[tuple[float, float], ...]:
    if not vertices:
        return vertices
    curto, longo = vertices[0][0], vertices[-1][0]
    novos = tuple(
        (prazo, taxa + _choque_no_prazo(cenario, prazo, curto, longo))
        for prazo, taxa in vertices
    )
    if any(not taxa > -1 for _, taxa in novos):
        raise ValueError(TAXA_IMPOSSIVEL.format(curva=curva))
    return novos


def com_choque(curva: CurvaDoDia, cenario: CenarioDeCurva) -> CurvaDoDia:
    """A curva do dia com o choque do cenário nas duas curvas."""
    return curva.com_vertices(
        _chocados(curva.nominal, cenario, "nominal"),
        _chocados(curva.implicita, cenario, "implícita"),
    )


def _rastro(curva: CurvaDoDia | None, simulacao: Simulacao) -> Rastro:
    base = curva.rastro if curva is not None else simulacao.rastros["parcela"]
    return Rastro(
        FORMULA_DO_CHOQUE,
        VERSAO_DOS_CENARIOS,
        base.fonte_id,
        base.publicado_em,
        base.documentos,
    )


def simular_cenario(
    instrumento: Instrumento,
    curva: CurvaDoDia | None,
    cenario: CenarioDeCurva,
    como_era_em: date,
) -> ResultadoDoCenario:
    """O instrumento simulado na curva do dia com o choque do cenário."""
    chocada = None if curva is None else com_choque(curva, cenario)
    simulacao = simular(instrumento, chocada, como_era_em)
    parcelas = [p.parcela for p in simulacao.periodos]
    return ResultadoDoCenario(
        cenario=cenario,
        simulacao=simulacao,
        total_de_juros=simulacao.total("juros"),
        total_de_correcao=simulacao.total("correcao_monetaria"),
        total_das_parcelas=math.fsum(parcelas),
        maior_parcela=max(parcelas),
        rastro=_rastro(curva, simulacao),
    )


def tabela_de_cenarios(
    instrumento: Instrumento,
    curva: CurvaDoDia | None,
    como_era_em: date,
    cenarios: Iterable[CenarioDeCurva] = CENARIOS_PADRAO,
) -> TabelaDeCenarios:
    """O instrumento em cada cenário de curva (o primeiro do padrão é a curva do dia sem choque)."""
    resultados = tuple(
        simular_cenario(instrumento, curva, cenario, como_era_em)
        for cenario in cenarios
    )
    aviso = PRE_NAO_USA_A_CURVA if instrumento.indexador == PRE else ""
    return TabelaDeCenarios(instrumento, resultados, aviso)
