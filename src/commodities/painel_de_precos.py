"""Painel de preços de referência mensais: café, algodão e fertilizantes (ADR 0094, Emenda 1).

Lê do acervo de séries (`bm-pink-<item>` do Pink Sheet do Banco Mundial e `fmi-<item>` do FMI), "como
era na data": o painel de uma data passada não usa valor divulgado depois dela. Só café e algodão
mostram as duas fontes lado a lado (medem o mesmo indicador e concordam em 1%); ureia, DAP e
potássio saem só do Pink Sheet, porque os indicadores das duas fontes diferem.

Decisão do Tiago (19/10/2026): mostrar já o preço mensal, com a atribuição e o aviso abaixo, sem
esperar o parecer do FMI. As séries continuam `uso_interno`: o dado não é exportado nem vendido.

Fica sem Streamlit: entradas e saídas em tipos simples.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd
import sqlalchemy as sa

from src.banco import series as acervo
from src.precos_de_referencia import COMPARAVEIS, FAMILIA_BM, ITENS

ATRIBUICAO = "Fonte: Banco Mundial, Pink Sheet, CC BY 4.0; FMI PCPS."
AVISO_DIARIO = "Preço de referência mensal; o diário depende de licença."
NOTA_FONTES_DIFEREM = (
    "Só o Pink Sheet: os indicadores do Banco Mundial e do FMI diferem para este item, "
    "então as duas fontes não são postas lado a lado."
)
CHAVES_DO_PAINEL = (
    "cafe-arabica",
    "cafe-robusta",
    "algodao",
    "ureia",
    "dap",
    "cloreto-de-potassio",
)
MESES_DO_HISTORICO = 60
MESES_NO_ANO = 12
ARABICA = "cafe-arabica"
ROBUSTA = "cafe-robusta"
TITULO_DO_SPREAD = "Spread arábica menos robusta"
NOTA_DO_SPREAD = "Quando a diferença abre muito, a indústria troca de grão; o conilon do Brasil é robusta."
SEM_COLETA = "Os preços de referência ainda não foram coletados neste servidor."

_ITEM_PELA_CHAVE = {item.chave: item for item in ITENS}


@dataclass(frozen=True)
class PontoMensal:
    mes: date  # sempre o dia 1
    bm: float | None  # Pink Sheet
    fmi: float | None  # None também quando o item não tem o FMI ao lado


@dataclass(frozen=True)
class PontoDoSpread:
    mes: date
    valor: float  # arábica menos robusta, em US$/kg


@dataclass(frozen=True)
class PrecoDeReferencia:
    chave: str
    nome: str
    unidade: str
    ultimo_mes: date
    ultimo_valor: float
    variacao_12_meses: float | None  # em %, contra o mesmo mês do ano anterior
    historico: tuple[PontoMensal, ...]
    com_fmi: bool
    nota_das_fontes: str | None


@dataclass(frozen=True)
class PainelDePrecos:
    itens: tuple[PrecoDeReferencia, ...]
    spread: tuple[PontoDoSpread, ...]
    atribuicao: str = ATRIBUICAO
    aviso_diario: str = AVISO_DIARIO


def _serie_do_mes(conexao: sa.Connection, codigo: str, dia: date) -> pd.Series:
    """A série como era em `dia`, sem meses vazios e com o índice no dia 1 de cada mês."""
    return acervo.como_estava_em(conexao, codigo, dia).dropna()


def _valor_ou_none(serie: pd.Series, mes: pd.Timestamp) -> float | None:
    return float(serie[mes]) if mes in serie.index else None


def _variacao_em_12_meses(serie: pd.Series) -> float | None:
    ultimo = serie.index[-1]
    um_ano_antes = ultimo - pd.DateOffset(months=MESES_NO_ANO)
    if um_ano_antes not in serie.index or serie[um_ano_antes] == 0:
        return None
    return float((serie.iloc[-1] / serie[um_ano_antes] - 1) * 100)


def _montar_item(
    conexao: sa.Connection, chave: str, dia: date
) -> PrecoDeReferencia | None:
    bm = _serie_do_mes(conexao, f"{FAMILIA_BM}-{chave}", dia)
    if bm.empty:
        return None
    com_fmi = chave in COMPARAVEIS
    fmi = (
        _serie_do_mes(conexao, f"fmi-{chave}", dia)
        if com_fmi
        else pd.Series(dtype=float)
    )
    meses = bm.index[-MESES_DO_HISTORICO:]
    item = _ITEM_PELA_CHAVE[chave]
    return PrecoDeReferencia(
        chave=chave,
        nome=item.nome,
        unidade=item.unidade,
        ultimo_mes=bm.index[-1].date(),
        ultimo_valor=float(bm.iloc[-1]),
        variacao_12_meses=_variacao_em_12_meses(bm),
        historico=tuple(
            PontoMensal(m.date(), float(bm[m]), _valor_ou_none(fmi, m)) for m in meses
        ),
        com_fmi=com_fmi,
        nota_das_fontes=None if com_fmi else NOTA_FONTES_DIFEREM,
    )


def _montar_spread(itens: tuple[PrecoDeReferencia, ...]) -> tuple[PontoDoSpread, ...]:
    por_chave = {i.chave: i for i in itens}
    if ARABICA not in por_chave or ROBUSTA not in por_chave:
        return ()
    robusta = {p.mes: p.bm for p in por_chave[ROBUSTA].historico}
    return tuple(
        PontoDoSpread(p.mes, p.bm - robusta[p.mes])
        for p in por_chave[ARABICA].historico
        if p.bm is not None and robusta.get(p.mes) is not None
    )


def montar_painel(conexao: sa.Connection, dia: date) -> PainelDePrecos:
    """O painel como era em `dia`; item sem série no acervo fica de fora."""
    montados = (_montar_item(conexao, chave, dia) for chave in CHAVES_DO_PAINEL)
    itens = tuple(i for i in montados if i is not None)
    return PainelDePrecos(itens=itens, spread=_montar_spread(itens))


# --- Os textos da tela (o Streamlit e a API mostram os mesmos) ---


def formatar_valor(valor: float) -> str:
    """O preço com duas casas no formato brasileiro: 1.234,50."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def texto_da_variacao(variacao: float | None) -> str | None:
    """A variação contra o mesmo mês do ano anterior ("+3,2% em 12 meses"), ou None sem o dado."""
    if variacao is None:
        return None
    return f"{variacao:+.1f}% em 12 meses".replace(".", ",")


def legenda_do_item(item: PrecoDeReferencia) -> str:
    """O mês do último valor e a fonte, numa linha."""
    return f"Média de {item.ultimo_mes:%m/%Y}, Pink Sheet do Banco Mundial."
