"""Simulador de trava do café: o que teria acontecido em cada forma de travar, safra a safra (linha 340).

O produtor informa a produção dele (arábica ou robusta, sacas, custo por saca, mês da colheita, com quantos
meses de antecedência travaria e que parte da safra) e a conta mostra, com o preço de referência **mensal**
do Pink Sheet e a PTAX, a receita por saca de cada instrumento em cada safra desde 2000, lado a lado. A
ordem dos instrumentos é fixa e nada aqui escolhe um deles: quem escolhe a parte travada é o produtor, e
nenhuma frase diz o que fazer (CVM 19; ADR 0047). Os textos estão em `textos_da_trava.py`.

Nada da produção é guardado (decisão do Tiago, 23/10/2026): a conta roda na memória e não registra os
números no log. Sem banco, sem LGPD nova.

Rota que exporia: `POST /agro/trava/simular` (entrada: `EntradaDaTrava`; saída: `SimulacaoDaTrava`).

Fica sem Streamlit: entradas e saídas em tipos simples.
"""

import dataclasses
import statistics
from dataclasses import dataclass
from datetime import date

import pandas as pd
import sqlalchemy as sa

from src.banco import series as acervo

KG_POR_SACA = 60
PTAX = "bcb-ptax-venda"
SERIE_DO_TIPO = {"arabica": "bm-pink-cafe-arabica", "robusta": "bm-pink-cafe-robusta"}
TIPOS = tuple(SERIE_DO_TIPO)
# o câmbio flutua desde janeiro de 1999: antes disso a PTAX não mostra o risco de câmbio do futuro em dólar
PRIMEIRA_SAFRA = 2000
ANTECEDENCIA_MAXIMA = 12  # meses; quem trava mais cedo que isso trava outra safra
PREMIO_MAXIMO = (
    0.5  # fração do preço da trava; acima disso o número digitado está errado
)
MESES_NO_ANO = 12

NAO_TRAVAR = "nao_travar"
TERMO = "termo"
FUTURO = "futuro"
OPCAO = "opcao"
ORDEM_DOS_INSTRUMENTOS = (NAO_TRAVAR, TERMO, FUTURO, OPCAO)


class SemPrecosError(Exception):
    """O acervo ainda não tem o preço de referência ou a PTAX."""


@dataclass(frozen=True)
class EntradaDaTrava:
    tipo: str  # "arabica" ou "robusta"
    sacas: float  # sacas de 60 kg esperadas
    custo_por_saca: float  # R$ por saca, de hoje
    mes_da_colheita: int  # 1 a 12
    meses_de_antecedencia: int  # quantos meses antes da colheita a trava é feita
    fracao_travada: float  # 0 a 1: a parte da safra que o produtor trava
    premio_da_opcao: float  # fração do preço da trava paga pela opção de venda


@dataclass(frozen=True)
class ResultadoDoInstrumento:
    chave: str
    receita_por_saca: float  # R$ da época, com a parte não travada vendida na colheita
    contra_nao_travar_por_saca: (
        float  # R$ da época; positivo: recebeu mais que sem travar
    )
    razao_contra_a_trava: (
        float  # receita ÷ preço da trava (o movimento, sem a moeda da época)
    )
    pior_chamada_por_saca: (
        float | None
    )  # só o futuro: a maior margem depositada, R$ da época
    margem_no_cenario: float | None = None  # R$ de hoje; preenchida por `simular_trava`


@dataclass(frozen=True)
class SafraSimulada:
    safra: int
    mes_da_trava: date
    mes_da_colheita: date
    preco_da_trava: float  # R$ por saca no mês da trava
    preco_na_colheita: float  # R$ por saca no mês da colheita
    instrumentos: tuple[ResultadoDoInstrumento, ...]


@dataclass(frozen=True)
class ResumoDoInstrumento:
    chave: str
    safras: int
    menor_margem: float | None  # R$ de hoje por saca, nos cenários
    mediana_da_margem: float | None
    maior_margem: float | None
    safras_abaixo_do_custo: int


@dataclass(frozen=True)
class SimulacaoDaTrava:
    entrada: EntradaDaTrava
    preco_de_hoje: float  # R$ por saca, o último mês com preço e PTAX
    mes_do_preco_de_hoje: date
    safras: tuple[SafraSimulada, ...]
    resumos: tuple[ResumoDoInstrumento, ...]


