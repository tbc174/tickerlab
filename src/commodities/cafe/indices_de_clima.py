"""Índices explicativos de clima por região cafeeira (plano do café, PR 8, tarefa 8.3).

Três índices, cada um com definição escrita antes do número (adendo de pesquisa do plano):

- **Florada** (setembro a novembro): a chuva acumulada contra a normal de 1991–2020; a *primeira
  chuva* (o primeiro dia da janela com `CHUVA_QUE_ABRE_A_FLORADA_MM` ou mais, na média das estações)
  e a temperatura máxima média das `SEMANAS_APOS_A_CHUVA` semanas seguintes, com os dias acima de
  `TEMPERATURA_QUE_ABORTA_C` (calor e seca depois da florada abortam a flor e o "chumbinho";
  Embrapa, Circular Técnica 35).
- **Geada** (junho a agosto): dias com temperatura mínima no abrigo abaixo de `LIMIAR_DE_GEADA_C`,
  média das estações ponderada pela área de café (PAM) do município de cada uma. A geada não tira a
  safra do ano, tira a do ano seguinte (`conteudo/commodities/cafe.md`).
- **Déficit na granação** (dezembro a março): a chuva acumulada contra a normal; anomalia negativa é
  o déficit (Minas em janeiro e fevereiro de 2014 é o caso de teste).

Todas são funções puras: recebem o mensal da região (as linhas de `clima_regiao_cafe`) ou o diário
por estação já com `regiao` (`base/commodities/clima_regiao.py`) e devolvem `IndiceClimatico`.
**Sem dado não vira zero**: mês ou estação que falta deixa o valor vazio (`None`), e o índice diz
quantas estações entraram. São índices **explicativos**, contexto datado: não são previsão de safra.
"""

import itertools
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from base.commodities.clima_regiao import (
    ANOS_MINIMOS_NA_NORMAL,
    FIM_DA_NORMAL,
    FONTE_INMET,
    FRACAO_MINIMA_DE_DIAS,
    HORAS_MINIMAS_NO_DIA,
    INICIO_DA_NORMAL,
    MINIMO_DE_ESTACOES,
    simplificar_nome,
)
from src.commodities.cafe.regioes import REGIOES, Regiao

MESES_DA_FLORADA = (9, 10, 11)
MESES_DA_GEADA = (6, 7, 8)
MESES_DA_GRANACAO = (12, 1, 2, 3)  # dezembro do ano anterior a março
CHUVA_QUE_ABRE_A_FLORADA_MM = 10.0
SEMANAS_APOS_A_CHUVA = 3
TEMPERATURA_QUE_ABORTA_C = 34.0
LIMIAR_DE_GEADA_C = 1.0  # no abrigo, a 1,5 m; na relva a geada vem com Tmín maior
DIAS_POR_SEMANA = 7


@dataclass(frozen=True)
class IndiceClimatico:
    """Um índice de uma região num período: valor, normal, anomalia (valor − normal) e quantas
    estações entraram. `None` é "sem dado" (nunca zero)."""

    valor: float | None
    normal: float | None
    anomalia: float | None
    n_estacoes: int
    periodo: tuple[date, date]

    @property
    def razao_da_normal(self) -> float | None:
        """valor / normal (1,0 = igual à normal); `None` sem dado ou com normal zero."""
        if self.valor is None or not self.normal:
            return None
        return self.valor / self.normal


@dataclass(frozen=True)
class Florada:
    """O índice de florada de uma região num ano: a chuva da janela, a primeira chuva e o calor
    das semanas seguintes."""

    chuva: IndiceClimatico
    primeira_chuva: date | None
    tmax_apos_a_chuva: IndiceClimatico
    dias_acima_de_34c: int | None


def _sem_dado(periodo: tuple[date, date], n_estacoes: int = 0) -> IndiceClimatico:
    return IndiceClimatico(None, None, None, n_estacoes, periodo)


def _indice(
    valor: float | None,
    normal: float | None,
    n_estacoes: int,
    periodo: tuple[date, date],
) -> IndiceClimatico:
    anomalia = valor - normal if valor is not None and normal is not None else None
    return IndiceClimatico(valor, normal, anomalia, n_estacoes, periodo)


# --- mensal: chuva acumulada contra a normal -----------------------------------------------------
def _competencias(ano_final: int, meses: Iterable[int]) -> list[pd.Timestamp]:
    """O fim de cada mês da janela que termina no `ano_final` (dezembro antes de janeiro é do ano
    anterior)."""
    competencias = []
    ano = ano_final
    meses = list(meses)
    if any(seguinte < mes for mes, seguinte in itertools.pairwise(meses)):
        ano -= (
            1  # a janela vira o ano (dezembro antes de janeiro): começa no ano anterior
        )
    for mes in meses:
        competencias.append(pd.Timestamp(ano, mes, 1) + pd.offsets.MonthEnd(0))
        if mes == 12:
            ano += 1
    return competencias


