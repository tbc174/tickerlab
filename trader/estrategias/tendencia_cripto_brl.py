"""Tendência em cripto no par em reais: a ficha P0-1b do pré-registro quant v0.2 (camada A2).

A regra é a da P0-1 (`tendencia_cripto`), importada e sem mudança: 9 canais de Donchian, sinal
médio, vol alvo de 25% sobre a σ de 90 dias, BTC e ETH com metade do capital cada, alavancagem
≤ 1, caixa a CDI, sinal em D e execução no fechamento de D+1, aquecimento de 365 dias por série.
A P0-1b muda três coisas, todas escritas na ficha antes de qualquer número:

- **Banda de 20%:** a posição só muda quando difere do peso-alvo em mais de 20% dele. Quando o alvo
  é zero, a posição zera. Quando a posição é zero, ela abre se o alvo passar de 0,5% do patrimônio
  (a convenção da P0-1). Quando muda, vai ao alvo. O mínimo de 0,5% do patrimônio por ordem da P0-1
  continua valendo (a regra da P0-1 fica inteira; a banda vem por cima). Sem banda (`banda=None`)
  é a regra da P0-1, para o teste (d).
- **Sem câmbio:** BTCBRL e ETHBRL são cotados em reais; não há IOF nem spread de câmbio.
- **Spread do livro em reais:** sem histórico de spread, o critério usa 0,3% por lado sobre o valor
  de cada ordem (conservador); 0,1% sai só como leitura (`SPREAD_DE_LEITURA`). O impacto é o mesmo
  modelo da P0-1, sobre o volume do par em reais.

Nada aqui envia ordem; é só simulação com dados do passado.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from trader.custos_br import apurar_ir_mensal, custo_de_negociar, custo_do_cambio
from trader.estrategias import tendencia_cripto as tc

VERSAO = "0.1"
FICHA = "P0-1b"
CANDIDATO = "BTCBRL e ETHBRL 50/50"
ORCAMENTO = 2
BANDA = 0.20
SPREAD_POR_LADO = 0.003  # o do critério
SPREAD_DE_LEITURA = 0.001  # só leitura no relatório
REGRA_DA_BANDA = (
    "muda só se |posição − alvo| > banda × alvo; alvo zero zera; posição zero abre se o alvo "
    "passar de 0,5% do patrimônio; ordem menor que 0,5% do patrimônio não sai (P0-1); "
    "quando muda, vai ao alvo"
)


@dataclass(frozen=True)
class Parametros(tc.Parametros):
    """Os da P0-1, mais a banda e o spread, e sem câmbio (o par já é em reais)."""

    com_cambio: bool = False
    spread_por_lado: float = SPREAD_POR_LADO
    banda: float | None = BANDA

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.spread_por_lado < 0:
            raise ValueError("o spread por lado não pode ser negativo")
        if self.banda is not None and not 0 < self.banda < 1:
            raise ValueError("a banda tem de ficar entre 0 e 1 (ou None, sem banda)")

    def especificacao(self) -> dict:
        return super().especificacao() | {
            "versao_do_codigo_p0_1b": VERSAO,
            "regra_da_banda": REGRA_DA_BANDA,
        }

    def em_estresse(self, fator: float = 2.0) -> Parametros:
        """O estresse da P0-1 (corretora, câmbio e impacto) e o spread do livro × fator."""
        base = super().em_estresse(fator)
        return replace(base, spread_por_lado=self.spread_por_lado * fator)


PARAMETROS_DA_FICHA = Parametros()


@dataclass
class Resultado(tc.Resultado):
    spread: pd.Series  # a parte do spread do livro, por dia (já somada em `custos`)


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia com algumas mudanças (vizinhos, estresse, bruto, sem banda, spread de leitura)."""
    return replace(parametros, **mudancas)


def deve_negociar(posicao: float, alvo: float, banda: float | None) -> bool:
    """A banda da ficha, em frações do patrimônio; `banda=None` é a regra da P0-1."""
    diferenca = abs(alvo - posicao)
    if banda is None:
        return diferenca >= tc.BANDA_MINIMA
    if alvo == 0:
        return posicao != 0
    if posicao == 0:
        return alvo > tc.BANDA_MINIMA
    return diferenca > banda * alvo and diferenca >= tc.BANDA_MINIMA


