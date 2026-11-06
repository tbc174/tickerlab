"""Calendário do café por região (plano do café, PR 9).

Seis fases de Camargo & Camargo (2001) em dois anos da planta: em cada mês há a safra em curso
(florada, enchimento, maturação, repouso) e a safra seguinte (vegetação, indução das gemas).
"""

import dataclasses
import json

import pytest

from src.commodities.cafe import calendario, indices_de_clima
from src.commodities.cafe.calendario import Fase, fase, o_que_o_mercado_olha
from src.commodities.cafe.regioes import POR_ID, Regiao
from src.conteudo import carregar_textos_do_cafe

PALAVRAS_VEDADAS = (
    "quebrada", "golpe", "calote", "recomendamos", "vai subir", "vai cair", "o preço vai",
    "garante", "certeza",
)  # fmt: skip


@pytest.mark.parametrize(
    ("regiao", "mes", "em_curso", "seguinte", "colheita", "geada"),
    [
        ("sul-de-minas", 9, "florada", "vegetacao", True, False),
        ("sul-de-minas", 11, "florada", "vegetacao", False, False),
        ("sul-de-minas", 12, "enchimento", "vegetacao", False, False),
        ("sul-de-minas", 3, "enchimento", "vegetacao", False, False),
        ("sul-de-minas", 4, "maturacao", "inducao", False, False),
        ("sul-de-minas", 5, "maturacao", "inducao", True, False),
        ("sul-de-minas", 6, "repouso", "inducao", True, True),
        ("sul-de-minas", 8, "repouso", "inducao", True, True),
        ("sul-de-minas", 10, "florada", "vegetacao", False, False),
        # o Espírito Santo começa a colher em abril
        ("es-norte", 4, "maturacao", "inducao", True, False),
        ("es-montanhas", 4, "maturacao", "inducao", True, False),
        ("es-norte", 3, "enchimento", "vegetacao", False, False),
        ("cerrado-mineiro", 4, "maturacao", "inducao", False, False),
    ],
)
def test_fase_do_mes_por_regiao(regiao, mes, em_curso, seguinte, colheita, geada):
    resultado = fase(mes, POR_ID[regiao])
    assert resultado == Fase(mes, regiao, em_curso, seguinte, colheita, geada)


def test_todo_mes_de_toda_regiao_tem_fase_nas_duas_safras():
    for regiao in POR_ID.values():
        for mes in range(1, 13):
            resultado = fase(mes, regiao)
            assert resultado.safra_em_curso and resultado.safra_seguinte


def test_fase_vira_json_com_tipos_simples():
    texto = json.dumps(dataclasses.asdict(fase(7, POR_ID["mogiana"])))
    assert json.loads(texto)["na_janela_de_geada"] is True


@pytest.mark.parametrize("mes", [0, 13, -1])
def test_mes_fora_de_1_a_12_da_erro_claro(mes):
    with pytest.raises(ValueError, match="mês"):
        fase(mes, POR_ID["sul-de-minas"])


def test_fase_sem_regiao_conhecida_da_erro_claro():
    desconhecida = Regiao("atlantida", "Atlântida", ("MG",), "arabica", ())
    with pytest.raises(ValueError, match="região"):
        fase(5, desconhecida)
    with pytest.raises(ValueError, match="região"):
        o_que_o_mercado_olha(5, desconhecida)


def test_o_que_o_mercado_olha_nesta_epoca():
    florada = o_que_o_mercado_olha(10, POR_ID["sul-de-minas"])
    temas = [item.tema for item in florada.itens]
    assert temas == ["florada", "vegetacao"]
    com_indices = {item.tema: item.indices for item in florada.itens}
    assert com_indices["florada"] == ("indice_de_florada",)

    # julho: repouso + colheita + janela de geada + indução das gemas
    inverno = o_que_o_mercado_olha(7, POR_ID["sul-de-minas"])
    assert [item.tema for item in inverno.itens] == [
        "repouso", "colheita", "geada", "inducao",
    ]  # fmt: skip
    assert next(i for i in inverno.itens if i.tema == "geada").indices == (
        "dias_de_geada",
    )

    granacao = o_que_o_mercado_olha(1, POR_ID["sul-de-minas"])
    assert next(i for i in granacao.itens if i.tema == "enchimento").indices == (
        "deficit_dez_mar",
    )


def test_os_indices_citados_existem_no_modulo_de_clima():
    for tema in calendario.INDICES_POR_TEMA.values():
        for nome in tema:
            assert callable(getattr(indices_de_clima, nome))


def test_o_que_o_mercado_olha_usa_a_fase_do_mes_e_da_regiao():
    abril_es = o_que_o_mercado_olha(4, POR_ID["es-norte"])
    assert "colheita" in [item.tema for item in abril_es.itens]
    abril_mg = o_que_o_mercado_olha(4, POR_ID["sul-de-minas"])
    assert "colheita" not in [item.tema for item in abril_mg.itens]


def test_textos_do_calendario_tem_fonte_e_nao_prometem_preco():
    textos = carregar_textos_do_cafe()
    for tema in calendario.TEMAS:
        titulo = calendario.TITULO_DO_TEXTO[tema]
        assert titulo in textos, titulo
        assert len(textos[titulo]) > 150, titulo
        minusculo = textos[titulo].lower()
        for palavra in PALAVRAS_VEDADAS:
            assert palavra not in minusculo, (titulo, palavra)
    todo = " ".join(textos.values())
    assert "Camargo" in todo and "2001" in todo
    assert "Embrapa" in todo and "CONAB" in todo


def test_o_texto_de_cada_item_vem_do_arquivo_de_conteudo():
    textos = carregar_textos_do_cafe()
    item = o_que_o_mercado_olha(7, POR_ID["mogiana"]).itens[2]
    assert item.tema == "geada"
    assert item.texto == textos[calendario.TITULO_DO_TEXTO["geada"]]