def chuva_acumulada(
    mensal: pd.DataFrame,
    regiao: str,
    ano: int,
    meses: Iterable[int],
    fonte: str = FONTE_INMET,
) -> IndiceClimatico:
    """A chuva somada dos `meses` (janela que termina em `ano`) contra a soma das normais.

    Falta um mês → valor vazio; falta uma normal → normal e anomalia vazias. `n_estacoes` é o menor
    número de estações dos meses (vazio no CHIRPS vira 0).
    """
    competencias = _competencias(ano, meses)
    periodo = (
        (competencias[0] - pd.offsets.MonthBegin(1)).date(),
        competencias[-1].date(),
    )
    linhas = mensal[(mensal["regiao"] == regiao) & (mensal["fonte"] == fonte)]
    por_mes = linhas.set_index(pd.to_datetime(linhas["competencia"]))
    por_mes = por_mes[~por_mes.index.duplicated()].reindex(competencias)
    chuva = por_mes["chuva_mm"].astype(float)
    normal = por_mes["chuva_normal_mm"].astype(float)
    estacoes = por_mes["n_estacoes"].astype(float)
    n_estacoes = 0 if estacoes.isna().all() else int(np.nanmin(estacoes))
    if chuva.isna().any():
        return _sem_dado(periodo, n_estacoes)
    normal_total = None if normal.isna().any() else float(normal.sum())
    return _indice(float(chuva.sum()), normal_total, n_estacoes, periodo)


def deficit_dez_mar(
    mensal: pd.DataFrame, regiao: str, ano: int, fonte: str = FONTE_INMET
) -> IndiceClimatico:
    """A chuva da granação (dezembro do ano anterior a março de `ano`) contra a normal: anomalia
    negativa é o déficit hídrico."""
    return chuva_acumulada(mensal, regiao, ano, MESES_DA_GRANACAO, fonte)


# --- diário: a primeira chuva, o calor seguinte e a geada ----------------------------------------
def _diario_da_regiao(diario: pd.DataFrame, regiao: str) -> pd.DataFrame:
    valido = diario[
        (diario["regiao"] == regiao) & (diario["horas_validas"] >= HORAS_MINIMAS_NO_DIA)
    ].copy()
    valido["dia"] = pd.to_datetime(valido["dia"])
    return valido


def _entre(diario: pd.DataFrame, inicio: date, fim: date) -> pd.DataFrame:
    return diario[
        (diario["dia"] >= pd.Timestamp(inicio)) & (diario["dia"] <= pd.Timestamp(fim))
    ]


def primeira_chuva_da_florada(
    diario: pd.DataFrame, regiao: str, ano: int
) -> date | None:
    """O primeiro dia de setembro a novembro com `CHUVA_QUE_ABRE_A_FLORADA_MM` ou mais na média
    das estações da região; `None` se não choveu tanto (ou não há estação)."""
    janela = _entre(
        _diario_da_regiao(diario, regiao),
        date(ano, MESES_DA_FLORADA[0], 1),
        date(ano, MESES_DA_FLORADA[-1], 30),
    )
    if janela.empty:
        return None
    media_do_dia = janela.groupby("dia")["chuva_mm"].mean()
    chuvosos = media_do_dia[media_do_dia >= CHUVA_QUE_ABRE_A_FLORADA_MM]
    return None if chuvosos.empty else chuvosos.index.min().date()


def _estacoes_com_dias_bastantes(janela: pd.DataFrame, dias: int) -> pd.DataFrame:
    contagem = janela.groupby("estacao")["dia"].size()
    bastantes = contagem[contagem >= FRACAO_MINIMA_DE_DIAS * dias].index
    return janela[janela["estacao"].isin(bastantes)]


def temperatura_apos_a_primeira_chuva(
    diario: pd.DataFrame, regiao: str, ano: int
) -> tuple[IndiceClimatico, int | None]:
    """A Tmáx média das `SEMANAS_APOS_A_CHUVA` semanas depois da primeira chuva da florada (média
    das estações com dias bastantes) e quantos dias passaram de `TEMPERATURA_QUE_ABORTA_C` (na
    estação mais quente). Não há normal para esta janela móvel."""
    primeira = primeira_chuva_da_florada(diario, regiao, ano)
    if primeira is None:
        fim = date(ano, MESES_DA_FLORADA[-1], 30)
        return _sem_dado((date(ano, MESES_DA_FLORADA[0], 1), fim)), None
    inicio = primeira + timedelta(days=1)
    dias = SEMANAS_APOS_A_CHUVA * DIAS_POR_SEMANA
    fim = primeira + timedelta(days=dias)
    janela = _estacoes_com_dias_bastantes(
        _entre(_diario_da_regiao(diario, regiao), inicio, fim), dias
    )
    if janela.empty:
        return _sem_dado((inicio, fim)), None
    por_estacao = janela.groupby("estacao")
    tmax = float(por_estacao["tmax_c"].mean().mean())
    quentes = int(
        (janela["tmax_c"] > TEMPERATURA_QUE_ABORTA_C)
        .groupby(janela["estacao"])
        .sum()
        .max()
    )
    return _indice(tmax, None, len(por_estacao), (inicio, fim)), quentes


