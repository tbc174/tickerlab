"""Mudanças mensais do CNPJ (ADR 0106, PR 5): o que mudou de um mês para o outro, e a volta.

A base guarda o retrato inicial, os meses âncora e, para cada mês, só o que mudou. `diff` compara dois
retratos pela chave e devolve uma linha por mudança (entrou, saiu ou mudou), com o valor antigo e o novo;
`reconstruir` aplica as mudanças até um mês e devolve o retrato daquele mês (é o teste de que nada se perdeu).

Chave repetida não perde linha: cada linha ganha uma `ordem` dentro da chave (pelo conteúdo, não pela
posição no arquivo). O QSA usa o `id_pessoa` como chave do sócio pessoa física: o nome nunca entra aqui, e
quando o titular se opõe, só o id fica no histórico.
"""

import re
from datetime import date

import pandas as pd

from base.pessoas.tabelas import ids_das_linhas
from base.receita_retrato import ParteDoQsa

ENTROU, SAIU, MUDOU = "entrou", "saiu", "mudou"
ORDEM = "ordem"
CHAVE_DO_QSA = ["cnpj_basico", "tipo_socio", "raiz_socio_pj", "id_pessoa"]
TIPO_PESSOA_JURIDICA = "1"
# A Receita põe a pasta AAAA-MM no ar durante o mês. Valor provisório e prudente até a medida no servidor
# (`getlastmodified` das pastas, plano de 20/10): dia 20 mais uma semana de folga.
DIA_DA_PUBLICACAO = 20
FOLGA = 7
MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _numerar(tabela: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    """A tabela ordenada pelo conteúdo, com a `ordem` de cada linha dentro da sua chave."""
    ordenada = tabela.sort_values(list(tabela.columns), kind="stable").copy()
    ordenada[ORDEM] = ordenada.groupby(chave, dropna=False).cumcount()
    return ordenada


def _mudou(antes: pd.Series, depois: pd.Series) -> pd.Series:
    return ~(antes.eq(depois) | (antes.isna() & depois.isna()))


def diff(
    antes: pd.DataFrame, depois: pd.DataFrame, chave: list[str], mes: str
) -> pd.DataFrame:
    """As mudanças de `antes` para `depois`: `mes`, `tipo`, a chave, a `ordem`, e `<coluna>_antes/_depois`."""
    valores = [c for c in depois.columns if c not in chave]
    ligacao = chave + [ORDEM]
    juntas = _numerar(antes[chave + valores], chave).merge(
        _numerar(depois[chave + valores], chave),
        on=ligacao,
        how="outer",
        suffixes=("_antes", "_depois"),
        indicator=True,
    )
    houve = pd.Series(False, index=juntas.index)
    for coluna in valores:
        houve |= _mudou(juntas[f"{coluna}_antes"], juntas[f"{coluna}_depois"])
    tipo = juntas["_merge"].map(
        {"left_only": SAIU, "right_only": ENTROU, "both": MUDOU}
    )
    mudancas = juntas[(juntas["_merge"] != "both") | houve].copy()
    mudancas["tipo"] = tipo[mudancas.index].astype(str)
    mudancas["mes"] = mes
    colunas = ["mes", "tipo", *ligacao]
    for coluna in valores:
        colunas += [f"{coluna}_antes", f"{coluna}_depois"]
    return mudancas[colunas].reset_index(drop=True)


def reconstruir(
    retrato: pd.DataFrame, mudancas: pd.DataFrame, chave: list[str], ate: str
) -> pd.DataFrame:
    """O retrato de `ate` (AAAA-MM): o inicial com as mudanças de cada mês até lá aplicadas em ordem."""
    colunas = list(retrato.columns)
    valores = [c for c in colunas if c not in chave]
    ligacao = chave + [ORDEM]
    estado = _numerar(retrato, chave)
    for mes in sorted(m for m in mudancas["mes"].unique() if m <= ate):
        do_mes = mudancas[mudancas["mes"] == mes]
        saem = do_mes[do_mes["tipo"].isin([SAIU, MUDOU])][ligacao]
        estado = estado.merge(saem, on=ligacao, how="left", indicator=True)
        estado = estado[estado["_merge"] == "left_only"].drop(columns="_merge")
        novas = do_mes[do_mes["tipo"].isin([ENTROU, MUDOU])]
        novas = novas[ligacao + [f"{c}_depois" for c in valores]]
        novas = novas.rename(columns={f"{c}_depois": c for c in valores})
        estado = pd.concat([estado, novas], ignore_index=True)
    return estado[colunas].reset_index(drop=True)


def qsa_para_diff(parte: ParteDoQsa, chave: bytes) -> pd.DataFrame:
    """Os sócios de um pedaço do QSA com o `id_pessoa` de quem é pessoa física (sem nome nem CPF).

    As linhas de `pessoas_brutas` seguem a ordem das de `socios` que não são PJ (é como o leitor as separa).
    """
    socios = parte.socios.copy()
    fisica = socios["tipo_socio"] != TIPO_PESSOA_JURIDICA
    if int(fisica.sum()) != len(parte.pessoas_brutas):
        raise ValueError("pessoas e sócios não alinhados: a ordem do leitor mudou")
    socios["id_pessoa"] = ""
    if fisica.any():
        socios.loc[fisica, "id_pessoa"] = ids_das_linhas(
            parte.pessoas_brutas, chave
        ).to_numpy()
    socios["raiz_socio_pj"] = socios["raiz_socio_pj"].fillna("")
    return socios


def disponivel_em(mes: str) -> date:
    """Desde quando o retrato do mês `AAAA-MM` era público: o dia da publicação mais a folga (o piso)."""
    if not MES.match(mes):
        raise ValueError("mês fora do formato AAAA-MM")
    return date(int(mes[:4]), int(mes[5:]), DIA_DA_PUBLICACAO + FOLGA)
