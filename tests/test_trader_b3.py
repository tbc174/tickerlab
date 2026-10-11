"""Leitor do boletim diário de futuros da B3 (com o CSV de exemplo, sem internet)."""

from datetime import date

import pandas as pd
import pytest

from trader import b3

CABECALHO = (
    "Ticker symbol;ISIN code;Segment;Opening price;Minimum price;Maximum price;"
    "Trade average price;Last price;Oscillation;Adjusted quote;Adjusted quote tax;"
    "Previous adjusted quote tax;Reference price;Variation;"
    "Settlement value per contract (R$);Last buy order;Last sell order;Trade quantity;"
    "Financial instrument quantity;National financial volume"
)
TEXTO = (
    "﻿It summarizes the transactions executed in derivatives during a trading session.\n"
    "\n"
    f"{CABECALHO}\n"
    "BGIV26C032400;BRBMEFCB1KB0;AGRIBUSINESS;-;-;-;-;-;-;-;-;-;64.34;-;-;-;-;-;-;-\n"
    "BGIV26;BRBMEFBGI7U5;AGRIBUSINESS;387.95;386.75;389.35;388.1;388.7;0.05;388.8;-;388.5;-;"
    "0.3;99;388.7;389.2;892;1,356;173670387\n"
    "WDOX26;BRBMEFWDO5I4;FINANCIAL;5021;4996;5029;5010.479;5013;-0.53;5004.412;-;5040.028;-;"
    "-35.616;-356.16;5011.5;5012.5;442,271;2,185,958;109526966975\n"
    "DI1F27;BRBMEFDI1F27;INTEREST RATE;-;-;-;-;-;-;-;14.2;14.3;-;-;-;-;-;-;-;-\n"
)
DIA = date(2026, 10, 9)


def test_le_so_os_futuros_e_deixa_as_opcoes_de_fora():
    t = b3.ler_boletim(TEXTO, DIA)
    assert list(t["contrato"]) == ["BGIV26", "WDOX26", "DI1F27"]
    assert list(t["produto"]) == ["BGI", "WDO", "DI1"]
    assert list(t["vencimento"]) == ["V26", "X26", "F27"]
    assert (t["Date"] == pd.Timestamp(DIA)).all()


def test_converte_numeros_com_virgula_de_milhar_e_traco_vira_vazio():
    t = b3.ler_boletim(TEXTO, DIA).set_index("contrato")
    assert t.loc["WDOX26", "Negocios"] == 442271
    assert t.loc["WDOX26", "Contratos"] == 2185958
    assert t.loc["WDOX26", "Volume_financeiro"] == 109526966975
    assert t.loc["BGIV26", "Contratos"] == 1356
    assert pd.isna(t.loc["DI1F27", "Open"])


def test_ajuste_e_ajuste_anterior_fecham_com_a_variacao():
    t = b3.ler_boletim(TEXTO, DIA).set_index("contrato")
    assert t.loc["BGIV26", "Ajuste"] == pytest.approx(388.8)
    assert t.loc["BGIV26", "Ajuste_anterior"] == pytest.approx(388.5)
    variacao = t.loc["BGIV26", "Ajuste"] - t.loc["BGIV26", "Ajuste_anterior"]
    assert variacao == pytest.approx(t.loc["BGIV26", "Variacao"])
    assert t.loc["BGIV26", "High"] >= t.loc["BGIV26", "Close"] >= t.loc["BGIV26", "Low"]


def test_dia_sem_pregao_devolve_tabela_vazia():
    assert b3.ler_boletim(f"﻿aviso\n\n{CABECALHO}\n", DIA).empty


def test_formato_diferente_levanta_erro_claro():
    with pytest.raises(ValueError, match="cabeçalho"):
        b3.ler_boletim("<html>erro</html>", DIA)
    mudado = TEXTO.replace("Opening price", "Abertura")
    with pytest.raises(ValueError, match="faltam"):
        b3.ler_boletim(mudado, DIA)


def test_dias_uteis_pula_fim_de_semana():
    dias = b3.dias_uteis(date(2026, 10, 9), date(2026, 10, 13))  # sexta a terça
    assert dias == [date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13)]


def test_atualizar_baixa_so_o_que_falta_e_marca_dia_sem_pregao(tmp_path):
    pedidos = []

    def falso(dia):
        pedidos.append(dia)
        return TEXTO if dia != date(2026, 10, 12) else f"x\n\n{CABECALHO}\n"

    r = b3.atualizar(
        date(2026, 10, 9), date(2026, 10, 13), pasta=tmp_path, baixar=falso, pausa=0
    )
    assert r["baixados"] == [date(2026, 10, 9), date(2026, 10, 13)]
    assert r["sem_pregao"] == [date(2026, 10, 12)]
    assert len(pedidos) == 3
    pedidos.clear()
    r2 = b3.atualizar(
        date(2026, 10, 9), date(2026, 10, 13), pasta=tmp_path, baixar=falso, pausa=0
    )
    assert r2["ja_tinha"] == [date(2026, 10, 9), date(2026, 10, 13)]
    assert pedidos == [date(2026, 10, 12)]  # o feriado é consultado de novo


def test_carregar_junta_os_dias(tmp_path):
    assert b3.carregar(tmp_path).empty
    b3.atualizar(
        date(2026, 10, 9),
        date(2026, 10, 13),
        pasta=tmp_path,
        baixar=lambda dia: TEXTO,
        pausa=0,
    )
    todos = b3.carregar(tmp_path)
    assert todos["Date"].nunique() == 3 and len(todos) == 9
