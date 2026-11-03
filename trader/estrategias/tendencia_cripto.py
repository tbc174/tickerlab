"""Tendência em cripto em reais: a ficha P0-1 do pré-registro quant v0.1 (ADR 0118).

A regra, como está no pré-registro (seção 4, ficha P0-1), com os parâmetros fixos:
- **Canais de Donchian** com janelas {5, 10, 20, 30, 60, 90, 150, 250, 360} dias corridos. Em cada
  janela o estado é 1 (comprado) quando o fechamento passa a máxima dos N fechamentos anteriores e
  0 (zerado) quando cai abaixo do meio do canal (média da máxima e da mínima dos N anteriores);
  entre os dois o estado fica como estava.
- **Sinal** = média dos 9 estados (de 0 a 1).
- **Peso** = sinal × min(1; 0,25 ÷ σ de 90 dias anualizada com 365). BTC e ETH com metade do
  capital cada: a fração alvo de cada um é o peso × 0,5, então a alavancagem nunca passa de 1.
- **Execução:** sinal no fechamento de D, ordem no fechamento de D+1 (todo dia do ano); a posição
  começa a render em D+2. Olhar o futuro (só para a verificação V) executa no fechamento de D o
  sinal de D+1.
- **Caixa a CDI** (o que não está em cripto rende o retorno do caixa de cada dia corrido).
- **Custos** (`trader/custos_br.py` v0.1): taxa da corretora por lado, impacto Y·σ·√(Q/V)·Q
  (Y = 1; 2 no estresse), IOF e spread de câmbio em toda ordem quando a série é em reais via
  dólar, e IR de 15% sobre o ganho do mês apurado por custo médio, isento no mês em que as vendas
  não passam de R$ 35 mil, DARF pago do caixa no último dia do mês seguinte.
- **Aquecimento:** cada série só entra 365 dias depois do primeiro preço (seção 2).

Convenções fixadas antes de qualquer número (o relatório as repete em "Limites e cuidados"):
- não negocia diferença menor que meio ponto percentual do patrimônio (`BANDA_MINIMA`), para a
  deriva do dia a dia não virar uma chuva de micro-ordens;
- o custo de aquisição do IR é o preço pago, sem as taxas (erra contra a estratégia);
- o DARF sai do caixa mesmo que ele fique negativo (empréstimo ao CDI); `caixa_minimo` mede isso;
- o IR dos meses que ainda não venceram é pago no último dia dos dados.

Nada aqui envia ordem; é só simulação com dados do passado.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, replace

import numpy as np
import pandas as pd

from trader import avaliacao
from trader.custos_br import (
    PADRAO,
    CustosBR,
    apurar_ir_mensal,
    custo_de_negociar,
    custo_do_cambio,
)
from trader.estrategias.carteira_rp import p_valor_do_acaso

__all__ = ["p_valor_do_acaso"]

VERSAO = "0.1"
ATIVOS = ("BTC", "ETH")
CLASSE = "cripto"
CANDIDATO = "BTC e ETH 50/50"
JANELAS = (5, 10, 20, 30, 60, 90, 150, 250, 360)
VOL_ALVO = 0.25
JANELA_DA_VOL = 90
FRACAO_POR_ATIVO = 0.5
DIAS_POR_ANO = 365
AQUECIMENTO_EM_DIAS = 365
CAPITAL_INICIAL = 100_000.0
BANDA_MINIMA = 0.005  # fração do patrimônio abaixo da qual a ordem não vale a pena
ATRASO_DA_EXECUCAO = 1  # sinal em D, ordem no fechamento de D+1
SEM_CUSTOS = CustosBR(
    corretagem_por_ordem=0.0,
    taxa_cripto_por_lado=0.0,
    ir_cripto=0.0,
    iof_cambio=0.0,
    spread_cambio=0.0,
)


@dataclass(frozen=True)
class Parametros:
    """Os parâmetros da ficha; os vizinhos do platô e o estresse são cópias com uma mudança."""

    janelas: tuple[int, ...] = JANELAS
    vol_alvo: float = VOL_ALVO
    janela_da_vol: int = JANELA_DA_VOL
    fracao_por_ativo: float = FRACAO_POR_ATIVO
    custos: CustosBR = PADRAO
    fator_de_impacto: float = 1.0
    com_cambio: bool = True
    olhar_o_futuro: bool = False

    def __post_init__(self) -> None:
        if not self.janelas or any(j < 2 for j in self.janelas):
            raise ValueError("cada janela do canal precisa ter pelo menos 2 dias")
        if self.vol_alvo <= 0:
            raise ValueError("a volatilidade alvo precisa ser positiva")
        if self.janela_da_vol < 2:
            raise ValueError("a janela da volatilidade precisa ter pelo menos 2 dias")
        if not 0 < self.fracao_por_ativo * len(ATIVOS) <= 1:
            raise ValueError("a soma das frações por ativo tem de ficar entre 0 e 1")
        if self.fator_de_impacto < 0:
            raise ValueError("o fator de impacto não pode ser negativo")

    def especificacao(self) -> dict:
        """Tudo o que define a tentativa, em tipos simples (vai para o registro)."""
        spec = asdict(self)
        spec["janelas"] = list(self.janelas)
        spec["custos"] = {
            k: list(v) if isinstance(v, tuple) else v for k, v in spec["custos"].items()
        }
        spec |= {
            "ativos": list(ATIVOS),
            "execucao": "fechamento de D+1",
            "dias_por_ano": DIAS_POR_ANO,
            "aquecimento_em_dias": AQUECIMENTO_EM_DIAS,
            "banda_minima": BANDA_MINIMA,
        }
        return spec

    def em_estresse(self, fator: float = 2.0) -> Parametros:
        """Custos de corretora e câmbio × fator e impacto com Y = fator; lei não muda."""
        return replace(
            self, custos=self.custos.em_estresse(fator), fator_de_impacto=fator
        )


PARAMETROS_DA_FICHA = Parametros()


@dataclass
class Resultado:
    retorno: (
        pd.Series
    )  # diário, líquido, do primeiro dia depois do aquecimento em diante
    patrimonio: pd.Series
    exposicao: pd.DataFrame  # fração do patrimônio em cada ativo no fechamento
    alvos: pd.DataFrame  # fração alvo executada em cada fechamento
    negociado: pd.DataFrame  # reais por ativo e dia (+ compra, - venda)
    custos: pd.Series  # corretora, impacto e câmbio, por dia
    cambio: pd.Series  # só a parte de IOF e spread
    imposto: pd.Series  # DARF pago, por dia
    vendas: pd.Series
    resultado_realizado: pd.Series
    ir: pd.DataFrame  # a apuração mensal inteira (colunas de `COLUNAS_DO_IR`)
    giro: float  # valor negociado por ano ÷ patrimônio médio
    caixa_minimo: float  # menor caixa ÷ patrimônio (negativo = empréstimo para o DARF)
    parametros: Parametros = field(repr=False)

    def exposicao_media(self) -> float:
        return float(self.exposicao.sum(axis=1).mean())

    def meses_acima_da_isencao(self) -> int:
        """Meses em que as vendas passaram do teto de isenção (e o ganho pagou imposto)."""
        teto = self.parametros.custos.isencao_cripto_no_mes
        return int((self.ir["vendas"] > teto).sum()) if len(self.ir) else 0


# --- a regra ---------------------------------------------------------------------------------------


def estado_do_canal(fechamento: pd.Series, janela: int) -> pd.Series:
    """1 depois de passar a máxima dos `janela` fechamentos anteriores, 0 depois de cair abaixo do
    meio do canal anterior; NaN enquanto não há canal."""
    f = fechamento.astype(float)
    anteriores = f.shift(1)
    maxima = anteriores.rolling(janela).max().to_numpy()
    meio = ((maxima + anteriores.rolling(janela).min().to_numpy()) / 2).astype(float)
    valores = f.to_numpy()
    estado = np.full(len(f), np.nan)
    atual = 0.0
    for i in range(len(f)):
        if np.isnan(maxima[i]) or np.isnan(valores[i]):
            continue
        if valores[i] > maxima[i]:
            atual = 1.0
        elif valores[i] < meio[i]:
            atual = 0.0
        estado[i] = atual
    return pd.Series(estado, index=f.index)


def sinal(fechamento: pd.Series, janelas: tuple[int, ...] = JANELAS) -> pd.Series:
    """A média dos estados dos canais (0 a 1); NaN até a maior janela ter canal."""
    estados = pd.concat([estado_do_canal(fechamento, j) for j in janelas], axis=1)
    return estados.mean(axis=1, skipna=False)


def volatilidade_anualizada(
    fechamento: pd.Series, janela: int, dias_por_ano: int = DIAS_POR_ANO
) -> pd.Series:
    return fechamento.pct_change().rolling(janela).std() * np.sqrt(dias_por_ano)


def peso(fechamento: pd.Series, parametros: Parametros) -> pd.Series:
    """sinal × min(1; vol alvo ÷ σ); σ zero deixa o peso igual ao sinal."""
    sigma = volatilidade_anualizada(fechamento, parametros.janela_da_vol)
    with np.errstate(divide="ignore"):
        escala = (parametros.vol_alvo / sigma).clip(upper=1.0)
    return sinal(fechamento, parametros.janelas) * escala


def fracoes_alvo(precos: pd.DataFrame, parametros: Parametros) -> pd.DataFrame:
    """A fração do patrimônio que cada ativo pede no fechamento de cada dia (0 no aquecimento)."""
    fracoes = pd.DataFrame(index=precos.index, columns=list(ATIVOS), dtype=float)
    for ativo in ATIVOS:
        serie = precos[ativo]
        alvo = (peso(serie, parametros) * parametros.fracao_por_ativo).fillna(0.0)
        primeiro = serie.first_valid_index()
        if primeiro is not None:
            alvo[alvo.index < primeiro + pd.Timedelta(days=AQUECIMENTO_EM_DIAS)] = 0.0
        fracoes[ativo] = alvo
    return fracoes


def escalar_janelas(janelas: tuple[int, ...], fator: float) -> tuple[int, ...]:
    """As janelas × fator, arredondadas (vizinhos de ±20% do platô)."""
    return tuple(max(2, round(j * fator)) for j in janelas)


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia dos parâmetros com algumas mudanças (vizinhos, estresse, bruto, sem câmbio)."""
    return replace(parametros, **mudancas)


