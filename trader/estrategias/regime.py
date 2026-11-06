"""Filtro de regime da ficha P0-8: liga ou desliga uma estratégia por variáveis observáveis.

A ficha (`docs/pre-registro-quant-p0-v0.1.md`, seção 9) fixa os cortes; as convenções abaixo foram
fixadas antes de qualquer número (04/11/2026), sem estratégia aprovada para testar:

- **Estado do dia D:** calculado só com dados até o fechamento de D. Ele entra em vigor no fechamento de
  D+1 (seção 4: sinal em D, execução em D+1), então o retorno de D+2 é o primeiro que ele afeta.
- **Média de 200 dias:** liga com o preço acima da média simples dos últimos 200 pregões (o regime "Alta"
  de `src/regimes.py`).
- **Volatilidade:** desvio dos retornos simples de 21 pregões; liga quando ela não passa do percentil 90% da
  própria história até D (o regime "Calmo" de `src/regimes.py`, que pede 60 dias de história).
- **Queda do ativo:** liga com o preço acima de −20% do maior preço visto até D.
- **Selic pelo Focus (opcional):** a série é a mudança esperada da meta nas próximas reuniões, em pontos
  percentuais, na data de publicação do Focus; liga sem ciclo de alta (mudança esperada ≤ 0). O sentido
  "alta desliga" é a leitura desta implementação: a ficha diz só "ciclo da Selic".
- **Funding e open interest (cripto, opcionais):** liga com o funding anualizado e a variação de 7 dias do
  open interest entre os percentis 10% e 90% da própria história até D (no mínimo 252 valores).
- **Sem história suficiente, a condição não desliga:** no aquecimento o filtro é neutro e a estratégia
  roda como sem ele, o que deixa a comparação "com e sem" justa.
- **Desligada, a estratégia vai para o CDI**, e cada troca de estado paga o custo de uma ida ao mercado.

A ficha só deixa o filtro entrar se ele melhorar o DSR sem piorar o PBO nem a queda máxima
(`filtro_entra`). Nada aqui é recomendação de investimento.
"""

from __future__ import annotations

import pandas as pd

from src import regimes

DIAS_DA_MEDIA = 200
DIAS_DA_VOL = 21
PERCENTIL_MAXIMO_DA_VOL = 0.90
QUEDA_MAXIMA_DO_ATIVO = -0.20
HISTORICO_MINIMO_DO_PERCENTIL = 252
PERCENTIS_DOS_EXTREMOS = (0.10, 0.90)
DIAS_DA_VARIACAO_DO_OI = 7
DIAS_DE_ATRASO = 1  # seção 4: execução em D+1
CONDICOES_DE_PRECO = ("media_200", "vol_21", "queda")


def _neutra_onde_falta(condicao: pd.Series, faltando: pd.Series) -> pd.Series:
    """Condição booleana com vazio (`pd.NA`) onde ainda não há história."""
    return condicao.astype("boolean").mask(faltando)


def _do_regime(rotulos: pd.Series, liga: str) -> pd.Series:
    return _neutra_onde_falta(rotulos == liga, rotulos == regimes.SEM_HISTORICO)


def acima_da_media(precos: pd.Series) -> pd.Series:
    return _do_regime(
        regimes.classificar_regimes_de_tendencia(precos, DIAS_DA_MEDIA), "Alta"
    )


def percentil_na_historia(serie: pd.Series) -> pd.Series:
    """Percentil de cada valor contra os valores até ele (inclusive), sem olhar o futuro."""
    return serie.expanding(min_periods=HISTORICO_MINIMO_DO_PERCENTIL).rank(pct=True)


def vol_fora_do_topo(precos: pd.Series) -> pd.Series:
    rotulos = regimes.classificar_regimes_de_volatilidade(
        precos, janela=DIAS_DA_VOL, percentil=PERCENTIL_MAXIMO_DA_VOL
    )
    return _do_regime(rotulos, "Calmo")


