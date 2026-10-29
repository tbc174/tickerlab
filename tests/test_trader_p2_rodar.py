"""Pesquisa 2, P5 parte 4b: a rodada completa com mercados sintéticos e um registro temporário."""

import numpy as np
import pandas as pd
import pytest

from trader import avaliacao
from trader.p2 import rodar
from trader.p2.mercados import por_codigo

DATAS = pd.bdate_range("1976-01-01", "2023-09-08")


def _tabela(semente, carry=0.0):
    r = np.random.default_rng(semente).normal(0.0001, 0.01, len(DATAS))
    preco = pd.Series(r, index=DATAS)
    return pd.DataFrame(
        {"preco": preco, "carry_anual": carry, "total": preco + carry / 365}
    )


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    mercados = {c: por_codigo(c) for c in ("EURUSD", "USA500", "GOLD")}
    tabelas = {
        "EURUSD": _tabela(1, 0.01),
        "USA500": _tabela(2, -0.01),
        "GOLD": _tabela(3, -0.02),
    }
    registro = rodar.abrir_registro(tmp_path_factory.mktemp("p2") / "registro.db")
    saida = rodar.executar(mercados, tabelas, registro)
    return mercados, tabelas, registro, saida


def test_registra_as_quatro_configuracoes(rodada):
    _, _, registro, saida = rodada
    assert set(saida["ids"]) == {"K1", "K2", "B0", "B1"}
    assert registro.contar() == 4
    assert registro.obter(saida["ids"]["K2"])["resultado"]["veredito"]["itens"]


def test_rodar_de_novo_nao_conta_tentativa_nova(rodada):
    mercados, tabelas, registro, _ = rodada
    rodar.executar(mercados, tabelas, registro)
    assert registro.contar() == 4


def test_veredito_tem_todos_os_itens_e_as_verificacoes_funcionam(rodada):
    saida = rodada[3]
    itens = {i.codigo: i for i in saida["veredito"].itens}
    assert list(itens) == [
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "A7",
        "A8",
        "A9",
        "A10",
        "V",
    ]
    assert itens["V"].passou  # olhar o futuro infla e a reexecução é idêntica


def test_dados_aleatorios_nao_passam(rodada):
    """Mercados sem tendência nem carry real: a pesquisa precisa reprovar."""
    assert not rodada[3]["veredito"].aprovado


def test_relatorio_e_escrito(rodada, tmp_path):
    caminho = rodar.escrever_relatorio(rodada[3], tmp_path)
    texto = caminho.read_text(encoding="utf-8")
    assert "Veredito do K2" in texto and "| A10 |" in texto


def test_resumos_vem_do_periodo_de_avaliacao(rodada):
    resumo = rodada[3]["resumos"]["K2"]
    assert resumo["inicio"] >= "1980-01-01" and resumo["fim"] <= "2023-09-08"
    assert np.isfinite(resumo["sharpe"]) or np.isnan(
        avaliacao.sharpe(pd.Series(dtype=float))
    )