def validar(entrada: EntradaDaTrava) -> None:
    """Levanta ValueError, com a mensagem para a tela, se algum número está fora do intervalo."""
    erros = {
        "o café precisa ser arábica ou robusta": entrada.tipo not in SERIE_DO_TIPO,
        "as sacas precisam ser positivas": entrada.sacas <= 0,
        "o custo por saca precisa ser positivo": entrada.custo_por_saca <= 0,
        "o mês da colheita vai de 1 a 12": not 1
        <= entrada.mes_da_colheita
        <= MESES_NO_ANO,
        f"a antecedência vai de 1 a {ANTECEDENCIA_MAXIMA} meses": not (
            1 <= entrada.meses_de_antecedencia <= ANTECEDENCIA_MAXIMA
        ),
        "a parte travada vai de 0% a 100%": not 0 <= entrada.fracao_travada <= 1,
        f"o prêmio da opção vai de 0% a {PREMIO_MAXIMO:.0%}": not (
            0 <= entrada.premio_da_opcao <= PREMIO_MAXIMO
        ),
    }
    achados = [mensagem for mensagem, errado in erros.items() if errado]
    if achados:
        raise ValueError("; ".join(achados))


def precos_por_saca(preco_usd_kg: pd.Series, ptax_diaria: pd.Series) -> pd.DataFrame:
    """Por mês (dia 1): `usd_por_saca`, `ptax` (média do mês) e `reais_por_saca`.

    Mês sem o preço ou sem a PTAX fica de fora (nunca vira zero)."""
    mensal = ptax_diaria.dropna()
    mensal = mensal.groupby(mensal.index.to_period("M")).mean()
    mensal.index = mensal.index.to_timestamp()
    usd = preco_usd_kg.dropna() * KG_POR_SACA
    tabela = pd.concat(
        [usd, mensal], axis=1, keys=["usd_por_saca", "ptax"], join="inner"
    )
    tabela = tabela.dropna().sort_index()
    tabela["reais_por_saca"] = tabela["usd_por_saca"] * tabela["ptax"]
    return tabela


def ler_precos(conexao: sa.Connection, tipo: str, dia: date) -> pd.DataFrame:
    """Os preços por saca como eram conhecidos no fim de `dia` (nada divulgado depois entra)."""
    preco = acervo.como_estava_em(conexao, SERIE_DO_TIPO[tipo], dia)
    ptax = acervo.como_estava_em(conexao, PTAX, dia)
    return precos_por_saca(preco, ptax)


def _menos_meses(mes: pd.Timestamp, meses: int) -> pd.Timestamp:
    return mes - pd.DateOffset(months=meses)


def _pior_chamada(
    precos: pd.DataFrame, trava: pd.Timestamp, colheita: pd.Timestamp
) -> float:
    """A maior margem depositada no futuro vendido, mês a mês, em R$ por saca (zero se o preço só caiu).

    Com a média do mês a conta fica abaixo da chamada de verdade, que é diária."""
    periodo = precos.loc[(precos.index > trava) & (precos.index <= colheita)]
    alta = (periodo["usd_por_saca"] - precos.at[trava, "usd_por_saca"]) * periodo[
        "ptax"
    ]
    return max(0.0, float(alta.max())) if not alta.empty else 0.0


def _receitas_da_parte_travada(
    entrada: EntradaDaTrava,
    precos: pd.DataFrame,
    trava: pd.Timestamp,
    colheita: pd.Timestamp,
) -> dict[str, float]:
    """Receita por saca de cada instrumento se a safra inteira fosse travada nele."""
    usd_trava, usd_colheita = (
        precos.at[trava, "usd_por_saca"],
        precos.at[colheita, "usd_por_saca"],
    )
    ptax_colheita = precos.at[colheita, "ptax"]
    preco_da_trava = precos.at[trava, "reais_por_saca"]
    return {
        NAO_TRAVAR: float(precos.at[colheita, "reais_por_saca"]),
        TERMO: float(preco_da_trava),
        FUTURO: float(usd_trava * ptax_colheita),
        OPCAO: float(
            max(usd_colheita, usd_trava) * ptax_colheita
            - entrada.premio_da_opcao * preco_da_trava
        ),
    }