# --- a simulação -----------------------------------------------------------------------------------


def _conferir_entradas(
    precos: pd.DataFrame, cdi: pd.Series, volumes: pd.DataFrame
) -> None:
    datas = precos.index
    passos = np.diff(datas.to_numpy()) == np.timedelta64(1, "D")
    if len(datas) < 2 or not passos.all():
        raise ValueError("os preços precisam estar em dias corridos, sem buracos")
    if list(precos.columns) != list(ATIVOS):
        raise ValueError(f"os ativos têm de ser {ATIVOS}, nesta ordem")
    if cdi.reindex(datas).isna().any():
        raise ValueError("CDI faltando em algum dia dos preços")
    if list(volumes.columns) != list(ATIVOS):
        raise ValueError(f"os volumes têm de ter as colunas {ATIVOS}")


def impacto(valor: float, sigma_diaria: float, volume: float, fator: float) -> float:
    """Raiz quadrada: Y·σ·√(Q/V)·Q; sem volume conhecido não há como medir (é erro).

    A P0-2 (`tendencia_b3`) usa a mesma conta.
    """
    if fator == 0.0 or valor == 0.0:
        return 0.0
    if not volume > 0:
        raise ValueError(
            "volume desconhecido no dia da ordem: o impacto não tem como ser medido"
        )
    return fator * sigma_diaria * np.sqrt(valor / volume) * valor


