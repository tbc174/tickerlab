"""A tabela `ligacoes` da rede: uma linha por relação, com as três datas (ADR 0077; plano, tarefa 3.1).

Cada linha diz "`de` → `para`" com um `tipo` (`controlada_de`, `detem`, `emite`...). As três datas têm
nomes fixos: `aconteceu_em` é a data do fato (na sanção, a do ato administrativo publicado; a da infração
vai em `infracao_em`), `publico_em` quando ficou público e `coletado_em` quando a base guardou o arquivo
(do registro de coletas). `ate` é o fim, sem incluir o dia (vazio: ainda vale).

**Nada é apagado entre cargas** (plano, D6): a ligação que some da fonte fica, com `situacao` =
encerrada, `ate` = dia da carga e `encerrada_por` = carga; quando a própria fonte diz o fim,
`encerrada_por` = fonte. A única exceção é a lápide (`base/parquet.py::regravar_por_lapide`).

**Como era em D** (D5): `publico_em ≤ D` e (`ate` vazio ou `ate > D`); quem decide **no** dia D passa
D − 1. O `ate` é a data do fato: um fim que só ficou público depois aparece já no passado. Para o
retrato exato de uma carga antiga, use a versão guardada dela (`ligacoes.v<N>`).
"""

from collections.abc import Mapping, Sequence

import pandas as pd

COLUNAS = (
    "de", "para", "tipo", "papel", "participacao", "aconteceu_em", "infracao_em", "publico_em",
    "coletado_em", "ate", "situacao", "encerrada_por", "fonte", "origem_sha256", "conferido_por",
)  # fmt: skip
DATAS = ("aconteceu_em", "infracao_em", "publico_em", "coletado_em", "ate")
# o que identifica uma ligação entre uma carga e a outra (o fim e a situação podem mudar)
CHAVE = ["de", "para", "tipo", "papel", "aconteceu_em", "fonte"]
VIGENTE, ENCERRADA = "vigente", "encerrada"
PELA_CARGA, PELA_FONTE = "carga", "fonte"
SANCIONADA_POR = "sancionada_por"


def _dia(serie: pd.Series) -> pd.Series:
    """Datas sem hora nem fuso (as três datas são dias)."""
    datas = pd.to_datetime(serie, errors="coerce", utc=True)
    return datas.dt.tz_localize(None).dt.normalize().astype("datetime64[ns]")


def _chaves(tabela: pd.DataFrame) -> pd.Series:
    return pd.util.hash_pandas_object(tabela[CHAVE].astype(str), index=False)


def normalizar(tabela: pd.DataFrame) -> pd.DataFrame:
    """As colunas na ordem e nos tipos certos; `situacao` e `encerrada_por` pelo `ate` da fonte.

    Chave repetida é erro: quem monta as ligações de uma fonte junta antes o que é a mesma relação.
    """
    tabela = tabela.reindex(columns=list(COLUNAS)).copy()
    for coluna in DATAS:
        tabela[coluna] = _dia(tabela[coluna])
    tabela["participacao"] = pd.to_numeric(tabela["participacao"]).astype(float)
    texto = [c for c in COLUNAS if c not in DATAS and c != "participacao"]
    tabela[texto] = tabela[texto].astype(object).where(tabela[texto].notna(), None)
    encerrada = tabela["ate"].notna()
    tabela["situacao"] = tabela["situacao"].where(
        tabela["situacao"].notna(), encerrada.map({True: ENCERRADA, False: VIGENTE})
    )
    tabela["encerrada_por"] = tabela["encerrada_por"].where(
        tabela["encerrada_por"].notna() | ~encerrada, PELA_FONTE
    )
    if _chaves(tabela).duplicated().any():
        raise ValueError("ligação com a chave repetida (de, para, tipo, papel, data)")
    return tabela.sort_values(CHAVE, na_position="first", kind="stable").reset_index(
        drop=True
    )


def de_sancoes(sancoes: pd.DataFrame) -> pd.DataFrame:
    """Sanções (série de governo): o fato é o ato publicado, a infração fica em `infracao_em`."""
    return normalizar(
        sancoes.rename(columns={"ato_publicado_em": "aconteceu_em"}).assign(
            tipo=SANCIONADA_POR, conferido_por="regra"
        )
    )


