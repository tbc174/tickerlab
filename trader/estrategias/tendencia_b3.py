"""Tendência na B3: a ficha P0-2 do pré-registro quant v0.1 (ADR 0118).

A regra, como está no pré-registro (seção 4, ficha P0-2): **a mesma família da P0-1** (nove canais
de Donchian, sinal médio, vol alvo de 25%, σ de 90) **sobre o excesso ao CDI do ativo**; a posição
zerada vai para o CDI. Três versões pré-registradas e comparadas (BOVA11 à vista, WIN e DI1
sintéticos); a candidata à carteira é o BOVA11 (a mais simples de executar à mão); WIN e DI1 são
comparação.

- **O que o sinal olha:** o índice do excesso ao CDI (começa em 100 e cresce pelo retorno diário
  do ativo menos o CDI do dia). Canais de {5, 10, 20, 30, 60, 90, 150, 250, 360} **pregões**: 1
  quando o índice passa a máxima dos N anteriores, 0 quando cai abaixo do meio do canal; sinal =
  média dos 9; peso = sinal × min(1; 0,25 ÷ σ de 90 pregões do excesso, anualizada com 252).
- **Execução:** sinal no fechamento de D, ordem no **leilão de abertura de D+1** (preço de
  abertura do pregão seguinte); nunca no mesmo dia. Olhar o futuro (só a verificação V) executa na
  abertura de D o sinal do fechamento de D+1, como na P0-1 (vale também para o DI1, que executa no
  fechamento).
- **BOVA11:** lote de 100 cotas (`arredondar_lote`), emolumentos do leilão (0,032%), impacto
  Y·σ·√(Q/V)·Q sobre a média dos 60 pregões anteriores do volume em reais, IR de 15% sobre o ganho
  do mês por custo médio (ETF não tem isenção), DARF do caixa no último pregão do mês seguinte.
- **WIN e DI1 sintéticos:** o nocional segue o índice do excesso (`dados_alavancagem`); o caixa
  inteiro rende CDI (margem a CDI); o ajuste diário entra no caixa; tarifa por contrato e spread
  por lado em toda ordem; rolagem no pregão anterior ao vencimento (WIN, meses pares) ou uma vez
  por ano (DI1, vértice de janeiro mais perto de 2 anos), com o custo das duas pernas, feita na
  abertura **antes** da ordem do dia (as pernas são contratos diferentes: não é day trade); IR de
  15% sobre o ajuste líquido do mês (sem isenção). Contratos fracionários, como na alavancagem do
  núcleo (declarado no relatório). O DI1 não tem leilão de abertura na série: executa na marcação
  do fechamento de D+1 (um dia a mais de atraso, declarado).
- **Aquecimento:** 360 pregões depois do primeiro excesso (a maior janela).

Convenções fixadas antes de qualquer número (o relatório as repete em "Limites e cuidados"):
- não negocia diferença menor que meio ponto percentual do patrimônio (`BANDA_MINIMA`);
- o custo de aquisição do IR é o preço pago, sem as taxas, e no futuro o ajuste do mês não desconta
  tarifa nem spread (os dois erram contra a estratégia);
- o DARF sai do caixa mesmo que ele fique negativo (empréstimo ao CDI); `caixa_minimo` mede isso;
- o IR dos meses que ainda não venceram é pago no último pregão dos dados;
- day trade: compra e venda do mesmo instrumento no mesmo pregão; com uma ordem por pregão no
  leilão de abertura, nenhuma saída vira day trade (`day_trades` conta e o relatório diz).

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
    arredondar_lote,
    custo_de_negociar,
)
from trader.estrategias import tendencia_cripto as tc
from trader.estrategias.alavancagem import (
    SPREAD_POR_LADO,
    VALOR_DO_CONTRATO,
    datas_de_rolagem,
)
from trader.estrategias.dados_alavancagem import excesso_do_di1, excesso_do_win

VERSAO = "0.1"
CANDIDATO = "BOVA11"
VERSOES = ("BOVA11", "WIN", "DI1")
CLASSES = ("etf", "acoes", "futuros")
JANELAS = tc.JANELAS  # em pregões
VOL_ALVO = tc.VOL_ALVO
JANELA_DA_VOL = tc.JANELA_DA_VOL
PREGOES_POR_ANO = 252
AQUECIMENTO_EM_PREGOES = max(JANELAS)
CAPITAL_INICIAL = tc.CAPITAL_INICIAL
BANDA_MINIMA = tc.BANDA_MINIMA
ATRASO_DA_EXECUCAO = 1  # sinal em D, ordem no leilão de abertura de D+1
LOTE = 100
FRACIONARIO = 0  # lote 0: quantidade fracionária (contratos sintéticos e a cesta)
DIAS_DO_VOLUME = 60
PERNAS_DA_ROLAGEM = 2
SEM_CUSTOS = CustosBR(
    corretagem_por_ordem=0.0,
    emolumentos_a_vista=0.0,
    emolumentos_no_leilao=0.0,
    emolumentos_day_trade=0.0,
    tarifa_futuro_por_contrato=0.0,
    ir_swing=0.0,
    ir_day_trade=0.0,
)


@dataclass(frozen=True)
class Ativo:
    """Uma versão da ficha: o que se negocia, o que o sinal olha e como se paga por isso.

    `abertura` é o preço do leilão de abertura (onde a ordem executa) e `fechamento` o da marcação;
    `excesso` é o retorno diário acima do CDI (o que o sinal olha); `volume` é o volume financeiro
    já conhecido em cada pregão (média dos 60 anteriores), para o impacto.
    """

    nome: str
    abertura: pd.Series
    fechamento: pd.Series
    excesso: pd.Series
    volume: pd.Series
    classe: str
    lote: int = LOTE
    valor_do_contrato: float = 0.0
    rolagens: tuple[pd.Timestamp, ...] = ()

    def __post_init__(self) -> None:
        if self.classe not in CLASSES:
            raise ValueError(
                f"classe desconhecida: {self.classe!r}; use uma de {CLASSES}"
            )
        datas = self.fechamento.index
        for serie in (self.abertura, self.excesso, self.volume):
            if not serie.index.equals(datas):
                raise ValueError(f"{self.nome}: as séries precisam ter as mesmas datas")
        if not (datas.is_monotonic_increasing and datas.is_unique):
            raise ValueError(
                f"{self.nome}: as datas precisam estar em ordem, sem repetição"
            )
        if self.futuro and self.valor_do_contrato <= 0:
            raise ValueError(f"{self.nome}: futuro precisa do valor do contrato")
        if self.abertura.isna().any() or self.fechamento.isna().any():
            raise ValueError(f"{self.nome}: preço faltando em algum pregão")

    @property
    def datas(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.fechamento.index)

    @property
    def futuro(self) -> bool:
        return self.classe == "futuros"

    def ate(self, corte: pd.Timestamp) -> Ativo:
        """A mesma versão só com os dados até `corte` (para cortar o futuro)."""
        return replace(
            self,
            abertura=self.abertura.loc[:corte],
            fechamento=self.fechamento.loc[:corte],
            excesso=self.excesso.loc[:corte],
            volume=self.volume.loc[:corte],
            rolagens=tuple(d for d in self.rolagens if d <= corte),
        )


@dataclass(frozen=True)
class Parametros:
    """Os parâmetros da ficha; os vizinhos do platô e o estresse são cópias com uma mudança."""

    janelas: tuple[int, ...] = JANELAS
    vol_alvo: float = VOL_ALVO
    janela_da_vol: int = JANELA_DA_VOL
    custos: CustosBR = PADRAO
    fator_de_impacto: float = 1.0
    spread_do_futuro_por_lado: float = SPREAD_POR_LADO
    olhar_o_futuro: bool = False

    def __post_init__(self) -> None:
        if not self.janelas or any(j < 2 for j in self.janelas):
            raise ValueError("cada janela do canal precisa ter pelo menos 2 pregões")
        if self.vol_alvo <= 0:
            raise ValueError("a volatilidade alvo precisa ser positiva")
        if self.janela_da_vol < 2:
            raise ValueError(
                "a janela da volatilidade precisa ter pelo menos 2 pregões"
            )
        if self.fator_de_impacto < 0 or self.spread_do_futuro_por_lado < 0:
            raise ValueError("impacto e spread não podem ser negativos")

    def especificacao(self) -> dict:
        """Tudo o que define a tentativa, em tipos simples (vai para o registro)."""
        spec = asdict(self)
        spec["janelas"] = list(self.janelas)
        spec["custos"] = {
            k: list(v) if isinstance(v, tuple) else v for k, v in spec["custos"].items()
        }
        spec |= {
            "candidato": CANDIDATO,
            "versoes": list(VERSOES),
            "sinal": "canais de Donchian sobre o índice do excesso ao CDI",
            "execucao": "leilão de abertura de D+1",
            "pregoes_por_ano": PREGOES_POR_ANO,
            "aquecimento_em_pregoes": AQUECIMENTO_EM_PREGOES,
            "banda_minima": BANDA_MINIMA,
            "lote": LOTE,
            "contratos": "fracionários",
        }
        return spec

    def em_estresse(self, fator: float = 2.0) -> Parametros:
        """Custos de bolsa × fator, spread × fator e impacto com Y = fator; lei não muda."""
        return replace(
            self,
            custos=self.custos.em_estresse(fator),
            fator_de_impacto=fator,
            spread_do_futuro_por_lado=self.spread_do_futuro_por_lado * fator,
        )


PARAMETROS_DA_FICHA = Parametros()


@dataclass
class Resultado:
    ativo: str
    classe: str
    retorno: (
        pd.Series
    )  # diário, líquido, do primeiro pregão depois do aquecimento em diante
    patrimonio: pd.Series
    exposicao: pd.Series  # nocional ÷ patrimônio no fechamento
    alvos: pd.Series  # fração alvo executada em cada abertura
    negociado: pd.Series  # reais por pregão (+ compra, - venda), sem as rolagens
    custos: pd.Series  # emolumentos ou tarifa, spread e impacto das ordens, por pregão
    rolagem: pd.Series  # custo das duas pernas de cada rolagem (só futuros)
    imposto: pd.Series  # DARF pago, por pregão
    vendas: pd.Series
    resultado_realizado: (
        pd.Series
    )  # ganho por custo médio (à vista) ou ajuste diário (futuro)
    ir: pd.DataFrame  # a apuração mensal inteira (colunas de `COLUNAS_DO_IR`)
    giro: float  # valor negociado por ano ÷ patrimônio médio
    caixa_minimo: float  # menor caixa ÷ patrimônio (negativo = empréstimo para o DARF)
    day_trades: int  # pregões com compra e venda do mesmo instrumento
    parametros: Parametros = field(repr=False)

    def exposicao_media(self) -> float:
        return float(self.exposicao.mean())

    def anos(self) -> float:
        return len(self.retorno) / PREGOES_POR_ANO

    def meses_com_imposto(self) -> int:
        return int((self.ir["imposto"] > 0).sum()) if len(self.ir) else 0

    def meses_acima_da_isencao(self) -> int:
        """Meses em que as vendas passaram do teto de isenção (zero quando a classe não tem)."""
        teto = self.parametros.custos.isencao_no_mes(self.classe, day_trade=False)
        if teto <= 0 or not len(self.ir):
            return 0
        return int((self.ir["vendas"] > teto).sum())

    def custo_de_rolagem_por_ano(self) -> float:
        """Custo das rolagens por ano, como fração do patrimônio médio."""
        return float(self.rolagem.sum() / self.anos() / self.patrimonio.mean())


# --- as versões (o que cada uma negocia) -------------------------------------------------------------


def volume_conhecido(
    volume_em_reais: pd.Series, dias: int = DIAS_DO_VOLUME
) -> pd.Series:
    """Média dos `dias` pregões anteriores (sem o dia), para o impacto só usar o já conhecido."""
    return volume_em_reais.astype(float).rolling(dias, min_periods=1).mean().shift(1)


def excesso_a_vista(fechamento: pd.Series, cdi: pd.Series) -> pd.Series:
    """Retorno diário do fechamento menos o CDI do dia (zero no primeiro pregão)."""
    retorno = fechamento.astype(float).pct_change(fill_method=None)
    excesso = retorno - cdi.reindex(retorno.index)
    excesso.iloc[0] = 0.0
    return excesso


def a_vista(
    nome: str,
    abertura: pd.Series,
    fechamento: pd.Series,
    volume_em_reais: pd.Series,
    cdi: pd.Series,
    classe: str = "etf",
    lote: int = LOTE,
) -> Ativo:
    """Um papel à vista (BOVA11): preços reais do leilão de abertura e do fechamento."""
    fechamento = fechamento.astype(float)
    return Ativo(
        nome=nome,
        abertura=abertura.astype(float).reindex(fechamento.index),
        fechamento=fechamento,
        excesso=excesso_a_vista(fechamento, cdi),
        volume=volume_conhecido(volume_em_reais.reindex(fechamento.index)),
        classe=classe,
        lote=lote,
    )


def indice_do_excesso(excesso: pd.Series) -> pd.Series:
    """O índice que o sinal olha (e o nocional do futuro sintético): começa em 100."""
    return 100.0 * (1.0 + excesso.fillna(0.0)).cumprod()


def abertura_sintetica(
    indice: pd.Series, abertura_real: pd.Series, fechamento_real: pd.Series
) -> pd.Series:
    """O índice sintético no leilão de abertura: o de ontem levado pelo salto da abertura do
    ativo real sobre o fechamento de ontem."""
    salto = (abertura_real / fechamento_real.shift(1)).fillna(1.0)
    return (indice.shift(1) * salto).fillna(indice)


def win_sintetico(bova11: Ativo, cdi: pd.Series) -> Ativo:
    """O mini índice sintético: nocional pelo excesso do BOVA11 ao CDI, rolado nos meses pares.

    O volume para o impacto é o do BOVA11 (o do WIN é ordens de grandeza maior: erra contra).
    """
    excesso = excesso_do_win(bova11.fechamento, cdi)
    indice = indice_do_excesso(excesso)
    return Ativo(
        nome="WIN",
        abertura=abertura_sintetica(indice, bova11.abertura, bova11.fechamento),
        fechamento=indice,
        excesso=excesso,
        volume=bova11.volume,
        classe="futuros",
        lote=FRACIONARIO,
        valor_do_contrato=VALOR_DO_CONTRATO["WIN"],
        rolagens=datas_de_rolagem(bova11.datas, "WIN"),
    )


def di1_sintetico(curva: pd.DataFrame, cdi: pd.Series, bova11: Ativo) -> Ativo:
    """O DI1 sintético (prefixado de 2 anos menos CDI), rolado uma vez por ano.

    Sem leilão de abertura na série: a ordem executa na marcação do fechamento de D+1.
    """
    excesso = excesso_do_di1(curva, cdi, bova11.datas)
    indice = indice_do_excesso(excesso)
    return Ativo(
        nome="DI1",
        abertura=indice,
        fechamento=indice,
        excesso=excesso,
        volume=bova11.volume,
        classe="futuros",
        lote=FRACIONARIO,
        valor_do_contrato=VALOR_DO_CONTRATO["DI1"],
        rolagens=datas_de_rolagem(bova11.datas, "DI1"),
    )


def cesta(
    aberturas: pd.DataFrame,
    fechamentos: pd.DataFrame,
    volumes_em_reais: pd.DataFrame,
    cdi: pd.Series,
    nome: str = "cesta",
) -> Ativo:
    """Cesta de ações com pesos iguais, rebalanceada todo pregão entre os papéis que têm preço.

    É só a comparação de imposto do teste (b) (classe "acoes", isenção de R$ 20 mil); com dez
    papéis o lote de 100 em cada um seria outra simulação, então a quantidade é fracionária.
    """
    retorno = fechamentos.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    indice = 100.0 * (1.0 + retorno).cumprod()
    salto = (aberturas / fechamentos.shift(1)).mean(axis=1).fillna(1.0)
    abertura = (indice.shift(1) * salto).fillna(indice)
    excesso = retorno - cdi.reindex(retorno.index)
    excesso.iloc[0] = 0.0
    return Ativo(
        nome=nome,
        abertura=abertura,
        fechamento=indice,
        excesso=excesso,
        volume=volume_conhecido(volumes_em_reais.sum(axis=1)),
        classe="acoes",
        lote=FRACIONARIO,
    )


# --- a regra ---------------------------------------------------------------------------------------


def volatilidade_do_excesso(excesso: pd.Series, janela: int) -> pd.Series:
    return excesso.rolling(janela).std() * np.sqrt(PREGOES_POR_ANO)


def peso(ativo: Ativo, parametros: Parametros) -> pd.Series:
    """sinal (canais sobre o índice do excesso) × min(1; vol alvo ÷ σ do excesso)."""
    sigma = volatilidade_do_excesso(ativo.excesso, parametros.janela_da_vol)
    with np.errstate(divide="ignore"):
        escala = (parametros.vol_alvo / sigma).clip(upper=1.0)
    return tc.sinal(indice_do_excesso(ativo.excesso), parametros.janelas) * escala


def _primeiro_excesso(ativo: Ativo) -> int:
    primeiro = ativo.excesso.first_valid_index()
    if primeiro is None:
        raise ValueError(f"{ativo.nome}: a série do excesso está vazia")
    return int(ativo.datas.get_loc(primeiro))


def _inicio(ativo: Ativo) -> int:
    """A posição do primeiro pregão simulado: 360 pregões depois do primeiro excesso."""
    posicao = _primeiro_excesso(ativo) + AQUECIMENTO_EM_PREGOES
    if posicao >= len(ativo.datas):
        raise ValueError(
            f"{ativo.nome}: menos de {AQUECIMENTO_EM_PREGOES} pregões: nada sobra do aquecimento"
        )
    return posicao


def fracao_alvo(ativo: Ativo, parametros: Parametros) -> pd.Series:
    """A fração do patrimônio que a regra pede no fechamento de cada pregão (0 no aquecimento)."""
    alvo = peso(ativo, parametros).fillna(0.0).clip(lower=0.0, upper=1.0)
    alvo.iloc[: _inicio(ativo)] = 0.0
    return alvo


escalar_janelas = tc.escalar_janelas


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia dos parâmetros com algumas mudanças (vizinhos, estresse, bruto)."""
    return replace(parametros, **mudancas)


