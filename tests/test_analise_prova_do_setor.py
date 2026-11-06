"""A prova do setor elétrico (molde D, PR 6): os textos que os modelos escreveram, guardados como vieram.

Rodada 1 (guia `setor_v1`): Haiku, Sonnet e Opus escreveram; a porta 2 às cegas conferiu cada um
(o Sonnet confere Haiku e Opus; o Opus confere o Sonnet). Os testes não chamam a API: leem o que foi
pago uma vez (22/10/2026, US$ 2,31) e prendem o que a prova mostrou. O principal: nenhum modelo usou
o ano que a base não fechou (2026) como fato do setor sem a lacuna. O que reprovou de verdade, e que
o guia `setor_v2` ensina: a porcentagem da tabela entra na conta como o número escrito (17,6), não
como a fração; e anos e datas sem a linha que os traz.

Rodada 2 (guia `setor_v2`, só o Opus, US$ 1,09; total da prova US$ 3,40): as contas e as datas
passaram, e ficaram do modelo 5 das 7 partes (eram 2). Sobrou uma frase de `limites` que cita a linha
do ano parcial sem a lacuna: a porta 1 reprova e o molde fica com a parte.
"""

import json

import pytest

from src.analise_escrita import avaliacao, entrada, montagem, pedido, porta1, saida
from tests.ajudantes_da_analise_do_setor import PAR_DO_SETOR, PARTES_DO_SETOR, gabarito

PROVA = PAR_DO_SETOR / "prova"
ESCRITORES_DA_RODADA_1 = ("haiku", "sonnet", "opus")
# as partes que ficam do modelo depois das portas 1 e 2 (o resto volta ao molde)
DO_MODELO_NA_RODADA_1 = {
    "haiku": set(),
    "sonnet": {"em_meia_pagina", "o_que_mudaria", "limites"},
    "opus": {"em_meia_pagina", "o_que_mudaria"},
}


def _ler(nome: str) -> dict:
    return json.loads((PROVA / nome).read_text(encoding="utf-8"))


def _entrada() -> dict:
    """A entrada contra a qual os textos foram escritos, congelada (o hash das respostas é dela)."""
    return _ler("entrada_da_prova.json")


def _texto(nome: str) -> saida.Analise:
    registro = _ler(f"resposta_{nome}.json")
    return saida.ler_analise(
        pedido.ler_resposta(registro["stop_reason"], registro["resposta_bruta"]),
        PARTES_DO_SETOR,
    )


def _montagem(nome: str) -> montagem.Montagem:
    registro = _ler(f"resposta_{nome}.json")
    return montagem.da_resposta_bruta(
        registro["stop_reason"],
        registro["resposta_bruta"],
        _entrada(),
        registro["hash_da_entrada"],
        _ler(f"cega_{nome}.json")["reprovadas"],
    )


@pytest.mark.parametrize("modelo", ESCRITORES_DA_RODADA_1)
def test_respostas_da_rodada_1_sao_da_entrada_guardada(modelo):
    registro = _ler(f"resposta_{modelo}_v1.json")
    assert registro["hash_da_entrada"] == entrada.hash_da_entrada(_entrada())
    assert registro["stop_reason"] == "end_turn"
    assert registro["versao_do_guia"] == "setor_v1"
    assert registro["setor"] == "eletricas"


@pytest.mark.parametrize("modelo", ESCRITORES_DA_RODADA_1)
def test_nenhum_modelo_usou_o_ano_parcial_como_fato(modelo):
    """O que a linha 167 da fila pedia: 2026 (8 meses) só aparece com a lacuna."""
    texto = _texto(f"{modelo}_v1")
    regras = {r.regra for r in porta1.conferir(texto, _entrada()).reprovacoes}
    assert regras.isdisjoint({porta1.ANO_PARCIAL, porta1.LACUNA})
    criterios = {c.numero: c for c in avaliacao.avaliar(texto, _entrada(), gabarito())}
    assert criterios[2].passou


