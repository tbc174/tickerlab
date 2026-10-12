"""Da previsão de cada mercado ao retorno diário da carteira, com custos (pré-registro, seções 4 e 6).

Passos, sempre com o que se sabia no fechamento do dia (a posição decidida em t rende em t+1):
1. volatilidade anual de cada mercado (35 dias misturada com a média de 10 anos, como na M2);
2. peso de risco de cada mercado: peso do grupo ÷ mercados disponíveis no grupo (disponível = com
   1 ano de dados e previsão); grupo sem nenhum mercado tem o peso repartido entre os outros;
3. IDM (multiplicador de diversificação entre mercados), recalculado no começo de cada ano só com os
   anos anteriores, limitado a 2,5;
4. posição = previsão ÷ 10 × volatilidade alvo × peso × IDM ÷ volatilidade do mercado, com buffer
   de 10% da posição de previsão cheia (10);
5. retorno = posição de ontem × retorno total de hoje − custo de negociação − margem de manter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from trader.p2.mercados import Mercado
from trader.p2.preregistro import PESOS_DOS_GRUPOS, VOLATILIDADE_ALVO
from trader.posicao import aplicar_buffer, volatilidade_mista

PREVISAO_MEDIA = 10.0
DIAS_DO_ANO = 365
DIAS_UTEIS_DO_ANO = 256
DIAS_MINIMOS_DE_DADOS = 256  # 1 ano de cotações antes de o mercado entrar na carteira
IDM_MAXIMO = 2.5
LARGURA_DO_BUFFER = 0.10

# Custo de negociação por lado (fração do valor negociado), seção 4.
CUSTO_POR_LADO = {
    "moedas": 0.0001,
    "indices": 0.0002,
    "metais": 0.0003,
    "energia": 0.0003,
    "titulos": 0.0002,
}
CUSTO_MOEDAS_EMERGENTES = 0.0003
MOEDAS_EMERGENTES = {"MXN", "BRL"}
# Margem de manter (fração ao ano sobre o valor da posição, comprada ou vendida), decisão 0013.
MARGEM_DE_MANTER = {
    "moedas": 0.01,
    "indices": 0.025,
    "metais": 0.025,
    "energia": 0.025,
    "titulos": 0.025,
}


@dataclass(frozen=True)
class Custos:
    """Custos de uma simulação; os estresses do pré-registro são variações deste."""

    multiplicador_de_negociacao: float = 1.0
    margem_por_grupo: dict[str, float] = field(
        default_factory=lambda: dict(MARGEM_DE_MANTER)
    )

    def por_lado(self, mercado: Mercado) -> float:
        base = CUSTO_POR_LADO[mercado.grupo]
        if mercado.grupo == "moedas" and mercado.codigo[3:] in MOEDAS_EMERGENTES:
            base = CUSTO_MOEDAS_EMERGENTES
        return base * self.multiplicador_de_negociacao

    def margem(self, mercado: Mercado) -> float:
        return self.margem_por_grupo[mercado.grupo]


CUSTOS_BASE = Custos()
ESTRESSE_A = Custos(multiplicador_de_negociacao=2.0)  # negociação × 2
ESTRESSE_B = Custos(
    margem_por_grupo=dict.fromkeys(MARGEM_DE_MANTER, 0.025)
)  # tabela da Admirals


@dataclass(frozen=True)
class Resultado:
    retorno: pd.Series  # retorno diário líquido da carteira
    contribuicao: pd.DataFrame  # retorno líquido de cada mercado (já pesado), por dia
    posicao: pd.DataFrame  # posição decidida no fechamento de cada dia
    idm: pd.Series


def calendario(tabelas: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Todos os dias úteis em que algum mercado teve cotação."""
    datas = pd.DatetimeIndex(sorted(set().union(*(t.index for t in tabelas.values()))))
    return datas[datas.weekday < 5]


def disponibilidade(
    tabelas: dict[str, pd.DataFrame],
    previsoes: dict[str, pd.Series],
    datas: pd.DatetimeIndex,
) -> pd.DataFrame:
    """True onde o mercado já tem 1 ano de cotações e uma previsão válida (só o passado)."""
    colunas = {}
    for codigo, tabela in tabelas.items():
        contagem = (
            pd.Series(1, index=tabela.index).cumsum().reindex(datas).ffill().fillna(0)
        )
        tem_previsao = previsoes[codigo].reindex(datas).ffill().notna()
        colunas[codigo] = (contagem >= DIAS_MINIMOS_DE_DADOS) & tem_previsao
    return pd.DataFrame(colunas, index=datas)


