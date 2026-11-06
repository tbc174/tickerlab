"""A classe do processo pela árvore da TPU do CNJ (`base/tpu.py`). Os códigos são os da TPU de
03/11/2026; a árvore aqui é só um pedaço dela."""

import json

import pytest

from base import tpu


def _classe(codigo: int, pai: int | None, nome: str, situacao: str = "A") -> dict:
    return {"cod_item": codigo, "cod_item_pai": pai, "nome": nome, "situacao": situacao}


ARVORE = [
    _classe(2, None, "PROCESSO CÍVEL E DO TRABALHO"),
    _classe(1106, 2, "Processo de Conhecimento"),
    _classe(1107, 1106, "Procedimento de Conhecimento"),
    _classe(7, 1107, "Procedimento Comum Cível"),
    _classe(436, 1107, "Procedimento do Juizado Especial Cível"),
    _classe(26, 1107, "Procedimentos Especiais"),
    _classe(62, 26, "Procedimentos Regidos por Outros Códigos"),
    _classe(65, 62, "Ação Civil Pública"),
    _classe(129, 62, "Recuperação Judicial"),
    _classe(158, 2, "Processo de Execução"),
    _classe(1116, 158, "Execução Fiscal"),
    _classe(159, 158, "Execução de Título Extrajudicial"),
    _classe(197, 2, "Recursos"),
    _classe(198, 197, "Apelação Cível"),
    _classe(460, 197, "Recurso Inominado Cível"),
    _classe(268, None, "PROCESSO CRIMINAL"),
    _classe(283, 268, "Ação Penal - Procedimento Ordinário"),
    _classe(9999, 2, "Classe Antiga", situacao="I"),
]
CLASSES = tpu.ler_classes(json.dumps(ARVORE).encode())


def test_ler_classes():
    assert CLASSES[65] == tpu.Classe(65, "Ação Civil Pública", 62, True)
    assert not CLASSES[9999].ativa


def test_caminho_da_raiz_ate_a_classe():
    assert tpu.caminho(65, CLASSES) == [
        "PROCESSO CÍVEL E DO TRABALHO",
        "Processo de Conhecimento",
        "Procedimento de Conhecimento",
        "Procedimentos Especiais",
        "Procedimentos Regidos por Outros Códigos",
        "Ação Civil Pública",
    ]
    assert tpu.caminho(123456, CLASSES) == []


def test_caminho_com_ciclo_nao_trava():
    com_ciclo = tpu.ler_classes(
        json.dumps([_classe(1, 2, "A"), _classe(2, 1, "B")]).encode()
    )
    assert tpu.caminho(1, com_ciclo) == ["B", "A"]


@pytest.mark.parametrize(
    ("codigo", "ramo"),
    [
        (65, "coletivo"),  # ação civil pública (o exemplo do plano)
        (129, "insolvencia"),
        (1116, "execucao_fiscal"),
        (436, "juizado_especial"),
        (
            460,
            "juizado_especial",
        ),  # o recurso do juizado é do juizado, não um recurso comum
        (198, "recurso"),
        (159, "execucao"),
        (7, "conhecimento"),
        (283, "criminal"),
        (9999, None),  # classe sem ramo conhecido
        (123456, None),  # classe que a TPU não tem
    ],
)
def test_ramo_pela_classe_mais_proxima(codigo: int, ramo: str | None):
    assert tpu.ramo(codigo, CLASSES) == ramo


def test_resposta_que_nao_e_a_tpu_falha():
    with pytest.raises(ValueError, match="TPU"):
        tpu.ler_classes(b'{"status": 404}')
