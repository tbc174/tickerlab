"""Reserva por regras dos gráficos (plano de 23/10/2026): o que entra quando o modelo erra.

A escolha do modelo passa pela porta 1; o gráfico reprovado sai e o destaque reprovado também. Se
sobram menos de `MINIMO_DE_GRAFICOS`, a reserva completa com gráficos fixos das tabelas que toda
ficha de empresa costuma ter (a cascata do resultado, a ponte da dívida, os fundos com a ação), na
ordem abaixo, pulando a tabela que esta ficha não tem e o desenho que o modelo já escolheu. A
reserva passa na mesma porta: um gráfico dela que não serve a esta ficha também fica de fora.
"""

from dataclasses import dataclass
from typing import Any

from src.analise_escrita import graficos as gr
from src.analise_escrita import porta1_dos_graficos as p1g
from src.analise_escrita import saida

ORIGEM_REGRAS = "regras"


@dataclass(frozen=True)
class _Fixo:
    tabela: str
    tipo: str
    eixo: str
    coluna: str
    titulo: str
    parte: str
    por_que: str  # sem número: a frase só diz o que o gráfico mostra


# a ordem é a da preferência: o que mais explica a empresa primeiro
_FIXOS = (
    _Fixo(
        "resultado.cascata", "cascata", "passo", "valor",
        "Da receita ao lucro, passo a passo", "o_que_os_numeros_mostram",
        "A cascata mostra quanto cada custo e cada despesa tiram da receita até o lucro.",
    ),
    _Fixo(
        "endividamento.ponte", "cascata", "passo", "valor",
        "Da dívida líquida do começo à de agora", "dinheiro",
        "A ponte mostra o que aumentou e o que diminuiu a dívida líquida no período.",
    ),
    _Fixo(
        "ofertas_e_fundos.fundos_por_mes", "linha_no_tempo", "Mês", "Fundos",
        "Fundos com a ação, mês a mês", "quem_manda",
        "A linha mostra quantos fundos tinham a ação em cada mês.",
    ),
    _Fixo(
        "ofertas_e_fundos.ofertas_por_ano", "barras_no_tempo", "Ano", "Ofertas",
        "Ofertas registradas por ano", "dinheiro",
        "As barras mostram quantas ofertas de papéis a empresa registrou em cada ano.",
    ),
)  # fmt: skip


def _grafico(fixo: _Fixo, primeira_linha: str) -> gr.Grafico:
    return gr.Grafico(
        tipo=fixo.tipo,
        tabela=fixo.tabela,
        eixo=fixo.eixo,
        colunas=(fixo.coluna,),
        titulo=fixo.titulo,
        parte=fixo.parte,
        paragrafo=0,
        por_que=saida.Frase(fixo.por_que, (primeira_linha,)),
        origem=ORIGEM_REGRAS,
    )


def graficos_de_reserva(
    entrada: dict[str, Any], analise: saida.Analise
) -> tuple[gr.Grafico, ...]:
    """Os gráficos fixos que esta ficha sustenta, já aprovados na porta 1, na ordem da preferência."""
    tabelas = gr.tabelas_da_entrada(entrada)
    candidatos = [
        _grafico(fixo, tabelas[fixo.tabela][0].id)
        for fixo in _FIXOS
        if fixo.tabela in tabelas
    ]
    conferencia = p1g.conferir(gr.Escolha(tuple(candidatos)), entrada, analise)
    return tuple(
        g for i, g in enumerate(candidatos) if i not in conferencia.graficos_reprovados
    )


def graficos_finais(
    escolha: gr.Escolha,
    entrada: dict[str, Any],
    analise: saida.Analise,
    reprovados_na_porta2: frozenset[str] | None,
) -> gr.Escolha:
    """A escolha que vai para o relatório: o que o modelo acertou nas duas portas, completado pela
    reserva. Sem a porta 2 (`None`), nada do modelo vai ao ar: fica só a reserva."""
    conferencia = p1g.conferir(escolha, entrada, analise)

    def aprovado(item: str, indice: int, reprovados_na_porta1: frozenset[int]) -> bool:
        if reprovados_na_porta2 is None or indice in reprovados_na_porta1:
            return False
        return p1g.rotulo(item, indice) not in reprovados_na_porta2

    graficos = [
        g
        for i, g in enumerate(escolha.graficos)
        if aprovado(p1g.GRAFICO, i, conferencia.graficos_reprovados)
    ]
    if len(graficos) < gr.MINIMO_DE_GRAFICOS:
        escolhidos = {g.chave for g in graficos}
        sobra = [
            g
            for g in graficos_de_reserva(entrada, analise)
            if g.chave not in escolhidos
        ]
        graficos += sobra[: gr.MINIMO_DE_GRAFICOS - len(graficos)]
    destaques = tuple(
        d
        for i, d in enumerate(escolha.destaques)
        if aprovado(p1g.DESTAQUE, i, conferencia.destaques_reprovados)
    )
    return gr.Escolha(tuple(graficos), destaques)
