"""A lista única de palavras vedadas (ADR 0103, item 7): um só lugar, a união da do café com a da 0085."""

from base import contestacoes, palavras_vedadas
from base.contrapartes import cafe
from src.credito import dossie

DO_CAFE = {
    "quebrou", "quebrada", "calote", "golpe", "fraude", "não confiável", "evite", "recomendamos",
    "seguro", "confiável",
}  # fmt: skip
DA_ADR_0085 = {
    "fraude", "fraudador", "corrupção", "cartel", "conluio", "laranja", "superfaturamento",
    "direcionamento", "suspeito",
}  # fmt: skip


def test_a_lista_e_a_uniao_da_do_cafe_com_a_da_0085_sem_repetir():
    assert set(palavras_vedadas.VEDADAS) == DO_CAFE | DA_ADR_0085
    assert len(palavras_vedadas.VEDADAS) == len(set(palavras_vedadas.VEDADAS))


def test_cada_palavra_da_lista_e_pega_sem_acento_nem_caixa():
    for palavra in palavras_vedadas.VEDADAS:
        achadas = palavras_vedadas.palavras_vedadas_em(f"texto {palavra.upper()} aqui")
        assert palavra in achadas, palavra


def test_so_palavra_inteira_conta():
    assert (
        palavras_vedadas.palavras_vedadas_em("assegurar, inseguro, cartelização") == []
    )


def test_o_cafe_o_dossie_e_as_contestacoes_usam_a_mesma_funcao():
    assert cafe.palavras_vedadas_em is palavras_vedadas.palavras_vedadas_em
    assert dossie.palavras_vedadas_em is palavras_vedadas.palavras_vedadas_em
    assert contestacoes.palavras_vedadas_em is palavras_vedadas.palavras_vedadas_em


def test_palavra_so_da_0085_agora_barra_a_ficha_do_cafe():
    assert cafe.palavras_vedadas_em("empresa suspeita de cartel") == ["cartel"]