# --- a simulação -----------------------------------------------------------------------------------


def _conferir_entradas(ativo: Ativo, cdi: pd.Series) -> None:
    if cdi.reindex(ativo.datas).isna().any():
        raise ValueError(f"{ativo.nome}: CDI faltando em algum pregão")


def _custo_do_futuro(nocional: float, ativo: Ativo, parametros: Parametros) -> float:
    """Um lado de uma ordem no futuro: tarifa por contrato (fração aceita) mais o spread."""
    return (
        custo_de_negociar(
            nocional,
            "futuros",
            contratos=nocional / ativo.valor_do_contrato,
            custos=parametros.custos,
        )
        + nocional * parametros.spread_do_futuro_por_lado
    )


def _custo_da_ordem(
    valor: float,
    sigma_diaria: float,
    volume: float,
    ativo: Ativo,
    parametros: Parametros,
) -> float:
    if ativo.futuro:
        bolsa = _custo_do_futuro(valor, ativo, parametros)
    else:
        bolsa = custo_de_negociar(
            valor, ativo.classe, no_leilao=True, custos=parametros.custos
        )
    return bolsa + tc.impacto(valor, sigma_diaria, volume, parametros.fator_de_impacto)


def _ultimo_pregao_do_mes(datas: pd.DatetimeIndex, i: int) -> bool:
    return i == len(datas) - 1 or datas[i + 1].month != datas[i].month