def _inicio(precos: pd.DataFrame) -> int:
    """A posição do primeiro dia simulado: 365 dias depois do primeiro preço."""
    primeiro = precos.index[0] + pd.Timedelta(days=AQUECIMENTO_EM_DIAS)
    posicao = int(precos.index.searchsorted(primeiro))
    if posicao >= len(precos):
        raise ValueError("menos de um ano de preços: nada sobra depois do aquecimento")
    return posicao


def _ultimo_dia_do_mes(dia: pd.Timestamp) -> bool:
    return (dia + pd.Timedelta(days=1)).month != dia.month


class _Carteira:
    """Quantidades, custo médio e caixa; sabe comprar, vender e pagar."""

    def __init__(self, capital: float) -> None:
        self.caixa = capital
        self.quantidade = np.zeros(len(ATIVOS))
        self.custo_medio = np.zeros(len(ATIVOS))

    def valores(self, precos_do_dia: np.ndarray) -> np.ndarray:
        return self.quantidade * precos_do_dia

    def patrimonio(self, precos_do_dia: np.ndarray) -> float:
        return float(self.caixa + self.valores(precos_do_dia).sum())

    def negociar(self, k: int, delta: float, preco: float) -> tuple[float, float]:
        """Compra (delta > 0) ou vende (delta < 0) `delta` reais; devolve (vendas, resultado)."""
        q = delta / preco
        if delta > 0:
            total = self.quantidade[k] * self.custo_medio[k] + delta
            self.quantidade[k] += q
            self.custo_medio[k] = total / self.quantidade[k]
            self.caixa -= delta
            return 0.0, 0.0
        vendido = -delta
        resultado = -q * (preco - self.custo_medio[k])
        self.quantidade[k] += q
        if self.quantidade[k] <= 1e-15:
            self.quantidade[k] = 0.0
            self.custo_medio[k] = 0.0
        self.caixa += vendido
        return vendido, resultado


