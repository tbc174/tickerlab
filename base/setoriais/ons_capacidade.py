"""Capacidade instalada do ONS (série T, PR T6): uma linha por unidade geradora, com a potência efetiva
(MW), o proprietário e o operador, a data de entrada em operação e a de desativação.

O arquivo é a foto de hoje do cadastro (uma captura, 14/10/2026), não uma série. Para não olhar o futuro:

- a unidade vale desde a **entrada em operação** (`disponivel_em`): antes disso ela não existe para quem
  pergunta, e a data de desativação só pode ser usada depois de passar;
- a potência de hoje vale desde a entrada (limite conhecido: mudanças de potência antes da 1ª coleta não
  aparecem); a partir daí, cada baixada que traz outro valor entra como revisão (`visto_em`).

O proprietário liga à empresa pelo nome exato do agente na B13 (a chave do `empresa_serie`); o que não
liga vai para os buracos com a potência.
"""

import pandas as pd

from base.setoriais import ons
from base.setoriais.comum import sem_espacos

FONTE = "ons-capacidade-geracao"
ARQUIVO = "CAPACIDADE_GERACAO.parquet"
COLUNAS = (
    "id_subsistema", "uf", "modalidade_de_operacao", "proprietario", "operador", "tipo_de_usina",
    "usina", "ceg", "unidade_geradora", "cod_equipamento", "numero_da_unidade", "combustivel",
    "entrada_em_teste", "entrada_em_operacao", "desativada_em", "potencia_efetiva_mw", "disponivel_em",
)  # fmt: skip
CHAVE = ("cod_equipamento",)
CARIMBOS: tuple[str, ...] = ()
TEXTOS = {
    "id_subsistema": "id_subsistema", "id_estado": "uf", "nom_modalidadeoperacao": "modalidade_de_operacao",
    "nom_agenteproprietario": "proprietario", "nom_agenteoperador": "operador",
    "nom_tipousina": "tipo_de_usina", "nom_usina": "usina", "ceg": "ceg",
    "nom_unidadegeradora": "unidade_geradora", "cod_equipamento": "cod_equipamento",
    "num_unidadegeradora": "numero_da_unidade", "nom_combustivel": "combustivel",
}  # fmt: skip
DATAS = {
    "dat_entradateste": "entrada_em_teste", "dat_entradaoperacao": "entrada_em_operacao",
    "dat_desativacao": "desativada_em",
}  # fmt: skip


def destino(url: str) -> str | None:
    return "capacidade" if url.endswith("/" + ARQUIVO) else None


def ler(conteudo_do_parquet: bytes) -> pd.DataFrame:
    """O cadastro de unidades geradoras, com `disponivel_em` = entrada em operação (ou em teste)."""
    tabela = ons.ler_original_em_parquet(conteudo_do_parquet)
    for velho, novo in TEXTOS.items():
        tabela[novo] = sem_espacos(tabela[velho], vazio_vira_none=True)
    for velho, novo in DATAS.items():
        tabela[novo] = pd.to_datetime(tabela[velho], errors="coerce")
    tabela["potencia_efetiva_mw"] = pd.to_numeric(
        tabela["val_potenciaefetiva"], errors="coerce"
    ).astype(float)
    tabela["disponivel_em"] = tabela["entrada_em_operacao"].fillna(
        tabela["entrada_em_teste"]
    )
    return tabela.reindex(columns=list(COLUNAS))
