"""O julgamento do papel (P1 a P3 da seção 5), 12 meses corridos depois do início.

A conta sai só das linhas gravadas: o retorno de um dia é a razão entre os patrimônios de dois
fechamentos seguidos, e o caixa do dia é o CDI que a própria foto gravou. Um intervalo que atravessa
uma falta não entra no Sharpe (seria o retorno de dois dias contado como um), mas entra na queda
máxima, que é medida na curva dos patrimônios gravados: pular a falta não esconde uma queda.

Antes dos 12 meses a mesma conta sai como parcial (`completo=False`), só para acompanhar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from trader.calendario import proxima_execucao
from trader.papel.registro import GRAVACAO, RegistroDoPapel
from trader.papel.series import Serie

MESES_DO_PAPEL = 12
FRACAO_MINIMA_DO_SHARPE = 0.5  # P1: ≥ 50% do Sharpe de referência
MULTIPLO_MAXIMO_DA_QUEDA = 1.5  # P2: ≤ 1,5 × a queda do desenvolvimento
MAXIMO_DE_FALTAS = 5  # P3


@dataclass(frozen=True)
class Criterio:
    nome: str
    valor: float | int
    limite: str
    passou: bool


def fim_do_papel(inicio: date) -> date:
    """Primeiro dia fora da janela de 12 meses corridos que começa em `inicio`."""
    return (pd.Timestamp(inicio) + pd.DateOffset(months=MESES_DO_PAPEL)).date()


def dias_esperados(inicio: date, ate: date, mercado: str) -> list[date]:
    """Os dias em que a série devia gravar, de `inicio` até a véspera de `ate`."""
    dias, dia = [], inicio
    while dia < ate:
        dias.append(dia)
        dia = proxima_execucao(dia, mercado)
    return dias


def curva_do_papel(linhas: list[dict]) -> pd.DataFrame:
    """Patrimônio e CDI de cada fechamento gravado, com o retorno só de passos de um dia."""
    gravadas = [linha for linha in linhas if linha["tipo"] == GRAVACAO]
    curva = pd.DataFrame(
        {
            "patrimonio": [linha["carteira"]["patrimonio"] for linha in gravadas],
            "cdi": [linha["cdi_do_dia"] for linha in gravadas],
            "seguido": _seguidos(linhas),
        },
        index=pd.DatetimeIndex(
            [pd.Timestamp(linha["fechamento"]) for linha in gravadas]
        ),
        dtype=float,
    )
    curva["retorno"] = (curva["patrimonio"] / curva["patrimonio"].shift(1) - 1).where(
        curva["seguido"] == 1
    )
    return curva


def _seguidos(linhas: list[dict]) -> list[float]:
    """1 quando a gravação anterior da cadeia é a linha imediatamente antes (sem falta no meio)."""
    seguidos, anterior = [], None
    for linha in linhas:
        if linha["tipo"] == GRAVACAO:
            seguidos.append(1.0 if anterior == GRAVACAO else 0.0)
        anterior = linha["tipo"]
    return seguidos


def _queda_maxima(patrimonio: pd.Series) -> float:
    if patrimonio.empty:
        return 0.0
    return float((patrimonio / patrimonio.cummax() - 1).min())


def _gravacao_no_prazo(linha: dict) -> bool:
    return datetime.fromisoformat(linha["registrado_em"]) < datetime.fromisoformat(
        linha["prazo"]
    )


def julgar(registro: RegistroDoPapel, serie: Serie, hoje: date) -> dict:
    """P1 a P3 da série nos 12 meses do papel (ou até `hoje`, como parcial)."""
    inicio = registro.inicio()
    if inicio is None:
        raise ValueError("o início do papel ainda não foi fixado")
    registro.verificar(serie.nome)
    fim = fim_do_papel(inicio)
    ate = min(fim, hoje)
    linhas = [
        linha
        for linha in registro.linhas(serie.nome)
        if date.fromisoformat(linha["dia"]) < ate
    ]
    criterios = _criterios(serie, linhas, dias_esperados(inicio, ate, serie.mercado))
    return {
        "serie": serie.nome,
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "completo": hoje >= fim,
        "criterios": [c.__dict__ for c in criterios],
        "passou": all(c.passou for c in criterios),
    }


def _criterios(
    serie: Serie, linhas: list[dict], esperados: list[date]
) -> list[Criterio]:
    curva = curva_do_papel(linhas)
    retorno = curva["retorno"].dropna()
    sharpe = (
        serie.sharpe_do_excesso(retorno, curva["cdi"]) if len(retorno) else float("nan")
    )
    minimo = FRACAO_MINIMA_DO_SHARPE * serie.sharpe_de_referencia
    queda = _queda_maxima(curva["patrimonio"])
    pior_aceita = MULTIPLO_MAXIMO_DA_QUEDA * serie.queda_do_desenvolvimento
    gravados = {
        date.fromisoformat(linha["dia"])
        for linha in linhas
        if linha["tipo"] == GRAVACAO
    }
    faltas = sum(dia not in gravados for dia in esperados)
    no_prazo = all(
        _gravacao_no_prazo(linha) for linha in linhas if linha["tipo"] == GRAVACAO
    )
    return [
        Criterio(
            "P1", sharpe, f"> 0 e ≥ {minimo:.3f}", bool(sharpe > 0 and sharpe >= minimo)
        ),
        Criterio("P2", queda, f"≥ {pior_aceita:.3f}", queda >= pior_aceita),
        Criterio(
            "P3",
            faltas,
            f"no prazo, sem regravar e ≤ {MAXIMO_DE_FALTAS} faltas",
            no_prazo and faltas <= MAXIMO_DE_FALTAS,
        ),
    ]
