"""Tráfego nas praças de pedágio (série 5 da base de ML, PR 1; ADR 0081): ANTT (rodovias federais) e
ARTESP (rodovias estaduais de São Paulo).

Recortes reais em `tests/arquivos/setoriais/`: a ANTT do acervo (Autopista Fernão Dias, praça "2
(Vargem)", e Ecosul, "Praça Retiro", em janeiro e fevereiro de 2010, 2023 e 2024 consolidado; em 2026 a
Fernão Dias aparece como "MOTIVA MINAS SP") e a ARTESP baixada em 16/10/2026 (AutoBAn e Ecovias dos
Imigrantes em 1º e 2 de janeiro de 2016, por hora, e de 2026, por dia).
"""

from pathlib import Path

import pandas as pd
import pytest

from base.setoriais import pedagio

PASTA = Path(__file__).parent / "arquivos" / "setoriais"
ANTT = "https://dados.antt.gov.br/dataset/x/resource/y/download/"


def _antt(nome: str) -> pd.DataFrame:
    return pedagio.ler_antt((PASTA / "antt" / nome).read_bytes(), ANTT + nome)


@pytest.fixture(scope="module")
def antt() -> pd.DataFrame:
    nomes = [
        "volume-trafego-praca-pedagio-2010.csv",
        "volume-trafego-praca-pedagio-2023.csv",
        "volume-trafego-praca-pedagio-2024_mensal_consolidado.csv",
        "volume-trafego-praca-pedagio-2026_mensal_consolidado.csv",
    ]
    return pd.concat([_antt(nome) for nome in nomes], ignore_index=True)


# --- ANTT -----------------------------------------------------------------------------------------
def test_le_a_antt_nos_tres_esquemas(antt):
    """2010 a 2023: "Categoria 1" e o mês como 01/MM/AAAA; 2024 em diante (consolidado): o número de
    eixos ("10") e o mês como MM/AAAA. Nada é convertido de um esquema para o outro."""
    assert list(antt.columns) == list(pedagio.COLUNAS_DA_ANTT)
    em_2010 = antt[antt["competencia"].dt.year == 2010]
    assert set(em_2010["esquema"]) == {"categoria"}
    assert "Categoria 1" in set(em_2010["categoria"])
    assert em_2010["categoria_eixo"].isna().all()
    primeira = em_2010[
        (em_2010["competencia"] == pd.Timestamp("2010-01-31"))
        & (em_2010["praca"] == "2 (Vargem)")
        & (em_2010["sentido"] == "Crescente")
        & (em_2010["categoria"] == "Categoria 1")
    ]
    assert primeira["volume_total"].tolist() == [277638.0]  # "277638,00"
    em_2024 = antt[antt["competencia"].dt.year == 2024]
    assert set(em_2024["esquema"]) == {"eixos"}
    assert "10" in set(em_2024["categoria_eixo"])
    assert em_2024["categoria"].isna().all()
    assert set(antt["competencia"].dt.day) == {28, 29, 31}  # o último dia do mês
    assert set(antt["concessionaria"]) == {
        "AUTOPISTA FERNÃO DIAS",
        "ECOSUL",
        "MOTIVA MINAS SP",
    }


def test_cada_mes_vem_de_um_arquivo_so(antt):
    """Em 2024 a ANTT publica o mesmo mês três vezes (o `2024.csv`, que é por dia, o `_diario` e o
    `_mensal_consolidado`): só o consolidado entra. De 2010 a 2023, o anual. Os JSON repetem o CSV."""
    escolhe = pedagio.arquivo_da_antt
    assert escolhe(ANTT + "volume-trafego-praca-pedagio-2010.csv") == "2010"
    assert escolhe(ANTT + "volume-trafego-praca-pedagio-2023.csv") == "2023"
    assert escolhe(ANTT + "volume-trafego-praca-pedagio-2024.csv") is None
    assert escolhe(ANTT + "volume-trafego-praca-pedagio-2024_diario.csv") is None
    assert (
        escolhe(ANTT + "volume-trafego-praca-pedagio-2024_mensal_consolidado.csv")
        == "2024"
    )
    assert (
        escolhe(ANTT + "volume-trafego-praca-pedagio-2026_mensal_consolidado.csv")
        == "2026"
    )
    assert escolhe(ANTT + "volume-trafego-praca-pedagio-2010.json") is None
    assert escolhe(ANTT + "volume_praca_2013.json") is None
    assert escolhe(ANTT + "dicionario_dados_volume_trafego.pdf") is None
    chave = ["competencia", "concessionaria", "praca", "sentido", "tipo_cobranca",
             "categoria", "categoria_eixo", "tipo_de_veiculo"]  # fmt: skip
    assert not antt.duplicated(chave).any()
    assert antt.groupby("competencia")["arquivo"].nunique().max() == 1


# --- prazos ("como era na data") ------------------------------------------------------------------
def test_disponivel_em_respeita_o_prazo_da_fonte(antt):
    """Pedágio: nenhum prazo escrito. Medido (16/10/2026, CKAN da ANTT): agosto/2026 saiu em 30/09
    (30 dias depois do fim do mês) e janeiro/2026 em 28/02 (28 dias). A regra dá folga sobre o medido e
    vale para todo o histórico (decisão 3(a) do Tiago): a recarga de 03/12/2024 dos anuais de 2010 a
    2023 não entra, senão nada de antes de 2024 serviria para treinar."""
    from base.setoriais import prazos

    assert prazos.DIAS_ATE_PUBLICAR_PEDAGIO > prazos.ATRASO_MEDIDO_PEDAGIO
    atraso = antt["disponivel_em"] - antt["competencia"]
    assert (atraso == pd.Timedelta(days=prazos.DIAS_ATE_PUBLICAR_PEDAGIO)).all()
    janeiro_de_2010 = antt[antt["competencia"] == pd.Timestamp("2010-01-31")]
    assert (janeiro_de_2010["disponivel_em"] < pd.Timestamp("2010-12-31")).all()
    agosto = pd.Series([pd.Timestamp("2026-08-31")])
    assert (prazos.disponivel_pedagio(agosto) >= pd.Timestamp("2026-09-30")).all()
