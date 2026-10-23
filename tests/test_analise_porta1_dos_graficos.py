"""Porta 1 dos gráficos: a escolha do modelo conferida por código contra a ficha e a análise.

Cada regra tem o gráfico que ela pega; a escolha boa sobre a ficha da CPFL de teste passa inteira.
"""

import json
from dataclasses import replace

import pytest

from src.analise_escrita import graficos as gr
from src.analise_escrita import porta1, saida
from src.analise_escrita import porta1_dos_graficos as p1g
from tests.ajudantes_da_analise import PAR_DA_CPFL


def _linha(i: int, ano: int, receita: float, lucro: float | None) -> dict:
    celulas = {"ano": ano, "receita": receita, "lucro_liquido": lucro, "nome": f"n{i}"}
    return {
        "id": f"historico.contas.{i}",
        "tipo": "linha",
        "tabela": "Contas",
        "celulas": celulas,
    }


ENTRADA = {
    "empresa": "CPFL ENERGIA S.A.",
    "setor": "Emp. Adm. Part. - Energia Elétrica",
    "corte": "2026-10-17",
    "secoes": {"historico": "Histórico", "resultado": "Resultado", "ficha_tecnica": "Ficha"},
    "fontes": ["CVM: dados abertos (ODbL)"],
    "linhas": [
        _linha(0, 2023, 4.1e10, 5.1e9),
        _linha(1, 2024, 4.4e10, 5.4e9),
        _linha(2, 2025, 4.5e10, None),
        {"id": "resultado.receita", "tipo": "numero", "texto": "R$ 44,4 bi", "valor": 4.44e10},
        {"id": "ficha_tecnica.nome", "tipo": "numero", "texto": "CPFL ENERGIA S.A."},
    ],
}  # fmt: skip

ANALISE = saida.Analise(
    (
        saida.Parte(
            "o_que_os_numeros_mostram",
            (saida.Paragrafo(saida.FATO, (saida.Frase("A receita subiu."),)),),
        ),
    )
)

POR_QUE = saida.Frase(
    "A receita foi de R$ 41,0 bi em 2023 a R$ 45,0 bi em 2025.",
    ("historico.contas.0", "historico.contas.2"),
)
BOM = gr.Grafico(
    tipo="linha_no_tempo",
    tabela="historico.contas",
    eixo="ano",
    colunas=("receita",),
    titulo="Receita ano a ano",
    parte="o_que_os_numeros_mostram",
    paragrafo=0,
    por_que=POR_QUE,
)
DESTAQUE = gr.Destaque(
    "resultado",
    "o_que_os_numeros_mostram",
    saida.Frase("A receita é a base.", ("resultado.receita",)),
)


def _regras(escolha: gr.Escolha, entrada: dict = ENTRADA) -> list[tuple[str, int, str]]:
    conferencia = p1g.conferir(escolha, entrada, ANALISE)
    return [(r.item, r.indice, r.regra) for r in conferencia.reprovacoes]


def test_escolha_boa_passa():
    conferencia = p1g.conferir(gr.Escolha((BOM,), (DESTAQUE,)), ENTRADA, ANALISE)
    assert conferencia.aprovada
    assert conferencia.graficos_reprovados == frozenset()


@pytest.mark.parametrize(
    ("mudanca", "regra"),
    [
        ({"tabela": "historico.anos"}, p1g.TABELA_INEXISTENTE),
        ({"colunas": ("ebitda",)}, p1g.COLUNA_INEXISTENTE),
        ({"eixo": "trimestre"}, p1g.COLUNA_INEXISTENTE),
        ({"colunas": ("nome",)}, p1g.FORMA),  # texto não é número
        ({"colunas": ("lucro_liquido",)}, p1g.FORMA),  # só 2 pontos; a linha pede 3
        ({"eixo": "nome"}, p1g.FORMA),  # linha no tempo com eixo que não é data
        ({"tipo": "barras_por_categoria", "colunas": ("receita", "lucro_liquido")}, p1g.FORMA),
        ({"colunas": ("receita", "receita")}, p1g.FORMA),
        ({"colunas": ("ano",)}, p1g.FORMA),  # o eixo não é valor
        ({"parte": "quem_manda"}, p1g.ANCORA),
        ({"paragrafo": 3}, p1g.ANCORA),
        ({"titulo": "Receita vai crescer"}, porta1.PREVISAO),
        ({"titulo": "Receita forte"}, porta1.PALAVRA),
        ({"titulo": "Receita de R$ 99 bi"}, porta1.NUMERO),
        ({"por_que": saida.Frase("A receita subiu nos três anos.")}, p1g.POR_QUE_FORA),
        ({"por_que": saida.Frase("A receita é R$ 44,4 bi.", ("resultado.receita",))},
         p1g.POR_QUE_FORA),
        ({"por_que": saida.Frase("A receita chegou a R$ 99 bi.", ("historico.contas.2",))},
         porta1.NUMERO),
        ({"por_que": saida.Frase("Compre.", ("historico.contas.2",))}, porta1.PALAVRA),
    ],
)  # fmt: skip
def test_grafico_reprovado(mudanca, regra):
    regras = _regras(gr.Escolha((replace(BOM, **mudanca),)))
    assert (p1g.GRAFICO, 0, regra) in regras


