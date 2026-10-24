"""Reserva por regras dos gráficos: o que entra quando o modelo erra ou escolhe pouco.

A reserva sai das tabelas fixas da ficha, passa na mesma porta 1 e só completa até o mínimo.
"""

import json
from dataclasses import replace

import pytest

from src.analise_escrita import graficos as gr
from src.analise_escrita import porta1_dos_graficos as p1g
from src.analise_escrita import reserva_dos_graficos as rg
from src.analise_escrita import saida
from tests.ajudantes_da_analise import PAR_DA_CPFL


@pytest.fixture(scope="module")
def cpfl() -> tuple[dict, saida.Analise]:
    entrada = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
    gabarito = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))
    return entrada, saida.ler_analise(gabarito["analise"])


# o achado do modelo tem número da primeira linha da tabela (a porta 1 confere)
ACHADOS = {
    "ofertas_e_fundos.fundos_por_mes": "No primeiro mês, 436 fundos tinham a ação.",
    "setor_regulado.aneel_consumidores": "No primeiro ano, a empresa tinha 11,1% dos consumidores.",
}


def _do_modelo(
    tabela: str, tipo: str, eixo: str, coluna: str, parte: str
) -> gr.Grafico:
    return gr.Grafico(
        tipo=tipo,
        tabela=tabela,
        eixo=eixo,
        colunas=(coluna,),
        titulo="Um gráfico",
        parte=parte,
        paragrafo=0,
        por_que=saida.Frase(ACHADOS[tabela], (f"{tabela}.0",)),
    )


FUNDOS = _do_modelo(
    "ofertas_e_fundos.fundos_por_mes", "linha_no_tempo", "Mês", "Fundos", "quem_manda"
)
CONSUMIDORES = _do_modelo(
    "setor_regulado.aneel_consumidores",
    "linha_no_tempo",
    "Ano",
    "Consumidores",
    "o_que_e",
)
ERRADO = replace(FUNDOS, tabela="historico.anos")
DESTAQUE_BOM = gr.Destaque(
    "resultado",
    "o_que_os_numeros_mostram",
    saida.Frase("A cascata mostra os passos.", ("resultado.cascata.0",)),
)


def test_reserva_da_cpfl_passa_na_porta1(cpfl):
    entrada, analise = cpfl
    reserva = rg.graficos_de_reserva(entrada, analise)
    assert len(reserva) >= gr.MINIMO_DE_GRAFICOS
    assert {g.origem for g in reserva} == {rg.ORIGEM_REGRAS}
    assert p1g.conferir(gr.Escolha(reserva), entrada, analise).aprovada


def test_reserva_pula_a_tabela_que_a_ficha_nao_tem(cpfl):
    entrada, analise = cpfl
    sem_tabelas = {
        **entrada,
        "linhas": [li for li in entrada["linhas"] if li["tipo"] != "linha"],
    }
    assert rg.graficos_de_reserva(sem_tabelas, analise) == ()


def test_escolha_boa_do_modelo_fica_inteira(cpfl):
    entrada, analise = cpfl
    escolha = gr.Escolha((FUNDOS, CONSUMIDORES))
    finais = rg.graficos_finais(escolha, entrada, analise, frozenset())
    assert finais.graficos == (FUNDOS, CONSUMIDORES)


def test_grafico_reprovado_sai_e_a_reserva_completa_o_minimo(cpfl):
    entrada, analise = cpfl
    finais = rg.graficos_finais(
        gr.Escolha((ERRADO, CONSUMIDORES)), entrada, analise, frozenset()
    )
    assert finais.graficos[0] == CONSUMIDORES
    assert len(finais.graficos) == gr.MINIMO_DE_GRAFICOS
    assert finais.graficos[1].origem == rg.ORIGEM_REGRAS


def test_reserva_nao_repete_o_que_o_modelo_escolheu(cpfl):
    entrada, analise = cpfl
    primeira = rg.graficos_de_reserva(entrada, analise)[0]
    do_modelo = replace(
        primeira, titulo="O mesmo, com outro título", origem=saida.ORIGEM_MODELO
    )
    finais = rg.graficos_finais(
        gr.Escolha((do_modelo, ERRADO)), entrada, analise, frozenset()
    )
    assert [g.chave for g in finais.graficos].count(primeira.chave) == 1
    assert len(finais.graficos) == gr.MINIMO_DE_GRAFICOS


def test_destaque_reprovado_sai(cpfl):
    entrada, analise = cpfl
    ruim = gr.Destaque("valuation", "quem_manda", saida.Frase("Nada.", ("x",)))
    escolha = gr.Escolha((FUNDOS, CONSUMIDORES), (ruim, DESTAQUE_BOM))
    finais = rg.graficos_finais(escolha, entrada, analise, frozenset())
    assert finais.destaques == (DESTAQUE_BOM,)


def test_sem_a_porta_2_nada_do_modelo_vai_ao_ar(cpfl):
    entrada, analise = cpfl
    escolha = gr.Escolha((FUNDOS, CONSUMIDORES), (DESTAQUE_BOM,))
    finais = rg.graficos_finais(escolha, entrada, analise, None)
    assert {g.origem for g in finais.graficos} == {rg.ORIGEM_REGRAS}
    assert finais.destaques == ()


def test_reprovado_na_porta_2_sai(cpfl):
    entrada, analise = cpfl
    escolha = gr.Escolha((FUNDOS, CONSUMIDORES), (DESTAQUE_BOM,))
    finais = rg.graficos_finais(
        escolha, entrada, analise, frozenset({"grafico.1", "destaque.0"})
    )
    assert finais.graficos[0] == FUNDOS
    assert finais.graficos[1].origem == rg.ORIGEM_REGRAS
    assert finais.destaques == ()
