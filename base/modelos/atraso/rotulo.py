"""Exemplos e rótulo do modelo de atraso na entrega da DFP/ITR (modelo 8 do catálogo, ADR 0030).

Um **exemplo** é uma empresa, um documento (DFP ou ITR) e uma data-base. A pergunta do modelo é feita
na própria data-base (`data_da_previsao`): a empresa vai entregar depois do prazo da CVM?

Quem entra:
- todo documento entregue até `hoje` (a primeira versão vale: reapresentar depois do prazo não é
  atraso);
- o documento que a empresa **devia e não entregou**: entregou o mesmo documento um ano antes e estava
  registrada e ativa no cadastro da CVM na data do prazo (a mesma regra da R8). Só o primeiro ano
  sem entrega entra; empresa fora do cadastro nunca "deve" (não dá para saber). E só conta como
  falta uma data-base que outra empresa entregou: sem o arquivo do ano no índice (um download que
  falhou), ninguém "deixou de entregar"; e só no calendário da empresa (DFP no mês de fim do
  exercício, ITR nos outros fins de trimestre): uma DFP especial fora do exercício não se repete.
- documento sem entrega com o prazo ainda aberto fica de fora: a resposta ainda não existe.

O rótulo `atrasou` vale 1 com a entrega 1 dia útil ou mais depois do prazo (`src/prazos.py`, com a UF
da sede e o mês de fim do exercício), ou sem entrega com o prazo vencido. Medidos, sem decidir nada:
`dias_uteis_de_atraso`, `atraso_grave` (mais de 30 dias corridos ou não entregou) e `zona_cinzenta`
(1 ou 2 dias úteis: pode ser um feriado local).

O rótulo não é coluna para prever: o mês de fim do exercício sai de todas as DFPs da empresa, e a UF,
do cadastro de hoje (ver `base/cadastro.py`).
"""

import numpy as np
import pandas as pd

from base.dias_uteis import dias_uteis
from src.prazos import ATRASO_GRAVE, prazo

COLUNAS = (
    "cnpj",
    "empresa",
    "documento",
    "referencia",
    "data_da_previsao",
    "prazo",
    "primeira_entrega",
    "dias_uteis_de_atraso",
    "atrasou",
    "atraso_grave",
    "zona_cinzenta",
    "uf",
    "mes_fim_do_exercicio",
)
DOCUMENTO = ["cnpj", "documento", "referencia"]
ZONA_CINZENTA = 2  # dias úteis


