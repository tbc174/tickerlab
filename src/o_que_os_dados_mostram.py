"""O que os dados mostram: os pontos fortes e os de atenção da ficha, por regras fixas.

Relatórios v2, PR 1 (plano de 17/10/2026). Cada ponto sai de uma regra escrita aqui, nunca de um
modelo de texto: a nota contra o setor nas pontas, as notas clássicas contra a escala do artigo, o
que mudou desde o balanço anterior, a faixa fixa do caixa, os fundos com a ação um ano antes, a troca
recente de auditor e a reapresentação ou o atraso da demonstração. E cada ponto leva o número, de
quando ele é e a tabela de onde veio, como todo número do relatório (`src/numero.py`).

Nada aqui recomenda nem prevê: os pontos descrevem o que os números já mostram. A seção "O que
mudaria esta leitura" (os gatilhos) fica no fim do relatório.

Lê as seções já montadas por `src/relatorio_empresa.py` (só os tipos, sem importar o módulo na hora
de rodar, para não haver import circular).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from src import notas, notas_classicas

if TYPE_CHECKING:
    from src.relatorio_empresa import Item, Secao

FORTE, ATENCAO = "forte", "atenção"
TITULOS_DOS_LADOS = {FORTE: "Pontos fortes nos dados", ATENCAO: "Pontos de atenção"}
MAXIMO_POR_LADO = 5
VARIACAO_RELEVANTE = 0.10  # mudança de 10% ou mais (para cima ou para baixo) vira ponto
ANOS_DA_TROCA_RECENTE = 3  # auditor trocado há menos que isto vira ponto de atenção
SECOES_COM_NOTA = ("resultado", "retorno", "endividamento", "caixa")
NOTAS_DAS_PONTAS = {"ótimo": FORTE, "péssimo": ATENCAO}
NOTAS_DO_MEIO = {"bom": FORTE, "ruim": ATENCAO}
# as frases que `ultima_demonstracao` escreve (e esta leitura procura)
REAPRESENTADA = "(reapresentada)"
DENTRO_DO_PRAZO, DEPOIS_DO_PRAZO = "dentro do prazo", "depois do prazo"
SEM_PONTOS = "Nenhuma regra encontrou um ponto deste lado nos dados desta empresa."


@dataclass(frozen=True)
class Ponto:
    lado: str  # FORTE ou ATENCAO
    texto: str
    numero: str  # o número escrito ("26,4%")
    medido_em: str  # de quando ("12 meses até 30/06/2026")
    tabela: str  # a fonte e a tabela de origem
    indicador: str  # a chave do item de origem (um ponto por indicador)


@dataclass(frozen=True)
class Mudanca:
    """Um indicador no balanço anterior e no de agora (de `relatorio_empresa._o_que_mudou`)."""

    indicador: str
    nome: str
    antes: float
    agora: float
    antes_texto: str
    agora_texto: str
    desde: date  # a data do balanço anterior
    item: Item  # o item de agora (dá a base e a fonte)
    maior_e_melhor: bool


def _itens(secoes: Iterable[Secao], chaves: Iterable[str]) -> Iterator[Item]:
    por_chave = {s.chave: s for s in secoes if not s.trancada}
    for chave in chaves:
        secao = por_chave.get(chave)
        if secao is not None:
            yield from (i for i in secao.itens if i.texto != "—")


def _ponto(lado: str, item: Item, texto: str) -> Ponto:
    return Ponto(lado, texto, item.texto, item.base, item.fonte, item.chave)


def _contra_o_setor(item: Item, lados: dict[str, str]) -> Ponto | None:
    lado = lados.get(item.nota or "")
    if lado is None or item.comparacao is None:
        return None
    return _ponto(
        lado,
        item,
        f"{item.nome} de {item.texto} ({item.base}): {item.nota} contra o "
        f"{item.comparacao.contra}; {item.comparacao.texto}.",
    )


def _pelo_setor(secoes: Sequence[Secao], lados: dict[str, str]) -> Iterator[Ponto]:
    for item in _itens(secoes, SECOES_COM_NOTA):
        if (ponto := _contra_o_setor(item, lados)) is not None:
            yield ponto


def _classicas(secoes: Sequence[Secao]) -> Iterator[Ponto]:
    """As notas clássicas contra a escala do próprio artigo (Altman, Beneish, Piotroski)."""
    for item in _itens(secoes, ("notas_classicas",)):
        escala = item.comparacao.texto if item.comparacao else ""
        if item.chave == "altman" and item.nota:
            lado = FORTE if item.nota == "segura" else ATENCAO
            yield _ponto(lado, item, f"{item.nome} de {item.texto}: faixa {item.nota} do artigo ({escala}).")  # fmt: skip
        elif item.chave == "beneish" and item.nota:
            lado = ATENCAO if item.nota.startswith("acima") else FORTE
            yield _ponto(
                lado, item, f"{item.nome} de {item.texto}: {item.nota} ({escala})."
            )
        elif item.chave == "piotroski" and item.valor is not None:
            if item.valor >= notas_classicas.PIOTROSKI_ALTO:
                yield _ponto(FORTE, item, f"{item.nome} de {item.texto} pontos de 9: no grupo de cima do artigo.")  # fmt: skip
            elif item.valor <= notas_classicas.PIOTROSKI_BAIXO:
                yield _ponto(ATENCAO, item, f"{item.nome} de {item.texto} pontos de 9: no grupo de baixo do artigo.")  # fmt: skip


def _mudancas(mudancas: Sequence[Mudanca]) -> Iterator[Ponto]:
    """O que andou 10% ou mais desde o balanço anterior; o lado segue o sentido do indicador."""
    for m in mudancas:
        if m.antes == 0:
            continue
        variacao = (m.agora - m.antes) / abs(m.antes)
        if abs(variacao) < VARIACAO_RELEVANTE:
            continue
        lado = FORTE if (variacao > 0) == m.maior_e_melhor else ATENCAO
        sentido = "subiu" if variacao > 0 else "caiu"
        yield _ponto(
            lado,
            m.item,
            f"{m.nome} {sentido} de {m.antes_texto} para {m.agora_texto} desde o balanço de "
            f"{m.desde:%d/%m/%Y} ({variacao:+.0%}).",
        )


def _faixa_fixa(secoes: Sequence[Secao]) -> Iterator[Ponto]:
    for item in _itens(secoes, ("caixa",)):
        faixa = notas.FAIXAS_FIXAS.get(item.chave)
        if faixa is None or not item.nota or item.comparacao is None:
            continue
        lado = FORTE if item.nota == faixa.notas[1] else ATENCAO
        yield _ponto(lado, item, f"{item.nome} de {item.texto}: {item.nota} na faixa fixa ({item.comparacao.texto}).")  # fmt: skip


def _fundos(secoes: Sequence[Secao]) -> Iterator[Ponto]:
    """Os fundos com a ação contra o mesmo mês do ano anterior (dossiê da base)."""
    for item in _itens(secoes, ("ofertas_e_fundos",)):
        c = item.comparacao
        if (
            item.chave != "fundos_com_a_acao"
            or c is None
            or not c.valor
            or item.valor is None
        ):
            continue
        variacao = (item.valor - c.valor) / c.valor
        if abs(variacao) >= VARIACAO_RELEVANTE:
            lado = FORTE if variacao > 0 else ATENCAO
            sentido = "mais" if variacao > 0 else "menos"
            yield _ponto(lado, item, f"{item.texto} fundos com a ação em {item.base}, {sentido} que um ano antes ({c.texto}).")  # fmt: skip


def _anos_entre(desde: str, ate: str) -> float | None:
    try:
        inicio, fim = (
            date(int(t[6:10]), int(t[3:5]), int(t[:2])) for t in (desde, ate)
        )
    except (ValueError, IndexError):
        return None
    return (fim - inicio).days / 365.25


def _auditor(secoes: Sequence[Secao]) -> Iterator[Ponto]:
    for item in _itens(secoes, ("auditor_e_controladas",)):
        if item.chave != "auditor_desde":
            continue
        anos = _anos_entre(item.texto, item.base)
        if anos is not None and anos < ANOS_DA_TROCA_RECENTE and item.comparacao:
            yield _ponto(ATENCAO, item, f"Auditor trocado em {item.texto}, há menos de {ANOS_DA_TROCA_RECENTE} anos (antes: {item.comparacao.texto}).")  # fmt: skip


def _demonstracao(secoes: Sequence[Secao]) -> Iterator[Ponto]:
    for item in _itens(secoes, ("ficha_tecnica",)):
        if item.chave != "ultima_demonstracao" or item.comparacao is None:
            continue
        prazo = item.comparacao.texto
        if REAPRESENTADA in item.texto:
            yield _ponto(ATENCAO, item, f"Última demonstração reapresentada: {item.texto} ({prazo}).")  # fmt: skip
        elif DEPOIS_DO_PRAZO in prazo:
            yield _ponto(ATENCAO, item, f"{item.texto} entregue {prazo}.")
        elif DENTRO_DO_PRAZO in prazo:
            yield _ponto(FORTE, item, f"{item.texto} entregue {prazo}.")


def pontos(secoes: Sequence[Secao], mudancas: Sequence[Mudanca]) -> list[Ponto]:
    """Até `MAXIMO_POR_LADO` pontos de cada lado, na ordem das regras (as mais fortes primeiro) e
    um por indicador (o primeiro que uma regra achar)."""
    candidatos = [
        *_classicas(secoes),
        *_pelo_setor(secoes, NOTAS_DAS_PONTAS),
        *_mudancas(mudancas),
        *_faixa_fixa(secoes),
        *_fundos(secoes),
        *_auditor(secoes),
        *_pelo_setor(secoes, NOTAS_DO_MEIO),
        *_demonstracao(secoes),
    ]
    escolhidos: list[Ponto] = []
    vistos: set[str] = set()
    for ponto in candidatos:
        do_lado = sum(p.lado == ponto.lado for p in escolhidos)
        if ponto.indicador in vistos or do_lado >= MAXIMO_POR_LADO:
            continue
        vistos.add(ponto.indicador)
        escolhidos.append(ponto)
    return escolhidos


def por_lado(pontos: Sequence[Ponto]) -> list[tuple[str, list[Ponto]]]:
    """Os pontos agrupados com o título de cada lado (fortes, depois atenção), só os que têm."""
    grupos = [
        (titulo, [p for p in pontos if p.lado == lado])
        for lado, titulo in TITULOS_DOS_LADOS.items()
    ]
    return [(titulo, lista) for titulo, lista in grupos if lista]


def frase(ponto: Ponto) -> str:
    """O ponto como a página e o PDF mostram: o texto e a tabela de origem."""
    return f"{ponto.texto} Fonte: {ponto.tabela}."
