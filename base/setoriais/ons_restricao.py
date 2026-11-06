"""Restrição de geração eólica e solar do ONS (série T, PR T6): quanto cada usina (ou conjunto) deixou de
gerar por ordem do operador (curtailment), por usina e hora.

A fonte traz uma leitura a cada 30 minutos (eólica desde 10/2021, fotovoltaica desde 04/2024; ~100 mil
linhas por mês). A base guarda **uma linha por usina e hora**: média das duas leituras nas colunas de
potência (MWmed, que numa hora é o mesmo número em MWh), soma dos minutos e a primeira razão e origem da
restrição da hora. Hora sem restrição fica com a energia não realizada **vazia** (a fonte só apura nas
horas com restrição: vazio não é zero).

O ONS fecha a apuração depois (a referência final e a energia apurada aparecem em arquivos novos de um
mês já publicado): cada arquivo é uma coleta e a revisão vale desde o dia em que foi vista
(`base/setoriais/revisoes.py`). O dono da usina não vem no arquivo: o que existe é o agente operador, ligado
à empresa pelo nome exato do agente na B13 (a mesma chave da capacidade); nada é casado por semelhança.
"""

import re

import pandas as pd

from base.setoriais import ons, prazos
from base.setoriais.comum import sem_espacos

FONTE = "ons-restricao-eolica-solar"
FONTE_DA_LIGACAO = "ons-capacidade-geracao"
TIPOS = {"EOLICA": "eolica", "FOTOVOLTAICA": "fotovoltaica"}
# o tipo vem do nome do arquivo (a pasta do ONS já mudou de nome entre as publicações)
ARQUIVO = re.compile(r"/RESTRICAO_COFF_(EOLICA|FOTOVOLTAICA)_(\d{4})_(\d{2})\.parquet$")
COLUNAS = (
    "instante", "tipo", "id_subsistema", "uf", "usina", "id_ons", "ceg", "agente_operador",
    "geracao_mwmed", "referencia_mwmed", "referencia_final_mwmed", "disponibilidade_mwmed",
    "nao_realizada_mwmed", "minutos_restricao", "razao_da_restricao", "origem_da_restricao",
    "leituras", "disponivel_em",
)  # fmt: skip
CHAVE = ("instante", "tipo", "id_ons")
CARIMBOS: tuple[str, ...] = ()
MEDIAS = {
    "val_geracao": "geracao_mwmed", "val_geracaoreferencia": "referencia_mwmed",
    "val_geracaoreferenciafinal": "referencia_final_mwmed",
    "val_disponibilidade": "disponibilidade_mwmed",
    "val_geracaonaorealizadaapurada": "nao_realizada_mwmed",
}  # fmt: skip
TEXTOS = {
    "id_subsistema": "id_subsistema", "id_estado": "uf", "nom_usina": "usina", "id_ons": "id_ons",
    "ceg": "ceg", "nom_agenteoperador": "agente_operador",
}  # fmt: skip
SEM_CODIGO = ("-", "")


def destino(url: str) -> str | None:
    """O nome do Parquet de cada arquivo mensal (`eolica_2026_09`); None para o dicionário em PDF."""
    achado = ARQUIVO.search(url)
    return None if achado is None else f"{achado[1].lower()}_{achado[2]}_{achado[3]}"


def _tipo(url: str) -> str:
    achado = ARQUIVO.search(url)
    if achado is None:
        raise ValueError(
            f"tipo de usina (eólica ou fotovoltaica) fora do endereço: {url}"
        )
    return TIPOS[achado[1]]


def _primeiro(coluna: pd.Series) -> object:
    return coluna.dropna().iloc[0] if coluna.notna().any() else None


def ler(conteudo_do_parquet: bytes, url: str) -> pd.DataFrame:
    """Um arquivo mensal de restrição, agregado por usina e hora, com `disponivel_em`."""
    tipo = _tipo(url)
    bruta = ons.ler_original_em_parquet(conteudo_do_parquet)
    bruta["instante"] = pd.to_datetime(bruta["din_instante"]).dt.floor("h")
    for coluna in TEXTOS:
        bruta[coluna] = sem_espacos(bruta[coluna], vazio_vira_none=True)
    bruta["ceg"] = bruta["ceg"].mask(bruta["ceg"].isin(SEM_CODIGO), None)
    grupos = bruta.groupby(["instante", "id_ons"], sort=True, dropna=False)
    tabela = grupos.agg(
        **{novo: (velho, "mean") for velho, novo in MEDIAS.items()},
        minutos_restricao=("num_minutos_restricao", lambda m: m.sum(min_count=1)),
        razao_da_restricao=("cod_razaorestricao", _primeiro),
        origem_da_restricao=("cod_origemrestricao", _primeiro),
        leituras=("din_instante", "size"),
        **{
            novo: (velho, "first")
            for velho, novo in TEXTOS.items()
            if velho != "id_ons"
        },
    ).reset_index()
    tabela["tipo"] = tipo
    tabela["minutos_restricao"] = tabela["minutos_restricao"].astype("Int64")
    for coluna in ("razao_da_restricao", "origem_da_restricao"):
        tabela[coluna] = (
            tabela[coluna].astype(object).where(tabela[coluna].notna(), None)
        )
    tabela["disponivel_em"] = prazos.disponivel_ons(tabela["instante"])
    return tabela.reindex(columns=list(COLUNAS))
