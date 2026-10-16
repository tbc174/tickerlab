"""Beneficiários de planos de saúde por operadora (ANS; série 4, PR 5): por operadora, mês, modalidade,
cobertura, vigência do plano, tipo de contratação e de financiamento, no formato da fonte.

Um arquivo só (`Beneficiarios_operadora_e_carteira.csv`, desde 01/2017), regravado pela ANS a cada
extração (`base_de`, o mês do `ID_CMPT`): os meses passados podem mudar (`base/setoriais/revisoes.py`).
A chave da operadora é o registro na ANS (`cd_operadora`), o mesmo da B13 (fonte `ans-beneficiarios`).
Medido no arquivo de 08/08/2026: 483.875 linhas, 1.249 operadoras, nenhuma chave repetida.
"""

import io

import pandas as pd

from base.setoriais import prazos
from base.setoriais.comum import sem_espacos

FONTE = "ans-beneficiarios-operadora"
FONTE_DA_LIGACAO = (
    "ans-beneficiarios"  # a B13 liga o registro da operadora por esta fonte
)
URL = (
    "https://dadosabertos.ans.gov.br/FTP/PDA/beneficiarios_vinculos_tipo_contratacao_vda/"
    "Beneficiarios_operadora_e_carteira.csv"
)
NOMES = {
    "CD_OPERADORA": "cd_operadora", "GR_MODALIDADE": "modalidade", "COBERTURA": "cobertura",
    "VIGENCIA_PLANO": "vigencia_do_plano", "GR_CONTRATACAO": "contratacao",
    "TIPO_FINANCIAMENTO": "financiamento",
}  # fmt: skip
TEXTOS = tuple(NOMES.values())
COLUNAS = ("competencia", *TEXTOS, "beneficiarios", "base_de", "disponivel_em")
CHAVE = ["competencia", *TEXTOS]
CARIMBOS = ("base_de",)


def _fim_do_mes(aaaamm: pd.Series) -> pd.Series:
    return prazos.fim_do_mes(aaaamm.str[:4], aaaamm.str[4:6])


def ler(conteudo: bytes) -> pd.DataFrame:
    """O arquivo inteiro, com a competência (último dia do mês) e `disponivel_em`."""
    bruto = pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    tabela = pd.DataFrame(
        {
            novo: sem_espacos(bruto[velho], vazio_vira_none=True)
            for velho, novo in NOMES.items()
        }
    )
    tabela["competencia"] = _fim_do_mes(bruto["MES"])
    tabela["beneficiarios"] = pd.to_numeric(bruto["NR_BENEF"], errors="coerce").astype(
        float
    )
    tabela["base_de"] = _fim_do_mes(bruto["ID_CMPT"])
    tabela["disponivel_em"] = prazos.disponivel_ans(tabela["competencia"])
    return tabela.reindex(columns=list(COLUNAS))
