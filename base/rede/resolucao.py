"""Resolução de entidades pelas regras de código, em ordem fixa (ADR 0077, item 4; plano, tarefa 2.6).

Cada fonte vira **observações** (`base/rede/montar.py`): "a âncora tem este identificador, de `desde` a
`ate`, público desde `publico_em`, pela regra N". A **âncora** é o que dá identidade (plano, D3): a raiz
do CNPJ na empresa (a filial liga pela raiz) e o CNPJ de 14 no fundo. O id sai dela (`base/rede/ids.py`).

Regras (ADR 0077, item 4): 1 CNPJ de 14; 2 raiz de 8; 3 LEI pelo GLEIF; 4 ISIN, emissor e ticker; 5
código do regulador; 7 tabela conferida à mão. A 6 (nome exato contra lista fechada) é da série de
governo. **Nada aproximado liga, e conflito não liga:** o mesmo identificador em duas entidades ao mesmo
tempo sai das duas e fica em `conflitos`, para a conferência medir.
"""

import pandas as pd

from base.rede import ids

REGRAS = (
    (1, "CNPJ de 14"),
    (2, "raiz do CNPJ"),
    (3, "LEI pelo GLEIF"),
    (4, "ISIN, emissor ou ticker"),
    (5, "código do regulador"),
    (7, "tabela conferida à mão"),
)
PELA_REGRA, PELA_TABELA = "regra", "tabela"
SISTEMA_DA_ANCORA = {"empresa": "cnpj_raiz", "fundo": "cnpj"}
COLUNAS_DAS_OBSERVACOES = (
    "fonte", "tipo", "ancora", "sistema", "valor", "desde", "ate", "publico_em", "regra",
    "conferido_por", "nome", "prioridade_do_nome", "natureza_da_fonte",
)  # fmt: skip
COLUNAS_DAS_ENTIDADES = (
    "id_entidade", "tipo", "ancora", "nome", "natureza_da_fonte", "fontes", "publico_em",
)  # fmt: skip
COLUNAS_DOS_IDENTIFICADORES = (
    "id_entidade", "sistema", "valor", "desde", "ate", "publico_em", "regra", "conferido_por",
    "fontes",
)  # fmt: skip
PERIODO = ["id_entidade", "sistema", "valor", "desde", "ate"]
SEM_PRIORIDADE = 99
_MUITO_ANTES, _MUITO_DEPOIS = pd.Timestamp.min, pd.Timestamp.max


def _juntar_fontes(fontes: pd.Series) -> str:
    return ",".join(sorted(set(fontes.dropna())))


def _ids(observacoes: pd.DataFrame, fixados: dict[ids.Chave, str]) -> pd.Series:
    primarios = pd.DataFrame(
        {
            "tipo": observacoes["tipo"],
            "sistema": observacoes["tipo"].map(SISTEMA_DA_ANCORA),
            "valor": observacoes["ancora"],
        }
    )
    return ids.atribuir_ids(primarios, fixados)


def _juntar_repetidos(observacoes: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (entidade, identificador, período): fontes juntas, a menor regra, a 1ª data pública."""
    pela_regra = observacoes["conferido_por"] == PELA_REGRA
    return (
        observacoes.assign(_pela_regra=pela_regra)
        .groupby(PERIODO, dropna=False, sort=True)
        .agg(
            publico_em=("publico_em", "min"),
            regra=("regra", "min"),
            _pela_regra=("_pela_regra", "any"),
            fontes=("fonte", _juntar_fontes),
            ancora=("ancora", "first"),
        )
        .reset_index()
        .assign(
            conferido_por=lambda t: t["_pela_regra"].map(
                {True: PELA_REGRA, False: PELA_TABELA}
            )
        )
        .drop(columns="_pela_regra")
    )


def _cruzam_com_outra_entidade(identificadores: pd.DataFrame) -> pd.Series:
    """Verdadeiro na linha cujo identificador está em outra entidade num período que se cruza."""
    linhas = identificadores.assign(
        _linha=range(len(identificadores)),
        _inicio=identificadores["desde"].fillna(_MUITO_ANTES),
        _fim=identificadores["ate"].fillna(_MUITO_DEPOIS),
    )
    varias = (
        linhas.groupby(["sistema", "valor"])["id_entidade"].transform("nunique") > 1
    )
    candidatas = linhas.loc[
        varias, ["_linha", "sistema", "valor", "id_entidade", "_inicio", "_fim"]
    ]
    pares = candidatas.merge(
        candidatas, on=["sistema", "valor"], suffixes=("", "_outra")
    )
    cruzam = (
        (pares["id_entidade"] != pares["id_entidade_outra"])
        & (pares["_inicio"] < pares["_fim_outra"])
        & (pares["_inicio_outra"] < pares["_fim"])
    )
    em_conflito = set(pares.loc[cruzam, "_linha"])
    return pd.Series(
        [n in em_conflito for n in range(len(linhas))], index=identificadores.index
    )


def _entidades(observacoes: pd.DataFrame) -> pd.DataFrame:
    ordem = observacoes.assign(
        _prioridade=observacoes["prioridade_do_nome"].fillna(SEM_PRIORIDADE)
    ).sort_values(  # o nome da fonte mais confiável; nela, o mais recente
        ["id_entidade", "_prioridade", "publico_em", "nome"],
        ascending=[True, True, False, True],
        na_position="last",
    )
    por_entidade = ordem.groupby("id_entidade", sort=True)
    return pd.DataFrame(
        {
            "tipo": por_entidade["tipo"].first(),
            "ancora": por_entidade["ancora"].first(),
            "nome": por_entidade["nome"].first(),
            "natureza_da_fonte": por_entidade["natureza_da_fonte"].first(),
            "fontes": por_entidade["fonte"].agg(_juntar_fontes),
            "publico_em": por_entidade["publico_em"].min(),
        }
    ).reset_index()[list(COLUNAS_DAS_ENTIDADES)]


def resolver(
    observacoes: pd.DataFrame, fixados: dict[ids.Chave, str]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(entidades, identificadores, conflitos) das observações de todas as fontes.

    `entidades` ainda sem natureza (`base/rede/entidades.py::com_natureza` completa); `conflitos` são
    as linhas que saíram, com a âncora, a regra e as fontes, para medir.
    """
    observacoes = observacoes.assign(id_entidade=_ids(observacoes, fixados))
    juntos = _juntar_repetidos(observacoes)
    cruzam = _cruzam_com_outra_entidade(juntos)
    identificadores = juntos.loc[
        ~cruzam, list(COLUNAS_DOS_IDENTIFICADORES)
    ].reset_index(drop=True)
    conflitos = juntos.loc[cruzam].reset_index(drop=True)
    return _entidades(observacoes), identificadores, conflitos