def _imposto_dos_meses(
    vendas: pd.Series, resultado: pd.Series, meses: pd.PeriodIndex, custos: CustosBR
) -> float:
    if len(meses) == 0 or vendas.empty:
        return 0.0
    tabela = apurar_ir_mensal(vendas, resultado, CLASSE, custos=custos)
    return float(tabela["imposto"].reindex(meses).fillna(0.0).sum())


def simular(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.DataFrame,
    parametros: Parametros = PARAMETROS_DA_FICHA,
    capital: float = CAPITAL_INICIAL,
) -> Resultado:
    """Simula a regra dia a dia; `cdi` é o retorno do caixa em cada dia corrido e `volumes` o
    volume financeiro (reais) conhecido em cada dia, para o impacto."""
    _conferir_entradas(precos, cdi, volumes)
    datas = precos.index
    atraso = -1 if parametros.olhar_o_futuro else ATRASO_DA_EXECUCAO
    alvos = fracoes_alvo(precos, parametros).shift(atraso).fillna(0.0)
    sigma = precos.pct_change().rolling(parametros.janela_da_vol).std().fillna(0.0)
    p = precos.to_numpy(float)
    a = alvos.to_numpy(float)
    s = sigma.to_numpy(float)
    v = volumes.reindex(datas).to_numpy(float)
    c = cdi.reindex(datas).to_numpy(float)
    custos = parametros.custos
    n = len(datas)
    inicio = _inicio(precos)

    retorno = np.full(n, np.nan)
    patrimonio = np.full(n, np.nan)
    exposicao = np.zeros((n, len(ATIVOS)))
    negociado = np.zeros((n, len(ATIVOS)))
    custo_do_dia = np.zeros(n)
    cambio_do_dia = np.zeros(n)
    imposto_do_dia = np.zeros(n)
    vendas = np.zeros(n)
    realizado = np.zeros(n)
    caixa_minimo = 1.0

    carteira = _Carteira(capital)
    anterior = capital
    pago_ate = datas[inicio].to_period("M") - 1

    def pagar(i: int, ate_o_mes: pd.Period, incluir_hoje: bool) -> None:
        nonlocal pago_ate
        meses = pd.period_range(pago_ate + 1, ate_o_mes, freq="M")
        fim = i + 1 if incluir_hoje else i
        devido = _imposto_dos_meses(
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
        if _ultimo_dia_do_mes(dia):
            pagar(i, mes - 1, incluir_hoje=False)
        patrimonio_antes = carteira.patrimonio(p[i])
        valores = carteira.valores(p[i])
        for k in range(len(ATIVOS)):
            delta = a[i, k] * patrimonio_antes - valores[k]
            if abs(delta) < BANDA_MINIMA * patrimonio_antes:
                continue
            valor = abs(delta)
            custo = custo_de_negociar(valor, CLASSE, custos=custos) + impacto(
                valor, s[i, k], v[i, k], parametros.fator_de_impacto
            )
            cambio = (
                custo_do_cambio(valor, custos=custos) if parametros.com_cambio else 0.0
            )
            vendido, resultado = carteira.negociar(k, delta, p[i, k])
            carteira.caixa -= custo + cambio
            negociado[i, k] = delta
            custo_do_dia[i] += custo + cambio
            cambio_do_dia[i] += cambio
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
        return pd.DataFrame(valores[inicio:], index=simulado, columns=list(ATIVOS))

    anos = len(simulado) / DIAS_POR_ANO
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
        ir=apurar_ir_mensal(serie(vendas), serie(realizado), CLASSE, custos=custos),
        giro=float(
            np.abs(negociado[inicio:]).sum() / anos / np.nanmean(patrimonio[inicio:])
        ),
        caixa_minimo=float(caixa_minimo),
        parametros=parametros,
    )