class _Posicao:
    """Quantidade, custo médio e caixa; sabe comprar e vender à vista ou no futuro."""

    def __init__(self, capital: float, futuro: bool) -> None:
        self.caixa = capital
        self.quantidade = 0.0
        self.custo_medio = 0.0
        self.futuro = futuro

    def valor(self, preco: float) -> float:
        """O que a posição vale no patrimônio: zero no futuro (o ajuste já foi para o caixa)."""
        return 0.0 if self.futuro else self.quantidade * preco

    def nocional(self, preco: float) -> float:
        return self.quantidade * preco

    def patrimonio(self, preco: float) -> float:
        return self.caixa + self.valor(preco)

    def ajustar(self, de: float, para: float) -> float:
        """Ajuste diário do futuro: a diferença de preço vezes a quantidade, no caixa."""
        ajuste = self.quantidade * (para - de)
        self.caixa += ajuste
        return ajuste

    def negociar(self, q: float, preco: float) -> tuple[float, float]:
        """Compra (q > 0) ou vende (q < 0) `q` unidades a `preco`; devolve (vendas, resultado)."""
        if self.futuro:
            self.quantidade += q
            return (abs(q) * preco if q < 0 else 0.0), 0.0
        if q > 0:
            total = self.quantidade * self.custo_medio + q * preco
            self.quantidade += q
            self.custo_medio = total / self.quantidade
            self.caixa -= q * preco
            return 0.0, 0.0
        vendido = -q * preco
        resultado = -q * (preco - self.custo_medio)
        self.quantidade += q
        if self.quantidade <= 1e-9:
            self.quantidade = 0.0
            self.custo_medio = 0.0
        self.caixa += vendido
        return vendido, resultado


