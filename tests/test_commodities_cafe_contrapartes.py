"""Os dois lados do risco de travar e a simulação (src/commodities/cafe/contrapartes.py, PR 12 do café)."""

import re
from dataclasses import fields

import pytest

from base.contrapartes import cafe as ficha
from src.commodities.cafe.contrapartes import (
    COMPRADOR,
    PRODUTOR,
    SimulacaoDaTrava,
    simular_risco_de_travar,
)
from src.conteudo import carregar_textos_do_cafe

DOIS_LADOS = "Os dois lados do risco de travar"
# nada de nota, cor ou classificação: nem no nome dos campos, nem no texto
NOTA = re.compile(
    r"\b(nota|score|sem[áa]foro|rating|classifica[çc][ãa]o|verde|amarelo|vermelho|"
    r"risco (alto|m[ée]dio|baixo))\b",
    re.IGNORECASE,
)


def test_preco_subiu_quem_vendeu_travado_deixa_de_ganhar():
    simulacao = simular_risco_de_travar(1500.0, 2300.0, 1000)
    assert simulacao.diferenca_por_saca == pytest.approx(800.0)
    assert simulacao.diferenca_total == pytest.approx(800_000.0)
    assert simulacao.quem_deixa_de_ganhar == PRODUTOR
    assert "R$ 800,00 por saca" in simulacao.texto
    assert "R$ 800.000,00 nas 1.000 sacas" in simulacao.texto


def test_preco_caiu_quem_comprou_travado_paga_acima():
    simulacao = simular_risco_de_travar(2300.0, 1800.0, 250)
    assert simulacao.diferenca_total == pytest.approx(-125_000.0)
    assert simulacao.quem_deixa_de_ganhar == COMPRADOR
    assert "caiu R$ 500,00" in simulacao.texto
    assert "R$ 125.000,00" in simulacao.texto


def test_preco_igual_ninguem_deixa_de_ganhar():
    simulacao = simular_risco_de_travar(2000.0, 2000.0, 10)
    assert simulacao.diferenca_total == 0
    assert simulacao.quem_deixa_de_ganhar is None


@pytest.mark.parametrize(
    ("preco_na_data", "preco_hoje", "sacas"),
    [(0, 2000, 10), (2000, -1, 10), (2000, 2000, 0)],
)
def test_entrada_sem_sentido_e_erro(preco_na_data, preco_hoje, sacas):
    with pytest.raises(ValueError):
        simular_risco_de_travar(preco_na_data, preco_hoje, sacas)


def test_texto_dos_dois_lados():
    texto = carregar_textos_do_cafe()[DOIS_LADOS]
    assert "**Quando o preço sobe**" in texto and "**Quando o preço cai**" in texto
    # os casos de 2024–25, cada um com o veículo e o link
    assert "900 mil sacas" in texto
    assert "[Brazil Journal](https://braziljournal.com/" in texto
    assert "R$ 2,13 bilhões" in texto
    assert "[Bloomberg Línea](https://www.bloomberglinea.com.br/" in texto
    assert "não é nota" in texto.casefold()
    assert "recomendação de investimento" in texto
    assert not ficha.palavras_vedadas_em(texto)
    # a única "nota" do texto é a que diz que a simulação não é uma
    assert not NOTA.search(re.sub(r"não é nota", "", texto, flags=re.IGNORECASE))


def test_ficha_na_tela_sem_nota_nem_semaforo():
    """Sem tela neste PR (a ficha chega ao Painel no PR 11): o que a tela vai receber já nasce sem nota."""
    fatos = ficha.ler()
    for contraparte in ficha.fichas(fatos):
        dado = ficha.ficha_em_dicionario(contraparte)
        chaves = set(dado) | {k for f in dado["fatos"] for k in f}  # type: ignore[union-attr]
        assert not any(NOTA.search(c.replace("_", " ")) for c in chaves), chaves
        textos = [str(contraparte.nome), *contraparte.o_que_nao_sabemos]
        textos += [f.descricao for f in contraparte.fatos]
        assert not any(NOTA.search(t) for t in textos)
    campos = {c.name for c in fields(SimulacaoDaTrava)}
    assert not any(NOTA.search(c.replace("_", " ")) for c in campos), campos
    for preco_hoje in (1000.0, 2000.0, 3000.0):
        simulacao = simular_risco_de_travar(2000.0, preco_hoje, 100)
        assert not NOTA.search(simulacao.texto)
        assert not ficha.palavras_vedadas_em(simulacao.texto)
