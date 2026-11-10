"""O que mudou no app, dia a dia (linha 804): `src/o_que_mudou.py`.

Cada PR que põe algo visível no ar acrescenta uma linha. Riscos que estes testes pegam:

1. link quebrado: a linha aponta para uma página que não existe ou que o app novo não abre;
2. ordem errada: a mais nova tem de ficar no topo, sem data repetida para a mesma página;
3. texto que promete (o mesmo filtro das novidades por e-mail) ou que fala de IA da casa.
"""

from datetime import date

import pytest

from src import o_que_mudou, paginas
from src.envio_novidades import EXPRESSOES_PROIBIDAS

PAGINAS = {p.chave: p for p in paginas.PAGINAS}


def test_cada_linha_aponta_para_uma_pagina_que_o_app_novo_abre():
    for entrega in o_que_mudou.ENTREGAS:
        pagina = PAGINAS.get(entrega.pagina)
        assert pagina is not None, entrega.pagina
        # o app novo só tem tela para página com contrato (web/src/app/rotas.tsx)
        assert pagina.contrato is not None, entrega.pagina
        assert not pagina.somente_admin, entrega.pagina


def test_a_mais_nova_fica_no_topo_e_nada_se_repete():
    datas = [e.data for e in o_que_mudou.ENTREGAS]
    assert datas == sorted(datas, reverse=True)
    chaves = [(e.data, e.pagina) for e in o_que_mudou.ENTREGAS]
    assert len(chaves) == len(set(chaves))


def test_texto_sem_promessa_e_uma_frase_curta():
    for entrega in o_que_mudou.ENTREGAS:
        minusculo = entrega.o_que.lower()
        assert not [e for e in EXPRESSOES_PROIBIDAS if e in minusculo], entrega.o_que
        assert "claude" not in minusculo and "conector" not in minusculo
        assert entrega.o_que.endswith("."), entrega.o_que
        assert len(entrega.o_que) <= o_que_mudou.TAMANHO_MAXIMO


def test_entrega_com_pagina_que_nao_existe_e_recusada():
    with pytest.raises(ValueError):
        o_que_mudou.como_lista(
            (o_que_mudou.Entrega(date(2026, 11, 11), "Algo novo.", "nao_existe"),)
        )


def test_como_lista_traz_o_titulo_e_o_endereco_da_pagina():
    entrega = o_que_mudou.Entrega(
        date(2026, 11, 11), "Ficha da empresa por CNPJ.", "ficha_da_empresa"
    )
    assert o_que_mudou.como_lista((entrega,)) == [
        {
            "data": "2026-11-11",
            "o_que": "Ficha da empresa por CNPJ.",
            "titulo": "Ficha da empresa",
            "url": "ficha-da-empresa",
        }
    ]


def test_a_propria_pagina_esta_no_registro():
    assert "o_que_mudou" in {e.pagina for e in o_que_mudou.ENTREGAS}
    assert "ficha_da_empresa" in {e.pagina for e in o_que_mudou.ENTREGAS}
