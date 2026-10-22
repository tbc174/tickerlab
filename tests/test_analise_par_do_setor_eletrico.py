"""O par dados → texto do setor elétrico: o relatório do setor de 21/10/2026 e a análise à mão.

Como o da CPFL, o gabarito é a régua da prova do setor: um texto escrito à mão, com uma nota em
cada frase e as contas declaradas, não pode ser reprovado pela porta 1. O roteiro é o do setor
(`PARTES_DO_SETOR`); por isso a conferência é parte a parte, sem a estrutura da análise de empresa.
"""

import dataclasses

from src.analise_escrita import porta1, saida
from tests.ajudantes_da_analise_do_setor import (
    PARTES_DO_SETOR,
    entrada_do_setor,
    ler_do_par,
    partes_do_gabarito,
)


def _frases(partes: tuple[saida.Parte, ...]) -> list[saida.Frase]:
    return [
        f
        for parte in partes
        for paragrafo in parte.paragrafos
        for f in paragrafo.frases
    ]


def _reprovacoes(partes: tuple[saida.Parte, ...]) -> list[porta1.Reprovacao]:
    ficha = porta1.ler_ficha(ler_do_par("entrada.json"))
    return [r for parte in partes for r in porta1._conferir_parte(parte, ficha)]


def test_entrada_do_par_e_a_do_relatorio_guardado():
    """Se o formato da entrada mudar, refaça-a com o comando do ajudante."""
    assert ler_do_par("entrada.json") == entrada_do_setor(ler_do_par("relatorio.json"))


def test_gabarito_tem_as_partes_do_setor_em_ordem():
    assert tuple(p.chave for p in partes_do_gabarito()) == PARTES_DO_SETOR
    assert tuple(ler_do_par("gabarito.json")["roteiro"]) == PARTES_DO_SETOR


def test_ids_do_gabarito_existem_na_entrada():
    """As notas e os operandos das contas apontam para linhas da entrada."""
    ids = {linha["id"] for linha in ler_do_par("entrada.json")["linhas"]}
    citados = {nota for frase in _frases(partes_do_gabarito()) for nota in frase.notas}
    citados |= {
        operando.id
        for frase in _frases(partes_do_gabarito())
        for conta in frase.contas
        for operando in conta.de
        if operando.id
    }
    assert citados - ids == set()


def test_gabarito_passa_na_porta1():
    assert _reprovacoes(partes_do_gabarito()) == []


def test_porta1_reprova_o_gabarito_com_um_numero_trocado():
    """A conferência acima lê a entrada do setor de verdade: um número errado não passa."""
    certo = "87.543.053 em 2025"
    partes = partes_do_gabarito()
    primeira = partes[0]
    paragrafo = primeira.paragrafos[0]
    frases = tuple(
        dataclasses.replace(f, texto=f.texto.replace(certo, "87.000.000 em 2025"))
        for f in paragrafo.frases
    )
    assert any(certo in f.texto for f in paragrafo.frases)
    trocada = dataclasses.replace(
        primeira,
        paragrafos=(
            dataclasses.replace(paragrafo, frases=frases),
            *primeira.paragrafos[1:],
        ),
    )
    assert [r.regra for r in _reprovacoes((trocada,))] == ["numero"]


def test_gabarito_nao_usa_a_linha_incompleta_de_2026_como_fato_do_setor():
    """O HHI de 689 e a CR4 de 43,7% saem de 8 meses de 2026: só aparecem como aviso."""
    frases = [f.texto for f in _frases(partes_do_gabarito())]
    com_689 = [t for t in frases if "689" in t]
    assert com_689 and all("incompleta" in t for t in com_689)
