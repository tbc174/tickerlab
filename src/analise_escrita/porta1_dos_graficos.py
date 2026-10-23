"""Porta 1 dos gráficos (plano de 23/10/2026): a escolha do modelo conferida por código.

O gráfico passa só se a tabela e as colunas existem na ficha, servem à forma escolhida no cardápio
(eixo de datas para o tempo, colunas de número, pontos bastantes), nenhuma data passa do corte, o
eixo do tempo não tem período ainda aberto no corte nem período faltando (a prova de 23/10 achou 2026
pela metade ao lado de anos inteiros e os anos sem oferta sumidos do eixo),
nenhum rótulo traz pessoa, a âncora existe na análise e o título e o porquê passam nas mesmas regras
das frases do texto (número, data, nome, palavra proibida, previsão). O porquê cita só linhas da
própria tabela; o do destaque, só linhas da seção puxada.

O item reprovado sai da escolha e a reserva por regras ocupa o lugar: a porta só diz qual e por quê.
"""

import calendar
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Any

from src.analise_escrita import graficos as gr
from src.analise_escrita import numeros, porta1, saida

GRAFICO, DESTAQUE = "grafico", "destaque"
TABELA_INEXISTENTE, COLUNA_INEXISTENTE = "tabela_inexistente", "coluna_inexistente"
FORMA, REPETIDO, ALEM_DO_MAXIMO, ANCORA = (
    "forma",
    "repetido",
    "alem_do_maximo",
    "ancora",
)
POR_QUE_FORA = "por_que_fora"
PERIODO_ABERTO, PERIODO_FALTANDO = "periodo_aberto", "periodo_faltando"
SECAO_INEXISTENTE, SECAO_SEM_DESTAQUE = "secao_inexistente", "secao_sem_destaque"
# seções que já ficam no começo ou no fim de todo relatório: puxá-las para o texto não mostra nada
SECOES_SEM_DESTAQUE = frozenset({"ficha_tecnica", "metodologia", "limites"})


def rotulo(item: str, indice: int) -> str:
    """`grafico.0`, `destaque.1`: o nome do item na porta 2 e na linhagem."""
    return f"{item}.{indice}"


@dataclass(frozen=True)
class Reprovacao:
    item: str  # GRAFICO ou DESTAQUE
    indice: int  # a posição na escolha
    regra: str
    detalhe: str


@dataclass(frozen=True)
class Conferencia:
    reprovacoes: tuple[Reprovacao, ...]

    @property
    def aprovada(self) -> bool:
        return not self.reprovacoes

    @property
    def graficos_reprovados(self) -> frozenset[int]:
        return frozenset(r.indice for r in self.reprovacoes if r.item == GRAFICO)

    @property
    def destaques_reprovados(self) -> frozenset[int]:
        return frozenset(r.indice for r in self.reprovacoes if r.item == DESTAQUE)


def _falhas_de_forma(
    grafico: gr.Grafico, linhas: list[gr.LinhaDaTabela], pontos: list[gr.Ponto]
) -> Iterator[str]:
    forma = gr.CARDAPIO[grafico.tipo]
    minimo, maximo = forma.colunas
    if not minimo <= len(grafico.colunas) <= maximo:
        yield f"{grafico.tipo} pede de {minimo} a {maximo} colunas, não {len(grafico.colunas)}"
    if (
        len(set(grafico.colunas)) < len(grafico.colunas)
        or grafico.eixo in grafico.colunas
    ):
        yield "coluna repetida ou o eixo usado como valor"
    if forma.eixo == gr.TEMPO and any(p.momento is None for p in pontos):
        yield f"{grafico.tipo} pede datas no eixo, e {grafico.eixo} tem linha sem data"
    unidades = {
        gr.unidade_da_celula(linha.celulas.get(c))
        for linha in linhas
        for c in grafico.colunas
    }
    if len(unidades - {None}) > 1:
        yield f"unidades misturadas no mesmo eixo: {', '.join(sorted(u or 'número' for u in unidades - {None}))}"
    for i, coluna in enumerate(grafico.colunas):
        com_valor = sum(p.valores[i] is not None for p in pontos)
        if com_valor < forma.pontos:
            yield f"{coluna} tem {com_valor} pontos com número; {grafico.tipo} pede {forma.pontos}"