def juntar_com_a_vigente(
    nova: pd.DataFrame, vigente: pd.DataFrame | None, dia_da_carga: pd.Timestamp
) -> pd.DataFrame:
    """A carga nova somada à tabela que já existe, sem apagar nada (D6).

    - a ligação que continua fica como a nova diz (o fim pode ter chegado), com o `publico_em` e o
      `coletado_em` da primeira vez em que a base soube dela;
    - a que sumiu da fonte fica, encerrada pela carga no `dia_da_carga` (se ainda estava vigente);
    - a nova entra.
    """
    nova = normalizar(nova)
    if vigente is None or vigente.empty:
        return nova
    chave_nova, chave_vigente = _chaves(nova), _chaves(vigente)
    primeira_vez = vigente.assign(_chave=chave_vigente.to_numpy()).set_index("_chave")[
        ["publico_em", "coletado_em"]
    ]
    nova = nova.assign(_chave=chave_nova.to_numpy())
    ja_sabia = nova["_chave"].isin(primeira_vez.index)
    for coluna in ("publico_em", "coletado_em"):
        nova[coluna] = nova[coluna].mask(
            ja_sabia, nova["_chave"].map(primeira_vez[coluna])
        )
    sumiram = vigente[~chave_vigente.isin(chave_nova).to_numpy()].copy()
    agora = sumiram["situacao"] == VIGENTE
    sumiram.loc[agora, "situacao"] = ENCERRADA
    sumiram.loc[agora, "encerrada_por"] = PELA_CARGA
    sumiram.loc[agora, "ate"] = pd.Timestamp(dia_da_carga).normalize()
    return normalizar(pd.concat([nova.drop(columns="_chave"), sumiram]))


def como_era_em(ligacoes: pd.DataFrame, dia: pd.Timestamp) -> pd.DataFrame:
    """As ligações como a base as conhecia no dia (D5): públicas até ele e ainda não encerradas."""
    dia = pd.Timestamp(dia)
    valia = (ligacoes["publico_em"] <= dia) & (
        ligacoes["ate"].isna() | (ligacoes["ate"] > dia)
    )
    return ligacoes[valia]


def com_coletado_em(
    ligacoes: pd.DataFrame, registro: Mapping[str, pd.Timestamp]
) -> pd.DataFrame:
    """`coletado_em` pelo registro de coletas: o dia em que a base guardou o arquivo da `origem_sha256`."""
    coletado = ligacoes["origem_sha256"].map(dict(registro))
    return ligacoes.assign(coletado_em=_dia(coletado))


SEM_VALOR = (
    "\x00"  # para comparar chaves com vazio sem que vazio seja diferente de vazio
)


def comprimir_periodos(linhas: pd.DataFrame, chave: Sequence[str]) -> pd.DataFrame:
    """Passos seguidos (`inicio`..`fim`, inteiros) da mesma chave viram um período só.

    Cada linha é um pedaço `inicio`..`fim` (um mês da carteira tem `inicio` = `fim`); um pedaço que
    começa logo depois do fim do anterior continua o período, um buraco começa outro. As outras colunas
    ficam as do primeiro pedaço (o `publico_em` é o de quando o período começou a ser público). Serve
    também para juntar períodos já comprimidos (os de cada ano).
    """
    chave = list(chave)
    ordenadas = (
        linhas.sort_values([*chave, "inicio"], kind="stable")
        .drop_duplicates([*chave, "inicio"])
        .reset_index(drop=True)
    )
    comparavel = ordenadas[chave].astype(object).fillna(SEM_VALOR)
    outra_chave = (comparavel != comparavel.shift()).any(axis=1)
    fim_ate_aqui = ordenadas.groupby(outra_chave.cumsum())["fim"].cummax().shift()
    novo = outra_chave | (ordenadas["inicio"] > fim_ate_aqui + 1)
    grupo = novo.cumsum()
    outras = {c: "first" for c in ordenadas.columns if c not in (*chave, "fim")}
    juntas = ordenadas.groupby(grupo).agg({**dict.fromkeys(chave, "first"), **outras})
    juntas["fim"] = ordenadas.groupby(grupo)["fim"].max()
    return juntas[list(ordenadas.columns)].reset_index(drop=True)
