"""Fechamento diário do Ibovespa pela B3 (estatísticas do índice, um arquivo por ano: `base/indices_b3.py`).

O formato é o de `GetPortfolioDay`: uma linha por dia do mês (`day`) e uma coluna por mês (`rateValue1`
a `rateValue12`), com o número em texto brasileiro ("175.710,05"); dia sem pregão vem `null` ou vazio.
"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from base import indices_b3
from base.arquivo import destinos, fontes


def _ano(valores: dict[tuple[int, int], str]) -> bytes:
    """O JSON da B3 para um ano: `valores[(mes, dia)]` = fechamento em texto."""
    linhas = []
    for dia in range(1, 32):
        linha: dict[str, object] = {"day": dia}
        for mes in range(1, 13):
            linha[f"rateValue{mes}"] = valores.get((mes, dia))
        linhas.append(linha)
    resumo = {"day": 0, **{f"rateValue{m}": "1,00" for m in range(1, 13)}}
    return json.dumps({"min": resumo, "max": resumo, "results": linhas}).encode()


def test_endereco_leva_o_pedido_em_base64_e_devolve_o_ano():
    endereco = indices_b3.endereco_do_ano(2026)
    assert endereco.startswith(
        "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/"
    )
    assert indices_b3.ano_do_endereco(endereco) == 2026


def test_ler_ano_da_um_fechamento_por_pregao():
    conteudo = _ano(
        {
            (10, 26): "176.609,51",
            (10, 27): "175.710,05",
            (1, 2): "160.538,69",
            (10, 28): "",
        }
    )
    serie = indices_b3.ler_ano(conteudo, 2026)
    assert list(serie.index) == [
        pd.Timestamp(2026, 1, 2),
        pd.Timestamp(2026, 10, 26),
        pd.Timestamp(2026, 10, 27),
    ]
    assert serie[pd.Timestamp(2026, 10, 27)] == pytest.approx(175_710.05)
    assert serie.name == "ibovespa"


def test_dia_que_nao_existe_no_calendario_falha():
    """31/11 não existe: se aparecer, a B3 mudou o formato, e o erro não pode passar calado."""
    with pytest.raises(ValueError):
        indices_b3.ler_ano(_ano({(11, 31): "1,00"}), 2026)


def test_serie_junta_os_anos_em_ordem():
    anos = {
        2026: _ano({(1, 2): "160.538,69"}),
        2025: _ano({(12, 30): "161.125,37", (1, 2): "118.532,68"}),
    }
    serie = indices_b3.serie_dos_anos(anos)
    assert list(serie.index.year) == [2025, 2025, 2026]
    assert serie.iloc[-1] == pytest.approx(160_538.69)
    assert serie.index.is_monotonic_increasing


# --- no arquivista ------------------------------------------------------------------------------

AGORA = datetime(2026, 10, 29, 5, tzinfo=UTC)  # 2h em Brasília


def test_fonte_pede_um_arquivo_por_ano_desde_2000():
    fonte = fontes.POR_ID["b3-ibov-diario"]
    alvos = fonte.descobrir(None, AGORA)
    anos = [indices_b3.ano_do_endereco(a.url) for a in alvos]
    assert anos == list(range(indices_b3.PRIMEIRO_ANO, 2027))
    assert {a.extensao for a in alvos} == {".json"}
    assert (fonte.grupo, fonte.tipo) == ("diaria", "json")
    assert destinos.DESTINOS["b3-ibov-diario"].tipo == destinos.SO_PESQUISA


def test_na_virada_do_ano_o_ano_novo_entra():
    alvos = fontes.POR_ID["b3-ibov-diario"].descobrir(
        None, datetime(2027, 1, 1, 5, tzinfo=UTC)
    )
    assert indices_b3.ano_do_endereco(alvos[-1].url) == 2027


def _guardado(ano: int, baixado_em: datetime) -> SimpleNamespace:
    return SimpleNamespace(url=indices_b3.endereco_do_ano(ano), baixado_em=baixado_em)


@pytest.mark.parametrize(
    ("ano", "baixado_em", "vale"),
    [
        (
            2025,
            datetime(2026, 1, 2, 5, tzinfo=UTC),
            True,
        ),  # baixado depois que o ano acabou
        (
            2025,
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            False,
        ),  # 31/12 às 22h em Brasília: pode faltar o último dia
        (
            2026,
            datetime(2026, 10, 29, 5, tzinfo=UTC),
            False,
        ),  # o ano corrente muda todo dia
        (
            2025,
            datetime(2026, 1, 2, 5, tzinfo=UTC).replace(tzinfo=None),
            True,
        ),  # o SQLite dos testes devolve sem fuso
    ],
)
def test_so_o_ano_fechado_vale_o_que_esta_guardado(ano, baixado_em, vale):
    guardado_vale = fontes.POR_ID["b3-ibov-diario"].guardado_vale
    assert guardado_vale is not None
    assert guardado_vale(_guardado(ano, baixado_em)) is vale
