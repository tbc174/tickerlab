"""Índices explicativos de clima por região cafeeira (plano do café, PR 8, tarefa 8.3).

Os dados são fabricados e determinísticos: um mensal com as colunas de `clima_regiao_cafe` e um
diário por estação como o de `base/commodities/clima_regiao.py`, com três estações do Sul de Minas
(nomes dos três primeiros municípios da região, para a ponderação pela área da PAM).
"""

from datetime import date

import pandas as pd
import pytest

from src.commodities.cafe import indices_de_clima as indices
from src.commodities.cafe.indices_de_clima import (
    IndiceClimatico,
    chuva_acumulada,
    deficit_dez_mar,
    dias_de_geada,
    em_dicionario,
    indice_de_florada,
    primeira_chuva_da_florada,
)
from src.commodities.cafe.regioes import POR_ID

SUL_DE_MINAS = POR_ID["sul-de-minas"]
MUNICIPIOS = SUL_DE_MINAS.municipios[:3]
ESTACOES = ("A1", "A2", "A3")
COLUNAS_DO_MENSAL = (
    "regiao", "competencia", "fonte", "chuva_mm", "chuva_normal_mm", "n_estacoes",
)  # fmt: skip


def _mensal(linhas, regiao="sul-de-minas", fonte="inmet") -> pd.DataFrame:
    """[(competência, chuva, normal, n_estacoes), ...] → o mensal da região."""
    return pd.DataFrame(
        [
            (regiao, pd.Timestamp(competencia), fonte, chuva, normal, n)
            for competencia, chuva, normal, n in linhas
        ],
        columns=list(COLUNAS_DO_MENSAL),
    )


def _diario(
    inicio: str,
    fim: str,
    estacoes=ESTACOES,
    chuva=None,
    tmin=None,
    tmax=None,
    horas=24,
) -> pd.DataFrame:
    """Um dia por estação entre `inicio` e `fim`; `chuva`, `tmin` e `tmax` são funções
    (estação, dia) → valor, com padrões secos e amenos."""
    chuva = chuva or (lambda estacao, dia: 0.0)
    tmin = tmin or (lambda estacao, dia: 12.0)
    tmax = tmax or (lambda estacao, dia: 28.0)
    linhas = [
        {
            "estacao": estacao,
            "nome": municipio.nome.upper(),
            "uf": municipio.uf,
            "dia": dia,
            "chuva_mm": chuva(estacao, dia.date()),
            "tmin_c": tmin(estacao, dia.date()),
            "tmax_c": tmax(estacao, dia.date()),
            "horas_validas": horas,
            "regiao": "sul-de-minas",
        }
        for estacao, municipio in zip(estacoes, MUNICIPIOS, strict=False)
        for dia in pd.date_range(inicio, fim, freq="D")
    ]
    return pd.DataFrame(linhas)


# --- florada --------------------------------------------------------------------------------------
def test_indice_de_florada():
    mensal = _mensal(
        [
            ("2023-09-30", 50.0, 60.0, 5),
            ("2023-10-31", 100.0, 110.0, 4),
            ("2023-11-30", 150.0, 160.0, 6),
        ]
    )
    primeira = date(2023, 9, 20)
    quentes = {date(2023, 9, 25), date(2023, 10, 2)}
    diario = _diario(
        "2023-09-01",
        "2023-11-30",
        chuva=lambda e, d: (
            12.0 if d == primeira else (5.0 if d == date(2023, 9, 10) else 0.0)
        ),
        tmax=lambda e, d: 35.0 if (e == "A1" and d in quentes) else 30.0,
    )
    florada = indice_de_florada(mensal, diario, "sul-de-minas", 2023)
    assert florada.chuva == IndiceClimatico(
        300.0, 330.0, -30.0, 4, (date(2023, 9, 1), date(2023, 11, 30))
    )
    assert florada.chuva.razao_da_normal == pytest.approx(300 / 330)
    assert florada.primeira_chuva == primeira  # 5 mm no dia 10 não abre a florada
    tmax = florada.tmax_apos_a_chuva
    assert tmax.periodo == (date(2023, 9, 21), date(2023, 10, 11))  # 3 semanas
    assert tmax.valor == pytest.approx(((19 * 30 + 2 * 35) / 21 + 30 + 30) / 3)
    assert tmax.n_estacoes == 3
    assert tmax.normal is None and tmax.anomalia is None  # janela móvel: sem normal
    assert florada.dias_acima_de_34c == 2


