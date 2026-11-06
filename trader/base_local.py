"""Leitura da base local para a pesquisa: o dado é servido como está ou recusado, nunca adivinhado.

Duas regras, emprestadas da "camada de dados" do Vibe-Trading e endurecidas:

- **Servida ou recusada** (`ler_serie`): símbolo que não está na base, período pedido fora da série,
  lacuna maior que `LACUNA_MAXIMA_DIARIA` ou preço vazio levantam `DadoAusenteError` com o nome do que
  faltou. Nada de `ffill` nem de zero no lugar do que falta: quem quiser preencher decide fora daqui,
  declara no pré-registro e conta como escolha da tentativa.
- **Balanço só depois de público** (`balanco_na_vespera`): o valor de uma conta que uma decisão no dia
  D pode usar é o que estava público na **véspera** (D - 1), pela `divulgado_em` da base "como era na
  data" (`base/ponto_no_tempo.py`, que já trata a reapresentação e a exceção do registro na CVM). A CVM
  dá só o dia da entrega, não a hora: quem decide no próprio dia não pode contar com ela.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from base.ponto_no_tempo import como_era_em
from trader.dados import LACUNA_MAXIMA_DIARIA, PRECOS, carregar

UM_DIA = pd.Timedelta(days=1)
DIAS_POR_MES = 30.4375  # 365,25 / 12: para reconhecer o tamanho do período de um fato
# trimestre de 90 a 92 dias, semestre de 181 a 184, ano de 365 ou 366: folga bem menor que os ~91
# dias entre um tamanho e o seguinte
TOLERANCIA_DO_PERIODO_EM_DIAS = 10


class DadoAusenteError(ValueError):
    """O dado pedido não está na base (ou não estava público na data): a leitura recusa."""


def _data(valor: object) -> pd.Timestamp:
    return pd.Timestamp(valor)  # type: ignore[arg-type]


def _conferir_periodo(
    candles: pd.DataFrame, simbolo: str, inicio: pd.Timestamp, fim: pd.Timestamp
) -> None:
    primeiro, ultimo = candles.index[0], candles.index[-1]
    # um feriado na ponta (pedir 1º de janeiro) é normal; mais do que a lacuna máxima, não
    if primeiro - inicio > LACUNA_MAXIMA_DIARIA:
        raise DadoAusenteError(
            f"{simbolo}: pedido desde {inicio:%Y-%m-%d}, mas a série começa em {primeiro:%Y-%m-%d}."
        )
    if fim - ultimo > LACUNA_MAXIMA_DIARIA:
        raise DadoAusenteError(
            f"{simbolo}: pedido até {fim:%Y-%m-%d}, mas a série termina em {ultimo:%Y-%m-%d}."
        )


def _conferir_trecho(trecho: pd.DataFrame, simbolo: str) -> None:
    passos = trecho.index.to_series().diff()
    grandes = passos[passos > LACUNA_MAXIMA_DIARIA]
    if not grandes.empty:
        depois = grandes.index[0]
        antes = trecho.index[trecho.index.get_loc(depois) - 1]
        raise DadoAusenteError(
            f"{simbolo}: lacuna de {grandes.iloc[0].days} dias entre {antes:%Y-%m-%d} e "
            f"{depois:%Y-%m-%d} (limite: {LACUNA_MAXIMA_DIARIA.days} dias)."
        )
    vazios = trecho[PRECOS].isna().any(axis=1)
    if vazios.any():
        raise DadoAusenteError(
            f"{simbolo}: preço vazio em {int(vazios.sum())} dia(s), o primeiro em "
            f"{trecho.index[vazios.argmax()]:%Y-%m-%d}."
        )


def ler_serie(pasta: Path, simbolo: str, inicio: object, fim: object) -> pd.DataFrame:
    """Os candles diários (D1) de `simbolo` entre `inicio` e `fim`, inclusive, sem mudar nada.

    Levanta `DadoAusenteError` se o símbolo não estiver em `pasta`, se o período pedido sair da série,
    se houver lacuna maior que `LACUNA_MAXIMA_DIARIA` ou preço vazio no trecho.
    """
    inicio, fim = _data(inicio), _data(fim)
    if inicio > fim:
        raise ValueError(
            f"O início ({inicio:%Y-%m-%d}) vem depois do fim ({fim:%Y-%m-%d})."
        )
    candles = carregar(simbolo, "D1", pasta)
    if candles is None or candles.empty:
        raise DadoAusenteError(f"{simbolo}: não está na base local ({pasta}).")
    candles = candles.sort_index()
    _conferir_periodo(candles, simbolo, inicio, fim)
    trecho = candles.loc[inicio:fim]
    if trecho.empty:
        raise DadoAusenteError(
            f"{simbolo}: nenhum pregão entre {inicio:%Y-%m-%d} e {fim:%Y-%m-%d}."
        )
    _conferir_trecho(trecho, simbolo)
    return trecho.copy()


def _da_duracao(fatos: pd.DataFrame, meses: int) -> pd.Series:
    """Fatos cujo período tem `meses` meses; fatos de saldo (balanço, sem início) sempre servem."""
    dias = (fatos["fim"] - fatos["inicio"]).dt.days + 1
    esperado = meses * DIAS_POR_MES
    return fatos["inicio"].isna() | (
        (dias - esperado).abs() <= TOLERANCIA_DO_PERIODO_EM_DIAS
    )


def _valor_do_periodo_mais_recente(
    foto: pd.DataFrame, conta: str, dia: pd.Timestamp
) -> float:
    if foto.empty:
        return float("nan")
    mais_recente = foto[foto["fim"] == foto["fim"].max()]
    if len(mais_recente) > 1:
        raise ValueError(
            f"Conta {conta}: {len(mais_recente)} períodos terminando em "
            f"{mais_recente['fim'].iloc[0]:%Y-%m-%d} na decisão de {dia:%Y-%m-%d} "
            "(trimestre e acumulado?): declare `meses`."
        )
    # valor apagado na última publicação fica vazio; não se volta para um período mais antigo
    return float(mais_recente["valor"].iloc[0])


def balanco_na_vespera(
    base: pd.DataFrame,
    datas: pd.DatetimeIndex,
    cnpj: str,
    conta: str,
    grupo: str = "con",
    meses: int | None = None,
    aceitar_vazio: bool = False,
) -> pd.Series:
    """O valor de `conta` que uma decisão em cada uma das `datas` podia usar: o do período mais recente
    já público na véspera, segundo a base "como era na data" (`base/ponto_no_tempo.py`).

    `meses` escolhe o tamanho do período (3 = trimestre, 12 = ano) quando a mesma data de fim tem mais
    de um (o ITR traz o trimestre e o acumulado). Sem valor público na véspera, levanta
    `DadoAusenteError`; com `aceitar_vazio=True` (declarado por quem chama) devolve vazio (NaN).
    """
    da_conta = base[
        (base["cnpj"] == cnpj) & (base["conta"] == conta) & (base["grupo"] == grupo)
    ]
    if meses is not None:
        da_conta = da_conta[_da_duracao(da_conta, meses)]
    valores = []
    for data in datas:
        dia = _data(data)
        valor = _valor_do_periodo_mais_recente(
            como_era_em(da_conta, dia - UM_DIA), conta, dia
        )
        if pd.isna(valor) and not aceitar_vazio:
            raise DadoAusenteError(
                f"{cnpj} conta {conta}: nada público na véspera da decisão de {dia:%Y-%m-%d}."
            )
        valores.append(valor)
    return pd.Series(valores, index=pd.DatetimeIndex(datas), name=conta, dtype=float)
