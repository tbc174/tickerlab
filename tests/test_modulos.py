"""O catálogo de módulos (src/modulos.py): só diz "disponível" o que existe no app."""

from src import modulos
from src.paginas import PAGINAS


def test_toda_funcionalidade_disponivel_aponta_para_uma_pagina_do_app():
    urls = {p.url for p in PAGINAS}
    for modulo in modulos.MODULOS:
        for f in modulo.funcionalidades:
            if f.disponivel:
                assert f.pagina_do_app in urls, (modulo.nome, f.nome)


def test_as_contagens_batem_com_as_funcionalidades():
    for modulo in modulos.MODULOS:
        assert modulo.disponiveis + modulo.em_breve == len(modulo.funcionalidades)
        assert modulo.funcionalidades, modulo.nome


def test_os_modulos_que_ainda_nao_existem_nao_dizem_que_existem():
    """Mercado e Ferramentas são ideias futuras (Mestre v3, seção 09): tudo "em breve"."""
    for chave in ("mercado", "ferramentas"):
        assert modulos.POR_CHAVE[chave].disponiveis == 0


def test_chaves_unicas_para_as_ancoras_da_pagina_produto():
    chaves = [m.chave for m in modulos.MODULOS]
    assert len(chaves) == len(set(chaves))