def test_primeira_chuva_e_a_media_das_estacoes_dentro_da_janela():
    # 30 mm numa estação só (média 10 mm) abre a florada; chuva em agosto não conta
    diario = _diario(
        "2023-08-01",
        "2023-11-30",
        chuva=lambda e, d: (
            30.0 if (e == "A1" and d in {date(2023, 8, 20), date(2023, 10, 5)}) else 0.0
        ),
    )
    assert primeira_chuva_da_florada(diario, "sul-de-minas", 2023) == date(2023, 10, 5)
    # dia com poucas horas de leitura não entra
    com_buraco = diario.copy()
    com_buraco.loc[com_buraco["dia"] == "2023-10-05", "horas_validas"] = 19
    assert primeira_chuva_da_florada(com_buraco, "sul-de-minas", 2023) is None


# --- geada ----------------------------------------------------------------------------------------
def _frios(estacao: str, dia: date) -> float:
    """A1 tem 3 dias com Tmín abaixo de 1 °C, A2 tem 1 e A3 nenhum (0,5 °C conta; 1,0 °C não)."""
    geadas = {
        "A1": {date(2021, 7, 20), date(2021, 7, 21), date(2021, 7, 30)},
        "A2": {date(2021, 7, 20)},
    }
    if dia in geadas.get(estacao, set()):
        return 0.5
    return 1.0 if dia == date(2021, 6, 30) else 12.0


def test_dias_de_geada_jun_ago():
    diario = _diario("2021-05-01", "2021-09-30", tmin=_frios)
    indice = dias_de_geada(diario, "sul-de-minas", 2021)
    areas = [m.area_ha for m in MUNICIPIOS]
    esperado = (3 * areas[0] + 1 * areas[1] + 0 * areas[2]) / sum(areas)
    assert indice.valor == pytest.approx(esperado)  # ponderado pela área de café da PAM
    assert indice.n_estacoes == 3
    assert indice.periodo == (date(2021, 6, 1), date(2021, 8, 31))
    assert (
        indice.normal is None and indice.anomalia is None
    )  # sem anos de 1991–2020 no diário


def test_geada_com_normal_dos_anos_do_diario_e_estacao_sem_area_pesa_igual():
    # 10 anos (2011–2020) com 2 dias de geada em toda estação: normal 2,0; 2021 fica como no outro teste
    historia = pd.concat(
        [
            _diario(
                f"{ano}-06-01",
                f"{ano}-08-31",
                tmin=lambda e, d: 0.0 if d.day in (10, 11) and d.month == 7 else 10.0,
            )
            for ano in range(2011, 2021)
        ]
    )
    diario = pd.concat([historia, _diario("2021-06-01", "2021-08-31", tmin=_frios)])
    indice = dias_de_geada(diario, "sul-de-minas", 2021)
    assert indice.normal == pytest.approx(2.0)
    assert indice.anomalia == pytest.approx(indice.valor - 2.0)  # type: ignore[operator]
    # estações com nome que não é de município da região: média simples
    anonimas = _diario("2021-06-01", "2021-08-31", tmin=_frios).assign(nome="FAZENDA X")
    assert dias_de_geada(anonimas, "sul-de-minas", 2021).valor == pytest.approx(
        (3 + 1 + 0) / 3
    )