@pytest.mark.parametrize("modelo", ESCRITORES_DA_RODADA_1)
def test_texto_montado_passa_na_porta1(modelo):
    """A análise que iria para a tela: o que ficou do modelo mais o molde, sem reprovação."""
    montada = _montagem(f"{modelo}_v1")
    assert montada.motivo is None
    assert porta1.conferir(montada.analise, _entrada()).reprovacoes == ()
    do_modelo = {
        p.chave for p in montada.analise.partes if p.origem == saida.ORIGEM_MODELO
    }
    assert do_modelo == DO_MODELO_NA_RODADA_1[modelo]


def test_faixa_do_lado_a_lado_nao_e_previsao():
    """O Opus escreveu "vai de -22,0% a 56,0%": faixa, não futuro (a porta 1 errava com o sinal)."""
    regras = {
        r.regra for r in porta1.conferir(_texto("opus_v1"), _entrada()).reprovacoes
    }
    assert porta1.PREVISAO not in regras


def test_contas_reprovadas_do_opus_sao_da_porcentagem_escrita_como_numero():
    """Cada conta reprovada usou a parte do mercado como o número escrito (x), não a fração (x/100)."""
    reprovacoes = porta1.conferir(_texto("opus_v1"), _entrada()).reprovacoes
    contas = [r for r in reprovacoes if r.regra == porta1.CONTA]
    assert contas and all(r.parte == "participacao" for r in contas)
    assert all("não está em participacao.participacao_" in r.detalhe for r in contas)


@pytest.mark.parametrize("modelo", ESCRITORES_DA_RODADA_1)
def test_porta2_conferiu_todas_as_frases_com_outro_modelo(modelo):
    cega = _ler(f"cega_{modelo}_v1.json")
    total = sum(
        len(g.frases) for p in _texto(f"{modelo}_v1").partes for g in p.paragrafos
    )
    assert len(cega["frases"]) == total
    assert cega["conferente"] != cega["escritor"]


DO_MODELO_NA_RODADA_2 = {
    "em_meia_pagina",
    "tamanho_e_concentracao",
    "participacao",
    "lado_a_lado",
    "o_que_mudaria",
}


def test_resposta_da_rodada_2_e_do_guia_v2():
    registro = _ler("resposta_opus_v2.json")
    assert registro["hash_da_entrada"] == entrada.hash_da_entrada(_entrada())
    assert registro["stop_reason"] == "end_turn"
    assert registro["versao_do_guia"] == pedido.VERSAO_DO_GUIA_DO_SETOR == "setor_v2"


def test_rodada_2_so_reprova_o_ano_parcial_em_limites():
    """Contas, datas e "vai até dez/2025" passam; fica uma frase que cita 2026 sem a lacuna."""
    reprovacoes = porta1.conferir(_texto("opus_v2"), _entrada()).reprovacoes
    assert {(r.parte, r.regra) for r in reprovacoes} == {
        ("limites", porta1.ANO_PARCIAL)
    }
    criterios = {
        c.numero: c.passou
        for c in avaliacao.avaliar(_texto("opus_v2"), _entrada(), gabarito())
    }
    assert criterios == {1: True, 2: False, 3: True, 4: True, 5: True}


def test_rodada_2_monta_com_mais_partes_do_modelo():
    montada = _montagem("opus_v2")
    assert montada.motivo is None
    assert porta1.conferir(montada.analise, _entrada()).reprovacoes == ()
    do_modelo = {
        p.chave for p in montada.analise.partes if p.origem == saida.ORIGEM_MODELO
    }
    assert do_modelo == DO_MODELO_NA_RODADA_2
    assert len(do_modelo) > len(DO_MODELO_NA_RODADA_1["opus"])


def test_porta2_da_rodada_2_conferiu_com_outro_modelo():
    cega = _ler("cega_opus_v2.json")
    total = sum(len(g.frases) for p in _texto("opus_v2").partes for g in p.paragrafos)
    assert len(cega["frases"]) == total
    assert cega["conferente"] != cega["escritor"]