def _entregues(indice: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """Cada documento com a data da primeira entrega até `hoje` e o nome mais recente da empresa."""
    ate_hoje = indice.dropna(subset=["referencia", "recebido_em"])
    ate_hoje = ate_hoje[ate_hoje["recebido_em"] <= hoje].sort_values("recebido_em")
    return ate_hoje.groupby(DOCUMENTO, as_index=False).agg(
        empresa=("empresa", "last"), primeira_entrega=("recebido_em", "min")
    )


def _mes_fim_do_exercicio(indice: pd.DataFrame) -> pd.Series:
    """Por CNPJ, o mês das data-bases da DFP que mais aparece (12 quando não há DFP)."""
    dfp = indice[indice["documento"] == "DFP"].dropna(subset=["referencia"])
    dfp = dfp.drop_duplicates(DOCUMENTO)
    meses = dfp["referencia"].dt.month
    return meses.groupby(dfp["cnpj"]).agg(lambda m: int(m.mode().max()))


def _ativa_no_prazo(candidatos: pd.DataFrame, cadastro: pd.DataFrame) -> pd.Series:
    """Para cada candidato, se algum registro da empresa estava ativo na data do prazo."""
    juntos = candidatos[["cnpj", "prazo"]].reset_index().merge(cadastro, on="cnpj")
    ativa = (juntos["registro"].isna() | (juntos["registro"] <= juntos["prazo"])) & (
        juntos["cancelamento"].isna() | (juntos["cancelamento"] > juntos["prazo"])
    )
    return (
        ativa.groupby(juntos["index"]).any().reindex(candidatos.index, fill_value=False)
    )


def _com_prazo(
    exemplos: pd.DataFrame, ufs: pd.Series, meses: pd.Series
) -> pd.DataFrame:
    exemplos = exemplos.assign(
        uf=exemplos["cnpj"].map(ufs).fillna(""),
        mes_fim_do_exercicio=exemplos["cnpj"].map(meses).fillna(12).astype(int),
    )
    prazos = [
        prazo(d, r.date(), mes_fim_do_exercicio=m, uf=u)
        for d, r, m, u in zip(
            exemplos["documento"],
            exemplos["referencia"],
            exemplos["mes_fim_do_exercicio"],
            exemplos["uf"],
            strict=True,
        )
    ]
    return exemplos.assign(
        prazo=pd.to_datetime(pd.Series(prazos, index=exemplos.index))
    )


def _esta_em(
    tabela: pd.DataFrame, outra: pd.DataFrame, colunas: list[str]
) -> pd.Series:
    chaves = pd.MultiIndex.from_frame(outra[colunas])
    return pd.Series(
        pd.MultiIndex.from_frame(tabela[colunas]).isin(chaves), index=tabela.index
    )


def _no_calendario_da_empresa(exemplos: pd.DataFrame) -> pd.Series:
    """DFP no mês de fim do exercício; ITR nos outros fins de trimestre do exercício."""
    distancia = (
        exemplos["referencia"].dt.month - exemplos["mes_fim_do_exercicio"]
    ) % 12
    dfp = exemplos["documento"] == "DFP"
    return (dfp & (distancia == 0)) | (~dfp & (distancia != 0) & (distancia % 3 == 0))


def _devidos_sem_entrega(
    entregues: pd.DataFrame,
    cadastro: pd.DataFrame,
    ufs: pd.Series,
    meses: pd.Series,
    hoje: pd.Timestamp,
) -> pd.DataFrame:
    """Os documentos de um ano depois de cada entrega que não chegaram e já venceram.

    Só data-bases do calendário da empresa (uma DFP especial fora do exercício não se repete) e que
    outra empresa entregou (o arquivo do ano está no índice).
    """
    seguinte = entregues["referencia"] + pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
    candidatos = entregues.assign(referencia=seguinte).drop(columns="primeira_entrega")
    candidatos = candidatos[
        ~_esta_em(candidatos, entregues, DOCUMENTO)
        & _esta_em(candidatos, entregues, ["documento", "referencia"])
    ]
    candidatos = _com_prazo(candidatos.reset_index(drop=True), ufs, meses)
    vencidos = candidatos[
        (candidatos["prazo"] < hoje) & _no_calendario_da_empresa(candidatos)
    ]
    return vencidos[_ativa_no_prazo(vencidos, cadastro)].assign(primeira_entrega=pd.NaT)


def montar_exemplos(
    indice: pd.DataFrame, cadastro: pd.DataFrame, hoje: pd.Timestamp
) -> pd.DataFrame:
    """Os exemplos com o rótulo, como se sabia em `hoje`.

    `indice`: as entregas de DFP e ITR de todos os anos (`base/contas_cvm.ler_indice`, juntos);
    `cadastro`: `base/cadastro.ler_cadastro` (`cnpj`, `registro`, `cancelamento`, `uf`).
    """
    if indice.empty:
        return pd.DataFrame(columns=list(COLUNAS))
    entregues = _entregues(indice, hoje)
    if entregues.empty:
        return pd.DataFrame(columns=list(COLUNAS))
    ufs = (
        cadastro[cadastro["uf"].ne("")].drop_duplicates("cnpj").set_index("cnpj")["uf"]
    )
    meses = _mes_fim_do_exercicio(indice)
    exemplos = pd.concat(
        [
            _com_prazo(entregues, ufs, meses),
            _devidos_sem_entrega(entregues, cadastro, ufs, meses, hoje),
        ],
        ignore_index=True,
    )
    entregue = exemplos["primeira_entrega"].notna()
    fim = exemplos["primeira_entrega"].where(entregue, hoje)
    dias = np.maximum(dias_uteis(exemplos["prazo"], fim), 0)
    corridos = (fim - exemplos["prazo"]).dt.days
    atrasou = ~entregue | (exemplos["primeira_entrega"] > exemplos["prazo"])
    exemplos = exemplos.assign(
        data_da_previsao=exemplos["referencia"],
        dias_uteis_de_atraso=dias,
        atrasou=atrasou,
        atraso_grave=~entregue | (corridos > ATRASO_GRAVE),
        zona_cinzenta=entregue & atrasou & (dias <= ZONA_CINZENTA),
    )
    return (
        exemplos[list(COLUNAS)]
        .sort_values(["referencia", "documento", "cnpj"])
        .reset_index(drop=True)
    )
