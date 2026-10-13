"""Linha do tempo: o preço do ativo (em base 100) e os acontecimentos da empresa no mesmo eixo.

Os acontecimentos são os documentos que a empresa publicou na CVM ou na SEC (o Research já coleta);
cada um aparece no dia da publicação. A linha do tempo só põe fatos e preço lado a lado: não diz
que um fato fez o preço subir ou cair (o preço muda por muitos motivos ao mesmo tempo). "O que
aconteceu depois de cada fato" é outra funcionalidade, com o teste contra a sorte (ADR 0038, T1).

A curva sai em base 100, nunca o preço bruto: assim a mesma função serve a uma rota da API sem
redistribuir preço (ADR 0048, item 6). Tudo em tipos simples, sem Streamlit.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.banco.eventos import Evento

MATERIALIDADE_PADRAO = (
    50  # 0 a 100 (`src.eventos.Classe`): abaixo disso, documento de rotina
)
MAXIMO_DE_MARCOS = 60  # mais que isso vira ruído no gráfico; os mais relevantes ficam
# o que a pessoa escolhe ver: nome do nível → materialidade mínima
RELEVANCIAS = {"Os mais relevantes": 70, "Relevantes": MATERIALIDADE_PADRAO, "Todos": 0}
SEM_ACONTECIMENTOS = (
    "Nenhum acontecimento deste ativo no período. A linha do tempo mostra os documentos das "
    "empresas da CVM e da SEC (ETFs, índices e cripto não têm)."
)
AVISO_DA_LINHA = (
    "Cada fato aparece no dia em que foi publicado. A linha do tempo não diz se um fato fez o "
    "preço subir ou cair: o preço muda por muitos motivos ao mesmo tempo."
)


@dataclass(frozen=True)
class PontoDaCurva:
    dia: date
    valor: float  # base 100 no primeiro dia


@dataclass(frozen=True)
class Marco:
    data: date  # quando o documento foi publicado
    dia_no_grafico: date  # o pregão em que o ponto fica (o mesmo dia ou o seguinte)
    valor_no_grafico: float  # a curva (base 100) nesse pregão
    rotulo: str
    tema: str
    materialidade: int
    assunto: str
    link: str  # vazio: sem link seguro


@dataclass(frozen=True)
class LinhaDoTempo:
    curva: tuple[PontoDaCurva, ...]
    marcos: tuple[Marco, ...]
    fora_do_grafico: (
        int  # acontecimentos do período que ficaram de fora (rotina ou excesso)
    )


def _no_grafico(curva: pd.Series, dia: date) -> tuple[date, float] | None:
    """O primeiro pregão no dia do fato ou depois dele; None se o fato é depois do último."""
    posicao = curva.index.searchsorted(pd.Timestamp(dia))
    if posicao >= len(curva):
        return None
    return curva.index[posicao].date(), float(curva.iloc[posicao])


def montar_linha_do_tempo(
    fechamento: pd.Series,
    eventos: list[Evento],
    materialidade_minima: int = MATERIALIDADE_PADRAO,
    maximo: int = MAXIMO_DE_MARCOS,
) -> LinhaDoTempo:
    """A curva em base 100 e os acontecimentos do período (os `maximo` mais relevantes, por data)."""
    precos = fechamento.dropna()
    if precos.empty:
        raise ValueError("Não há preço no período para montar a linha do tempo.")
    curva = precos / precos.iloc[0] * 100
    inicio, fim = curva.index[0].date(), curva.index[-1].date()
    do_periodo = [e for e in eventos if inicio <= e.publicado_em <= fim]
    relevantes = [e for e in do_periodo if e.materialidade >= materialidade_minima]
    escolhidos = sorted(relevantes, key=lambda e: e.materialidade, reverse=True)[
        :maximo
    ]
    marcos = []
    for evento in sorted(escolhidos, key=lambda e: e.publicado_em):
        ponto = _no_grafico(curva, evento.publicado_em)
        if ponto is None:
            continue
        marcos.append(
            Marco(evento.publicado_em, ponto[0], ponto[1], evento.rotulo, evento.tema,
                  evento.materialidade, evento.assunto, evento.link)
        )  # fmt: skip
    return LinhaDoTempo(
        curva=tuple(PontoDaCurva(d.date(), float(v)) for d, v in curva.items()),
        marcos=tuple(marcos),
        fora_do_grafico=len(do_periodo) - len(marcos),
    )


def descricao_do_marco(marco: Marco) -> str:
    """Uma linha para a tabela e para o gráfico: data, tipo do documento e assunto."""
    return f"{marco.data:%d/%m/%Y} · {marco.rotulo}: {marco.assunto}"


def texto_fora_do_grafico(quantos: int) -> str:
    """Quantos documentos do período ficaram de fora do gráfico, e como ver todos."""
    return (
        f"{quantos} documentos de rotina ou de menor relevância ficaram de fora; escolha "
        '"Todos" para ver mais.'
    )
