"""Testes de src/exportacao.py."""

import io

import pandas as pd
import pytest

from src.backtest import COLUNAS_DAS_OPERACOES
from src.exportacao import (
    converter_para_csv,
    montar_tabela_de_curvas,
    montar_tabela_de_operacoes,
    montar_tabela_de_precos,
)


def _dados():
    return pd.DataFrame(
        {"Close": [10.0, 11.0, 12.1], "Volume": [100, 200, 300]},
        index=pd.date_range("2026-01-05", periods=3),
    )


def test_csv_brasileiro_usa_ponto_e_virgula_e_virgula_decimal():
    texto = converter_para_csv(montar_tabela_de_precos(_dados())).decode("utf-8-sig")
    linhas = texto.splitlines()
    assert linhas[0] == "Data;Close;Volume;Retorno diário"
    assert linhas[2].startswith("2026-01-06;11,0;200;0,1")


def test_csv_internacional_e_a_marca_utf8_fica_no_inicio():
    bruto = converter_para_csv(_dados(), formato_brasileiro=False)
    assert bruto.startswith(b"\xef\xbb\xbf")
    lido = pd.read_csv(io.BytesIO(bruto), encoding="utf-8-sig", index_col=0)
    assert list(lido["Close"]) == [10.0, 11.0, 12.1]


def test_csv_de_tabela_vazia_da_erro():
    with pytest.raises(ValueError, match="exportar"):
        converter_para_csv(pd.DataFrame())


def test_tabela_de_precos_tem_retorno_diario_e_nao_muda_o_original():
    dados = _dados()
    tabela = montar_tabela_de_precos(dados)
    assert tabela["Retorno diário"].iloc[1] == pytest.approx(0.1)
    assert "Retorno diário" not in dados.columns


def test_curvas_multiplicam_pelo_capital_inicial():
    indice = pd.date_range("2026-01-05", periods=2)
    tabela = montar_tabela_de_curvas({"A": pd.Series([1.0, 1.5], index=indice)}, 10_000)
    assert list(tabela["A"]) == [10_000, 15_000]
    with pytest.raises(ValueError, match="curvas"):
        montar_tabela_de_curvas({}, 100)


def test_operacoes_ganham_nomes_em_portugues_e_numeracao():
    operacoes = pd.DataFrame(
        [[pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-09"), 5, 0.03, False]],
        columns=COLUNAS_DAS_OPERACOES,
    )
    tabela = montar_tabela_de_operacoes(operacoes)
    assert list(tabela.columns) == [
        "Primeiro dia",
        "Último dia",
        "Dias",
        "Retorno",
        "Em aberto",
    ]
    assert tabela.index[0] == 1 and tabela.index.name == "Operação"
    texto = converter_para_csv(tabela).decode("utf-8-sig")
    assert "1;2026-01-05;2026-01-09;5;0,03;False" in texto
