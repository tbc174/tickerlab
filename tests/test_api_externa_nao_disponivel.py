"""O jeito único de dizer "não disponível para a sua organização" na API externa (linhas 878 e 880).

O ajudante `src/api_externa/nao_disponivel.py` é usado pelos eventos e pelos vínculos, pelos compradores, pelo
perfil e pelos comparáveis (linha 881): a parte pedida que o portão não libera vai numa lista com nome de fora, e os limites
só falam do que foi servido. Os testes de cada conjunto ficam com o conjunto; aqui, as regras do ajudante.
"""

import pytest

from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import (
    comparaveis,
    compradores,
    demonstracoes,
    eventos,
    ficha,
    fundos,
    setores,
    vinculos,
)
from src.api_externa.nomes import NOMES_DE_FORA

GERAIS = ("o do dia", "o do meio", "o do fim")
DAS_PARTES = {"a": "frase de a", "b": "frase de b", "c": "frase de a"}
AVISO = "o aviso"


def test_nao_disponiveis_sao_as_partes_sem_campo_na_ordem_do_pedido():
    servidas = {"c": (), "a": ("x",), "b": ()}
    assert nao_disponivel.nao_disponiveis(servidas) == ["c", "b"]
    assert nao_disponivel.nao_disponiveis({"a": ("x",)}) == []


def test_os_limites_falam_so_das_partes_servidas():
    limites = nao_disponivel.limites(GERAIS, DAS_PARTES, ["b"], [], AVISO)
    assert limites == ["o do dia", "frase de b", "o do meio", "o do fim"]


def test_com_parte_de_fora_o_aviso_entra_depois_das_frases_das_partes():
    limites = nao_disponivel.limites(GERAIS, DAS_PARTES, ["a"], ["b"], AVISO)
    assert limites == ["o do dia", "frase de a", "o aviso", "o do meio", "o do fim"]


def test_a_frase_que_vale_para_duas_partes_sai_uma_vez_so():
    limites = nao_disponivel.limites(GERAIS, DAS_PARTES, ["a", "c"], [], AVISO)
    assert limites.count("frase de a") == 1


def test_antes_diz_quantos_gerais_vem_antes_das_partes():
    limites = nao_disponivel.limites(GERAIS, DAS_PARTES, ["b"], ["a"], AVISO, antes=2)
    assert limites == ["o do dia", "o do meio", "frase de b", "o aviso", "o do fim"]


def test_a_parte_pode_ter_mais_de_uma_frase_e_a_comum_sai_uma_vez():
    das_partes = {"a": "comum", "b": ("comum", "so de b")}
    assert nao_disponivel.limites(GERAIS, das_partes, ["a", "b"], [], AVISO) == [
        "o do dia", "comum", "so de b", "o do meio", "o do fim",
    ]  # fmt: skip
    assert "so de b" not in nao_disponivel.limites(
        GERAIS, das_partes, ["a"], ["b"], AVISO
    )


def test_o_aviso_cita_o_nome_de_fora_da_lista():
    frase = nao_disponivel.aviso("tipos_nao_disponiveis", "tipos", "a lista de eventos")
    assert NOMES_DE_FORA["tipos_nao_disponiveis"] in frase
    assert "tipos_nao_disponiveis" not in frase


def test_lista_sem_nome_de_fora_nao_vira_aviso():
    with pytest.raises(KeyError):
        nao_disponivel.aviso("lista_que_nao_existe", "tipos", "a lista")


def test_o_aviso_dos_eventos_continua_o_mesmo_texto_do_contrato():
    # a CLI e quem integra já leem esta frase desde o #1088 (linha 878)
    assert eventos.LIMITE_DO_TIPO_NAO_DISPONIVEL == (
        "Os tipos em unavailable_event_types não estão disponíveis para esta organização e não foram "
        "consultados: a lista de eventos não diz nada sobre eles."
    )


@pytest.mark.parametrize(
    ("chave", "de_fora"),
    [
        (eventos.NAO_DISPONIVEIS, "unavailable_event_types"),
        (vinculos.NAO_DISPONIVEIS, "unavailable_link_types"),
        (compradores.NAO_DISPONIVEIS, "unavailable_signals"),
        (ficha.NAO_DISPONIVEIS, "unavailable_filings"),
        (ficha.CAMPOS_DO_CADASTRO_NAO_DISPONIVEIS, "unavailable_registration_fields"),
        (comparaveis.NAO_DISPONIVEIS, "unavailable_figures"),
        (demonstracoes.NAO_DISPONIVEIS, "unavailable_filings"),
        (fundos.NAO_DISPONIVEIS, "unavailable_sections"),
        (setores.SERIES_NAO_DISPONIVEIS, "unavailable_series"),
        (setores.BLOCOS_NAO_DISPONIVEIS, "unavailable_sections"),
    ],
)
def test_toda_lista_de_partes_de_fora_segue_o_molde_unavailable(chave, de_fora):
    assert chave.endswith("_nao_disponiveis")
    assert NOMES_DE_FORA[chave] == de_fora