def test_grafico_repetido_reprova_o_segundo():
    regras = _regras(gr.Escolha((BOM, replace(BOM, titulo="Outra receita"))))
    assert regras == [(p1g.GRAFICO, 1, p1g.REPETIDO)]


def test_grafico_alem_do_maximo_reprova():
    seis = gr.Escolha(
        (
            BOM,
            replace(BOM, tipo="barras_no_tempo"),
            replace(BOM, tipo="barras_no_tempo", colunas=("lucro_liquido",)),
            replace(BOM, tipo="barras_no_tempo", colunas=("receita", "lucro_liquido")),
            replace(BOM, tipo="cascata", eixo="nome"),
            replace(BOM, tipo="barras_por_categoria", eixo="nome"),
        )
    )
    assert _regras(seis) == [(p1g.GRAFICO, 5, p1g.ALEM_DO_MAXIMO)]


def test_unidades_misturadas_reprovam():
    entrada = json.loads(json.dumps(ENTRADA))
    linhas = [
        {"id": f"o_que_mudou.indicadores.{i}", "tipo": "linha", "tabela": "Indicadores",
         "celulas": {"indicador": nome, "antes": antes, "agora": agora}}
        for i, (nome, antes, agora) in enumerate(
            [("Receita", "R$ 45,1 bi", "R$ 45,6 bi"), ("Margem", "32,1%", "30,0%")]
        )
    ]  # fmt: skip
    entrada["linhas"] += linhas
    grafico = replace(
        BOM, tipo="antes_e_agora", tabela="o_que_mudou.indicadores", eixo="indicador",
        colunas=("antes", "agora"),
        por_que=saida.Frase("A receita e a margem.", ("o_que_mudou.indicadores.0",)),
    )  # fmt: skip
    assert (p1g.GRAFICO, 0, p1g.FORMA) in _regras(gr.Escolha((grafico,)), entrada)
    so_receita = {**entrada, "linhas": entrada["linhas"][:-1]}
    grafico = replace(grafico, tipo="barras_por_categoria", colunas=("antes",))
    assert (
        _regras(
            gr.Escolha(
                (replace(grafico, tipo="antes_e_agora", colunas=("antes", "agora")),)
            ),
            so_receita,
        )
        == []
    )


def test_rotulo_com_pessoa_reprova():
    entrada = json.loads(json.dumps(ENTRADA))
    entrada["linhas"][0]["celulas"]["nome"] = "Maria Souza, Diretora-Presidente"
    grafico = replace(BOM, tipo="barras_por_categoria", eixo="nome")
    assert (p1g.GRAFICO, 0, porta1.PESSOA) in _regras(gr.Escolha((grafico,)), entrada)


def test_eixo_depois_do_corte_reprova():
    entrada = json.loads(json.dumps(ENTRADA))
    entrada["linhas"][2]["celulas"]["ano"] = 2027
    assert (p1g.GRAFICO, 0, porta1.DATA_FUTURA) in _regras(gr.Escolha((BOM,)), entrada)


# o porquê sem data: os testes do tempo mudam os anos do eixo
SEM_DATA = replace(
    BOM, por_que=saida.Frase("A receita ano a ano.", ("historico.contas.0",))
)