def indice_de_florada(
    mensal: pd.DataFrame,
    diario: pd.DataFrame,
    regiao: str,
    ano: int,
    fonte: str = FONTE_INMET,
) -> Florada:
    """O índice de florada de `regiao` em `ano`: chuva de setembro a novembro contra a normal, a
    primeira chuva e o calor das três semanas seguintes."""
    tmax, quentes = temperatura_apos_a_primeira_chuva(diario, regiao, ano)
    return Florada(
        chuva=chuva_acumulada(mensal, regiao, ano, MESES_DA_FLORADA, fonte),
        primeira_chuva=primeira_chuva_da_florada(diario, regiao, ano),
        tmax_apos_a_chuva=tmax,
        dias_acima_de_34c=quentes,
    )


def _area_por_estacao(
    diario: pd.DataFrame, regioes: Iterable[Regiao]
) -> dict[str, float]:
    """A área de café (PAM) do município de cada estação, pelo nome e UF; sem par, peso zero."""
    area = {
        (simplificar_nome(m.nome), m.uf): m.area_ha
        for r in regioes
        for m in r.municipios
    }
    estacoes = diario.drop_duplicates("estacao")
    return {
        str(linha.estacao): area.get(
            (simplificar_nome(str(linha.nome)), str(linha.uf)), 0.0
        )
        for linha in estacoes.itertuples()
    }


def _geada_de_um_ano(
    valido: pd.DataFrame, ano: int, pesos: dict[str, float]
) -> tuple[float | None, int]:
    inicio, fim = date(ano, MESES_DA_GEADA[0], 1), date(ano, MESES_DA_GEADA[-1], 31)
    janela = _estacoes_com_dias_bastantes(
        _entre(valido, inicio, fim), (fim - inicio).days + 1
    )
    if janela.empty:
        return None, 0
    frios = (janela["tmin_c"] < LIMIAR_DE_GEADA_C).groupby(janela["estacao"]).sum()
    if len(frios) < MINIMO_DE_ESTACOES:
        return None, len(frios)
    peso = np.array([pesos.get(str(e), 0.0) for e in frios.index])
    if peso.sum() == 0:
        peso = np.ones(len(frios))  # sem área conhecida: média simples
    return float(np.average(frios.to_numpy(dtype=float), weights=peso)), len(frios)


def dias_de_geada(
    diario: pd.DataFrame,
    regiao: str,
    ano: int,
    regioes: Iterable[Regiao] = REGIOES,
) -> IndiceClimatico:
    """Dias de junho a agosto de `ano` com Tmín abaixo de `LIMIAR_DE_GEADA_C`, média das estações
    ponderada pela área de café do município de cada uma.

    Precisa de `MINIMO_DE_ESTACOES` estações com dias bastantes na janela. A normal é a média do
    mesmo índice nos anos de 1991–2020 que houver no diário (pelo menos `ANOS_MINIMOS_NA_NORMAL`).
    """
    regioes = tuple(regioes)
    periodo = (date(ano, MESES_DA_GEADA[0], 1), date(ano, MESES_DA_GEADA[-1], 31))
    valido = _diario_da_regiao(diario, regiao)
    if valido.empty:
        return _sem_dado(periodo)
    pesos = _area_por_estacao(valido, regioes)
    valor, n_estacoes = _geada_de_um_ano(valido, ano, pesos)
    anos = sorted(
        a
        for a in valido["dia"].dt.year.unique()
        if INICIO_DA_NORMAL <= a <= FIM_DA_NORMAL
    )
    historico = [_geada_de_um_ano(valido, a, pesos)[0] for a in anos]
    com_dado = [g for g in historico if g is not None]
    normal = (
        float(np.mean(com_dado)) if len(com_dado) >= ANOS_MINIMOS_NA_NORMAL else None
    )
    return _indice(valor, normal, n_estacoes, periodo)


def em_dicionario(indice: IndiceClimatico) -> dict[str, object]:
    """O índice em tipos simples (para a API e para o painel)."""
    return {
        "valor": indice.valor,
        "normal": indice.normal,
        "anomalia": indice.anomalia,
        "razao_da_normal": indice.razao_da_normal,
        "n_estacoes": indice.n_estacoes,
        "inicio": indice.periodo[0].isoformat(),
        "fim": indice.periodo[1].isoformat(),
    }
