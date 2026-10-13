"""A análise da carteira da B3: concentração, comportamento no passado, Raio-X e Rebalanceamento.

A carteira vem da planilha de posição da Área do Investidor (`src/carteira_b3.py`), lida só na
memória. As mesmas contas servem à página "Carteira da B3" e ao PDF "Minha carteira", para os dois
nunca mostrarem números diferentes. Saídas em tipos simples, sem Streamlit (prontas para uma rota
da API, ADR 0044 e 0048).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.carteira_b3 import (
    CarteiraB3,
    numero_efetivo_de_ativos,
    retorno_com_os_pesos_de_hoje,
)
from src.metricas import resumir_desempenho

MAIORES = 3  # "as 3 maiores juntas"
SEM_SETOR = "Sem setor conhecido"  # FII, ETF, BDR e empresas sem setor na CVM
SETOR_DA_RENDA_FIXA = "Tesouro e renda fixa"
REAL = "Real"
DOLAR_BDR = "Dólar (BDR)"
NOTA_DA_MOEDA = (
    "BDR conta como dólar (é uma empresa de fora); o resto conta como real. ETFs de índices de "
    "fora (como o IVVB11) também têm exposição ao dólar, mas aqui contam como real."
)


def _sem_sufixo(ticker: str) -> str:
    return ticker.removesuffix(".SA")


@dataclass(frozen=True)
class Concentracao:
    pesos: tuple[tuple[str, float], ...]  # (código, peso), do maior para o menor
    maior: tuple[str, float] | None
    tres_maiores: float | None
    numero_efetivo: float  # quantos ativos de mesmo peso dariam a mesma concentração
    quantidade: int
    fracao_renda_fixa: float | None  # Tesouro e renda fixa sobre o total da posição


def concentracao(carteira: CarteiraB3) -> Concentracao:
    """Quanto o dinheiro em ativos com cotação depende de poucos deles."""
    pesos = carteira.pesos().sort_values(ascending=False)
    total = carteira.valor_total
    renda_fixa = float(carteira.sem_cotacao["valor"].sum() / total) if total else None
    if pesos.empty:
        return Concentracao((), None, None, 0.0, 0, renda_fixa)
    return Concentracao(
        pesos=tuple((_sem_sufixo(t), float(p)) for t, p in pesos.items()),
        maior=(_sem_sufixo(pesos.index[0]), float(pesos.iloc[0])),
        tres_maiores=float(pesos.iloc[:MAIORES].sum()),
        numero_efetivo=numero_efetivo_de_ativos(pesos),
        quantidade=len(pesos),
        fracao_renda_fixa=renda_fixa,
    )


@dataclass(frozen=True)
class Ponto:
    dia: date
    valor: float


@dataclass(frozen=True)
class Comportamento:
    """A carteira de HOJE mantida com os mesmos pesos no passado (não é o resultado real)."""

    retorno_total: float
    retorno_anualizado: float
    volatilidade_anual: float
    maior_queda: float
    sharpe: float
    curva: tuple[Ponto, ...]  # base 100
    curva_ibovespa: tuple[Ponto, ...] | None
    retorno_ibovespa: float | None


def _pontos(serie: pd.Series) -> tuple[Ponto, ...]:
    return tuple(Ponto(d.date(), float(v)) for d, v in serie.items())


def comportamento(
    carteira: CarteiraB3,
    fechamentos: pd.DataFrame,
    referencia: pd.Series | None,
    taxa_livre_de_risco: float,
) -> Comportamento:
    """Como a carteira de hoje teria se comportado no período, contra o Ibovespa (`referencia`).

    `fechamentos`: um ativo por coluna (tickers com .SA). Ativos sem histórico ficam de fora e o
    peso deles é dividido entre os outros (`retorno_com_os_pesos_de_hoje`).
    """
    retorno = retorno_com_os_pesos_de_hoje(fechamentos, carteira.pesos())
    resumo = resumir_desempenho(retorno, taxa_livre_de_risco=taxa_livre_de_risco)
    curva_ibovespa, retorno_ibovespa = None, None
    if referencia is not None and not referencia.dropna().empty:
        alinhada = referencia.reindex(retorno.index).ffill().dropna()
        if len(alinhada) > 1:
            curva_ibovespa = _pontos(alinhada / alinhada.iloc[0] * 100)
            retorno_ibovespa = float(alinhada.iloc[-1] / alinhada.iloc[0] - 1)
    return Comportamento(
        retorno_total=float(resumo["Retorno total"]),
        retorno_anualizado=float(resumo["Retorno anualizado"]),
        volatilidade_anual=float(resumo["Volatilidade anual"]),
        maior_queda=float(resumo["Maior queda"]),
        sharpe=float(resumo["Índice de Sharpe"]),
        curva=_pontos((1 + retorno).cumprod() * 100),
        curva_ibovespa=curva_ibovespa,
        retorno_ibovespa=retorno_ibovespa,
    )


# --- Raio-X --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fatia:
    grupo: str
    valor: float  # R$
    peso: float  # sobre o total da posição, com Tesouro e renda fixa


@dataclass(frozen=True)
class RaioX:
    por_tipo: tuple[Fatia, ...]
    por_setor: tuple[Fatia, ...]
    por_moeda: tuple[Fatia, ...]


def _fatias(valores: pd.Series, total: float) -> tuple[Fatia, ...]:
    somados = valores.groupby(level=0).sum().sort_values(ascending=False)
    return tuple(Fatia(str(g), float(v), float(v / total)) for g, v in somados.items())


def raio_x(carteira: CarteiraB3, setores: dict[str, str]) -> RaioX:
    """A posição inteira por tipo de ativo, por setor da CVM e por moeda.

    `setores`: o setor de cada ticker (com .SA); quem não está nele vai para "Sem setor conhecido".
    """
    total = carteira.valor_total
    if not total:
        return RaioX((), (), ())
    ativos, fixa = carteira.posicoes, carteira.sem_cotacao
    por_tipo = pd.concat(
        [ativos.set_index("tipo")["valor"], fixa.set_index("tipo")["valor"]]
    )
    por_setor = pd.concat(
        [
            pd.Series(
                ativos["valor"].to_numpy(),
                index=[setores.get(t, SEM_SETOR) for t in ativos["ticker"]],
            ),
            pd.Series(
                fixa["valor"].to_numpy(), index=[SETOR_DA_RENDA_FIXA] * len(fixa)
            ),
        ]
    )
    moedas = [DOLAR_BDR if tipo == "BDR" else REAL for tipo in ativos["tipo"]]
    por_moeda = pd.concat(
        [
            pd.Series(ativos["valor"].to_numpy(), index=moedas),
            pd.Series(fixa["valor"].to_numpy(), index=[REAL] * len(fixa)),
        ]
    )
    return RaioX(
        _fatias(por_tipo, total), _fatias(por_setor, total), _fatias(por_moeda, total)
    )


# --- Rebalanceamento -----------------------------------------------------------------------

AVISO_DO_REBALANCEAMENTO = (
    "A conta usa os pesos que você escolheu e os valores da planilha da B3. Não é recomendação: "
    "custos, imposto e o preço na hora da ordem mudam o resultado. Tesouro e renda fixa ficam fora "
    "da conta."
)
TOLERANCIA_DA_SOMA = 0.001  # 0,1 ponto: arredondamento de quem digita os pesos


@dataclass(frozen=True)
class Ajuste:
    codigo: str
    valor_atual: float  # R$
    peso_atual: float
    peso_alvo: float
    valor_alvo: float  # R$
    diferenca: float  # R$: positivo = comprar, negativo = vender
    quantidade: (
        int  # ações a comprar (+) ou vender (−), pelo preço da planilha, para baixo
    )


def rebalancear(
    carteira: CarteiraB3, pesos_alvo: dict[str, float]
) -> tuple[Ajuste, ...]:
    """Quanto comprar ou vender de cada ativo com cotação para chegar aos pesos escolhidos.

    `pesos_alvo`: código (sem .SA) → fração (0,25 = 25%). Precisa trazer todos os ativos da
    carteira e somar 100%: um ativo esquecido não vira "vender tudo" sem a pessoa pedir.
    """
    posicoes = carteira.posicoes
    faltando = [c for c in posicoes["codigo"] if c not in pesos_alvo]
    if faltando:
        raise ValueError(f"Falta o peso de: {', '.join(faltando)}.")
    soma = sum(pesos_alvo.get(c, 0.0) for c in posicoes["codigo"])
    if abs(soma - 1) > TOLERANCIA_DA_SOMA:
        raise ValueError(
            f"Os pesos escolhidos somam {soma * 100:.0f}%: precisam somar 100%.".replace(
                ".", ","
            )
        )
    total = float(posicoes["valor"].sum())
    ajustes = []
    for _, p in posicoes.iterrows():
        alvo = pesos_alvo[p["codigo"]]
        diferenca = alvo * total - float(p["valor"])
        preco = float(p["valor"]) / float(p["quantidade"]) if p["quantidade"] else 0.0
        quantidade = (
            int(diferenca / preco) if preco else 0
        )  # int() corta em direção ao zero
        ajustes.append(
            Ajuste(p["codigo"], float(p["valor"]), float(p["valor"]) / total, alvo,
                   alvo * total, diferenca, quantidade)
        )  # fmt: skip
    return tuple(ajustes)
