"""CNPJ de verdade nas tabelas que só trazem o código da fonte (linha 904, lote 4).

`ans_beneficiarios` (registro da operadora na ANS), `susep_seguros` (código da seguradora na SUSEP) e
`ifdata_valores` (código da instituição no BC) falam de empresas, mas guardam o código da fonte. A ponte entre o
código e o CNPJ é o cadastro da própria fonte: `ans_operadoras` e `susep_cadastro` (retratos de
`base/cadastros_em_retrato.py`, linha 915) e `ifdata_cadastro`. Esta função só lê a ponte pronta: não a monta.

- **Sem olhar o futuro:** para cada linha vale a linha da ponte mais nova **que já era pública** no dia em que o
  fato ficou público (`disponivel_em` da ponte menor ou igual ao do fato). Ponte que só existe depois, ou sem
  `disponivel_em`, não liga nada.
- **Sem pessoa:** a linha da ponte marcada `trata_como_pessoa` (MEI, empresário individual, natureza do grupo 4
  ou CNPJ que a Receita guardada não tem), ou que saiu da fonte (`consta` falso), deixa o CNPJ vazio.
- **Sem chute:** a chave tem de ser igual (só se tiram espaços e zeros à esquerda dos dois lados); nada é
  casado por nome. O que não liga fica com o CNPJ vazio, e a contagem diz quantas linhas ligaram.
- Ponte ausente (ainda não montada na base): as colunas saem vazias, a tabela não muda no resto.

Sem Streamlit; pandas só.
"""

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from base.parquet import arquivos_atuais, ler_tabela, origem_de_tabela

CHAVE_AUXILIAR = "_chave_da_ponte"
CNPJ_E_RAIZ = {
    "cnpj": "cnpj",
    "cnpj_basico": "cnpj_basico",
}  # coluna nova -> coluna da ponte
SO_A_RAIZ = {
    "cnpj_basico": "cnpj_raiz"
}  # IF.data: o cadastro dá a raiz, não o CNPJ inteiro


def _normal(serie: pd.Series) -> pd.Series:
    """A chave sem espaços e sem zeros à esquerda (o registro da ANS e o código da SUSEP vêm com e sem eles)."""
    return serie.astype("string").str.strip().str.lstrip("0")


def _usavel(ponte: pd.DataFrame) -> pd.Series:
    """Linhas da ponte que podem dar CNPJ: constam na fonte e não são pessoa (quando a ponte diz)."""
    ok = pd.Series(True, index=ponte.index)
    if "consta" in ponte:
        ok &= ponte["consta"].fillna(False).astype(bool)
    if "trata_como_pessoa" in ponte:
        ok &= ~ponte["trata_como_pessoa"].fillna(True).astype(bool)
    return ok


def com_cnpj_da_ponte(
    tabela: pd.DataFrame,
    chave: str,
    ponte: pd.DataFrame | None,
    saida: Mapping[str, str],
    chave_da_ponte: str = "id_na_fonte",
) -> tuple[pd.DataFrame, dict[str, int]]:
    """A tabela com as colunas de `saida` (coluna nova -> coluna da ponte) e a contagem do que ligou.

    `tabela` precisa de `chave` e `disponivel_em`; `ponte` de `chave_da_ponte`, `disponivel_em` e das colunas
    pedidas. Devolve uma cópia na mesma ordem; a original não muda."""
    resultado = tabela.copy()
    for nova in saida:
        resultado[nova] = pd.Series(pd.NA, index=resultado.index, dtype="string")
    contagem = {"linhas": len(tabela), "ligadas": 0, "ponte_vazia": 0}
    if ponte is None or ponte.empty or tabela.empty:
        contagem["ponte_vazia"] = 1
        return resultado, contagem
    esquerda = pd.DataFrame(
        {
            CHAVE_AUXILIAR: _normal(tabela[chave]),
            "disponivel_em": pd.to_datetime(tabela["disponivel_em"]),
        },
        index=tabela.index,
    )
    esquerda["_linha"] = range(len(esquerda))
    valida = esquerda[CHAVE_AUXILIAR].notna() & esquerda["disponivel_em"].notna()
    direita = pd.DataFrame(
        {
            CHAVE_AUXILIAR: _normal(ponte[chave_da_ponte]),
            "disponivel_em": pd.to_datetime(ponte["disponivel_em"]),
            "_usavel": _usavel(ponte),
            **{nova: ponte[velha].astype("string") for nova, velha in saida.items()},
        }
    )
    direita = direita[
        direita[CHAVE_AUXILIAR].notna() & direita["disponivel_em"].notna()
    ]
    ligada = pd.merge_asof(
        esquerda[valida].sort_values("disponivel_em"),
        direita.sort_values("disponivel_em"),
        on="disponivel_em",
        by=CHAVE_AUXILIAR,
        direction="backward",
    ).sort_values("_linha")
    ligada = ligada[ligada["_usavel"].fillna(False).astype(bool)]
    posicoes = ligada["_linha"].to_numpy()
    for nova in saida:
        coluna = resultado.columns.get_loc(nova)
        resultado.iloc[posicoes, coluna] = ligada[nova].to_numpy()
    contagem["ligadas"] = int(resultado[next(iter(saida))].notna().sum())
    return resultado, contagem


def ler_ponte(
    pasta: Path, raiz: Path
) -> tuple[pd.DataFrame | None, list[dict[str, str]]]:
    """A ponte gravada em `pasta` (todos os Parquets atuais, sem as versões guardadas) e as origens dela.

    `None` e nenhuma origem quando a pasta ainda não existe (a ponte não foi montada). As origens são as
    tabelas da ponte (`origem_de_tabela`, caminho a partir de `raiz`): a tabela que usa a ponte se refaz quando
    a ponte muda, e a linhagem dela chega aos originais pela ponte (série 4)."""
    arquivos = arquivos_atuais(pasta) if pasta.is_dir() else []
    if not arquivos:
        return None, []
    ponte = pd.concat([ler_tabela(a) for a in arquivos], ignore_index=True)
    return ponte, [origem_de_tabela(arquivo, raiz) for arquivo in arquivos]