# --- déficit --------------------------------------------------------------------------------------
def test_deficit_dez_mar():
    # Minas em 2014: janeiro e fevereiro muito abaixo da normal (a seca que derrubou a safra 2014/15)
    mensal = _mensal(
        [
            ("2013-11-30", 150.0, 160.0, 7),
            ("2013-12-31", 200.0, 300.0, 7),
            ("2014-01-31", 80.0, 290.0, 7),
            ("2014-02-28", 60.0, 190.0, 6),
            ("2014-03-31", 150.0, 160.0, 7),
            ("2014-04-30", 50.0, 60.0, 7),
        ]
    )
    deficit = deficit_dez_mar(mensal, "sul-de-minas", 2014)
    assert deficit == IndiceClimatico(
        490.0, 940.0, -450.0, 6, (date(2013, 12, 1), date(2014, 3, 31))
    )
    assert deficit.razao_da_normal == pytest.approx(490 / 940)
    # a mesma janela pelo CHIRPS (sem estações) e a janela só de janeiro e fevereiro
    chirps = _mensal([("2013-12-31", 1.0, 2.0, None), ("2014-01-31", 1.0, 2.0, None), ("2014-02-28", 1.0, 2.0, None), ("2014-03-31", 1.0, 2.0, None)], fonte="chirps")  # fmt: skip
    assert deficit_dez_mar(mensal, "sul-de-minas", 2014, fonte="chirps").valor is None
    assert deficit_dez_mar(
        chirps, "sul-de-minas", 2014, fonte="chirps"
    ) == IndiceClimatico(4.0, 8.0, -4.0, 0, (date(2013, 12, 1), date(2014, 3, 31)))
    jan_fev = chuva_acumulada(mensal, "sul-de-minas", 2014, (1, 2))
    assert (jan_fev.valor, jan_fev.normal) == (140.0, 480.0)
    assert jan_fev.periodo == (date(2014, 1, 1), date(2014, 2, 28))


# --- sem dado -------------------------------------------------------------------------------------
def test_indice_sem_dado_nao_vira_zero():
    # falta fevereiro: a soma não vale
    sem_fevereiro = _mensal(
        [
            ("2013-12-31", 200.0, 300.0, 7),
            ("2014-01-31", 80.0, 290.0, 7),
            ("2014-03-31", 150.0, 160.0, 7),
        ]
    )
    deficit = deficit_dez_mar(sem_fevereiro, "sul-de-minas", 2014)
    assert (
        deficit.valor is None and deficit.anomalia is None and deficit.n_estacoes == 7
    )
    # mês sem normal: valor sim, normal e anomalia não
    sem_normal = _mensal([("2013-12-31", 200.0, None, 7), ("2014-01-31", 80.0, 290.0, 7), ("2014-02-28", 60.0, 190.0, 6), ("2014-03-31", 150.0, 160.0, 7)])  # fmt: skip
    deficit = deficit_dez_mar(sem_normal, "sul-de-minas", 2014)
    assert (deficit.valor, deficit.normal, deficit.anomalia) == (490.0, None, None)
    assert deficit.razao_da_normal is None
    # outra região: nada
    vazio = deficit_dez_mar(sem_fevereiro, "mogiana", 2014)
    assert vazio == IndiceClimatico(
        None, None, None, 0, (date(2013, 12, 1), date(2014, 3, 31))
    )
    # geada com 2 estações, ou sem diário, não vira zero
    duas = _diario("2021-06-01", "2021-08-31", estacoes=("A1", "A2"), tmin=_frios)
    assert dias_de_geada(duas, "sul-de-minas", 2021) == IndiceClimatico(
        None, None, None, 2, (date(2021, 6, 1), date(2021, 8, 31))
    )
    assert dias_de_geada(duas.iloc[:0], "sul-de-minas", 2021).valor is None
    # estação com menos de 80% dos dias da janela sai da conta
    curta = _diario("2021-06-01", "2021-07-31", estacoes=("A3",), tmin=_frios)
    tres = pd.concat([duas, curta])
    assert dias_de_geada(tres, "sul-de-minas", 2021).n_estacoes == 2
    # florada sem chuva de 10 mm: sem primeira chuva, sem temperatura, sem dias quentes
    seco = _diario("2023-09-01", "2023-11-30")
    florada = indice_de_florada(sem_fevereiro, seco, "sul-de-minas", 2023)
    assert florada.primeira_chuva is None and florada.dias_acima_de_34c is None
    assert florada.tmax_apos_a_chuva.valor is None and florada.chuva.valor is None


def test_em_dicionario_so_tem_tipos_simples():
    indice = IndiceClimatico(
        490.0, 940.0, -450.0, 6, (date(2013, 12, 1), date(2014, 3, 31))
    )
    assert em_dicionario(indice) == {
        "valor": 490.0,
        "normal": 940.0,
        "anomalia": -450.0,
        "razao_da_normal": pytest.approx(490 / 940),
        "n_estacoes": 6,
        "inicio": "2013-12-01",
        "fim": "2014-03-31",
    }
    assert (
        indices.LIMIAR_DE_GEADA_C == 1.0 and indices.CHUVA_QUE_ABRE_A_FLORADA_MM == 10.0
    )
