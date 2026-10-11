"""O mapa de páginas precisa ser coerente: sem repetição, todos os grupos usados, recursos conhecidos."""

import pytest

from src import paginas
from src.planos import LIMITES_DOS_PLANOS


def test_chaves_e_enderecos_sao_unicos():
    chaves = [p.chave for p in paginas.PAGINAS]
    assert len(chaves) == len(set(chaves))
    enderecos = [p.url for p in paginas.PAGINAS]
    assert len(enderecos) == len(set(enderecos))


def test_todo_grupo_tem_paginas_e_toda_pagina_tem_grupo_conhecido():
    for grupo in paginas.GRUPOS:
        assert paginas.paginas_do_grupo(grupo), grupo
        assert grupo in paginas.FRASE_DE_CADA_GRUPO
    assert {p.grupo for p in paginas.PAGINAS} <= set(paginas.GRUPOS)


def test_pagina_inicial_existe_e_e_a_primeira():
    assert paginas.PAGINAS[0].chave == paginas.PAGINA_INICIAL
    assert not paginas.pagina(paginas.PAGINA_INICIAL).precisa_do_ativo


@pytest.mark.parametrize("pagina", paginas.PAGINAS, ids=lambda p: p.chave)
def test_textos_completos(pagina):
    assert pagina.titulo and pagina.descricao.endswith((".", "?"))
    assert pagina.icone.startswith(":material/") and pagina.icone.endswith(":")
    assert pagina.url == pagina.url.lower() and " " not in pagina.url


def test_recursos_exigidos_existem_em_algum_plano():
    conhecidos = set().union(*(p.recursos for p in LIMITES_DOS_PLANOS.values()))
    for p in paginas.PAGINAS:
        if p.recurso:
            assert p.recurso in conhecidos


def test_o_grupo_avancado_tem_so_paginas_pro_e_so_ele():
    for p in paginas.PAGINAS:
        assert p.e_pro == (p.grupo == paginas.GRUPO_AVANCADO)


def test_paginas_de_conta_e_ajuda_nao_pedem_ativo():
    for chave in ("inicio", "guia", "simulacoes", "planos"):
        assert not paginas.pagina(chave).precisa_do_ativo
