"""Meta da Selic (SGS 432) e Focus Selic anual na base, com a safra (ADR 0093, notícias de dado).

As duas séries já estão no acervo do VPS (`observacoes`, com a safra em `divulgado_em`); aqui elas
viram uma **tabela derivada** da exportação do acervo (`src/exportacao_do_acervo.py`), sem coleta nova
(regra 2.1 da ADR 0090). A nota do Copom lê daqui, pela base, e não do banco do VPS.

- `bcb-sgs-432`: a meta da Selic. A meta só muda quando o Copom muda; a manutenção não aparece.
- `focus-selic-anual`: a mediana do Focus para a Selic no fim de cada ano (`bcb-focus-selic` no
  acervo). É o Focus **anual**, não o "por reunião" (esse seria coleta nova).
- Cada revisão é uma linha a mais: o valor passa a valer em `divulgado_em` (a safra), que também é
  `publico_em`. A linha antiga fica, para "como era na data" funcionar.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from base.dias_uteis import proximo_dia_util
from base.parquet import LINHAGEM, gravar_se_mudou, hash_da_tabela
from src.versao_do_codigo import versao_do_codigo

TABELA = "bcb_selic_focus"
CAMINHO_DO_COPOM = Path(__file__).resolve().parent / "conferidas" / "copom_reunioes.csv"
SERIE_DA_META = "bcb-sgs-432"
SERIE_DO_FOCUS = "bcb-focus-selic"
SERIES_DO_ACERVO = {
    SERIE_DA_META: SERIE_DA_META,
    SERIE_DO_FOCUS: "focus-selic-anual",
}
COLUNAS_DAS_OBSERVACOES = [
    "serie",
    "referencia",
    "valor",
    "divulgado_em",
    "registrado_em",
]
CHAVE = ["serie", "referencia", "divulgado_em"]
COLUNAS = [
    "serie",
    "referencia",
    "valor",
    "divulgado_em",
    "publico_em",
    "origem_coletada_em",
    "origem_sha256",
    "montado_em",
    "versao_do_codigo",
]


def montar(observacoes: pd.DataFrame) -> pd.DataFrame:
    """Só a meta da Selic e o Focus Selic anual, uma linha por safra, em ordem fixa."""
    if observacoes.empty:
        return pd.DataFrame(columns=COLUNAS)
    escolhidas = pd.DataFrame(observacoes[observacoes["serie"].isin(SERIES_DO_ACERVO)])
    saida = pd.DataFrame(
        {
            "serie": pd.Series(escolhidas["serie"]).map(SERIES_DO_ACERVO),
            "referencia": pd.to_datetime(escolhidas["referencia"]),
            "valor": escolhidas["valor"].astype(float),
            "divulgado_em": pd.to_datetime(escolhidas["divulgado_em"]),
            "origem_coletada_em": pd.to_datetime(escolhidas["registrado_em"], utc=True),
        }
    )
    saida["publico_em"] = saida["divulgado_em"]
    saida = saida.sort_values(CHAVE).reset_index(drop=True)
    return saida.reindex(columns=COLUNAS)


def gravar(observacoes: pd.DataFrame, pasta: Path, agora: datetime) -> int:
    """`<pasta>/bcb_selic_focus/bcb_selic_focus.parquet` com manifesto; devolve as linhas gravadas."""
    tabela = montar(observacoes)
    if tabela.empty:
        return 0
    tabela = tabela.assign(
        origem_sha256=hash_da_tabela(tabela.drop(columns=COLUNAS[6:]), CHAVE),
        montado_em=pd.Timestamp(agora).isoformat(),
        versao_do_codigo=versao_do_codigo(),
    )
    gravar_se_mudou(
        tabela,
        pasta / TABELA / TABELA,
        [{"url": "acervo:series", "sha256": str(tabela["origem_sha256"].iloc[0])}],
        CHAVE,
        carimbos=LINHAGEM,
    )
    return len(tabela)


def reunioes_do_copom(caminho: Path = CAMINHO_DO_COPOM) -> pd.DataFrame:
    """As reuniões do Copom conferidas à mão (`base/conferidas/copom_reunioes.csv`), da mais velha à mais nova.

    O Banco Central não publica o calendário numa tabela que a base coleta, e a meta (SGS 432) só muda
    quando o Copom muda: a manutenção não aparece na série. Por isso a tabela é conferida à mão.
    """
    reunioes = pd.read_csv(
        caminho, sep=";", parse_dates=["data", "conferido_em"], encoding="utf-8"
    )
    return reunioes.sort_values("reuniao").reset_index(drop=True)


def divergencias_com_a_sgs(
    reunioes: pd.DataFrame, selic_focus: pd.DataFrame
) -> list[dict[str, object]]:
    """Reuniões cuja meta conferida não é a da SGS 432 no dia útil seguinte (vazio = tudo bate).

    A meta decidida vale a partir do dia útil seguinte à reunião. Sem valor da SGS naquele dia, a
    reunião também diverge (`meta_sgs` None): a nota do Copom não sai sem as duas fontes de acordo.
    """
    metas = pd.DataFrame(selic_focus[selic_focus["serie"] == SERIE_DA_META])
    metas = metas.sort_values("divulgado_em").drop_duplicates("referencia", keep="last")
    da_sgs = dict(
        zip(
            pd.to_datetime(metas["referencia"]),
            metas["valor"].astype(float),
            strict=True,
        )
    )
    vigente_em = proximo_dia_util(pd.Series(reunioes["data"]))
    divergencias: list[dict[str, object]] = []
    for (_, reuniao), dia in zip(reunioes.iterrows(), vigente_em, strict=True):
        meta_sgs = da_sgs.get(pd.Timestamp(dia))
        meta = float(reuniao["meta_selic"])
        if meta_sgs is None or abs(meta_sgs - meta) > 1e-9:
            divergencias.append(
                {
                    "reuniao": int(reuniao["reuniao"]),
                    "meta_conferida": meta,
                    "meta_sgs": meta_sgs,
                    "vigente_em": pd.Timestamp(dia).date(),
                }
            )
    return divergencias


def _dia_da_coleta(coletado_em: datetime) -> pd.Timestamp:
    return pd.Timestamp(coletado_em).tz_localize(None).normalize()


def observacoes_da_meta(conteudo: bytes, coletado_em: datetime) -> pd.DataFrame:
    """A SGS 432 como o banco de produção a guarda: a meta vale desde o dia em que aparece."""
    itens = pd.DataFrame(json.loads(conteudo))
    if itens.empty:
        return pd.DataFrame(columns=COLUNAS_DAS_OBSERVACOES)
    dia = pd.to_datetime(itens["data"], format="%d/%m/%Y")
    # o SGS responde também as semanas seguintes: a meta só vale a partir do dia em que aparece
    itens, dia = (
        itens[dia <= _dia_da_coleta(coletado_em)],
        dia[dia <= _dia_da_coleta(coletado_em)],
    )
    return pd.DataFrame(
        {
            "serie": SERIE_DA_META,
            "referencia": dia,
            "valor": itens["valor"].astype(float),
            "divulgado_em": dia,
            "registrado_em": pd.Timestamp(coletado_em),
        }
    )


def observacoes_do_focus(conteudo: bytes, coletado_em: datetime) -> pd.DataFrame:
    """O Focus Selic anual: a safra é a data da pesquisa; a referência, o fim do ano projetado."""
    itens = pd.DataFrame(json.loads(conteudo)["value"])
    if itens.empty:
        return pd.DataFrame(columns=COLUNAS_DAS_OBSERVACOES)
    ano = pd.to_numeric(itens["DataReferencia"]).astype(int)
    return pd.DataFrame(
        {
            "serie": SERIE_DO_FOCUS,
            "referencia": pd.to_datetime(ano.astype(str) + "-12-31"),
            "valor": itens["Mediana"].astype(float),
            "divulgado_em": pd.to_datetime(itens["Data"]),
            "registrado_em": pd.Timestamp(coletado_em),
        }
    )
