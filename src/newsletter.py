"""A edição da Newsletter do Research (etapa 4): um objeto só, para a página e para o PDF.

Uma **edição** junta, para uma lista de ativos e uma janela de dias, o que as outras páginas do
Research já calculam: eventos por relevância (com o "por que aparece?"), sinais de alerta,
negociações de pessoas de dentro, documentos de resultado e a variação de fundos e gestores.

Regras (PRD seção 12 e decisão 0011):
- **Modelos fixos, sem IA:** cada frase é montada a partir de um fato com fonte e data; nada é
  inventado, resumido por modelo de linguagem ou opinado. Os **trechos** de um fato relevante são
  frases copiadas do próprio documento pelo algoritmo do TickerLab (R5, `src/leitura.py`), nunca
  reescritas.
- **Mesma edição, várias saídas:** a página e o PDF (Report Studio) mostram o mesmo conteúdo, com
  a mesma data de corte, os mesmos parâmetros e as mesmas fontes.
- **Limites explícitos:** a seção de limites é obrigatória; nada é recomendação.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from src import research
from src.banco.eventos import Evento
from src.parametros import CATALOGO

JANELA_DA_CADENCIA = {"diaria": 1, "semanal": 7, "sob_demanda": 30, "gatilhos": 30}
TEMA_DOS_ALERTAS = "risco"
TEMA_DOS_RESULTADOS = "resultados"
TEMA_DAS_PARTICIPACOES = "participacoes"
TITULO_DOS_TRECHOS = "Trechos do documento (escolhidos por algoritmo, sem IA)"
LIMITES = (
    (
        "Os dados vêm de documentos públicos entregues à CVM e à SEC, coletados uma vez por dia; "
        "podem ter atraso, correções posteriores e lacunas."
    ),
    (
        "A ordem dos itens segue os seus pesos de relevância (página Parâmetros): é uma regra "
        "editorial para organizar a leitura, não uma previsão de preço."
    ),
    (
        "Negociações de pessoas de dentro e carteiras de fundos mostram o passado, com atraso, e "
        "não revelam a intenção de ninguém."
    ),
    (
        "Os trechos dos fatos relevantes são escolhidos por um algoritmo do TickerLab, sem IA: "
        "copiam frases do documento, mas podem deixar de fora algo importante. Leia o original."
    ),
    (
        "Esta edição não é recomendação de investimento, não considera a sua situação e não diz "
        "se um ativo está caro ou barato."
    ),
)


@dataclass(frozen=True)
class Item:
    titulo: str  # "PETR4 · Fato relevante · 10/10/2026"
    texto: str
    link: str = ""
    sigla_da_fonte: str = ""
    razoes: tuple[str, ...] = ()
    trechos: tuple[str, ...] = ()  # frases do próprio documento (R5), na ordem original


@dataclass(frozen=True)
class Secao:
    chave: str
    titulo: str
    itens: tuple[Item, ...]
    vazio: str  # o que dizer quando não há itens (nunca inventar um)


@dataclass(frozen=True)
class Edicao:
    lista: str
    tickers: tuple[str, ...]
    inicio: date
    fim: date
    gerada_em: datetime
    secoes: tuple[Secao, ...]
    fontes: tuple[tuple[str, str], ...]  # (fonte, "coletado em ...")
    parametros: tuple[str, ...]  # frases sobre os pesos e temas usados
    limites: tuple[str, ...] = LIMITES
    cobertos: tuple[str, ...] = field(default=())  # tickers com dados nas fontes

    def secao(self, chave: str) -> Secao:
        return next(s for s in self.secoes if s.chave == chave)


@dataclass(frozen=True)
class Entrada:
    """Tudo o que a edição usa, já lido do banco (a montagem é uma função pura)."""

    lista: str
    tickers: tuple[str, ...]
    eventos: tuple[Evento, ...]
    pesos: dict
    temas: tuple[str, ...]
    hoje: date
    janela: int
    max_itens: int
    gerada_em: datetime
    detentores: tuple[str, ...] = ()  # uma frase por ativo, já com fonte e competência
    fontes: tuple[tuple[str, str], ...] = ()
    cobertos: tuple[str, ...] = ()
    resumos: dict = field(
        default_factory=dict
    )  # protocolo → resumo da R5 (`src.leitura`)


def _codigo(ticker: str) -> str:
    return ticker.removesuffix(".SA")


def _item(pontuado: research.ItemDoResearch, resumos: dict) -> Item:
    e = pontuado.evento
    resumo = resumos.get(e.protocolo, {})
    return Item(
        titulo=f"{_codigo(e.ticker)} · {e.rotulo} · {e.publicado_em:%d/%m/%Y}",
        texto=e.assunto or f"{e.rotulo} de {e.empresa}.",
        link=e.link,
        sigla_da_fonte=research.SIGLAS_DAS_FONTES.get(e.fonte, ""),
        razoes=tuple(pontuado.razoes),
        trechos=tuple(resumo.get("frases", ())),
    )


def _do_tema(
    pontuados: list, tema: str, quantos: int, resumos: dict
) -> tuple[Item, ...]:
    """Os itens de um tema, com o limite por empresa aplicado dentro da seção."""
    por_ativo: Counter[str] = Counter()
    itens = []
    for p in pontuados:
        if (
            p.evento.tema != tema
            or por_ativo[p.evento.ticker] >= research.MAXIMO_POR_EMPRESA
        ):
            continue
        por_ativo[p.evento.ticker] += 1
        itens.append(_item(p, resumos))
    return tuple(itens[:quantos])


def _sem_artigo(texto: str) -> str:
    """ "da exposição" → "exposição"."""
    return re.sub(r"^(da|do|das|dos) ", "", texto)


def _parametros(entrada: Entrada) -> tuple[str, ...]:
    """Frases sobre os parâmetros usados (para a edição poder ser refeita igual)."""
    pesos = ", ".join(
        f"{_sem_artigo(CATALOGO[f'relevancia.{c}'].rotulo.removeprefix('Peso '))} "
        f"{entrada.pesos[c]:.0f}%"
        for c in research.COMPONENTES
    )
    temas = ", ".join(entrada.temas) if entrada.temas else "todos"
    return (
        f"Janela: os últimos {entrada.janela} dia(s), até {entrada.hoje:%d/%m/%Y}.",
        f"Pesos de relevância: {pesos}.",
        f"Temas preferidos: {temas}. No máximo {entrada.max_itens} destaques.",
    )


def montar(entrada: Entrada) -> Edicao:
    """A edição a partir dos eventos já lidos, com os pesos e temas da pessoa."""
    argumentos = (
        list(entrada.eventos),
        entrada.pesos,
        list(entrada.temas),
        entrada.hoje,
        entrada.janela,
        entrada.lista,
    )
    destaques = tuple(
        _item(p, entrada.resumos)
        for p in research.ordenar(*argumentos, maximo=entrada.max_itens)
    )
    # nas seções por tema, o limite por empresa vale dentro de cada uma
    pontuados = research.ordenar(*argumentos, maximo_por_ativo=None)
    secoes = (
        Secao("destaques", "Destaques", destaques, "Nenhum evento das empresas da lista no período."),
        Secao(
            "alertas", "Sinais de alerta", _do_tema(pontuados, TEMA_DOS_ALERTAS, entrada.max_itens, entrada.resumos),
            "Nenhum sinal de alerta no período (troca de auditor, atraso de balanço...).",
        ),
        Secao(
            "por_dentro", "Pessoas de dentro e participações",
            _do_tema(pontuados, TEMA_DAS_PARTICIPACOES, entrada.max_itens, entrada.resumos),
            "Nenhuma negociação de pessoas de dentro nem participação de 5% informada no período.",
        ),
        Secao(
            "resultados", "Resultados e documentos",
            _do_tema(pontuados, TEMA_DOS_RESULTADOS, entrada.max_itens, entrada.resumos),
            "Nenhum documento de resultados entregue no período.",
        ),
        Secao(
            "donos", "Donos e fundos",
            tuple(Item(titulo=frase.split(":", 1)[0], texto=frase) for frase in entrada.detentores),
            "Sem carteiras de fundos ou gestores comparáveis para os ativos da lista.",
        ),
    )  # fmt: skip
    return Edicao(
        lista=entrada.lista,
        tickers=entrada.tickers,
        inicio=date.fromordinal(entrada.hoje.toordinal() - entrada.janela),
        fim=entrada.hoje,
        gerada_em=entrada.gerada_em,
        secoes=secoes,
        fontes=entrada.fontes,
        parametros=_parametros(entrada),
        cobertos=entrada.cobertos,
    )