def _imposto_dos_meses(
    vendas: pd.Series,
    resultado: pd.Series,
    meses: pd.PeriodIndex,
    classe: str,
    custos: CustosBR,
) -> float:
    if len(meses) == 0 or vendas.empty:
        return 0.0
    tabela = apurar_ir_mensal(vendas, resultado, classe, custos=custos)
    return float(tabela["imposto"].reindex(meses).fillna(0.0).sum())


def _quantidade_da_ordem(delta: float, preco: float, lote: int) -> float:
    q = delta / preco
    return float(arredondar_lote(q, lote=lote)) if lote else q


def simular(
    ativo: Ativo,
    cdi: pd.Series,
    parametros: Parametros = PARAMETROS_DA_FICHA,
    capital: float = CAPITAL_INICIAL,
) -> Resultado:
    """Simula a regra pregão a pregão numa versão da ficha; `cdi` é o retorno do caixa por pregão."""
    _conferir_entradas(ativo, cdi)
    datas = ativo.datas
    atraso = -1 if parametros.olhar_o_futuro else ATRASO_DA_EXECUCAO
    alvos = fracao_alvo(ativo, parametros).shift(atraso).fillna(0.0)
    sigma = (
        ativo.fechamento.pct_change(fill_method=None)
        .rolling(parametros.janela_da_vol)
        .std()
        .fillna(0.0)
        .to_numpy(float)
    )
    ab = ativo.abertura.to_numpy(float)
    fe = ativo.fechamento.to_numpy(float)
    a = alvos.to_numpy(float)
    v = ativo.volume.to_numpy(float)
    c = cdi.reindex(datas).to_numpy(float)
    rolagens = set(ativo.rolagens)
    custos = parametros.custos
    n = len(datas)
    inicio = _inicio(ativo)

    retorno = np.full(n, np.nan)
    patrimonio = np.full(n, np.nan)
    exposicao = np.zeros(n)
    negociado = np.zeros(n)
    custo_do_dia = np.zeros(n)
    rolagem_do_dia = np.zeros(n)
    imposto_do_dia = np.zeros(n)
    vendas = np.zeros(n)
    realizado = np.zeros(n)
    compras_e_vendas = np.zeros((n, 2))
    caixa_minimo = 1.0

    posicao = _Posicao(capital, ativo.futuro)
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
            ativo.classe,
            custos,
        )
        imposto_do_dia[i] += devido
        posicao.caixa -= devido
        pago_ate = max(pago_ate, ate_o_mes)

    for i in range(inicio, n):
        dia = datas[i]
        posicao.caixa *= 1 + c[i]
        mes = dia.to_period("M")
        if _ultimo_pregao_do_mes(datas, i):
            pagar(i, mes - 1, incluir_hoje=False)
        if ativo.futuro:
            realizado[i] += posicao.ajustar(fe[i - 1], ab[i])
            if dia in rolagens and posicao.quantidade != 0.0:
                custo = PERNAS_DA_ROLAGEM * _custo_do_futuro(
                    abs(posicao.nocional(ab[i])), ativo, parametros
                )
                posicao.caixa -= custo
                rolagem_do_dia[i] += custo
        patrimonio_antes = posicao.patrimonio(ab[i])
        delta = a[i] * patrimonio_antes - posicao.nocional(ab[i])
        if abs(delta) >= BANDA_MINIMA * patrimonio_antes:
            q = _quantidade_da_ordem(delta, ab[i], ativo.lote)
            if q != 0.0:
                valor = abs(q) * ab[i]
                custo = _custo_da_ordem(valor, sigma[i], v[i], ativo, parametros)
                vendido, resultado = posicao.negociar(q, ab[i])
                posicao.caixa -= custo
                negociado[i] = q * ab[i]
                custo_do_dia[i] += custo
                vendas[i] += vendido
                realizado[i] += resultado
                compras_e_vendas[i, 0 if q > 0 else 1] += 1
        if ativo.futuro:
            realizado[i] += posicao.ajustar(ab[i], fe[i])
        if i == n - 1:
            pagar(i, mes, incluir_hoje=True)
        fechamento = posicao.patrimonio(fe[i])
        patrimonio[i] = fechamento
        retorno[i] = fechamento / anterior - 1
        exposicao[i] = posicao.nocional(fe[i]) / fechamento
        caixa_minimo = min(caixa_minimo, posicao.caixa / fechamento)
        anterior = fechamento

    simulado = datas[inicio:]

    def serie(valores: np.ndarray) -> pd.Series:
        return pd.Series(valores[inicio:], index=simulado)

    anos = len(simulado) / PREGOES_POR_ANO
    return Resultado(
        ativo=ativo.nome,
        classe=ativo.classe,
        retorno=serie(retorno),
        patrimonio=serie(patrimonio),
        exposicao=serie(exposicao),
        alvos=alvos.iloc[inicio:],
        negociado=serie(negociado),
        custos=serie(custo_do_dia),
        rolagem=serie(rolagem_do_dia),
        imposto=serie(imposto_do_dia),
        vendas=serie(vendas),
        resultado_realizado=serie(realizado),
        ir=apurar_ir_mensal(
            serie(vendas), serie(realizado), ativo.classe, custos=custos
        ),
        giro=float(
            np.abs(negociado[inicio:]).sum() / anos / np.nanmean(patrimonio[inicio:])
        ),
        caixa_minimo=float(caixa_minimo),
        day_trades=int((compras_e_vendas[inicio:] > 0).all(axis=1).sum()),
        parametros=parametros,
    )