def _simular_uma_safra(
    entrada: EntradaDaTrava, precos: pd.DataFrame, colheita: pd.Timestamp
) -> SafraSimulada | None:
    trava = _menos_meses(colheita, entrada.meses_de_antecedencia)
    if trava not in precos.index or colheita not in precos.index:
        return None
    cheias = _receitas_da_parte_travada(entrada, precos, trava, colheita)
    f, sem_travar = entrada.fracao_travada, cheias[NAO_TRAVAR]
    preco_da_trava = float(precos.at[trava, "reais_por_saca"])
    chamada = f * _pior_chamada(precos, trava, colheita)
    instrumentos = []
    for chave in ORDEM_DOS_INSTRUMENTOS:
        receita = f * cheias[chave] + (1 - f) * sem_travar
        instrumentos.append(
            ResultadoDoInstrumento(
                chave=chave,
                receita_por_saca=receita,
                contra_nao_travar_por_saca=receita - sem_travar,
                razao_contra_a_trava=receita / preco_da_trava,
                pior_chamada_por_saca=chamada if chave == FUTURO else None,
            )
        )
    return SafraSimulada(
        safra=colheita.year,
        mes_da_trava=trava.date(),
        mes_da_colheita=colheita.date(),
        preco_da_trava=preco_da_trava,
        preco_na_colheita=sem_travar,
        instrumentos=tuple(instrumentos),
    )


def simular_safras(
    entrada: EntradaDaTrava, precos: pd.DataFrame
) -> tuple[SafraSimulada, ...]:
    """Cada safra desde 2000 com preço e PTAX na trava e na colheita, da mais antiga à mais nova."""
    validar(entrada)
    if precos.empty:
        return ()
    anos = range(max(PRIMEIRA_SAFRA, precos.index[0].year), precos.index[-1].year + 1)
    colheitas = (pd.Timestamp(ano, entrada.mes_da_colheita, 1) for ano in anos)
    simuladas = (_simular_uma_safra(entrada, precos, c) for c in colheitas)
    return tuple(s for s in simuladas if s is not None)


def _com_cenario(
    safra: SafraSimulada, preco_de_hoje: float, custo: float
) -> SafraSimulada:
    """A safra com a margem de cada instrumento no cenário "o preço anda como andou nela", a partir de hoje."""
    instrumentos = tuple(
        dataclasses.replace(
            i, margem_no_cenario=preco_de_hoje * i.razao_contra_a_trava - custo
        )
        for i in safra.instrumentos
    )
    return dataclasses.replace(safra, instrumentos=instrumentos)


def _resumir(chave: str, safras: tuple[SafraSimulada, ...]) -> ResumoDoInstrumento:
    margens = [
        i.margem_no_cenario
        for s in safras
        for i in s.instrumentos
        if i.chave == chave and i.margem_no_cenario is not None
    ]
    if not margens:
        return ResumoDoInstrumento(chave, 0, None, None, None, 0)
    return ResumoDoInstrumento(
        chave=chave,
        safras=len(margens),
        menor_margem=min(margens),
        mediana_da_margem=statistics.median(margens),
        maior_margem=max(margens),
        safras_abaixo_do_custo=sum(m < 0 for m in margens),
    )


def simular_trava(entrada: EntradaDaTrava, precos: pd.DataFrame) -> SimulacaoDaTrava:
    """As safras simuladas, a margem de cada uma como cenário a partir do preço de hoje e o resumo.

    O custo informado é de hoje e o real de 2005 não é o de hoje: por isso a margem não compara o custo com a
    receita da época, e sim com o movimento da safra (receita ÷ preço da trava) aplicado ao último preço."""
    validar(entrada)
    if precos.empty:
        raise SemPrecosError(
            "O preço de referência do café ou a PTAX ainda não foram coletados."
        )
    preco_de_hoje = float(precos["reais_por_saca"].iloc[-1])
    safras = tuple(
        _com_cenario(s, preco_de_hoje, entrada.custo_por_saca)
        for s in simular_safras(entrada, precos)
    )
    return SimulacaoDaTrava(
        entrada=entrada,
        preco_de_hoje=preco_de_hoje,
        mes_do_preco_de_hoje=precos.index[-1].date(),
        safras=safras,
        resumos=tuple(_resumir(chave, safras) for chave in ORDEM_DOS_INSTRUMENTOS),
    )
