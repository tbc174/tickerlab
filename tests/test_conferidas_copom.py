"""Reuniões do Copom conferidas à mão (ADR 0093): a tabela tem de bater com a meta da Selic (SGS 432)."""

import pandas as pd
import pytest

from base import bcb_selic_focus
from base.bcb_selic_focus import (
    CAMINHO_DO_COPOM,
    divergencias_com_a_sgs,
    reunioes_do_copom,
)

# Mudanças da SGS 432 (`src.bcb.baixar_serie_sgs`, conferidas em 17/10/2026): a meta passa a
# valer no dia seguinte à reunião, e a manutenção não aparece na série.
MUDANCAS_DA_SGS_432 = {
    "2023-12-14": 11.75,
    "2024-02-01": 11.25,
    "2024-03-21": 10.75,
    "2024-05-09": 10.5,
    "2024-09-19": 10.75,
    "2024-11-07": 11.25,
    "2024-12-12": 12.25,
    "2025-01-30": 13.25,
    "2025-03-20": 14.25,
    "2025-05-08": 14.75,
    "2025-06-19": 15.0,
    "2026-03-19": 14.75,
    "2026-04-30": 14.5,
    "2026-06-18": 14.25,
    "2026-08-06": 14.0,
    "2026-09-17": 13.75,
}


def _sgs_diaria() -> pd.DataFrame:
    """A SGS 432 como a tabela da base a guarda: uma linha por dia com a meta vigente."""
    dias = pd.date_range("2023-12-14", "2026-10-16", freq="D")
    mudancas = pd.Series(
        {pd.Timestamp(d): v for d, v in MUDANCAS_DA_SGS_432.items()}
    ).reindex(dias)
    metas = mudancas.ffill()
    return pd.DataFrame(
        {
            "serie": "bcb-sgs-432",
            "referencia": dias,
            "valor": metas.to_numpy(),
            "divulgado_em": dias,
        }
    )


@pytest.fixture(scope="module")
def reunioes() -> pd.DataFrame:
    return reunioes_do_copom()


def test_colunas_e_campos_obrigatorios(reunioes):
    assert list(reunioes.columns) == [
        "reuniao",
        "data",
        "meta_selic",
        "link",
        "fonte",
        "conferido_em",
    ]
    assert not reunioes.isna().any().any()
    assert reunioes["link"].str.startswith("https://www.bcb.gov.br/").all()
    assert reunioes["fonte"].str.len().gt(10).all()
    assert (reunioes["conferido_em"] >= pd.Timestamp("2026-10-17")).all()


def test_numeros_seguidos_e_datas_em_ordem(reunioes):
    numeros = reunioes["reuniao"].tolist()
    assert numeros == list(range(numeros[0], numeros[0] + len(numeros)))
    assert reunioes["data"].is_monotonic_increasing
    assert reunioes["data"].is_unique
    assert reunioes["link"].is_unique


def test_oito_reunioes_por_ano(reunioes):
    por_ano = reunioes.groupby(reunioes["data"].dt.year).size()
    assert por_ano.index.min() == 2024
    # o ano corrente ainda está andando: só os anos fechados têm de ter 8
    fechados = por_ano.iloc[:-1]
    assert (fechados == 8).all(), por_ano.to_dict()
    assert por_ano.iloc[-1] <= 8


def test_meta_conferida_bate_com_a_sgs_432(reunioes):
    assert divergencias_com_a_sgs(reunioes, _sgs_diaria()) == []


def test_meta_trocada_na_tabela_conferida_e_pega(reunioes):
    errada = reunioes.copy()
    errada.loc[errada.index[3], "meta_selic"] += 0.25
    achadas = divergencias_com_a_sgs(errada, _sgs_diaria())
    assert [d["reuniao"] for d in achadas] == [int(errada.iloc[3]["reuniao"])]


def test_sgs_sem_valor_no_dia_seguinte_conta_como_divergencia(reunioes):
    sem_o_dia = _sgs_diaria()
    sem_o_dia = sem_o_dia[sem_o_dia["referencia"] != "2024-02-01"]
    achadas = divergencias_com_a_sgs(reunioes, sem_o_dia)
    assert [d["reuniao"] for d in achadas] == [260]
    assert achadas[0]["meta_sgs"] is None


def test_o_arquivo_fica_onde_o_plano_diz():
    assert CAMINHO_DO_COPOM.as_posix().endswith("base/conferidas/copom_reunioes.csv")
    assert bcb_selic_focus.SERIE_DA_META == "bcb-sgs-432"