def _falhas_do_eixo(
    pontos: list[gr.Ponto], ficha: porta1.Ficha
) -> Iterator[tuple[str, str]]:
    for ponto in pontos:
        if ponto.momento is not None and ponto.momento.depois_de(ficha.corte):
            yield porta1.DATA_FUTURA, ponto.rotulo
        for regra, detalhe in porta1.falhas_de_pessoa(ponto.rotulo):
            yield regra, f"{ponto.rotulo} [{detalhe}]"


def _aberto_no_corte(momento: numeros.DataEscrita, corte: date) -> bool:
    """O ano (ou o mês) do corte que ainda não fechou: o ponto dele não se compara com os inteiros."""
    if momento.dia is not None:
        return False
    if momento.mes is None:
        return momento.ano == corte.year and corte < date(corte.year, 12, 31)
    ultimo_dia = calendar.monthrange(momento.ano, momento.mes)[1]
    return (momento.ano, momento.mes) == (
        corte.year,
        corte.month,
    ) and corte.day < ultimo_dia


def _posicao(momento: numeros.DataEscrita) -> int:
    """O lugar do período na sequência: anos contam de 1 em 1, meses também."""
    return momento.ano if momento.mes is None else momento.ano * 12 + momento.mes - 1


def _falhas_do_tempo(pontos: list[gr.Ponto], corte: date) -> Iterator[tuple[str, str]]:
    datados = [(p.rotulo, p.momento) for p in pontos if p.momento is not None]
    for rotulo_, momento in datados:
        if _aberto_no_corte(momento, corte):
            yield PERIODO_ABERTO, f"{rotulo_} ainda não fechou em {corte:%d/%m/%Y}"
    precisoes = {(m.mes is None, m.dia is None) for _, m in datados}
    if len(precisoes) != 1 or (False, False) in precisoes:
        return  # datas com dia ou precisões misturadas: sem sequência para conferir
    em_ordem = sorted(datados, key=lambda d: _posicao(d[1]))
    for (antes, de), (depois, ate) in pairwise(em_ordem):
        if _posicao(ate) - _posicao(de) > 1:
            yield PERIODO_FALTANDO, f"de {antes} pula para {depois}"


def _falhas_do_texto(
    titulo: saida.Frase, por_que: saida.Frase, permitidos: set[str], ficha: porta1.Ficha
) -> Iterator[tuple[str, str]]:
    """O título (que pode usar os números da tabela inteira) e o porquê, com as regras das frases."""
    for frase in (titulo, por_que):
        for regra, detalhe in porta1.falhas_da_frase(frase, ficha):
            yield regra, f"{frase.texto} [{detalhe}]"
    fora = [n for n in por_que.notas if n not in permitidos]
    if fora or not por_que.notas:
        yield POR_QUE_FORA, f"{por_que.texto} [cita {fora or 'nada'}]"


def _ancora(analise: saida.Analise, parte: str, paragrafo: int) -> str:
    """O motivo de a âncora não existir na análise ("" se existe)."""
    achada = next((p for p in analise.partes if p.chave == parte), None)
    if achada is None:
        return f"a análise não tem a parte {parte}"
    if paragrafo >= len(achada.paragrafos):
        return (
            f"{parte} tem {len(achada.paragrafos)} parágrafos, não chega ao {paragrafo}"
        )
    return ""


def _conferir_grafico(
    grafico: gr.Grafico,
    tabelas: dict[str, list[gr.LinhaDaTabela]],
    analise: saida.Analise,
    ficha: porta1.Ficha,
) -> Iterator[tuple[str, str]]:
    linhas = tabelas.get(grafico.tabela)
    if linhas is None:
        yield TABELA_INEXISTENTE, grafico.tabela
        return
    colunas = {coluna for linha in linhas for coluna in linha.celulas}
    faltam = [c for c in (grafico.eixo, *grafico.colunas) if c not in colunas]
    if faltam:
        yield COLUNA_INEXISTENTE, f"{grafico.tabela} não tem {', '.join(faltam)}"
        return
    pontos = gr.pontos(grafico, linhas)
    yield from ((FORMA, motivo) for motivo in _falhas_de_forma(grafico, linhas, pontos))
    yield from _falhas_do_eixo(pontos, ficha)
    if gr.CARDAPIO[grafico.tipo].eixo == gr.TEMPO:
        yield from _falhas_do_tempo(pontos, ficha.corte)
    ids = {linha.id for linha in linhas}
    titulo = saida.Frase(grafico.titulo, tuple(sorted(ids)))
    yield from _falhas_do_texto(titulo, grafico.por_que, ids, ficha)
    ancora = _ancora(analise, grafico.parte, grafico.paragrafo)
    if ancora:
        yield ANCORA, ancora


