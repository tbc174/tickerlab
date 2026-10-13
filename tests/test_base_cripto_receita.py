"""Dados abertos de criptoativos da Receita Federal (base de cripto, série 1, PR 4).

As abas são montadas com a mesma estrutura da planilha real (`criptoativos_dados_abertos_20260826.xls`,
conferida em 13/10/2026): títulos e notas no alto, o mês escrito por extenso ("Agosto de 2019").
"""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.cripto import receita
from base.cripto.receita import (
    abrir_planilha,
    data_do_arquivo,
    divulgado_em,
    ler_por_criptoativo,
    ler_totais,
)

NAN = float("nan")


def _relatorio_1() -> pd.DataFrame:
    linhas = [
        ["Relatório nº 1", *[NAN] * 8],
        [NAN] * 9,
        ["Por período mensal e por tipo de declaração. [...]", *[NAN] * 8],
        [NAN] * 9,
        [NAN, "Valores em R$ milhões", *[NAN] * 7],
        ["MÊS/ANO", "Declarações", *[NAN] * 6, "Total Geral"],
        [NAN, "Com uso de exchanges no exterior", NAN, NAN, "Sem o uso de exchanges"]
        + [NAN, NAN, "Exchanges no Brasil*", NAN],
        [NAN, "PF", "PJ", "Subtotal", "PF", "PJ", "Subtotal", NAN, NAN],
        ["Agosto de 2019", 376.245602, 745.333187, 1121.578789, 114.879436, 269.535927]
        + [384.415363, 2531.017852, 4037.012005],
        ["Junho de 2026", 136.977446, 7194.843418, 7331.820864, 7.016751, 14279.729474]
        + [14286.746225, 35923.422283, 57541.989373],
    ]
    return pd.DataFrame(linhas)


def _relatorio_4() -> pd.DataFrame:
    linhas = [
        ["Relatório nº 4:", NAN, NAN, NAN, NAN],
        [NAN] * 5,
        [
            "CRIPTOATIVO",
            "MÊS/ANO",
            "Nº DE OPERAÇÕES",
            "VALOR TOTAL DAS OPERAÇÕES",
            "VALOR MÉDIO",
        ],
        ["AAVE", "Agosto de 2020", 1, 59638.94, 59638.94],
        ["BTC", "Agosto de 2019", 1042292, 3798621044.970042, 3644.488344],
        ["BTC", "Junho de 2026", 2014068, 2386411374.050024, 1184.871302],
    ]
    return pd.DataFrame(linhas)


PUBLICADO = date(2026, 8, 26)


def test_totais_por_mes_em_milhoes_de_reais():
    tabela = ler_totais(_relatorio_1(), PUBLICADO)

    assert tabela["mes"].tolist() == [date(2019, 8, 1), date(2026, 6, 1)]
    primeiro = tabela.iloc[0]
    assert primeiro["exchanges_no_brasil_milhoes"] == pytest.approx(2531.017852)
    assert primeiro["exterior_milhoes"] == pytest.approx(1121.578789)
    assert primeiro["sem_exchange_milhoes"] == pytest.approx(384.415363)
    assert primeiro["total_milhoes"] == pytest.approx(4037.012005)


def test_por_criptoativo_so_o_pedido():
    tabela = ler_por_criptoativo(_relatorio_4(), PUBLICADO, "BTC")

    assert tabela["mes"].tolist() == [date(2019, 8, 1), date(2026, 6, 1)]
    assert tabela.iloc[1]["operacoes"] == 2_014_068
    assert tabela.iloc[1]["valor_total_reais"] == pytest.approx(2386411374.05)


def test_mes_escrito_por_extenso_com_e_sem_acento():
    assert receita.ler_mes("Março de 2026") == date(2026, 3, 1)
    assert receita.ler_mes("Marco de 2026") == date(2026, 3, 1)
    assert receita.ler_mes("Relatório nº 1") is None


def test_data_do_arquivo_vem_do_nome():
    assert data_do_arquivo("criptoativos_dados_abertos_20260826.xls") == date(
        2026, 8, 26
    )


def test_vale_no_dia_seguinte_ao_do_nome_a_meia_noite_de_brasilia():
    # o nome traz 26/08 e a página diz publicado em 27/08: vale o dia seguinte, às 0h de Brasília
    assert divulgado_em(PUBLICADO) == datetime(2026, 8, 27, 3, tzinfo=UTC)
    assert (
        ler_totais(_relatorio_1(), PUBLICADO)["divulgado_em"] == divulgado_em(PUBLICADO)
    ).all()


def test_abrir_planilha_le_todas_as_abas_sem_cabecalho(monkeypatch):
    pedidos = {}

    def ler_excel(arquivo, **opcoes):
        pedidos.update(opcoes)
        return {"Relatorio1": pd.DataFrame()}

    monkeypatch.setattr(receita.pd, "read_excel", ler_excel)

    assert list(abrir_planilha(b"conteudo")) == ["Relatorio1"]
    assert pedidos == {"sheet_name": None, "header": None, "engine": "xlrd"}