# --- réguas e verificações ---------------------------------------------------------------------------


def comprar_e_segurar(
    ativo: Ativo, parametros: Parametros, capital: float = CAPITAL_INICIAL
) -> pd.Series:
    """Compra tudo no leilão de abertura do primeiro pregão simulado (pagando emolumentos e
    impacto) e segue o fechamento; não vende, então não paga IR. Sem arredondar o lote."""
    inicio = _inicio(ativo)
    sigma = (
        ativo.fechamento.pct_change(fill_method=None)
        .rolling(parametros.janela_da_vol)
        .std()
    )
    custo = _custo_da_ordem(
        capital,
        float(np.nan_to_num(sigma.iloc[inicio])),
        float(ativo.volume.iloc[inicio]),
        ativo,
        parametros,
    )
    retorno = ativo.fechamento.iloc[inicio:].pct_change(fill_method=None)
    retorno.iloc[0] = (
        ativo.fechamento.iloc[inicio] / ativo.abertura.iloc[inicio]
        - 1
        - custo / capital
    )
    return retorno


def sharpe_do_excesso(retorno: pd.Series, cdi: pd.Series) -> float:
    """Sharpe (252) do excesso sobre o caixa, pregão a pregão."""
    return avaliacao.sharpe((retorno - cdi.reindex(retorno.index)).dropna())


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do retorno e do patrimônio (reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.patrimonio.round(6).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def cortar_o_futuro_nao_muda_o_passado(
    ativo: Ativo,
    cdi: pd.Series,
    parametros: Parametros,
    corte: pd.Timestamp,
    capital: float = CAPITAL_INICIAL,
) -> bool:
    """Rodar só até `corte` dá, até a véspera do corte, o mesmo retorno de rodar tudo.

    O pregão do corte fica de fora: na série cortada ele é o último dos dados e paga o IR que
    ainda não venceu, o que não é olhar o futuro, é o fim dos dados.
    """
    inteiro = simular(ativo, cdi, parametros, capital)
    cortado = simular(ativo.ate(corte), cdi.loc[:corte], parametros, capital)
    return bool(
        np.allclose(
            inteiro.retorno.loc[inteiro.retorno.index < corte].to_numpy(),
            cortado.retorno.loc[cortado.retorno.index < corte].to_numpy(),
            rtol=0,
            atol=1e-12,
        )
    )
