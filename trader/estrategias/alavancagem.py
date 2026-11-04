"""Alavancagem da camada A1 (o núcleo) a 1,3x via WIN ou DI1 (pré-registro v0.1, seção 7).

Só duas versões existem, as duas pré-registradas: **1,0x** (a própria base) e **1,3x**; nada entre
elas. A 1,3x é a base inteira mais um futuro cujo nocional faz a exposição total dividida pelo
patrimônio dar 1,3 nos dias de ajuste (primeiro pregão de cada mês e dias de rolagem). A margem do
futuro sai da base e rende CDI; o ajuste diário do futuro entra e sai desse caixa; a rolagem segue o
calendário (`trader/calendario.py`) e custa tarifa, corretagem e spread nos dois lados.

A 1,3x só entra se passar o critério inteiro, inclusive F1 (queda máxima ≤ 35%); se reprovar e a
1,0x passar, a camada opera a 1,0x (`versao_que_entra`). Nada aqui olha o futuro: o nocional de
hoje vem do patrimônio de ontem à noite (há teste de que cortar o futuro não muda o passado).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from trader import avaliacao, calendario, criterio_quant
from trader.custos_br import PADRAO, CustosBR, custo_de_negociar

VERSAO = "0.1"
FATORES = criterio_quant.ALAVANCAGENS_DO_NUCLEO
INSTRUMENTOS = ("WIN", "DI1")
# Margem exigida como fração do nocional (a confirmar na tabela da B3; o WIN pede mais que o DI1).
MARGEM_DO_FUTURO = {"WIN": 0.15, "DI1": 0.05}
# Valor aproximado de um contrato, em reais, só para contar a tarifa por contrato.
VALOR_DO_CONTRATO = {"WIN": 20_000.0, "DI1": 80_000.0}
SPREAD_POR_LADO = 0.0001  # um ponto-base do nocional por lado (a confirmar)
MARGEM_DE_AVISO = criterio_quant.MARGEM_DE_AVISO
PRAZO_DO_DI1_EM_ANOS = 2
PREGOES_POR_ANO = 252


@dataclass(frozen=True)
class Parametros:
    fator: float = 1.3
    instrumento: str = "WIN"
    margem: float | None = None  # fração do nocional; padrão por instrumento
    valor_do_contrato: float | None = None  # reais; padrão por instrumento
    spread_por_lado: float = SPREAD_POR_LADO
    custos: CustosBR = PADRAO

    def __post_init__(self) -> None:
        if self.fator not in FATORES:
            raise ValueError(
                f"a alavancagem do núcleo é 1,0x ou 1,3x, nada entre as duas; recebi {self.fator}"
            )
        if self.instrumento not in INSTRUMENTOS:
            raise ValueError(f"instrumento desconhecido: {self.instrumento}")
        if self.margem is None:
            object.__setattr__(self, "margem", MARGEM_DO_FUTURO[self.instrumento])
        if self.valor_do_contrato is None:
            object.__setattr__(
                self, "valor_do_contrato", VALOR_DO_CONTRATO[self.instrumento]
            )

    def em_estresse(self, fator: float = 2.0) -> Parametros:
        """Custos de corretora e bolsa e o spread multiplicados (A8)."""
        return replace(
            self,
            custos=self.custos.em_estresse(fator),
            spread_por_lado=self.spread_por_lado * fator,
        )

    def especificacao(self) -> dict:
        """Tudo o que define a versão alavancada, em tipos simples (vai para o registro)."""
        custos = asdict(self.custos)
        custos["a_confirmar"] = list(custos["a_confirmar"])
        return {
            "alavancagem": self.fator,
            "instrumento": self.instrumento,
            "margem": self.margem,
            "valor_do_contrato": self.valor_do_contrato,
            "spread_por_lado": self.spread_por_lado,
            "custos": custos,
            "versao_da_alavancagem": VERSAO,
        }


@dataclass
class Resultado:
    retorno: pd.Series  # diário, líquido
    patrimonio: pd.Series
    exposicao: pd.Series  # exposição total ÷ patrimônio, todo dia
    nocional: pd.Series  # do futuro, em reais
    margem: pd.Series  # margem exigida ÷ patrimônio
    custos: pd.Series  # reais por dia (rolagem, ajustes e caixa movido)
    rolagens: tuple[pd.Timestamp, ...]
    parametros: Parametros

    def dias_com_margem_acima(self, limite: float = MARGEM_DE_AVISO) -> int:
        """Quantos dias a margem exigida passou da fração do patrimônio (aviso de chamada)."""
        return int((self.margem > limite).sum())

    def custo_de_rolagem_por_ano(self) -> float:
        """Custo das rolagens como fração do patrimônio médio, por ano."""
        anos = len(self.retorno) / PREGOES_POR_ANO
        if anos == 0 or not self.rolagens:
            return 0.0
        return float(
            self.custos[list(self.rolagens)].sum() / self.patrimonio.mean() / anos
        )


def com(parametros: Parametros, **mudancas: object) -> Parametros:
    """Uma cópia dos parâmetros com algumas mudanças (estresse, bruto, 1,0x)."""
    return replace(parametros, **mudancas)


def datas_de_rolagem(
    datas: pd.DatetimeIndex, instrumento: str
) -> tuple[pd.Timestamp, ...]:
    """Os pregões em que o backtest troca de contrato.

    WIN: o pregão anterior a cada vencimento (meses pares). DI1: o dia em que o contrato de
    janeiro mais perto de 2 anos passa a ser o do ano seguinte (perto de julho).
    """
    if instrumento == "WIN":
        inicio, fim = datas.min().date(), datas.max().date()
        rolagens = []
        for vencimento in calendario.vencimentos_do_win(inicio, fim):
            dia = pd.Timestamp(
                calendario.rolagem_do_win(vencimento.year, vencimento.month)
            )
            no_calendario = datas[datas <= dia]
            if len(no_calendario) and no_calendario[-1] > datas[0]:
                rolagens.append(no_calendario[-1])
        return tuple(dict.fromkeys(rolagens))
    codigos = [
        calendario.di1_de_janeiro(dia.date(), PRAZO_DO_DI1_EM_ANOS) for dia in datas
    ]
    return tuple(
        datas[posicao]
        for posicao in range(1, len(datas))
        if codigos[posicao] != codigos[posicao - 1]
    )


def _primeiros_pregoes_dos_meses(datas: pd.DatetimeIndex) -> set[pd.Timestamp]:
    meses = pd.Series(datas.to_period("M"), index=datas)
    return set(datas[meses.ne(meses.shift(1)).to_numpy()])


def _alinhar(serie: pd.Series, datas: pd.DatetimeIndex, nome: str) -> np.ndarray:
    alinhada = serie.reindex(datas)
    if alinhada.isna().any():
        raise ValueError(
            f"{nome} faltando em {alinhada.index[alinhada.isna()][0].date()}"
        )
    return alinhada.to_numpy(dtype=float)


def simular(
    base: pd.Series,
    cdi: pd.Series,
    excesso_do_futuro: pd.Series,
    parametros: Parametros,
    capital_inicial: float = 100_000.0,
) -> Resultado:
    """A camada A1 alavancada: base, mais o futuro, mais a margem em CDI, menos os custos.

    `base` é o retorno diário líquido da camada a 1,0x; `excesso_do_futuro` é o que o futuro rende
    por dia sobre o nocional, já descontado o CDI. Todo dia: a parte na base rende a base, o caixa
    de margem rende CDI e recebe o ajuste do futuro; o nocional anda com o índice. No primeiro
    pregão do mês e nas rolagens o nocional e a margem voltam ao alvo.
    """
    datas = pd.DatetimeIndex(base.index)
    retorno_da_base = base.to_numpy(dtype=float)
    cdi_do_dia = _alinhar(cdi, datas, "CDI")
    excesso = _alinhar(excesso_do_futuro, datas, "excesso do futuro")
    alavancado = parametros.fator > 1.0
    rolagens = datas_de_rolagem(datas, parametros.instrumento) if alavancado else ()
    ajustes = (
        _primeiros_pregoes_dos_meses(datas) | set(rolagens) | {pd.Timestamp(datas[0])}
    )
    margem, valor_do_contrato = parametros.margem, parametros.valor_do_contrato
    assert margem is not None and valor_do_contrato is not None
    patrimonio = np.empty(len(datas))
    exposicao = np.empty(len(datas))
    nocionais = np.empty(len(datas))
    margens = np.empty(len(datas))
    custos = np.zeros(len(datas))
    na_base = capital_inicial
    caixa = 0.0
    nocional = 0.0
    for posicao, dia in enumerate(datas):
        na_base *= 1 + retorno_da_base[posicao]
        caixa = caixa * (1 + cdi_do_dia[posicao]) + nocional * excesso[posicao]
        nocional *= 1 + excesso[posicao] + cdi_do_dia[posicao]
        custo = 0.0
        if dia in rolagens and nocional > 0:
            custo += 2 * _custo_do_futuro(nocional, parametros)
        if alavancado and dia in ajustes:
            total = na_base + caixa - custo
            alvo_do_nocional = (parametros.fator - 1) * total / (1 - margem)
            alvo_do_caixa = margem * alvo_do_nocional
            custo += _custo_do_futuro(abs(alvo_do_nocional - nocional), parametros)
            movido = alvo_do_caixa - caixa
            custo += custo_de_negociar(abs(movido), "acoes", custos=parametros.custos)
            na_base -= movido
            caixa, nocional = alvo_do_caixa, alvo_do_nocional
        caixa -= custo
        total = na_base + caixa
        patrimonio[posicao] = total
        exposicao[posicao] = (na_base + nocional) / total
        nocionais[posicao] = nocional
        margens[posicao] = margem * nocional / total
        custos[posicao] = custo
    serie_do_patrimonio = pd.Series(patrimonio, index=datas)
    retorno = serie_do_patrimonio.pct_change(fill_method=None)
    retorno.iloc[0] = patrimonio[0] / capital_inicial - 1
    return Resultado(
        retorno=retorno,
        patrimonio=serie_do_patrimonio,
        exposicao=pd.Series(exposicao, index=datas),
        nocional=pd.Series(nocionais, index=datas),
        margem=pd.Series(margens, index=datas),
        custos=pd.Series(custos, index=datas),
        rolagens=tuple(rolagens),
        parametros=parametros,
    )


def _custo_do_futuro(nocional: float, parametros: Parametros) -> float:
    """Um lado de uma ordem no futuro: tarifa por contrato, corretagem e spread."""
    if nocional == 0:
        return 0.0
    assert parametros.valor_do_contrato is not None
    contratos = nocional / parametros.valor_do_contrato
    return (
        custo_de_negociar(
            nocional, "futuros", contratos=contratos, custos=parametros.custos
        )
        + nocional * parametros.spread_por_lado
    )


def cai_para_1_0x(resultado: Resultado) -> bool:
    """F1: a versão alavancada que cai mais de 35% do pico não entra; a camada fica a 1,0x."""
    return avaliacao.maior_queda(resultado.retorno) < -criterio_quant.QUEDA_MAXIMA


def versao_que_entra(*, aprovada_1_0: bool, aprovada_1_3: bool) -> float | None:
    """1,3x se passou o critério inteiro; senão 1,0x se ela passou; senão nenhuma."""
    if aprovada_1_3:
        return 1.3
    if aprovada_1_0:
        return 1.0
    return None


def hash_do_resultado(resultado: Resultado) -> str:
    """Impressão digital do retorno e do patrimônio (reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.patrimonio.round(6).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def cortar_o_futuro_nao_muda_o_passado(
    base: pd.Series,
    cdi: pd.Series,
    excesso_do_futuro: pd.Series,
    parametros: Parametros,
    corte: pd.Timestamp,
    capital_inicial: float = 100_000.0,
) -> bool:
    """Rodar só até a véspera de `corte` dá o mesmo retorno de rodar tudo, até lá."""
    inteiro = simular(base, cdi, excesso_do_futuro, parametros, capital_inicial)
    cortado = simular(
        base[base.index < corte], cdi, excesso_do_futuro, parametros, capital_inicial
    )
    return bool(
        np.allclose(cortado.retorno, inteiro.retorno[inteiro.retorno.index < corte])
    )
