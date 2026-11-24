"""O contrato de todo número do relatório (`src/numero.py`): data, fonte e comparação (ou o motivo de não haver)."""

import pytest

from src.numero import COMPARACAO, DATA, FONTE, Comparacao, Numero

COMP = Comparacao(contra="setor Energia", texto="mediana 12,4%")


def test_numero_completo_nao_tem_o_que_falte() -> None:
    numero = Numero(0.26, "12 meses até 30/06/2026", "DFP e ITR", COMP)
    assert numero.o_que_falta() == []


def test_sem_comparacao_com_motivo_esta_completo() -> None:
    numero = Numero(
        3,
        "FRE de 2026",
        "FRE",
        None,
        sem_comparacao="só existe no documento mais recente",
    )
    assert numero.o_que_falta() == []


@pytest.mark.parametrize(
    ("numero", "esperado"),
    [
        (Numero(1.0, "", "fonte", COMP), [DATA]),
        (Numero(1.0, "dez/2025", "", COMP), [FONTE]),
        (Numero(1.0, "dez/2025", "fonte", None), [COMPARACAO]),
        (Numero(None, "", "", None), [DATA, FONTE, COMPARACAO]),
    ],
)
def test_aponta_cada_parte_que_falta(numero: Numero, esperado: list[str]) -> None:
    assert numero.o_que_falta() == esperado


def test_comparacao_sem_valor_aceita_so_texto() -> None:
    assert COMP.valor is None