def _conferir_destaque(
    destaque: gr.Destaque,
    entrada: dict[str, Any],
    analise: saida.Analise,
    ficha: porta1.Ficha,
) -> Iterator[tuple[str, str]]:
    secoes = entrada.get("secoes", {})
    if destaque.secao not in secoes:
        yield SECAO_INEXISTENTE, destaque.secao
        return
    if destaque.secao in SECOES_SEM_DESTAQUE:
        yield SECAO_SEM_DESTAQUE, destaque.secao
    prefixo = f"{destaque.secao}."
    da_secao = {li["id"] for li in entrada["linhas"] if li["id"].startswith(prefixo)}
    titulo = saida.Frase(secoes[destaque.secao])
    yield from _falhas_do_texto(titulo, destaque.por_que, da_secao, ficha)
    ancora = _ancora(analise, destaque.parte, 0)
    if ancora:
        yield ANCORA, ancora


def _uma_por_regra(
    item: str, indice: int, falhas: Iterable[tuple[str, str]]
) -> list[Reprovacao]:
    por_regra: dict[str, list[str]] = {}
    for regra, detalhe in falhas:
        por_regra.setdefault(regra, []).append(detalhe)
    return [
        Reprovacao(item, indice, regra, "; ".join(detalhes))
        for regra, detalhes in por_regra.items()
    ]


def _conferir_graficos(
    graficos: tuple[gr.Grafico, ...],
    entrada: dict[str, Any],
    analise: saida.Analise,
    ficha: porta1.Ficha,
) -> Iterator[Reprovacao]:
    tabelas = gr.tabelas_da_entrada(entrada)
    vistos: set[tuple[str, str, str, frozenset[str]]] = set()
    for i, grafico in enumerate(graficos):
        if i >= gr.MAXIMO_DE_GRAFICOS:
            yield Reprovacao(GRAFICO, i, ALEM_DO_MAXIMO, grafico.titulo)
        elif grafico.chave in vistos:
            yield Reprovacao(GRAFICO, i, REPETIDO, grafico.titulo)
        else:
            vistos.add(grafico.chave)
            falhas = _conferir_grafico(grafico, tabelas, analise, ficha)
            yield from _uma_por_regra(GRAFICO, i, falhas)


def _conferir_destaques(
    destaques: tuple[gr.Destaque, ...], entrada: dict[str, Any], analise: saida.Analise,
    ficha: porta1.Ficha,
) -> Iterator[Reprovacao]:  # fmt: skip
    vistas: set[str] = set()
    for i, destaque in enumerate(destaques):
        if i >= gr.MAXIMO_DE_DESTAQUES:
            yield Reprovacao(DESTAQUE, i, ALEM_DO_MAXIMO, destaque.secao)
        elif destaque.secao in vistas:
            yield Reprovacao(DESTAQUE, i, REPETIDO, destaque.secao)
        else:
            vistas.add(destaque.secao)
            falhas = _conferir_destaque(destaque, entrada, analise, ficha)
            yield from _uma_por_regra(DESTAQUE, i, falhas)


def conferir(
    escolha: gr.Escolha, entrada: dict[str, Any], analise: saida.Analise
) -> Conferencia:
    """Todas as reprovações da escolha contra a ficha e a análise (nenhuma: aprovada na porta 1)."""
    ficha = porta1.ler_ficha(entrada)
    return Conferencia(
        (
            *_conferir_graficos(escolha.graficos, entrada, analise, ficha),
            *_conferir_destaques(escolha.destaques, entrada, analise, ficha),
        )
    )