def test_ano_do_corte_ainda_aberto_reprova():
    """2026 até 17/10 ao lado de anos inteiros: a barra menor parece queda (achado da prova)."""
    entrada = json.loads(json.dumps(ENTRADA))
    entrada["linhas"][2]["celulas"]["ano"] = 2026
    entrada["linhas"][1]["celulas"]["ano"] = 2025
    entrada["linhas"][0]["celulas"]["ano"] = 2024
    assert (p1g.GRAFICO, 0, p1g.PERIODO_ABERTO) in _regras(
        gr.Escolha((SEM_DATA,)), entrada
    )
    entrada["corte"] = "2026-12-31"  # o ano fechou no corte: passa
    assert _regras(gr.Escolha((SEM_DATA,)), entrada) == []


def test_mes_do_corte_ainda_aberto_reprova():
    entrada = json.loads(json.dumps(ENTRADA))
    for i, mes in enumerate(("ago/2026", "set/2026", "out/2026")):
        entrada["linhas"][i]["celulas"]["ano"] = mes
    assert (p1g.GRAFICO, 0, p1g.PERIODO_ABERTO) in _regras(
        gr.Escolha((SEM_DATA,)), entrada
    )
    entrada["linhas"][2]["celulas"]["ano"] = "jul/2026"  # fora de ordem também vale
    assert _regras(gr.Escolha((SEM_DATA,)), entrada) == []


def test_periodo_faltando_no_eixo_reprova():
    """Ofertas por ano pula os anos sem oferta: o eixo esconde os zeros (achado da prova)."""
    entrada = json.loads(json.dumps(ENTRADA))
    entrada["linhas"][0]["celulas"]["ano"] = 2019
    regras = _regras(gr.Escolha((BOM,)), entrada)
    assert (p1g.GRAFICO, 0, p1g.PERIODO_FALTANDO) in regras
    # a forma por categoria não tem tempo: nomes podem pular
    por_nome = replace(BOM, tipo="barras_por_categoria")
    assert p1g.PERIODO_FALTANDO not in {
        r for *_, r in _regras(gr.Escolha((por_nome,)), entrada)
    }


@pytest.mark.parametrize(
    ("destaque", "regra"),
    [
        (replace(DESTAQUE, secao="valuation"), p1g.SECAO_INEXISTENTE),
        (replace(DESTAQUE, secao="ficha_tecnica",
                 por_que=saida.Frase("Ficha.", ("ficha_tecnica.nome",))), p1g.SECAO_SEM_DESTAQUE),
        (replace(DESTAQUE, parte="quem_manda"), p1g.ANCORA),
        (replace(DESTAQUE, por_que=saida.Frase("Os anos.", ("historico.contas.0",))),
         p1g.POR_QUE_FORA),
    ],
)  # fmt: skip
def test_destaque_reprovado(destaque, regra):
    assert (p1g.DESTAQUE, 0, regra) in _regras(gr.Escolha((BOM,), (destaque,)))


def test_destaque_alem_do_maximo_e_repetido():
    escolha = gr.Escolha((BOM,), (DESTAQUE, DESTAQUE, DESTAQUE))
    regras = _regras(escolha)
    assert (p1g.DESTAQUE, 1, p1g.REPETIDO) in regras
    assert (p1g.DESTAQUE, 2, p1g.ALEM_DO_MAXIMO) in regras


def test_escolha_boa_na_ficha_da_cpfl():
    entrada = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
    gabarito = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))
    analise = saida.ler_analise(gabarito["analise"])
    fundos = gr.Grafico(
        tipo="linha_no_tempo",
        tabela="ofertas_e_fundos.fundos_por_mes",
        eixo="Mês",
        colunas=("Fundos",),
        titulo="Fundos com a ação, mês a mês",
        parte="quem_manda",
        paragrafo=0,
        por_que=saida.Frase(
            "Em abril de 2024, 436 fundos tinham a ação.",
            ("ofertas_e_fundos.fundos_por_mes.0",),
        ),
    )
    cascata = gr.Grafico(
        tipo="cascata",
        tabela="resultado.cascata",
        eixo="passo",
        colunas=("valor",),
        titulo="Da receita ao lucro no último ano",
        parte="o_que_os_numeros_mostram",
        paragrafo=0,
        por_que=saida.Frase("A cascata parte da receita.", ("resultado.cascata.0",)),
    )
    conferencia = p1g.conferir(gr.Escolha((fundos, cascata)), entrada, analise)
    assert conferencia.reprovacoes == ()