def queda_acima_do_limite(precos: pd.Series) -> pd.Series:
    queda = precos / precos.cummax() - 1
    return _neutra_onde_falta(queda > QUEDA_MAXIMA_DO_ATIVO, queda.isna())


def sem_ciclo_de_alta(mudanca_esperada_da_selic: pd.Series) -> pd.Series:
    serie = mudanca_esperada_da_selic
    return _neutra_onde_falta(serie <= 0, serie.isna())


def fora_dos_extremos(serie: pd.Series) -> pd.Series:
    percentil = percentil_na_historia(serie.dropna()).reindex(serie.index)
    baixo, alto = PERCENTIS_DOS_EXTREMOS
    dentro = (percentil >= baixo) & (percentil <= alto)
    return _neutra_onde_falta(dentro, percentil.isna())


def _no_calendario(condicao: pd.Series, calendario: pd.DatetimeIndex) -> pd.Series:
    """Leva uma condição de outro calendário (o Focus é semanal) ao do ativo: vale a última até o dia."""
    todos = calendario.union(pd.DatetimeIndex(condicao.index))
    return condicao.reindex(todos).ffill().reindex(calendario).astype("boolean")


def estado(
    precos: pd.Series,
    selic: pd.Series | None = None,
    funding: pd.Series | None = None,
    open_interest: pd.Series | None = None,
) -> pd.DataFrame:
    """Cada condição e o estado do dia D (`ligado`), só com dados até D.

    `selic` é a mudança esperada da meta pelo Focus; `funding`, o funding anualizado; `open_interest`, o
    nível (a variação de 7 dias é feita aqui). Entrada ausente não entra no filtro.
    """
    precos = precos.sort_index()
    calendario = pd.DatetimeIndex(precos.index)
    condicoes = {
        "media_200": acima_da_media(precos),
        "vol_21": vol_fora_do_topo(precos),
        "queda": queda_acima_do_limite(precos),
    }
    if selic is not None:
        condicoes["selic"] = _no_calendario(
            sem_ciclo_de_alta(selic.sort_index()), calendario
        )
    if funding is not None:
        condicoes["funding"] = _no_calendario(
            fora_dos_extremos(funding.sort_index()), calendario
        )
    if open_interest is not None:
        variacao = open_interest.sort_index().pct_change(DIAS_DA_VARIACAO_DO_OI)
        condicoes["open_interest"] = _no_calendario(
            fora_dos_extremos(variacao), calendario
        )
    tabela = pd.DataFrame(condicoes, index=calendario)
    tabela["ligado"] = tabela.fillna(True).all(axis=1)
    return tabela


def aplicar(
    retorno: pd.Series,
    cdi: pd.Series,
    ligado: pd.Series,
    custo_por_troca: float = 0.0,
) -> pd.Series:
    """Retorno diário com o filtro: o da estratégia quando ligada, o CDI quando desligada.

    O estado de D vale no fechamento de D+1, então o retorno de D+2 é o primeiro que ele decide. A
    troca paga `custo_por_troca` (fração do patrimônio) no dia da execução. Antes do primeiro estado a
    estratégia fica ligada (o filtro é neutro).
    """
    em_vigor = (
        ligado.reindex(retorno.index).shift(DIAS_DE_ATRASO).fillna(True).astype(bool)
    )
    decide_o_retorno = em_vigor.shift(1, fill_value=True)
    trocou = em_vigor != em_vigor.shift(1, fill_value=True)
    cdi = cdi.reindex(retorno.index).fillna(0.0)
    com_filtro = retorno.where(decide_o_retorno, cdi)
    return com_filtro - trocou.astype(float) * custo_por_troca


def filtro_entra(
    dsr_sem: float,
    dsr_com: float,
    queda_sem: float,
    queda_com: float,
    pbo_sem: float | None = None,
    pbo_com: float | None = None,
) -> bool:
    """A regra da ficha: o DSR melhora e nem o PBO nem a queda máxima pioram (quedas negativas)."""
    if dsr_com <= dsr_sem or queda_com < queda_sem:
        return False
    if pbo_sem is None or pbo_com is None:
        return True
    return pbo_com <= pbo_sem
