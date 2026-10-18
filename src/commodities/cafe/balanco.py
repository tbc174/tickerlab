"""Derivados do balanço mundial do café (USDA PSD): funções puras sobre a tabela `usda_psd_cafe`.

Recebem o `pd.DataFrame` da tabela (colunas de `base.commodities.usda_psd.COLUNAS`) e devolvem
dataclasses simples, fáceis de virar JSON. Para "como era numa data", o chamador passa a tabela já
cortada por `usda_psd.como_estava_em`: aqui nada olha o relógio nem o futuro.

"Mundo" é a soma dos países que a tabela traz; o PSD cobre os países relevantes do café, mas quem
passa um recorte menor (como o dublê dos testes) tem um "mundo" menor.
"""

from dataclasses import dataclass

import pandas as pd

TIPOS = ("arabica", "conilon", "total")
BRASIL = "BR"
MUNDO = "mundo"
# os grandes do robusta (conilon) no PSD: Vietnã, Brasil, Indonésia e Uganda (códigos do USDA)
PAISES_DO_ROBUSTA = ("VM", BRASIL, "ID", "UG")


@dataclass(frozen=True)
class PontoAnual:
    """Um número por ano-safra: `valor` na unidade da função; `rotulo` diz de que recorte vem."""

    ano_safra: int
    valor: float
    rotulo: str


@dataclass(frozen=True)
class SurpresaDoUsda:
    """Quanto uma safra mudou entre duas fotografias do USDA (ex.: junho × dezembro)."""

    ano_safra: int
    antes: float
    depois: float
    diferenca: float  # em mil sacas de 60 kg
    percentual: float  # fração do número de antes (0,05 = 5%)


@dataclass(frozen=True)
class BalancoDoPais:
    """Um país numa safra, lado a lado com os outros: quanto produz do tipo e quanto sobra em estoque."""

    codigo_do_pais: str
    ano_safra: int
    tipo: str
    producao: float  # mil sacas de 60 kg
    participacao_na_producao: float  # fração da produção do tipo nos países da tabela
    relacao_estoque_consumo: (
        float | None
    )  # None quando a tabela não traz consumo do país


def _por_safra(
    tabela: pd.DataFrame, atributo: str, tipo: str, pais: str | None
) -> pd.Series:
    """Soma do atributo por ano-safra (de um país, ou de todos quando `pais` é None)."""
    linhas = tabela[(tabela["atributo"] == atributo) & (tabela["tipo"] == tipo)]
    if pais is not None:
        linhas = linhas[linhas["codigo_do_pais"] == pais]
    return linhas.groupby("ano_safra")["valor"].sum()


def relacao_estoque_consumo(
    tabela: pd.DataFrame, pais: str | None = None
) -> list[PontoAnual]:
    """Estoque final ÷ consumo doméstico por safra (fração); `pais=None` é o mundo."""
    estoque = _por_safra(tabela, "estoque_final", "total", pais)
    consumo = _por_safra(tabela, "consumo_domestico", "total", pais)
    rotulo = pais or MUNDO
    return [
        PontoAnual(int(safra), float(estoque[safra] / consumo[safra]), rotulo)
        for safra in sorted(estoque.index.intersection(consumo.index))
        if consumo[safra] > 0
    ]


def participacao_do_brasil(
    tabela: pd.DataFrame, tipo: str = "total"
) -> list[PontoAnual]:
    """Produção do Brasil ÷ produção dos países da tabela, por safra (fração), de um tipo."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo {tipo!r} inválido: use um de {TIPOS}")
    brasil = _por_safra(tabela, "producao", tipo, BRASIL)
    mundo = _por_safra(tabela, "producao", tipo, None)
    return [
        PontoAnual(int(safra), float(brasil[safra] / mundo[safra]), tipo)
        for safra in sorted(brasil.index.intersection(mundo.index))
        if mundo[safra] > 0
    ]


def surpresa_do_usda(
    antes: pd.DataFrame,
    depois: pd.DataFrame,
    pais: str,
    atributo: str,
    tipo: str = "total",
) -> list[SurpresaDoUsda]:
    """Quanto cada safra mudou da fotografia `antes` para `depois` (só as safras das duas)."""
    a = _por_safra(antes, atributo, tipo, pais)
    d = _por_safra(depois, atributo, tipo, pais)
    return [
        SurpresaDoUsda(
            ano_safra=int(safra),
            antes=float(a[safra]),
            depois=float(d[safra]),
            diferenca=float(d[safra] - a[safra]),
            percentual=float((d[safra] - a[safra]) / a[safra]),
        )
        for safra in sorted(a.index.intersection(d.index))
        if a[safra] != 0
    ]


def balanco_por_pais(
    tabela: pd.DataFrame,
    paises: tuple[str, ...] = PAISES_DO_ROBUSTA,
    tipo: str = "conilon",
) -> list[BalancoDoPais]:
    """Participação na produção do `tipo` e relação estoque/consumo dos `paises`, por safra.

    A participação é sobre todos os países da tabela (o "mundo" do PSD), não só sobre `paises`,
    para que Vietnã, Indonésia, Uganda e Brasil somem menos de 100% e a conta diga a verdade.
    """
    if tipo not in TIPOS:
        raise ValueError(f"tipo {tipo!r} inválido: use um de {TIPOS}")
    mundo = _por_safra(tabela, "producao", tipo, None)
    pontos = []
    for pais in paises:
        producao = _por_safra(tabela, "producao", tipo, pais)
        estoque = _por_safra(tabela, "estoque_final", "total", pais)
        consumo = _por_safra(tabela, "consumo_domestico", "total", pais)
        for safra in sorted(producao.index.intersection(mundo.index)):
            if producao[safra] <= 0 or mundo[safra] <= 0:
                continue
            tem_relacao = safra in estoque.index and consumo.get(safra, 0) > 0
            pontos.append(
                BalancoDoPais(
                    codigo_do_pais=pais,
                    ano_safra=int(safra),
                    tipo=tipo,
                    producao=float(producao[safra]),
                    participacao_na_producao=float(producao[safra] / mundo[safra]),
                    relacao_estoque_consumo=(
                        float(estoque[safra] / consumo[safra]) if tem_relacao else None
                    ),
                )
            )
    return sorted(pontos, key=lambda p: (p.ano_safra, p.codigo_do_pais))
