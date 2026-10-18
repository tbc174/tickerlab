"""O primeiro par dados → texto: a ficha da CPFL e a análise que o Tiago aprovou em 18/10/2026.

O gabarito é a régua da prova (o texto do modelo é comparado com ele) e o teste mais duro da
porta 1: um texto bom, escrito à mão, com 43 notas e contas nossas, não pode ser reprovado.
"""

import json

from src.analise_escrita import porta1, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL, entrada_da_cpfl


def _ler(nome: str) -> dict:
    return json.loads((PAR_DA_CPFL / nome).read_text(encoding="utf-8"))


def _gabarito() -> saida.Analise:
    return saida.ler_analise(_ler("gabarito.json")["analise"])


def test_entrada_do_par_e_a_ficha_de_hoje():
    """Se a ficha mudar, a entrada guardada fica velha: refaça com o comando do ajudante."""
    hoje = json.loads(json.dumps(entrada_da_cpfl(), ensure_ascii=False))
    assert _ler("entrada.json") == hoje


def test_gabarito_tem_as_8_partes_em_ordem():
    assert tuple(p.chave for p in _gabarito().partes) == saida.PARTES


def test_ids_do_gabarito_existem_na_entrada():
    ids = {linha["id"] for linha in _ler("entrada.json")["linhas"]}
    citados = {
        nota
        for parte in _gabarito().partes
        for paragrafo in parte.paragrafos
        for frase in paragrafo.frases
        for nota in frase.notas
    }
    assert citados - ids == set()


def test_gabarito_passa_na_porta1():
    conferencia = porta1.conferir(_gabarito(), _ler("entrada.json"))
    assert conferencia.reprovacoes == ()


def test_gabarito_registra_o_que_mudou_do_texto_aprovado():
    """Toda mudança no texto que o Tiago aprovou fica escrita (a única: um assunto interno)."""
    par = _ler("gabarito.json")
    assert any("PRs 2 e 3" in mudanca for mudanca in par["mudancas"])
    textos = [
        frase.texto
        for parte in _gabarito().partes
        for paragrafo in parte.paragrafos
        for frase in paragrafo.frases
    ]
    assert not any("PRs 2 e 3" in texto for texto in textos)