def simular(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.DataFrame,
    parametros: Parametros = PARAMETROS_DA_FICHA,
    capital: float = tc.CAPITAL_INICIAL,
) -> Resultado:
    """O mesmo laço da P0-1 (`tendencia_cripto.simular`), com a banda e o spread do livro.

    Preço vazio antes do 1º candle de um par é aceito: o alvo dele fica zero até o próprio
    aquecimento acabar, e a simulação só começa 365 dias depois do primeiro preço da tabela.
    """
    tc._conferir_entradas(precos, cdi, volumes)
    datas = precos.index
    atraso = -1 if parametros.olhar_o_futuro else tc.ATRASO_DA_EXECUCAO
    alvos = tc.fracoes_alvo(precos, parametros).shift(atraso).fillna(0.0)
    sigma = precos.pct_change().rolling(parametros.janela_da_vol).std().fillna(0.0)
    p = precos.to_numpy(float)
    a = alvos.to_numpy(float)
    s = sigma.to_numpy(float)
    v = volumes.reindex(datas).to_numpy(float)
    c = cdi.reindex(datas).to_numpy(float)
    custos = parametros.custos
    n = len(datas)
    inicio = tc._inicio(precos)
    if np.isnan(p[inicio:]).any():
        raise ValueError("preço vazio depois do primeiro dia simulado")

    retorno = np.full(n, np.nan)
    patrimonio = np.full(n, np.nan)
    exposicao = np.zeros((n, len(tc.ATIVOS)))
    negociado = np.zeros((n, len(tc.ATIVOS)))
    custo_do_dia = np.zeros(n)
    cambio_do_dia = np.zeros(n)
    spread_do_dia = np.zeros(n)
    imposto_do_dia = np.zeros(n)
    vendas = np.zeros(n)
    realizado = np.zeros(n)
    caixa_minimo = 1.0

    carteira = tc._Carteira(capital)
    anterior = capital
    pago_ate = datas[inicio].to_period("M") - 1

    def pagar(i: int, ate_o_mes: pd.Period, incluir_hoje: bool) -> None:
        nonlocal pago_ate
        meses = pd.period_range(pago_ate + 1, ate_o_mes, freq="M")
        fim = i + 1 if incluir_hoje else i
        devido = tc._imposto_dos_meses(
            pd.Series(vendas[inicio:fim], index=datas[inicio:fim]),
            pd.Series(realizado[inicio:fim], index=datas[inicio:fim]),
            meses,
            custos,
        )
        imposto_do_dia[i] += devido
        carteira.caixa -= devido
        pago_ate = max(pago_ate, ate_o_mes)

    for i in range(inicio, n):
        dia = datas[i]
        carteira.caixa *= 1 + c[i]
        mes = dia.to_period("M")
        if tc._ultimo_dia_do_mes(dia):
            pagar(i, mes - 1, incluir_hoje=False)
        patrimonio_antes = carteira.patrimonio(p[i])
        valores = carteira.valores(p[i])
        for k in range(len(tc.ATIVOS)):
            posicao = valores[k] / patrimonio_antes
            if not deve_negociar(posicao, a[i, k], parametros.banda):
                continue
            delta = a[i, k] * patrimonio_antes - valores[k]
            valor = abs(delta)
            spread = parametros.spread_por_lado * valor
            custo = (
                custo_de_negociar(valor, tc.CLASSE, custos=custos)
                + tc.impacto(valor, s[i, k], v[i, k], parametros.fator_de_impacto)
                + spread
            )
            cambio = (
                custo_do_cambio(valor, custos=custos) if parametros.com_cambio else 0.0
            )
            vendido, resultado = carteira.negociar(k, delta, p[i, k])
            carteira.caixa -= custo + cambio
            negociado[i, k] = delta
            custo_do_dia[i] += custo + cambio
            cambio_do_dia[i] += cambio
            spread_do_dia[i] += spread
            vendas[i] += vendido
            realizado[i] += resultado
        if i == n - 1:
            pagar(i, mes, incluir_hoje=True)
        fechamento = carteira.patrimonio(p[i])
        patrimonio[i] = fechamento
        retorno[i] = fechamento / anterior - 1
        exposicao[i] = carteira.valores(p[i]) / fechamento
        caixa_minimo = min(caixa_minimo, carteira.caixa / fechamento)
        anterior = fechamento

    simulado = datas[inicio:]

    def serie(valores: np.ndarray) -> pd.Series:
        return pd.Series(valores[inicio:], index=simulado)

    def tabela(valores: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(valores[inicio:], index=simulado, columns=list(tc.ATIVOS))

    anos = len(simulado) / tc.DIAS_POR_ANO
    return Resultado(
        retorno=serie(retorno),
        patrimonio=serie(patrimonio),
        exposicao=tabela(exposicao),
        alvos=alvos.iloc[inicio:],
        negociado=tabela(negociado),
        custos=serie(custo_do_dia),
        cambio=serie(cambio_do_dia),
        imposto=serie(imposto_do_dia),
        vendas=serie(vendas),
        resultado_realizado=serie(realizado),
        ir=apurar_ir_mensal(serie(vendas), serie(realizado), tc.CLASSE, custos=custos),
        giro=float(
            np.abs(negociado[inicio:]).sum() / anos / np.nanmean(patrimonio[inicio:])
        ),
        caixa_minimo=float(caixa_minimo),
        parametros=parametros,
        spread=serie(spread_do_dia),
    )


def comprar_e_segurar(
    fechamento: pd.Series,
    volume: pd.Series,
    parametros: Parametros,
    capital: float = tc.CAPITAL_INICIAL,
) -> pd.Series:
    """A régua da P0-1 no par em reais: paga corretora, impacto e o spread do livro na compra."""
    retorno = tc.comprar_e_segurar(fechamento, volume, parametros, capital)
    retorno.iloc[0] -= parametros.spread_por_lado
    return retorno


def cortar_o_futuro_nao_muda_o_passado(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.DataFrame,
    parametros: Parametros,
    corte: pd.Timestamp,
    capital: float = tc.CAPITAL_INICIAL,
) -> bool:
    """A verificação da P0-1 com esta simulação (o dia do corte fica de fora, como lá)."""
    inteiro = simular(precos, cdi, volumes, parametros, capital)
    cortado = simular(
        precos.loc[:corte], cdi.loc[:corte], volumes.loc[:corte], parametros, capital
    )
    return bool(
        np.allclose(
            inteiro.retorno.loc[inteiro.retorno.index < corte].to_numpy(),
            cortado.retorno.loc[cortado.retorno.index < corte].to_numpy(),
            rtol=0,
            atol=1e-12,
        )
    )