def pesos_de_risco(
    mercados: dict[str, Mercado], disponivel: pd.DataFrame
) -> pd.DataFrame:
    """Peso do grupo dividido entre os disponíveis do grupo; grupos vazios repartidos entre os outros."""
    grupos = pd.Series({c: mercados[c].grupo for c in disponivel.columns})
    pesos = pd.DataFrame(0.0, index=disponivel.index, columns=disponivel.columns)
    total_dos_grupos = pd.Series(0.0, index=disponivel.index)
    for grupo, peso in PESOS_DOS_GRUPOS.items():
        membros = grupos.index[grupos == grupo]
        if len(membros) == 0:
            continue
        quantos = disponivel[membros].sum(axis=1)
        com_alguem = quantos > 0
        pesos.loc[:, membros] = disponivel[membros].mul(
            np.where(com_alguem, peso / quantos.replace(0, 1), 0.0), axis=0
        )
        total_dos_grupos += np.where(com_alguem, peso, 0.0)
    return pesos.div(total_dos_grupos.where(total_dos_grupos > 0), axis=0).fillna(0.0)


def idm_anual(retornos: pd.DataFrame, pesos: pd.DataFrame) -> pd.Series:
    """IDM de cada dia, calculado no 1º dia útil de cada ano com os retornos semanais até o ano anterior."""
    semanais = retornos.fillna(0.0).resample("W-FRI").sum()
    idm = pd.Series(1.0, index=retornos.index)
    for ano in sorted(set(retornos.index.year)):
        passado = semanais[semanais.index.year < ano]
        dias_do_ano = retornos.index.year == ano
        w = pesos.loc[dias_do_ano].iloc[0]
        ativos = w[w > 0].index
        if len(passado) < 52 or len(ativos) < 2:
            continue
        correlacao = passado[ativos].corr().clip(lower=0).fillna(0).to_numpy(copy=True)
        np.fill_diagonal(correlacao, 1.0)
        pesos_ativos = w[ativos].to_numpy()
        variancia = float(pesos_ativos @ correlacao @ pesos_ativos)
        idm.loc[dias_do_ano] = (
            min(IDM_MAXIMO, 1 / np.sqrt(variancia)) if variancia > 0 else 1.0
        )
    return idm


def simular(
    mercados: dict[str, Mercado],
    tabelas: dict[str, pd.DataFrame],
    previsoes: dict[str, pd.Series],
    custos: Custos = CUSTOS_BASE,
) -> Resultado:
    """Carteira inteira. `tabelas` de `retornos.montar` e `previsoes` de `regras.previsao`, por código."""
    datas = calendario(tabelas)
    retorno_total = pd.DataFrame({c: t["total"] for c, t in tabelas.items()}).reindex(
        datas
    )
    disponivel = disponibilidade(tabelas, previsoes, datas)
    pesos = pesos_de_risco(mercados, disponivel)
    idm = idm_anual(retorno_total, pesos)
    dias = np.diff(datas.to_numpy()).astype("timedelta64[D]").astype(float)
    dias = pd.Series(np.concatenate([[1.0], dias]), index=datas)

    posicoes, contribuicoes = {}, {}
    for codigo, mercado in mercados.items():
        vol = (
            volatilidade_mista(tabelas[codigo]["preco"], dias_por_ano=DIAS_UTEIS_DO_ANO)
            .reindex(datas)
            .ffill()
        )
        escala = (VOLATILIDADE_ALVO * pesos[codigo] * idm / vol.where(vol > 0)).fillna(
            0.0
        )
        previsao = previsoes[codigo].reindex(datas).ffill().fillna(0.0)
        ideal = previsao / PREVISAO_MEDIA * escala
        posicao = aplicar_buffer(ideal, escala, LARGURA_DO_BUFFER)
        ontem = posicao.shift(1).fillna(0.0)
        giro = posicao.diff().abs().fillna(posicao.abs())
        resultado = (
            ontem * retorno_total[codigo].fillna(0.0)
            - giro * custos.por_lado(mercado)
            - ontem.abs() * custos.margem(mercado) * dias / DIAS_DO_ANO
        )
        posicoes[codigo], contribuicoes[codigo] = posicao, resultado

    contribuicao = pd.DataFrame(contribuicoes)
    algum_mercado = pesos.shift(1).fillna(0.0).sum(axis=1) > 0
    return Resultado(
        retorno=contribuicao.sum(axis=1)[algum_mercado],
        contribuicao=contribuicao[algum_mercado],
        posicao=pd.DataFrame(posicoes),
        idm=idm,
    )
