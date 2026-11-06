"""Ligação fundo → ação → empresa (série 3 da base de ML, PR 5; pedido 1 da sessão "FactSet").

A posição de cada fundo (CDA, `base/cda.py`) traz o ISIN, e o ISIN dá o **emissor** (4 posições: PETR,
B3SA). O emissor vira CNPJ por duas fontes, nesta ordem:

1. **FCA** (`base/fca.py::emissores`): o que a empresa informa à CVM, de 2018 em diante, mais os
   códigos que ela informa fora do formato, conferidos um a um (o BTG põe "000000"; série 3, PR 8);
2. **tabela conferida** (`base/conferidas/emissores_antigos.csv`): os emissores que saíram da bolsa ou
   mudaram de código antes de 2018, ligados um a um pelo cadastro de companhias da CVM (inclusive as
   canceladas), com a fonte e a observação de cada linha. Decisão do Tiago em 14/10/2026: conferir pelos
   de maior valor até cada ano ter 95% do valor com CNPJ; o resto fica no relatório de buracos.

Emissor com CNPJ diferente nas duas fontes é **conflito** e fica sem CNPJ: nada é casado no escuro. O
painel **por emissor** sai sempre, desde 2005; o **por empresa**, quando há ligação.

Os emissores que ficam sem empresa **de propósito** estão em `base/conferidas/emissores_sem_ligacao.csv`
(série 4, PR 3), cada um com o motivo: companhia sem ação na bolsa (Comerc, Granja Faria; decisão 3 da
ADR 0074), dois CNPJs no período, BDR de empresa de fora ou falta de prova. O motivo vai para o
relatório de buracos.
"""

from pathlib import Path

import pandas as pd

from base.fca import PELOS_CODIGOS_CONFERIDOS

TABELA_CONFERIDA = (
    Path(__file__).resolve().parent / "conferidas" / "emissores_antigos.csv"
)
SEM_LIGACAO = (
    Path(__file__).resolve().parent / "conferidas" / "emissores_sem_ligacao.csv"
)
PELO_FCA, PELA_TABELA = "fca", "tabela conferida"
# na ordenação, as tabelas da `carga_fca` vêm antes
PRIORIDADE = {PELO_FCA: "0", PELOS_CODIGOS_CONFERIDOS: "0", PELA_TABELA: "1"}
COMPRADO = "comprado"
COLUNAS_DA_LIGACAO = ["emissor", "cnpj", "origem", "conflito"]
SOMAS = {"valor": "sum", "quantidade": "sum", "compras": "sum", "vendas": "sum"}


def tabela_conferida(caminho: Path = TABELA_CONFERIDA) -> pd.DataFrame:
    """A tabela de emissores antigos, conferida linha a linha (com fonte e observação)."""
    return pd.read_csv(
        caminho, sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
    )


def emissores_sem_ligacao(caminho: Path = SEM_LIGACAO) -> pd.DataFrame:
    """Os emissores que ficam sem empresa de propósito, cada um com o motivo e a fonte."""
    return pd.read_csv(
        caminho, sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
    )


def ligacao_dos_emissores(
    emissores_do_fca: pd.DataFrame, conferida: pd.DataFrame
) -> pd.DataFrame:
    """Emissor → CNPJ: o FCA primeiro, a tabela conferida no que faltar; conflito marcado."""
    fca = emissores_do_fca.loc[~emissores_do_fca["conflito"]]
    # tabelas gravadas antes do PR 8 não têm a coluna
    origem = fca.get("origem", PELO_FCA)
    juntas = pd.concat(
        [
            fca[["emissor", "cnpj"]].assign(origem=origem),
            conferida[["emissor", "cnpj"]].assign(origem=PELA_TABELA),
        ],
        ignore_index=True,
    )
    # as duas fontes dizendo o mesmo: fica uma linha, a do FCA
    juntas = juntas.sort_values(
        ["emissor", "origem"], key=lambda coluna: coluna.map(PRIORIDADE).fillna(coluna)
    ).drop_duplicates(["emissor", "cnpj"])
    conflito = juntas.groupby("emissor")["cnpj"].transform("nunique") > 1
    return juntas.assign(conflito=conflito).reset_index(drop=True)[COLUNAS_DA_LIGACAO]


def resolver(ligacao: pd.DataFrame, emissor: str) -> str | None:
    """O CNPJ do emissor, ou None se não há ligação ou se ela é conflito."""
    linhas = ligacao[(ligacao["emissor"] == emissor) & ~ligacao["conflito"]]
    return str(linhas["cnpj"].iloc[0]) if len(linhas) == 1 else None


def _sem_conflito(ligacao: pd.DataFrame) -> pd.DataFrame:
    return ligacao.loc[~ligacao["conflito"], ["emissor", "cnpj"]]


