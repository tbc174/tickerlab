"""A curva de juros de um dia, como era pública numa data (protótipo B, DCM, do dossiê; B-23).

Lê a tabela `curva_juros` da base (`base/curva.py`: taxas zero dos títulos sem cupom do Tesouro
Direto, flat-forward entre os títulos) **pela porta** e "como era" no dia pedido: a curva mais nova
com `disponivel_em` até esse dia. Guarda duas curvas, só os vértices que a base tem:

- `nominal` (Tesouro Prefixado): projeta o CDI no simulador;
- `implicita` (nominal ÷ real − 1): projeta o IPCA.

Entre dois vértices, a mesma flat-forward da base (`base.curva.flat_forward`). Entre hoje e o
primeiro vértice, também flat-forward, a partir do fator 1 de hoje (que vale por definição): a taxa
a termo até lá é a do primeiro vértice. **Depois do vértice mais longo não há curva**: o prazo dá
`ForaDaCurva`, nunca uma taxa extrapolada. Tipos simples, sem Streamlit (fáceis de virar JSON).
"""

import math
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np
import pandas as pd

from base.curva import FONTE, TABELA, flat_forward
from base.porta import Porta
from src.rastro import DocumentoUsado, Rastro, datas_em_texto

VERSAO_DA_CURVA = (
    "curva do dia 1"  # sobe quando a leitura ou a interpolação abaixo mudar
)
NOMINAL, IMPLICITA = "nominal", "implicita"
CURVAS = (NOMINAL, IMPLICITA)
FORMULA_DA_CURVA = (
    "taxa zero dos títulos sem cupom do Tesouro Direto nos vértices da base (base/curva.py); "
    "flat-forward entre os vértices e de hoje (fator 1) até o primeiro; sem extrapolar"
)
SEM_CURVA = "Não há curva de juros pública até {dia:%d/%m/%Y} nesta base."
SEM_VERTICES = "A curva {curva} de {dia:%d/%m/%Y} não tem vértices nesta base."
PRAZO_FORA = (
    "O prazo de {prazo:.2f} anos passa do vértice mais longo da curva {curva} de "
    "{dia:%d/%m/%Y} ({maior:.2f} anos). O simulador não extrapola a curva."
)


class ForaDaCurva(ValueError):
    """O prazo pedido passa do vértice mais longo da curva (nada é extrapolado)."""


@dataclass(frozen=True)
class CurvaDoDia:
    """Os vértices (prazo em anos, taxa ao ano em fração) de cada curva de um dia, com o rastro."""

    data_base: date  # o dia das taxas
    disponivel_em: date  # quando ficaram públicas
    nominal: tuple[tuple[float, float], ...]
    implicita: tuple[tuple[float, float], ...]
    rastro: Rastro

    def vertices(self, curva: str) -> tuple[tuple[float, float], ...]:
        if curva not in CURVAS:
            raise ValueError(f"curva {curva!r} não existe; use uma de {CURVAS}")
        return self.nominal if curva == NOMINAL else self.implicita

    def maior_prazo(self, curva: str) -> float:
        """O vértice mais longo da curva, em anos (até onde o simulador vai)."""
        vertices = self.vertices(curva)
        if not vertices:
            raise ForaDaCurva(SEM_VERTICES.format(curva=curva, dia=self.data_base))
        return vertices[-1][0]

    def fator(self, curva: str, prazo: float) -> float:
        """(1 + taxa zero) ^ prazo, com o prazo em anos; `ForaDaCurva` depois do último vértice."""
        if prazo < 0:
            raise ValueError("prazo negativo")
        if prazo == 0:
            return 1.0
        maior = self.maior_prazo(curva)
        if prazo > maior:
            raise ForaDaCurva(
                PRAZO_FORA.format(
                    prazo=prazo, curva=curva, dia=self.data_base, maior=maior
                )
            )
        prazos, taxas = zip(*self.vertices(curva), strict=True)
        # o vértice zero entra com qualquer taxa: o fator dele é 1 (prazo × log(1 + taxa) = 0)
        taxa = flat_forward(np.array([0.0, *prazos]), np.array([0.0, *taxas]), prazo)
        return math.pow(1 + taxa, prazo)

    def a_termo(self, curva: str, inicio: float, fim: float) -> float:
        """A taxa a termo entre dois prazos (anos), no período inteiro (não anualizada)."""
        if fim <= inicio:
            raise ValueError("o fim do período precisa vir depois do início")
        return self.fator(curva, fim) / self.fator(curva, inicio) - 1

    def com_vertices(
        self,
        nominal: tuple[tuple[float, float], ...],
        implicita: tuple[tuple[float, float], ...],
    ) -> "CurvaDoDia":
        """A mesma curva (dia e rastro) com outros vértices, para os cenários de choque."""
        return CurvaDoDia(
            self.data_base, self.disponivel_em, nominal, implicita, self.rastro
        )

    def como_dict(self) -> dict:
        return {k: datas_em_texto(v) for k, v in asdict(self).items()}


def _dia(valor: object) -> date:
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _vertices(do_dia: pd.DataFrame, curva: str) -> tuple[tuple[float, float], ...]:
    linhas = do_dia[do_dia["curva"] == curva].sort_values("prazo_anos")
    return tuple(
        (float(p), float(t))
        for p, t in zip(linhas["prazo_anos"], linhas["taxa"], strict=True)
    )


def rastro_da_curva(data_base: date, disponivel_em: date) -> Rastro:
    """O rastro de um número tirado da curva de `data_base`."""
    documento = DocumentoUsado(
        f"curva de juros de {data_base:%d/%m/%Y} (Tesouro Direto, títulos sem cupom)",
        disponivel_em,
    )
    return Rastro.dos_documentos(FORMULA_DA_CURVA, VERSAO_DA_CURVA, FONTE, [documento])


def curva_de_tabela(tabela: pd.DataFrame, como_era_em: date) -> CurvaDoDia:
    """A curva mais nova da tabela (colunas de `curva_juros`) já pública em `como_era_em`."""
    disponiveis = pd.to_datetime(tabela["disponivel_em"]).dt.date
    publicas = tabela[disponiveis <= como_era_em]
    if publicas.empty:
        raise ForaDaCurva(SEM_CURVA.format(dia=como_era_em))
    dias = pd.to_datetime(publicas["data_base"]).dt.date
    data_base = max(dias)
    do_dia = publicas[dias == data_base]
    disponivel_em = _dia(do_dia["disponivel_em"].max())
    return CurvaDoDia(
        data_base=data_base,
        disponivel_em=disponivel_em,
        nominal=_vertices(do_dia, NOMINAL),
        implicita=_vertices(do_dia, IMPLICITA),
        rastro=rastro_da_curva(data_base, disponivel_em),
    )


def curva_como_era(porta: Porta, como_era_em: date) -> CurvaDoDia:
    """A curva do Tesouro Direto como era pública em `como_era_em`, lida pela porta da base."""
    tabela = porta.ler(
        TABELA,
        como_era_em=como_era_em,
        filtros={"curva": list(CURVAS)},
        colunas=["data_base", "curva", "prazo_anos", "taxa", "disponivel_em"],
    )
    return curva_de_tabela(tabela, como_era_em)
