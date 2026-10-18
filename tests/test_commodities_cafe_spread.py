"""Spread arábica–robusta do Pink Sheet (PR 14): em centavos de dólar por libra-peso, desde 1960."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src import precos_de_referencia as precos
from src.banco import series as acervo_de_series
from src.commodities.cafe import spread
from src.commodities.cafe.spread import Marco

PINK = (
    Path(__file__).parent.parent
    / "dados_de_exemplo"
    / "commodities"
    / "pink_sheet_mensal.xlsx"
).read_bytes()
US_KG_PARA_C_LB = 100 * precos.LIBRA_EM_KG  # US$/kg → centavos de dólar por libra


def _serie(*pares: tuple[str, float | None]) -> pd.Series:
    return pd.Series(
        [v for _, v in pares],
        index=pd.to_datetime([m for m, _ in pares]),
        dtype=float,
    )


def test_spread_em_centavos_por_libra():
    arabica = _serie(("2024-01-01", 4.0))
    robusta = _serie(("2024-01-01", 2.5))
    [ponto] = spread.spread_arabica_robusta(arabica, robusta)
    assert ponto.mes == date(2024, 1, 1)
    assert ponto.arabica == pytest.approx(4.0 * US_KG_PARA_C_LB)
    assert ponto.robusta == pytest.approx(2.5 * US_KG_PARA_C_LB)
    assert ponto.spread == pytest.approx(1.5 * US_KG_PARA_C_LB)
    assert ponto.razao == pytest.approx(4.0 / 2.5)


def test_spread_comeca_em_1960_quando_a_serie_comeca():
    arabica = _serie(("1960-01-01", 0.8), ("1960-02-01", 0.79))
    robusta = _serie(("1960-01-01", 0.5), ("1960-02-01", 0.5))
    pontos = spread.spread_arabica_robusta(arabica, robusta)
    assert pontos[0].mes == date(1960, 1, 1)


def test_mes_sem_um_dos_dois_precos_fica_de_fora_nunca_vira_zero():
    arabica = _serie(("2024-01-01", 4.0), ("2024-02-01", 4.1), ("2024-03-01", None))
    robusta = _serie(("2024-01-01", 2.5), ("2024-03-01", 2.6))
    pontos = spread.spread_arabica_robusta(arabica, robusta)
    assert [p.mes for p in pontos] == [date(2024, 1, 1)]


def test_spread_pode_ser_negativo_quando_o_robusta_passa_o_arabica():
    pontos = spread.spread_arabica_robusta(
        _serie(("2024-01-01", 2.0)), _serie(("2024-01-01", 2.5))
    )
    assert pontos[0].spread < 0


def test_spread_do_pink_sheet_de_exemplo_confere_com_a_conta_a_mao():
    valores = {(v.id, v.mes): v.valor for v in precos.ler_pink_sheet(PINK)}
    setembro = date(2026, 9, 1)
    arabica = valores[("bm-pink-cafe-arabica", setembro)]
    robusta = valores[("bm-pink-cafe-robusta", setembro)]
    series = {
        i: _serie(*[(m.isoformat(), v) for (c, m), v in valores.items() if c == i])
        for i in ("bm-pink-cafe-arabica", "bm-pink-cafe-robusta")
    }
    pontos = spread.spread_arabica_robusta(
        series["bm-pink-cafe-arabica"], series["bm-pink-cafe-robusta"]
    )
    ultimo = pontos[-1]
    assert ultimo.mes == setembro
    assert ultimo.spread == pytest.approx((arabica - robusta) * US_KG_PARA_C_LB)


def test_marcos_de_2014_2021_e_2024_25_tem_data_texto_e_fonte():
    anos = {m.data.year for m in spread.MARCOS}
    assert {2014, 2021, 2024, 2025} <= anos
    for marco in spread.MARCOS:
        assert marco.texto and marco.fonte, marco
    assert list(spread.MARCOS) == sorted(spread.MARCOS, key=lambda m: m.data)


def test_marcos_nao_trazem_numero_de_fonte_so_pesquisa():
    """A ICO é só pesquisa: nenhum marco cita preço dela (o spread mostrado é o do Pink Sheet)."""
    for marco in spread.MARCOS:
        assert "ICO" not in marco.fonte.split(), marco


def test_marcos_ate_nao_olha_o_futuro():
    assert spread.marcos_ate(date(2013, 12, 31)) == []
    ate_2021 = spread.marcos_ate(date(2021, 12, 31))
    assert {m.data.year for m in ate_2021} == {2014, 2021}
    assert all(isinstance(m, Marco) for m in ate_2021)


def test_spread_como_estava_em_d_nao_usa_revisao_posterior(banco):
    with banco.begin() as conexao:
        precos.gravar_precos(conexao, precos.ler_pink_sheet(PINK), date(2026, 10, 3))
        revisados = [
            v
            if v.id != "bm-pink-cafe-arabica"
            else precos.ValorMensal(v.id, v.mes, 9.0)
            for v in precos.ler_pink_sheet(PINK)
        ]
        precos.gravar_precos(conexao, revisados, date(2026, 11, 3))
    with banco.connect() as conexao:
        antes = spread.spread_como_estava_em(conexao, date(2026, 10, 31))
        depois = spread.spread_como_estava_em(conexao, date(2026, 11, 30))
        assert acervo_de_series.tem_dados(conexao, spread.SERIE_ARABICA)
    assert antes[-1].arabica == pytest.approx(7.26 * US_KG_PARA_C_LB)
    assert depois[-1].arabica == pytest.approx(9.0 * US_KG_PARA_C_LB)
    assert len(antes) == len(depois) == 12
