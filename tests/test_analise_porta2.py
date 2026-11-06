"""A porta 2: um segundo modelo confere o sentido de cada frase, às cegas (sem saber quem escreveu)."""

import json

import pytest

from src.analise_escrita import molde, pedido, porta2, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

ENTRADA = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
GABARITO = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))
ANALISE = saida.ler_analise(GABARITO["analise"])


def _todas_sustentadas(analise: saida.Analise = ANALISE) -> list[dict]:
    return [
        {"frase": rotulo, "veredito": porta2.SUSTENTADA, "motivo": ""}
        for rotulo, _ in porta2.frases_rotuladas(analise)
    ]


def _veredito(itens: list[dict]) -> porta2.Veredito:
    return porta2.ler_veredito("end_turn", json.dumps({"frases": itens}), ANALISE)


def test_conferente_e_sempre_outro_modelo():
    for escritor in pedido.ESCRITORES:
        assert porta2.conferente(escritor) != escritor
        assert porta2.conferente(escritor) in pedido.MODELOS


def test_pedido_as_cegas_nao_diz_quem_escreveu_nem_leva_o_gabarito():
    analise = molde.molde(ENTRADA)
    parametros = porta2.pedido(analise, ENTRADA, pedido.OPUS)
    texto = json.dumps(
        [parametros["system"], parametros["messages"]], ensure_ascii=False
    ).lower()
    for nome in ("haiku", "sonnet", "opus", "claude", "gabarito", "modelo escreveu"):
        assert nome not in texto
    do_gabarito = [f.texto.lower() for _, f in porta2.frases_rotuladas(ANALISE)]
    assert not any(frase in texto for frase in do_gabarito if len(frase) > 40)
    assert parametros["model"] == pedido.OPUS


def test_pedido_numera_cada_frase_com_tipo_e_notas():
    parametros = porta2.pedido(ANALISE, ENTRADA, pedido.SONNET)
    conteudo = parametros["messages"][0]["content"]
    rotulo, frase = porta2.frases_rotuladas(ANALISE)[0]
    assert f"[{rotulo}] (fato) {frase.texto}" in conteudo
    assert parametros["output_config"]["format"]["schema"] == porta2.ESQUEMA


def test_tudo_sustentado_nada_reprova():
    veredito = _veredito(_todas_sustentadas())
    assert veredito.reprovadas == frozenset()
    assert veredito.motivo is None


@pytest.mark.parametrize("ruim", [porta2.FORA_DOS_DADOS, porta2.JUIZO_DE_VALOR])
def test_frase_fora_dos_dados_ou_com_juizo_manda_a_parte_ao_molde(ruim):
    itens = _todas_sustentadas()
    (alvo,) = [i for i in itens if i["frase"] == "dinheiro.1.1"]
    alvo.update(veredito=ruim, motivo="a ficha não diz isso")
    veredito = _veredito(itens)
    assert veredito.reprovadas == frozenset({"dinheiro"})
    assert ("dinheiro.1.1", ruim, "a ficha não diz isso") in veredito.frases


def test_frase_sem_veredito_reprova_a_parte():
    """Nunca aprova por falta: a frase que a porta 2 não julgou reprova a parte dela."""
    itens = [i for i in _todas_sustentadas() if i["frase"] != "limites.0.0"]
    assert _veredito(itens).reprovadas == frozenset({"limites"})


def test_veredito_fora_da_lista_reprova_a_parte():
    itens = _todas_sustentadas()
    itens[0]["veredito"] = "talvez"
    assert _veredito(itens).reprovadas == frozenset({"em_meia_pagina"})


def test_resposta_fora_do_formato_reprova_tudo():
    veredito = porta2.ler_veredito("max_tokens", "{", ANALISE)
    assert veredito.reprovadas == frozenset(saida.PARTES)
    assert veredito.motivo is not None and "max_tokens" in veredito.motivo
    sem_lista = porta2.ler_veredito("end_turn", '{"frases": "todas boas"}', ANALISE)
    assert sem_lista.reprovadas == frozenset(saida.PARTES)
