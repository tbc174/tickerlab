"""Reserva por regras dos gráficos (plano de 23/10/2026): o que entra quando o modelo erra.

A escolha do modelo passa pela porta 1; o gráfico reprovado sai e o destaque reprovado também. Se
sobram menos de `MINIMO_DE_GRAFICOS`, a reserva completa com gráficos fixos das tabelas que toda
ficha de empresa costuma ter (a cascata do resultado, a ponte da dívida, os fundos com a ação), na
ordem abaixo, pulando a tabela que esta ficha não tem e o desenho que o modelo já escolheu. A
reserva passa na mesma porta: um gráfico dela que não serve a esta ficha também fica de fora.

O relatório do setor tem a sua (a concentração, o tamanho do mercado e as empresas lado a lado):
as tabelas dele mudam de nome com a fonte (`tamanho_aneel_consumidores`), então a reserva acha a
tabela pela seção.
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
    outra_coluna: str = ""  # a dispersão tem duas


# a ordem é a da preferência: o que mais explica a empresa primeiro
_FIXOS = (
    _Fixo(
        "resultado.cascata", "cascata", "passo", "valor",
        "Da receita ao lucro, passo a passo", "o_que_os_numeros_mostram",
        "A cascata mostra quanto cada custo e cada despesa tiram da receita até o lucro.",
    ),
    _Fixo(
        "endividamento.ponte", "cascata", "passo", "valor",
        # a ponte vai de um balanço anual ao seguinte: termina no último ano fechado, não no
        # balanço mais recente (a porta 2 da prova de 23/10 pegou o "de agora" do título antigo)
        "Da dívida líquida no último ano fechado", "dinheiro",
        "A ponte mostra o que aumentou e o que diminuiu a dívida líquida no último ano fechado.",
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


COLUNAS_QUE_NAO_SAO_O_VALOR = frozenset({"Ano", "Meses no ano", "Até"})
HHI = "HHI (pontos)"  # a coluna que a seção de concentração escreve


def _tabela_da_secao(
    tabelas: dict[str, list[gr.LinhaDaTabela]], secao: str
) -> str | None:
    """O id da primeira tabela da seção (`secao.nome_da_tabela`), ou None se a ficha não a tem."""
    return next((t for t in tabelas if t.startswith(f"{secao}.")), None)


def _valor_do_tamanho(linhas: list[gr.LinhaDaTabela]) -> str:
    """A coluna do tamanho do mercado: a que sobra depois do ano, dos meses e do "até"."""
    colunas = [c for c in linhas[0].celulas if c not in COLUNAS_QUE_NAO_SAO_O_VALOR]
    return colunas[0] if colunas else ""


def _fixos_do_setor(tabelas: dict[str, list[gr.LinhaDaTabela]]) -> list[_Fixo]:
    """Os desenhos fixos do relatório do setor, nas tabelas que a ficha do setor tem."""
    fixos = []
    if concentracao := _tabela_da_secao(tabelas, "concentracao"):
        fixos.append(
            _Fixo(
                concentracao, "linha_no_tempo", "Ano", HHI,
                "Concentração do mercado (HHI) ano a ano", "tamanho_e_concentracao",
                "A linha mostra como o índice de concentração do mercado andou em cada ano fechado.",
            )
        )  # fmt: skip
    if tamanho := _tabela_da_secao(tabelas, "tamanho"):
        fixos.append(
            _Fixo(
                tamanho, "barras_no_tempo", "Ano", _valor_do_tamanho(tabelas[tamanho]),
                "Tamanho do mercado ano a ano", "tamanho_e_concentracao",
                "As barras mostram o tamanho do mercado em cada ano fechado.",
            )
        )  # fmt: skip
    if lado_a_lado := _tabela_da_secao(tabelas, "lado_a_lado"):
        fixos.append(
            _Fixo(
                lado_a_lado, "dispersao", "Companhia", "Margem líquida",
                "Margem líquida e ROE de cada companhia aberta", "lado_a_lado",
                "Cada ponto é uma companhia aberta: a margem líquida de um lado, o retorno sobre o patrimônio do outro.",
                outra_coluna="ROE pelo DuPont",
            )
        )  # fmt: skip
    return fixos


def _grafico(fixo: _Fixo, primeira_linha: str) -> gr.Grafico:
    return gr.Grafico(
        tipo=fixo.tipo,
        tabela=fixo.tabela,
        eixo=fixo.eixo,
        colunas=tuple(c for c in (fixo.coluna, fixo.outra_coluna) if c),
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
    fixos = (
        _fixos_do_setor(tabelas) if entrada.get("tipo") == saida.TIPO_SETOR else _FIXOS
    )
    candidatos = [
        _grafico(fixo, tabelas[fixo.tabela][0].id)
        for fixo in fixos
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