# --- réguas e verificações ---------------------------------------------------------------------------


def comprar_e_segurar(
    fechamento: pd.Series,
    volume: pd.Series,
    parametros: Parametros,
    capital: float = CAPITAL_INICIAL,
) -> pd.Series:
    """Compra tudo no primeiro dia depois do aquecimento (pagando corretora, impacto e câmbio) e
    segue o preço; não vende, então não paga IR."""
    primeiro = fechamento.index[0] + pd.Timedelta(days=AQUECIMENTO_EM_DIAS)
    serie = fechamento.loc[primeiro:]
    if serie.empty:
        raise ValueError("menos de um ano de preços: nada sobra depois do aquecimento")
    inicio = serie.index[0]
    sigma = fechamento.pct_change().rolling(parametros.janela_da_vol).std()
    custo = (
        custo_de_negociar(capital, CLASSE, custos=parametros.custos)
        + impacto(
            capital,
            float(np.nan_to_num(sigma.loc[inicio])),
            float(volume.loc[inicio]),
            parametros.fator_de_impacto,
        )
        + (
            custo_do_cambio(capital, custos=parametros.custos)
            if parametros.com_cambio
            else 0.0
        )
    )
    retorno = serie.pct_change()
    retorno.iloc[0] = -custo / capital
    return retorno


def em_dias_uteis(serie: pd.Series) -> pd.Series:
    """Fim de semana composto na segunda: o critério anualiza com 252."""
    return avaliacao.para_dias_uteis(serie)


def sharpe_do_excesso(retorno: pd.Series, cdi: pd.Series) -> float:
    """Sharpe (252) do excesso sobre o caixa, com os dois compostos em dias úteis."""
    uteis = em_dias_uteis(retorno)
    caixa = em_dias_uteis(cdi.reindex(retorno.index))
    return avaliacao.sharpe(uteis - caixa.reindex(uteis.index))


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do retorno e do patrimônio (reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.patrimonio.round(6).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def cortar_o_futuro_nao_muda_o_passado(
    precos: pd.DataFrame,
    cdi: pd.Series,
    volumes: pd.DataFrame,
    parametros: Parametros,
    corte: pd.Timestamp,
    capital: float = CAPITAL_INICIAL,
) -> bool:
    """Rodar só até `corte` dá, até a véspera do corte, o mesmo retorno de rodar tudo.

    O dia do corte fica de fora: na série cortada ele é o último dia dos dados e paga o IR que
    ainda não venceu, o que não é olhar o futuro, é o fim dos dados.
    """
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
