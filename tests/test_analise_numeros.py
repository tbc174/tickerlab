"""Números e datas escritos em português, lidos igual na entrada e na resposta do modelo."""

from datetime import date

import pytest

from src.analise_escrita import numeros as nu


def _valores(texto: str) -> list[float]:
    return [n.valor for n in nu.numeros(texto)]


@pytest.mark.parametrize(
    ("texto", "valor", "tolerancia"),
    [
        ("R$ 45,6 bilhões", 45.6e9, 0.05e9),
        ("R$ 45,6 bi", 45.6e9, 0.05e9),
        ("R$ 312 milhões", 312e6, 0.5e6),
        ("26,4%", 0.264, 0.0005),
        ("1,21×", 1.21, 0.005),
        ("2,2 vezes", 2.2, 0.05),
        ("1.152.254.440 ações", 1152254440, 0.5),
        ("94 ofertas", 94, 0.5),
        ("R$ 68", 68, 0.5),
    ],
)
def test_numero_e_tolerancia_pela_precisao_escrita(texto, valor, tolerancia):
    (numero,) = nu.numeros(texto)
    assert numero.valor == pytest.approx(valor)
    assert numero.tolerancia == pytest.approx(tolerancia)


def test_arredondamento_aceita_meia_unidade_e_nada_mais():
    (numero,) = nu.numeros("26,4%")
    assert numero.bate_com(0.26433)
    assert numero.bate_com(0.2635)
    assert not numero.bate_com(0.2656)


def test_sinal_conta():
    (negativo,) = nu.numeros("lucro de -1,2 bi")
    assert negativo.valor == pytest.approx(-1.2e9)
    (positivo,) = nu.numeros("saída de 1,2 bi")
    assert not positivo.bate_com(-1.2e9)
    assert positivo.bate_com(-1.2e9, sem_sinal=True)
    assert not negativo.bate_com(1.2e9, sem_sinal=True)


def test_ordinal_ano_e_periodo_nao_sao_numeros():
    assert _valores("1º trimestre de 2026, nos 12 meses até junho") == []
    assert _valores("CPFE3 e 2T2026") == []


def test_datas_em_todos_os_formatos():
    datas = nu.datas(
        "31/08/2026, 06/2026, mar/2025, dezembro de 2025, 2024-12-31 e 2023"
    )
    assert [(d.ano, d.mes, d.dia) for d in datas] == [
        (2026, 8, 31),
        (2024, 12, 31),
        (2025, 3, None),
        (2025, 12, None),
        (2026, 6, None),
        (2023, None, None),
    ]
    assert _valores("31/08/2026 e 06/2026") == []


def test_data_bate_na_precisao_das_duas():
    (dezembro,) = nu.datas("dezembro de 2025")
    (dia,) = nu.datas("31/12/2025")
    (ano,) = nu.datas("DFP de 2025")
    (outro,) = nu.datas("30/06/2025")
    assert dezembro.bate_com(dia) and dia.bate_com(ano) and ano.bate_com(outro)
    assert not dezembro.bate_com(outro)


def test_data_depois_do_corte():
    corte = date(2026, 10, 17)
    assert nu.datas("18/10/2026")[0].depois_de(corte)
    assert not nu.datas("outubro de 2026")[0].depois_de(corte)
    assert nu.datas("2027")[0].depois_de(corte)
