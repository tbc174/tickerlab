"""Derivados do balanço mundial do café (PR 4): estoque/consumo, participação do Brasil e surpresa."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.commodities import usda_psd
from src.commodities.cafe import balanco
from src.commodities.cafe.balanco import PontoAnual

EXEMPLO = Path("dados_de_exemplo/commodities/psd_coffee_pequeno.csv")


def _linhas(*linhas: tuple) -> pd.DataFrame:
    """(país, safra, atributo, tipo, valor, divulgado_em) → tabela no formato do USDA."""
    return pd.DataFrame(
        [
            {
                "codigo_do_pais": pais,
                "pais": pais,
                "ano_safra": safra,
                "atributo": atributo,
                "tipo": tipo,
                "valor": valor,
                "unidade": "mil sacas de 60 kg",
                "divulgado_em": pd.Timestamp(quando),
            }
            for pais, safra, atributo, tipo, valor, quando in linhas
        ]
    )


@pytest.fixture
def balanco_de_dois_paises() -> pd.DataFrame:
    d = "2025-06-30"
    return _linhas(
        ("BR", 2024, "estoque_final", "total", 2000.0, d),
        ("BR", 2024, "consumo_domestico", "total", 10000.0, d),
        ("CO", 2024, "estoque_final", "total", 500.0, d),
        ("CO", 2024, "consumo_domestico", "total", 2000.0, d),
        ("BR", 2023, "estoque_final", "total", 1000.0, d),
        ("BR", 2023, "consumo_domestico", "total", 10000.0, d),
        ("BR", 2024, "producao", "total", 60000.0, d),
        ("BR", 2024, "producao", "arabica", 40000.0, d),
        ("BR", 2024, "producao", "conilon", 20000.0, d),
        ("CO", 2024, "producao", "total", 12000.0, d),
        ("CO", 2024, "producao", "arabica", 12000.0, d),
    )


def test_relacao_estoque_consumo_por_pais(balanco_de_dois_paises):
    pontos = balanco.relacao_estoque_consumo(balanco_de_dois_paises, "BR")
    assert pontos == [
        PontoAnual(2023, pytest.approx(0.10), "BR"),
        PontoAnual(2024, pytest.approx(0.20), "BR"),
    ]


def test_relacao_estoque_consumo_do_mundo_soma_os_paises(balanco_de_dois_paises):
    pontos = balanco.relacao_estoque_consumo(balanco_de_dois_paises)
    [ponto] = [p for p in pontos if p.ano_safra == 2024]
    assert ponto.rotulo == "mundo"
    assert ponto.valor == pytest.approx(2500 / 12000)


def test_relacao_estoque_consumo_sem_consumo_nao_inventa_numero():
    tabela = _linhas(("BR", 2024, "estoque_final", "total", 100.0, "2025-06-30"))
    assert balanco.relacao_estoque_consumo(tabela, "BR") == []


def test_participacao_do_brasil_total_e_por_tipo(balanco_de_dois_paises):
    total = balanco.participacao_do_brasil(balanco_de_dois_paises, "total")
    assert total == [PontoAnual(2024, pytest.approx(60000 / 72000), "total")]
    arabica = balanco.participacao_do_brasil(balanco_de_dois_paises, "arabica")
    assert arabica[0].valor == pytest.approx(40000 / 52000)
    assert arabica[0].rotulo == "arabica"


def test_participacao_do_brasil_recusa_tipo_invalido(balanco_de_dois_paises):
    with pytest.raises(ValueError, match="tipo"):
        balanco.participacao_do_brasil(balanco_de_dois_paises, "robusta")


def test_surpresa_do_usda_junho_contra_dezembro():
    tabela = _linhas(
        ("BR", 2024, "producao", "total", 63000.0, "2024-06-30"),
        ("BR", 2024, "producao", "total", 66000.0, "2024-12-31"),
        ("BR", 2025, "producao", "total", 70000.0, "2025-06-30"),
    )
    junho = usda_psd.como_estava_em(tabela, date(2024, 6, 30))
    dezembro = usda_psd.como_estava_em(tabela, date(2024, 12, 31))
    [s] = balanco.surpresa_do_usda(junho, dezembro, "BR", "producao")
    assert (s.ano_safra, s.antes, s.depois) == (2024, 63000.0, 66000.0)
    assert s.diferenca == 3000.0
    assert s.percentual == pytest.approx(3000 / 63000)


def test_surpresa_ignora_safra_que_so_existe_numa_das_fotografias():
    antes = _linhas(("BR", 2024, "producao", "total", 100.0, "2024-06-30"))
    depois = _linhas(("BR", 2025, "producao", "total", 110.0, "2024-12-31"))
    assert balanco.surpresa_do_usda(antes, depois, "BR", "producao") == []


def test_corte_em_d_nao_muda_o_passado_dos_derivados():
    """Sem olhar o futuro: o que veio depois do corte não pode mexer no que o corte já mostrava."""
    tabela = usda_psd.ler(EXEMPLO.read_bytes(), date(2026, 10, 18))
    corte = pd.Timestamp("2025-06-30")
    so_ate_o_corte = tabela[tabela["divulgado_em"] <= corte]
    antes = balanco.relacao_estoque_consumo(
        usda_psd.como_estava_em(so_ate_o_corte, corte.date()), "BR"
    )
    depois = balanco.relacao_estoque_consumo(
        usda_psd.como_estava_em(tabela, corte.date()), "BR"
    )
    assert antes == depois


@pytest.fixture
def robusta_em_quatro_paises() -> pd.DataFrame:
    d = "2025-06-30"
    return _linhas(
        ("BR", 2024, "producao", "conilon", 20000.0, d),
        ("VM", 2024, "producao", "conilon", 30000.0, d),
        ("ID", 2024, "producao", "conilon", 10000.0, d),
        ("UG", 2024, "producao", "conilon", 5000.0, d),
        ("CO", 2024, "producao", "conilon", 0.0, d),  # arábica pura: fica fora da conta
        ("VM", 2024, "estoque_final", "total", 600.0, d),
        ("VM", 2024, "consumo_domestico", "total", 3000.0, d),
        ("ID", 2024, "estoque_final", "total", 100.0, d),
        ("ID", 2024, "consumo_domestico", "total", 5000.0, d),
        ("UG", 2024, "estoque_final", "total", 50.0, d),
    )


def test_balanco_por_pais_lado_a_lado_com_o_brasil(robusta_em_quatro_paises):
    pontos = balanco.balanco_por_pais(robusta_em_quatro_paises)
    por_pais = {p.codigo_do_pais: p for p in pontos}
    assert set(por_pais) == {"BR", "VM", "ID", "UG"}
    assert por_pais["VM"].participacao_na_producao == pytest.approx(30000 / 65000)
    assert por_pais["BR"].participacao_na_producao == pytest.approx(20000 / 65000)
    assert por_pais["VM"].relacao_estoque_consumo == pytest.approx(0.2)
    assert por_pais["ID"].relacao_estoque_consumo == pytest.approx(0.02)
    assert all(p.tipo == "conilon" for p in pontos)


def test_balanco_por_pais_sem_consumo_deixa_a_relacao_vazia(robusta_em_quatro_paises):
    uganda = next(
        p
        for p in balanco.balanco_por_pais(robusta_em_quatro_paises)
        if p.codigo_do_pais == "UG"
    )
    assert uganda.relacao_estoque_consumo is None


def test_balanco_por_pais_ordena_por_safra_e_ignora_pais_fora_da_lista(
    robusta_em_quatro_paises,
):
    pontos = balanco.balanco_por_pais(robusta_em_quatro_paises, ("VM",))
    assert [(p.codigo_do_pais, p.ano_safra) for p in pontos] == [("VM", 2024)]
    # a participação continua sendo sobre o mundo da tabela, não sobre a lista pedida
    assert pontos[0].participacao_na_producao == pytest.approx(30000 / 65000)


def test_balanco_por_pais_recusa_tipo_invalido(robusta_em_quatro_paises):
    with pytest.raises(ValueError, match="tipo"):
        balanco.balanco_por_pais(robusta_em_quatro_paises, tipo="robusta")


def test_balanco_por_pais_do_duble_do_usda_traz_o_vietna_e_o_brasil():
    tabela = usda_psd.ler(EXEMPLO.read_bytes(), date(2026, 10, 18))
    pontos = balanco.balanco_por_pais(tabela)
    assert {p.codigo_do_pais for p in pontos} >= {"BR", "VM"}
    assert all(0 < p.participacao_na_producao <= 1 for p in pontos)
