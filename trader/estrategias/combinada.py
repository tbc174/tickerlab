"""Carteira combinada das camadas, ficha C-1 do pré-registro quant v0.2 (seção 9).

Convenções fixadas AQUI, antes de qualquer número (seção 10: mudar depois de ver um resultado é
tentativa nova):

- **Entradas.** Uma tabela de retornos diários líquidos, uma coluna por camada, no calendário dos
  pregões da B3 (NaN antes do início de cada camada), e o CDI do dia. A cripto chega em dias
  corridos e é composta no pregão seguinte por `compor_no_pregao` antes de entrar.
- **Freio.** Cada camada entra com o freio de 40% da seção 6 (`trader/freios.py`), aplicado aqui
  sobre a série sem freio da camada (`serie_freada`), como a camada operaria.
- **Pesos.** No primeiro pregão D de cada mês: entram as camadas com pelo menos `janela` retornos
  até D; σ = desvio dos `janela` últimos retornos do excesso sobre o CDI até D; peso-alvo ∝ 1 ÷ σ,
  com teto por camada repetido até nenhuma passar dele (σ zero vai direto ao teto); se todas
  estão no teto, a sobra fica no CDI. Banda: só volta ao alvo se alguma camada está mais de
  `banda` × alvo longe do alvo dela, e então todas voltam. A primeira alocação acontece no
  primeiro D com pelo menos duas camadas, e o período avaliado começa no pregão seguinte.
- **Execução.** Os pesos decididos em D valem a partir do retorno de D+1 (texto da ficha). Entre
  um rebalanceamento e outro, os pesos andam com o retorno de cada camada. Camada sem retorno num
  pregão depois do início rende o CDI (o caixa que ela já tem).
- **Custo e imposto da troca.** O valor trocado (soma das compras e das vendas entre camadas)
  paga o custo à vista da seção 3 (`custo_de_negociar`, classe "acoes", com a corretagem fixa
  zero da tabela; patrimônio normalizado em 1). O valor retirado de uma camada paga 15% de IR
  sobre a parte que é lucro, medida pelo retorno da camada desde a última vez que ela recebeu
  dinheiro, sem isenção e sem compensar prejuízo entre camadas (aproximação conservadora).
  Custo e imposto saem do patrimônio no dia da execução.
- **Olhar o futuro** (`olhar_o_futuro=True`): a σ da decisão em D usa os retornos de D+1 até
  D+`janela`. Serve só para o teste V1 provar que o motor rende diferente quando vê o futuro.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from trader import freios
from trader.criterio_quant import FATOR_DO_PLATO_ABAIXO, FATOR_DO_PLATO_ACIMA
from trader.custos_br import PADRAO, CustosBR, custo_de_negociar

VERSAO = "0.1"
JANELA = 252
TETO = 0.40
BANDA = 0.20
MINIMO_DE_CAMADAS = 2
CLASSE_DA_TROCA = "acoes"
TOLERANCIA = 1e-12
# O bruto (A4) da troca entre camadas: sem corretagem, emolumentos nem IR.
SEM_CUSTOS_DA_TROCA = replace(
    PADRAO, corretagem_por_ordem=0.0, emolumentos_a_vista=0.0, ir_swing=0.0
)

# Camadas da candidata (seção 9, tabela da ficha C-1) e da comparação (escolhida olhando o
# resultado; o relatório diz isso ao lado de cada número dela).
CAMADAS_DA_CANDIDATA = ("P0-3", "F-B3", "P0-1", "P0-2 BOVA11", "P0-4", "P0-5")
CAMADAS_DA_COMPARACAO = ("P0-3", "P0-1", "P0-2 DI1")
CAMADAS_DE_CRIPTO = ("P0-1",)


@dataclass(frozen=True)
class ParametrosC1:
    """Os parâmetros fixos da ficha; o platô (A3) mexe ±20% em `janela`, `teto` e `banda`."""

    janela: int = JANELA
    teto: float = TETO
    banda: float = BANDA
    olhar_o_futuro: bool = False

    def hash(self) -> str:
        texto = repr(sorted(asdict(self).items()))
        return hashlib.sha256(texto.encode()).hexdigest()


@dataclass(frozen=True)
class ResultadoC1:
    """A combinação dia a dia, do primeiro pregão avaliado ao último."""

    retorno: pd.Series  # líquido de custo e imposto da troca
    bruto: pd.Series  # sem o custo e o imposto da troca (as camadas já vêm líquidas)
    pesos: pd.DataFrame  # peso de cada camada no começo de cada pregão (a sobra é CDI)
    custo: pd.Series  # custo da troca, como fração do patrimônio do dia
    imposto: pd.Series  # IR da troca, como fração do patrimônio do dia
    decisoes: tuple[pd.Timestamp, ...]  # os D em que a carteira voltou ao alvo
    parametros: ParametrosC1


def compor_no_pregao(
    retorno_corrido: pd.Series, pregoes: pd.DatetimeIndex
) -> pd.Series:
    """Leva retornos em dias corridos ao calendário dos pregões, compondo os dias sem pregão.

    Cada dia corrido vai para o primeiro pregão igual ou posterior a ele. Dias depois do último
    pregão ficam de fora. Pregão sem nenhum dia corrido da série fica NaN.
    """
    if retorno_corrido.empty:
        return pd.Series(np.nan, index=pregoes, name=retorno_corrido.name)
    posicoes = pregoes.searchsorted(retorno_corrido.index, side="left")
    dentro = posicoes < len(pregoes)
    destino = pregoes[posicoes[dentro]]
    fatores = (1 + retorno_corrido[dentro]).groupby(destino).prod()
    composto = (fatores - 1).reindex(pregoes)
    composto.name = retorno_corrido.name
    return composto


def freio_da_camada(retorno: pd.Series, cdi: pd.Series) -> freios.Freio | None:
    """O freio de 40% da seção 6 sobre a camada, do primeiro retorno dela em diante."""
    valida = retorno.dropna()
    if valida.empty:
        return None
    trecho = retorno.loc[valida.index[0] :].fillna(cdi)
    return freios.aplicar_freio(trecho, cdi)


def serie_freada(retorno: pd.Series, cdi: pd.Series) -> pd.Series:
    """A série da camada com o freio de 40% da seção 6, a partir do primeiro retorno dela."""
    freio = freio_da_camada(retorno, cdi)
    if freio is None:
        return retorno
    return freio.retorno.reindex(retorno.index)


def pesos_alvo(sigmas: Mapping[str, float], teto: float = TETO) -> dict[str, float]:
    """Peso ∝ 1 ÷ σ com teto por camada, repetido até ninguém passar do teto.

    σ zero vai direto ao teto (1 ÷ σ seria infinito). Se todas ficam no teto, a soma fica abaixo
    de 1 e a sobra é CDI.
    """
    if not sigmas:
        return {}
    if any(s < 0 or not np.isfinite(s) for s in sigmas.values()):
        raise ValueError(f"σ inválido: {dict(sigmas)}")
    if len(sigmas) * teto < 1 - TOLERANCIA:
        return dict.fromkeys(sigmas, teto)
    pesos = {nome: teto for nome, s in sigmas.items() if s == 0}
    if sum(pesos.values()) > 1 + TOLERANCIA:
        raise ValueError("camadas com σ zero demais para o teto")
    livres = {nome: 1 / s for nome, s in sigmas.items() if s > 0}
    while livres:
        resto = 1 - sum(pesos.values())
        total = sum(livres.values())
        proposta = {nome: resto * inverso / total for nome, inverso in livres.items()}
        acima = [nome for nome, peso in proposta.items() if peso > teto + TOLERANCIA]
        if not acima:
            pesos.update(proposta)
            break
        for nome in acima:
            pesos[nome] = teto
            del livres[nome]
    return pesos


def fora_da_banda(
    atuais: Mapping[str, float], alvos: Mapping[str, float], banda: float = BANDA
) -> bool:
    """Alguma camada está mais de `banda` × alvo longe do alvo dela (ou fora do alvo)?"""
    for nome in set(atuais) | set(alvos):
        alvo = alvos.get(nome, 0.0)
        atual = atuais.get(nome, 0.0)
        if alvo == 0.0:
            if atual > TOLERANCIA:
                return True
        elif abs(atual - alvo) > banda * alvo:
            return True
    return False


def _cdi_nos_pregoes(cdi: pd.Series, datas: pd.DatetimeIndex) -> np.ndarray:
    alinhado = cdi.reindex(datas)
    if alinhado.isna().any():
        raise ValueError(f"CDI faltando em {alinhado.index[alinhado.isna()][0].date()}")
    return alinhado.to_numpy(dtype=float)


def _primeiros_do_mes(datas: pd.DatetimeIndex) -> np.ndarray:
    mes = datas.year * 12 + datas.month
    primeiro = np.zeros(len(datas), dtype=bool)
    primeiro[1:] = mes[1:] != mes[:-1]
    return primeiro


def _sigmas_em(
    excesso: pd.DataFrame,
    contagem: pd.DataFrame,
    posicao: int,
    janela: int,
    olhar_o_futuro: bool,
) -> dict[str, float]:
    sigmas: dict[str, float] = {}
    for nome in excesso.columns:
        if contagem[nome].iloc[posicao] < janela:
            continue
        if olhar_o_futuro:
            trecho = excesso[nome].iloc[posicao + 1 : posicao + 1 + janela].dropna()
            if len(trecho) < janela:
                continue
        else:
            trecho = excesso[nome].iloc[: posicao + 1].dropna().iloc[-janela:]
        sigmas[nome] = float(trecho.std())
    return sigmas


def _executar(
    valores: dict[str, float],
    caixa: float,
    ganho: dict[str, float],
    alvos: Mapping[str, float],
    custos: CustosBR,
) -> tuple[dict[str, float], float, float, float]:
    """Volta ao alvo; devolve os valores novos, o caixa, o custo e o imposto (em fração)."""
    patrimonio = sum(valores.values()) + caixa
    nomes = set(valores) | set(alvos)
    novos = {nome: alvos.get(nome, 0.0) * patrimonio for nome in nomes}
    trocado = sum(abs(novos[n] - valores.get(n, 0.0)) for n in nomes)
    custo = custo_de_negociar(trocado, CLASSE_DA_TROCA, custos=custos)
    imposto = 0.0
    for nome in nomes:
        diferenca = novos[nome] - valores.get(nome, 0.0)
        if diferenca < 0:
            fator = ganho.get(nome, 1.0)
            parte_lucro = max(0.0, 1 - 1 / fator)
            imposto += -diferenca * parte_lucro * custos.ir_swing
        elif diferenca > 0:
            ganho[nome] = 1.0
    caixa_novo = patrimonio - sum(novos.values())
    desconto = (custo + imposto) / patrimonio
    novos = {nome: valor * (1 - desconto) for nome, valor in novos.items()}
    return novos, caixa_novo * (1 - desconto), custo, imposto


def combinar(
    retornos: pd.DataFrame,
    cdi: pd.Series,
    parametros: ParametrosC1 | None = None,
    custos: CustosBR = PADRAO,
) -> ResultadoC1:
    """Simula a C-1 sobre as camadas (já freadas e no calendário dos pregões)."""
    parametros = parametros or ParametrosC1()
    datas = pd.DatetimeIndex(retornos.index)
    cdi_do_dia = _cdi_nos_pregoes(cdi, datas)
    excesso = retornos.sub(cdi_do_dia, axis=0)
    contagem = retornos.notna().cumsum()
    primeiros = _primeiros_do_mes(datas)
    valores: dict[str, float] = {}
    ganho: dict[str, float] = {}
    caixa = 1.0
    pendente: dict[str, float] | None = None
    comecou = False
    linhas: list[tuple[pd.Timestamp, float, float, float, float, dict[str, float]]] = []
    decisoes: list[pd.Timestamp] = []
    for posicao, dia in enumerate(datas):
        custo = imposto = 0.0
        if pendente is not None:
            valores, caixa, custo, imposto = _executar(
                valores, caixa, ganho, pendente, custos
            )
            pendente = None
        if comecou:
            depois_da_troca = sum(valores.values()) + caixa
            inicio = depois_da_troca + custo + imposto
            pesos = {nome: valor / depois_da_troca for nome, valor in valores.items()}
            for nome in valores:
                r = retornos[nome].iloc[posicao]
                r = cdi_do_dia[posicao] if np.isnan(r) else float(r)
                valores[nome] *= 1 + r
                ganho[nome] *= 1 + r
            caixa *= 1 + cdi_do_dia[posicao]
            fim = sum(valores.values()) + caixa
            bruto = (fim + custo + imposto) / inicio - 1
            linhas.append(
                (dia, fim / inicio - 1, bruto, custo / inicio, imposto / inicio, pesos)
            )
        if not primeiros[posicao] or posicao + 1 >= len(datas):
            continue
        sigmas = _sigmas_em(
            excesso, contagem, posicao, parametros.janela, parametros.olhar_o_futuro
        )
        if not comecou and len(sigmas) < MINIMO_DE_CAMADAS:
            continue
        alvos = pesos_alvo(sigmas, parametros.teto)
        patrimonio = sum(valores.values()) + caixa
        atuais = {nome: valor / patrimonio for nome, valor in valores.items()}
        if not comecou or fora_da_banda(atuais, alvos, parametros.banda):
            pendente = alvos
            decisoes.append(dia)
            comecou = True
    return _montar(linhas, retornos.columns, decisoes, parametros)


def _montar(
    linhas: list[tuple[pd.Timestamp, float, float, float, float, dict[str, float]]],
    camadas: pd.Index,
    decisoes: list[pd.Timestamp],
    parametros: ParametrosC1,
) -> ResultadoC1:
    indice = pd.DatetimeIndex([linha[0] for linha in linhas])
    pesos = pd.DataFrame(
        [linha[5] for linha in linhas], index=indice, columns=camadas
    ).fillna(0.0)
    return ResultadoC1(
        retorno=pd.Series([linha[1] for linha in linhas], index=indice, name="C-1"),
        bruto=pd.Series([linha[2] for linha in linhas], index=indice),
        pesos=pesos,
        custo=pd.Series([linha[3] for linha in linhas], index=indice),
        imposto=pd.Series([linha[4] for linha in linhas], index=indice),
        decisoes=tuple(decisoes),
        parametros=parametros,
    )


def hash_do_resultado(resultado: ResultadoC1) -> str:
    """Impressão digital do retorno e dos pesos (V2, reexecução idêntica)."""
    bruto = (
        resultado.retorno.round(12).to_numpy().tobytes()
        + resultado.pesos.round(12).to_numpy().tobytes()
    )
    return hashlib.sha256(bruto).hexdigest()


def variacoes_do_plato(parametros: ParametrosC1 | None = None) -> list[ParametrosC1]:
    """As seis vizinhas do platô (A3): ±20% na janela da σ, no teto e na banda."""
    base = parametros or ParametrosC1()
    return [
        replace(base, janela=round(base.janela * FATOR_DO_PLATO_ABAIXO)),
        replace(base, janela=round(base.janela * FATOR_DO_PLATO_ACIMA)),
        replace(base, teto=base.teto * FATOR_DO_PLATO_ABAIXO),
        replace(base, teto=base.teto * FATOR_DO_PLATO_ACIMA),
        replace(base, banda=base.banda * FATOR_DO_PLATO_ABAIXO),
        replace(base, banda=base.banda * FATOR_DO_PLATO_ACIMA),
    ]