def _agregar(posicoes: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    return (
        posicoes.groupby(chave)
        .agg(
            fundos=("cnpj_fundo", "nunique"),
            disponivel_em=("disponivel_em", "max"),
            **{coluna: (coluna, conta) for coluna, conta in SOMAS.items()},
        )
        .reset_index()
    )


def painel_por_emissor(posicoes: pd.DataFrame) -> pd.DataFrame:
    """Por mês, emissor e tipo (comprado, emprestado, vendido): fundos, valor, quantidade, fluxo.

    `disponivel_em` é a maior data entre as posições somadas: o total só era público quando a última
    posição dele ficou pública.
    """
    return _agregar(posicoes, ["competencia", "emissor", "tipo"])


DO_BLOCO_8 = {
    "fundos": "fundos_no_bloco_8",
    "valor": "valor_no_bloco_8",
    "quantidade": "quantidade_no_bloco_8",
}


def painel_por_empresa(
    posicoes: pd.DataFrame,
    ligacao: pd.DataFrame,
    bloco_8: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """O mesmo por CNPJ: junta os emissores da mesma empresa (ITAU e ITUB) e conta o fundo uma vez.

    As ações do bloco 8 (`cda.ler_acoes_do_bloco_8`) entram pelo CNPJ que o fundo informa, só de
    empresa da ligação (com ação na bolsa, conferida), em colunas próprias (`*_no_bloco_8`): as do
    bloco 4 não mudam. `disponivel_em` é a maior data entre os dois blocos.
    """
    chave = ["competencia", "cnpj", "tipo"]
    com_cnpj = posicoes.merge(_sem_conflito(ligacao), on="emissor", how="inner")
    painel = _agregar(com_cnpj, chave)
    listadas = set(_sem_conflito(ligacao)["cnpj"])
    do_8 = (
        bloco_8[bloco_8["cnpj_emissor"].isin(listadas)].rename(
            columns={"cnpj_emissor": "cnpj"}
        )
        if bloco_8 is not None
        else pd.DataFrame(columns=[*chave, "cnpj_fundo", "disponivel_em", *SOMAS])
    )
    extra = _agregar(do_8, chave)[[*chave, "disponivel_em", *DO_BLOCO_8]].rename(
        columns={**DO_BLOCO_8, "disponivel_em": "_disponivel_no_bloco_8"}
    )
    juntos = painel.merge(extra, on=chave, how="outer")
    numeros = [c for c in juntos.columns if c in SOMAS or c in DO_BLOCO_8.values()]
    juntos[[*numeros, "fundos"]] = juntos[[*numeros, "fundos"]].fillna(0)
    datas = juntos[["disponivel_em", "_disponivel_no_bloco_8"]].apply(pd.to_datetime)
    juntos["disponivel_em"] = datas.max(axis=1)
    return juntos.drop(columns="_disponivel_no_bloco_8")


def cobertura(posicoes: pd.DataFrame, ligacao: pd.DataFrame) -> pd.DataFrame:
    """Por mês: quanto do valor comprado chega a um CNPJ (a meta da tabela conferida é 95%)."""
    compradas = posicoes[posicoes["tipo"] == COMPRADO]
    ligados = set(_sem_conflito(ligacao)["emissor"])
    tabela = compradas.assign(
        valor_com_cnpj=compradas["valor"].where(compradas["emissor"].isin(ligados), 0.0)
    )
    resumo = (
        tabela.groupby("competencia")
        .agg(valor_comprado=("valor", "sum"), valor_com_cnpj=("valor_com_cnpj", "sum"))
        .reset_index()
    )
    return resumo.assign(
        fracao_com_cnpj=resumo["valor_com_cnpj"] / resumo["valor_comprado"]
    )


def buracos(
    posicoes: pd.DataFrame,
    ligacao: pd.DataFrame,
    motivos: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Os emissores sem CNPJ, do maior valor comprado para o menor (o relatório de buracos), com o
    motivo conferido de quem fica sem empresa de propósito (`emissores_sem_ligacao`)."""
    sem = posicoes[
        (posicoes["tipo"] == COMPRADO)
        & ~posicoes["emissor"].isin(set(_sem_conflito(ligacao)["emissor"]))
    ]
    tabela = (
        sem.groupby("emissor")
        .agg(
            valor=("valor", "sum"),
            primeira=("competencia", "min"),
            ultima=("competencia", "max"),
            descricao=("descricao", "first"),
        )
        .sort_values("valor", ascending=False)
        .reset_index()
    )
    motivo = (
        pd.Series(dtype=object)
        if motivos is None
        else motivos.set_index("emissor")["motivo"]
    )
    return tabela.assign(motivo=tabela["emissor"].map(motivo))
