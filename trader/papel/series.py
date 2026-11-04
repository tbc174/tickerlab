"""As séries do papel (lista fixa da seção 5) e a foto de cada dia, feita pelo simulador registrado.

Nada aqui reescreve uma regra: cada série chama o `simular` do próprio módulo, com os parâmetros da
ficha, sobre os dados até o fechamento da véspera. A foto do dia é o sinal que vale no pregão
seguinte e a carteira simulada no fechamento, em tipos simples (vai para o JSON da cadeia).

**Aquecimento e o início do papel.** Os sinais precisam de um ano de preços (252 pregões na P0-3,
365 dias na P0-1, 360 pregões no DI1). Cada série corta os dados para começar exatamente esse
aquecimento antes do primeiro fechamento do papel (a véspera do início): assim o simulador fica 100%
em caixa até lá, e a primeira posição só pode nascer no início do papel. `_sem_posicao_ate` confere
isso em toda foto. Nenhum retorno da estratégia antes do início é calculado, gravado ou mostrado.

**O sinal da P0-3.** A carteira multiativo só decide no último pregão do mês, e o `simular` só
decide quando há o pregão seguinte nos dados (`t + 1 < n`). A foto acrescenta o pregão em que o sinal
vale como uma linha fantasma (preço e CDI repetidos da véspera): o alvo decidido no fechamento só
depende dos retornos até ele, então a linha fantasma não muda o alvo, só deixa a decisão aparecer.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from trader import criterio_quant
from trader.calendario import proxima_execucao
from trader.estrategias import carteira_rp as rp
from trader.estrategias import tendencia_b3 as tb
from trader.estrategias import tendencia_cripto as tc
from trader.estrategias import tendencia_cripto_brl as brl
from trader.registro import hash_da_especificacao

CAPITAL_DO_PAPEL = 100_000.0  # o capital inicial das fichas, no primeiro fechamento


class AntesDoInicioError(RuntimeError):
    """A simulação teria posição antes do início do papel (aquecimento cortado errado)."""


@dataclass(frozen=True)
class Tabelas:
    """Preços, CDI e volumes de uma série (P0-3: volumes por ativo; cripto: por dia e ativo)."""

    precos: pd.DataFrame
    cdi: pd.Series
    volumes: pd.Series | pd.DataFrame
    # o que ainda não saiu no fechamento e repete o último valor
    estimados: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntradasDoDI1:
    ativo: tb.Ativo
    cdi: pd.Series
    estimados: tuple[str, ...] = ()


@dataclass(frozen=True)
class Serie:
    """Uma série da lista fixa do papel e as referências do desenvolvimento para o julgamento."""

    nome: str
    titulo: str
    mercado: str
    registro: int  # a tentativa no registro da pesquisa quant
    # Sharpe do excesso no desenvolvimento (tabela da seção 5)
    sharpe_de_referencia: float
    # maior queda do pico no desenvolvimento (F1), negativa
    queda_do_desenvolvimento: float
    fotografar: Callable[[Any, date, date], dict] = field(repr=False)
    sharpe_do_excesso: Callable[[pd.Series, pd.Series], float] = field(repr=False)


# --- ajudantes comuns ----------------------------------------------------------------------------


def _ts(dia: date) -> pd.Timestamp:
    return pd.Timestamp(dia)


def _hash_dos_dados(*tabelas: pd.Series | pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for tabela in tabelas:
        digest.update(
            pd.util.hash_pandas_object(tabela, index=True).to_numpy().tobytes()
        )
    return digest.hexdigest()


def _numeros(valores: pd.Series) -> dict[str, float]:
    return {str(k): float(v) for k, v in valores.items()}


def _conferir_fechamento(datas: pd.DatetimeIndex, fechamento: date) -> None:
    if _ts(fechamento) not in datas:
        raise ValueError(f"os dados não têm o fechamento de {fechamento}")


def _sem_posicao_ate(exposicao: pd.Series | pd.DataFrame, ultimo: date) -> None:
    """Até o primeiro fechamento do papel a simulação só pode estar em caixa."""
    antes = np.abs(exposicao.loc[: _ts(ultimo)].to_numpy(float)).reshape(
        -1, 1 if exposicao.ndim == 1 else exposicao.shape[1]
    )
    com_posicao = antes.max(axis=1) > 0
    if com_posicao.any():
        dia = exposicao.index[int(np.argmax(com_posicao))]
        raise AntesDoInicioError(
            f"a simulação tem posição em {dia.date()}, antes do início do papel "
            f"(primeiro fechamento {ultimo})"
        )


def _caixa_parado_ate(cdi: pd.Series, primeiro: date) -> pd.Series:
    """O CDI que a simulação usa: zero até o primeiro fechamento, inclusive.

    O aquecimento cai no período do holdout. Sem posição e sem rendimento do caixa, a simulação
    chega ao primeiro fechamento com o capital inicial intacto: nenhum retorno daquele trecho sai
    dela, nem pelo tamanho das ordens. O CDI de verdade continua no hash e no `cdi_do_dia`.
    """
    return cdi.where(cdi.index > _ts(primeiro), 0.0)


def _patrimonio_no_papel(
    patrimonio: pd.Series, fechamento: date, primeiro: date
) -> float:
    """O patrimônio contado a partir do primeiro fechamento, que vale o capital inicial.

    A simulação começa no aquecimento, que cai no período do holdout. Até o primeiro fechamento ela
    fica em caixa (`_sem_posicao_ate`). Mesmo assim, o que ela acumulou ali não entra na foto: cada
    linha gravada só reflete retornos de depois do início do papel.
    """
    if _ts(primeiro) not in patrimonio.index:
        raise AntesDoInicioError(
            f"a simulação não tem o primeiro fechamento do papel ({primeiro})"
        )
    relativo = patrimonio.loc[_ts(fechamento)] / patrimonio.loc[_ts(primeiro)]
    return float(CAPITAL_DO_PAPEL * relativo)


def _regra(registro: int, versao: str, parametros: dict) -> dict:
    return {
        "registro": registro,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": versao,
        "parametros": hash_da_especificacao(parametros),
    }


def _foto(
    fechamento: date,
    sinal: dict,
    patrimonio: float,
    exposicao: dict[str, float],
    cdi_do_dia: float,
    regra: dict,
    desde: pd.Timestamp,
    hash_dos_dados: str,
    estimados: tuple[str, ...],
) -> dict:
    return {
        "fechamento": fechamento.isoformat(),
        "sinal": sinal,
        "carteira": {"patrimonio": float(patrimonio), "exposicao": exposicao},
        "cdi_do_dia": float(cdi_do_dia),
        "regra": regra,
        "dados": {
            "desde": desde.date().isoformat(),
            "hash": hash_dos_dados,
            "estimados": sorted(estimados),
        },
    }


def _desde_por_linhas(
    datas: pd.DatetimeIndex, primeiro: date, linhas: int
) -> pd.Timestamp:
    """A data `linhas` posições antes do primeiro fechamento do papel (o aquecimento em pregões)."""
    _conferir_fechamento(datas, primeiro)
    posicao = int(datas.get_loc(_ts(primeiro))) - linhas
    if posicao < 0:
        raise ValueError(
            f"faltam {-posicao} pregões de aquecimento antes de {primeiro}"
        )
    return datas[posicao]


# --- P0-3: carteira multiativo, risk parity a 1,0x (registro 5) ----------------------------------

PARAMETROS_DA_P0_3 = rp.Parametros()


def fotografar_p0_3(tabelas: Tabelas, fechamento: date, primeiro: date) -> dict:
    precos = tabelas.precos
    desde = _desde_por_linhas(
        pd.DatetimeIndex(precos.index), primeiro, PARAMETROS_DA_P0_3.janela
    )
    precos = precos.loc[desde : _ts(fechamento)]
    _conferir_fechamento(pd.DatetimeIndex(precos.index), fechamento)
    cdi = tabelas.cdi.reindex(precos.index)
    volumes = tabelas.volumes
    caixa = _caixa_parado_ate(cdi, primeiro)
    resultado = rp.simular(precos, caixa, volumes, PARAMETROS_DA_P0_3)  # type: ignore[arg-type]
    _sem_posicao_ate(resultado.pesos, primeiro)
    return _foto(
        fechamento,
        _sinal_da_p0_3(precos, caixa, volumes, fechamento),  # type: ignore[arg-type]
        _patrimonio_no_papel(resultado.patrimonio, fechamento, primeiro),
        _numeros(resultado.pesos.loc[_ts(fechamento)]),
        cdi.loc[_ts(fechamento)],
        _regra(5, rp.VERSAO, PARAMETROS_DA_P0_3.especificacao()),
        desde,
        _hash_dos_dados(precos, cdi),
        tabelas.estimados,
    )


def _sinal_da_p0_3(
    precos: pd.DataFrame, cdi: pd.Series, volumes: pd.Series, fechamento: date
) -> dict:
    """O alvo decidido no fechamento (só no último pregão do mês); senão, a carteira segue."""
    fantasma = _ts(proxima_execucao(fechamento, "b3"))
    precos = pd.concat([precos, precos.iloc[[-1]].set_axis([fantasma])])
    cdi = pd.concat([cdi, cdi.iloc[[-1]].set_axis([fantasma])])
    alvos = rp.simular(precos, cdi, volumes, PARAMETROS_DA_P0_3).alvos
    if _ts(fechamento) not in alvos.index:
        return {"decisao": False, "alvo": None}
    return {"decisao": True, "alvo": _numeros(alvos.loc[_ts(fechamento)])}


# --- P0-1 (USDT × PTAX, registro 11) e P0-1b (par em reais, registro 18): tendência em cripto ----


def fotografar_p0_1(tabelas: Tabelas, fechamento: date, primeiro: date) -> dict:
    return _fotografar_cripto(
        tabelas, fechamento, primeiro, tc.simular, tc.PARAMETROS_DA_FICHA, 11, tc.VERSAO
    )


def fotografar_p0_1b(tabelas: Tabelas, fechamento: date, primeiro: date) -> dict:
    """A regra da P0-1 no BTCBRL e no ETHBRL, com a banda de 20% e o spread do livro."""
    return _fotografar_cripto(
        tabelas,
        fechamento,
        primeiro,
        brl.simular,
        brl.PARAMETROS_DA_FICHA,
        18,
        brl.VERSAO,
    )


def _fotografar_cripto(
    tabelas: Tabelas,
    fechamento: date,
    primeiro: date,
    simular: Callable[..., tc.Resultado],
    parametros: tc.Parametros,
    registro: int,
    versao: str,
) -> dict:
    desde = _ts(primeiro) - pd.Timedelta(days=tc.AQUECIMENTO_EM_DIAS)
    precos = tabelas.precos.loc[desde : _ts(fechamento)]
    if len(precos) == 0 or precos.index[0] != desde:
        raise ValueError(f"os preços de cripto precisam começar em {desde.date()}")
    _conferir_fechamento(pd.DatetimeIndex(precos.index), fechamento)
    cdi = tabelas.cdi.reindex(precos.index)
    volumes = tabelas.volumes.loc[precos.index]
    resultado = simular(precos, _caixa_parado_ate(cdi, primeiro), volumes, parametros)
    _sem_posicao_ate(resultado.exposicao, primeiro)
    alvo = tc.fracoes_alvo(precos, parametros).loc[_ts(fechamento)]
    return _foto(
        fechamento,
        {"alvo": _numeros(alvo)},
        _patrimonio_no_papel(resultado.patrimonio, fechamento, primeiro),
        _numeros(resultado.exposicao.loc[_ts(fechamento)]),
        cdi.loc[_ts(fechamento)],
        _regra(registro, versao, parametros.especificacao()),
        desde,
        _hash_dos_dados(precos, cdi),
        tabelas.estimados,
    )


# --- DI1: tendência nos juros, a versão de comparação da P0-2 (registro 12) ----------------------


def _ativo_desde(ativo: tb.Ativo, desde: pd.Timestamp) -> tb.Ativo:
    return replace(
        ativo,
        abertura=ativo.abertura.loc[desde:],
        fechamento=ativo.fechamento.loc[desde:],
        excesso=ativo.excesso.loc[desde:],
        volume=ativo.volume.loc[desde:],
        rolagens=tuple(d for d in ativo.rolagens if d >= desde),
    )


def fotografar_di1(entradas: EntradasDoDI1, fechamento: date, primeiro: date) -> dict:
    datas = pd.DatetimeIndex(entradas.ativo.excesso.dropna().index)
    desde = _desde_por_linhas(datas, primeiro, tb.AQUECIMENTO_EM_PREGOES)
    ativo = _ativo_desde(entradas.ativo, desde).ate(_ts(fechamento))
    _conferir_fechamento(ativo.datas, fechamento)
    cdi = entradas.cdi.reindex(ativo.datas)
    parametros = tb.PARAMETROS_DA_FICHA
    resultado = tb.simular(ativo, _caixa_parado_ate(cdi, primeiro), parametros)
    _sem_posicao_ate(resultado.exposicao, primeiro)
    alvo = tb.fracao_alvo(ativo, parametros).loc[_ts(fechamento)]
    return _foto(
        fechamento,
        {"alvo": {"DI1": float(alvo)}},
        _patrimonio_no_papel(resultado.patrimonio, fechamento, primeiro),
        {"DI1": float(resultado.exposicao.loc[_ts(fechamento)])},
        cdi.loc[_ts(fechamento)],
        _regra(12, tb.VERSAO, parametros.especificacao()),
        desde,
        _hash_dos_dados(ativo.excesso, ativo.fechamento, cdi),
        entradas.estimados,
    )


# --- a lista fixa (seção 5) ----------------------------------------------------------------------

# Referências do desenvolvimento: Sharpe do excesso da tabela da seção 5 e a maior queda (F1) dos
# relatórios docs/resultado-carteira-p0-3-tentativa-3.md, resultado-tendencia-cripto-p0-1.md e
# resultado-tendencia-b3-p0-2.md; os da P0-1b são os da 1ª tentativa (resultado-p0-1b-tentativa-1.md,
# reprovada: o papel grava a série mesmo assim). A C-1 (candidata e comparação) fica fora desta versão
# do papel (decisão do Tiago em 04/11/2026): os pesos dela pedem 252 pregões de retorno de cada camada,
# que no início estão no holdout, e quatro camadas da candidata não têm dado diário. Ela volta numa
# v0.3, com regra de aquecimento própria.
SERIES: tuple[Serie, ...] = (
    Serie(
        nome="p0_3",
        titulo="carteira multiativo (P0-3, risk parity a 1,0x)",
        mercado="b3",
        registro=5,
        sharpe_de_referencia=0.41,
        queda_do_desenvolvimento=-0.113,
        fotografar=fotografar_p0_3,
        sharpe_do_excesso=tb.sharpe_do_excesso,
    ),
    Serie(
        nome="p0_1",
        titulo="tendência em cripto (P0-1, USDT × PTAX)",
        mercado="cripto",
        registro=11,
        sharpe_de_referencia=0.68,
        queda_do_desenvolvimento=-0.106,
        fotografar=fotografar_p0_1,
        sharpe_do_excesso=tc.sharpe_do_excesso,
    ),
    Serie(
        nome="di1",
        titulo="tendência no DI1 (comparação da P0-2)",
        mercado="b3",
        registro=12,
        sharpe_de_referencia=0.44,
        queda_do_desenvolvimento=-0.029,
        fotografar=fotografar_di1,
        sharpe_do_excesso=tb.sharpe_do_excesso,
    ),
    Serie(
        nome="p0_1b",
        titulo="tendência em cripto no par em reais (P0-1b)",
        mercado="cripto",
        registro=18,
        sharpe_de_referencia=-1.16,
        queda_do_desenvolvimento=-0.079,
        fotografar=fotografar_p0_1b,
        sharpe_do_excesso=tc.sharpe_do_excesso,
    ),
)


def serie(nome: str) -> Serie:
    for candidata in SERIES:
        if candidata.nome == nome:
            return candidata
    raise KeyError(
        f"série desconhecida: {nome!r}; use uma de {[s.nome for s in SERIES]}"
    )
