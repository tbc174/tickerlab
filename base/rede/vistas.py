"""As duas vistas das ligações (ADR 0077, item 3; plano, tarefa 3.3).

- **Interna**: a tabela `ligacoes` inteira, só em casa.
- **Publicada**: o que um dia vai ao VPS e à API (PR 5). **Nenhuma aresta de pessoa**: cada uma vira um
  atributo da empresa, gerado em casa, com fonte e data, e nenhum `id_pessoa` sai (ADR 0075):
  `socios_em_comum_com` (a outra empresa com o mesmo sócio, no mesmo período), `tem_socio_pep` e
  `administrador_sancionado`.

**Quem é tratado como pessoa** (`entidades.trata_como_pessoa`: MEI, empresário individual, grupo 4 e
natureza não informada; plano, D8) não recebe sinal negativo publicado: a sanção e a dívida dele não
saem, nem atributo vindo de pessoa. Entidade fora da rede conta como pessoa (o conservador). A aresta
anônima da lápide (sem a ponta) também não sai.

Nesta série nenhuma aresta real de pessoa existe: as funções ficam prontas e testadas com dado de mentira.
"""

import pandas as pd

from base.rede.ids import PREFIXO_DE_PESSOA

SOCIO_DE, ADMINISTRADOR_DE, PEP, SANCIONADA_POR = (
    "socio_de",
    "administrador_de",
    "pep",
    "sancionada_por",
)
# o que é sinal negativo sobre quem está em `de`
TIPOS_NEGATIVOS = (SANCIONADA_POR, "deve_a")
SOCIOS_EM_COMUM_COM, TEM_SOCIO_PEP, ADMINISTRADOR_SANCIONADO = (
    "socios_em_comum_com",
    "tem_socio_pep",
    "administrador_sancionado",
)
SIM = "sim"
COLUNAS_DOS_ATRIBUTOS = (
    "id_entidade", "atributo", "valor", "aconteceu_em", "publico_em", "ate", "fonte",
)  # fmt: skip
SEPARADOR_DE_FONTES = ","


def vista_interna(ligacoes: pd.DataFrame) -> pd.DataFrame:
    """Tudo: só em casa."""
    return ligacoes.copy()


def _e_pessoa(ids: pd.Series) -> pd.Series:
    return ids.astype(str).str.startswith(PREFIXO_DE_PESSOA)


def _juntar_fontes(*fontes: pd.Series) -> pd.Series:
    juntas = pd.concat(fontes, axis=1).astype(str)
    return juntas.apply(
        lambda linha: SEPARADOR_DE_FONTES.join(sorted(set(linha))), axis=1
    )


def _cruzam(a: pd.DataFrame, sufixo: str) -> pd.Series:
    """As duas arestas valeram ao mesmo tempo (o fim não inclui o dia)."""
    inicio = a[["aconteceu_em", f"aconteceu_em{sufixo}"]].max(axis=1)
    fim = a[["ate", f"ate{sufixo}"]].min(axis=1)
    return fim.isna() | inicio.isna() | (inicio < fim)


def _atributo(
    pares: pd.DataFrame, sufixo: str, atributo: str, coluna_do_valor: str | None = None
) -> pd.DataFrame:
    """Um atributo por par de arestas que se cruzam, público quando as duas eram públicas."""
    pares = pares[_cruzam(pares, sufixo)]
    return pd.DataFrame(
        {
            "id_entidade": pares["para"],
            "atributo": atributo,
            "valor": pares[coluna_do_valor] if coluna_do_valor else SIM,
            "aconteceu_em": pares[["aconteceu_em", f"aconteceu_em{sufixo}"]].max(
                axis=1
            ),
            "publico_em": pares[["publico_em", f"publico_em{sufixo}"]].max(axis=1),
            "ate": pares[["ate", f"ate{sufixo}"]].min(axis=1),
            "fonte": _juntar_fontes(pares["fonte"], pares[f"fonte{sufixo}"])
            if not pares.empty
            else pd.Series(dtype=object),
        }
    )


def _atributos_de_pessoas(ligacoes: pd.DataFrame) -> pd.DataFrame:
    """As arestas de pessoa viram atributos da empresa (sem a pessoa)."""
    de_pessoa = ligacoes[_e_pessoa(ligacoes["de"])]
    socios = de_pessoa[de_pessoa["tipo"] == SOCIO_DE]
    administradores = de_pessoa[de_pessoa["tipo"] == ADMINISTRADOR_DE]
    peps = de_pessoa[de_pessoa["tipo"] == PEP]
    sancoes = de_pessoa[de_pessoa["tipo"] == SANCIONADA_POR]
    em_comum = socios.merge(socios, on="de", suffixes=("", "_outra"))
    em_comum = em_comum[em_comum["para"] != em_comum["para_outra"]]
    partes = [
        _atributo(em_comum, "_outra", SOCIOS_EM_COMUM_COM, "para_outra"),
        _atributo(
            socios.merge(peps, on="de", suffixes=("", "_pep")), "_pep", TEM_SOCIO_PEP
        ),
        _atributo(
            administradores.merge(sancoes, on="de", suffixes=("", "_sancao")),
            "_sancao",
            ADMINISTRADOR_SANCIONADO,
        ),
    ]
    atributos = pd.concat(partes, ignore_index=True)[list(COLUNAS_DOS_ATRIBUTOS)]
    # vários sócios ou arestas dando o mesmo atributo: fica o que ficou público primeiro
    return (
        atributos.sort_values(
            ["id_entidade", "atributo", "valor", "publico_em"], kind="stable"
        )
        .drop_duplicates(["id_entidade", "atributo", "valor"])
        .reset_index(drop=True)
    )


def vista_publicada(
    ligacoes: pd.DataFrame, entidades: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(ligações sem pessoa, atributos das empresas): o que pode sair de casa.

    `entidades` precisa de `id_entidade` e `trata_como_pessoa`.
    """
    empresas = set(
        entidades.loc[~entidades["trata_como_pessoa"].astype(bool), "id_entidade"]
    )
    sem_pessoa = (
        ligacoes["de"].notna()
        & ligacoes["para"].notna()
        & ~_e_pessoa(ligacoes["de"])
        & ~_e_pessoa(ligacoes["para"])
    )
    negativo_sobre_pessoa = ligacoes["tipo"].isin(TIPOS_NEGATIVOS) & ~ligacoes[
        "de"
    ].isin(empresas)
    publicadas = ligacoes[sem_pessoa & ~negativo_sobre_pessoa].reset_index(drop=True)
    atributos = _atributos_de_pessoas(ligacoes)
    atributos = atributos[atributos["id_entidade"].isin(empresas)].reset_index(
        drop=True
    )
    return publicadas, atributos
