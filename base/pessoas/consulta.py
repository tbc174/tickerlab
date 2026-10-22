"""Os sócios de **uma** empresa para a saída (tela, API, PDF): a única leitura de nome que sai de casa.

A porta é o CNPJ (ADR 0106, regra 3.2): uma empresa por chamada, nunca busca por nome ou CPF. Os sócios vêm do
QSA vigente; o nome da pessoa física vem do restrito e só aparece com o portão da fonte aberto e sem oposição
registrada (regra 3.8: o pedido já tira o nome, antes mesmo da lápide). Sem nome, a linha é "sócio pessoa
física" com a qualificação e a data. O `id_pessoa` e o CPF mascarado não saem.
"""

from pathlib import Path

import pandas as pd

from base.pessoas import oposicoes, portao
from base.porta import pessoas as porta

FONTE = "rfb-cnpj"
COLUNAS_DE_SAIDA = (
    "tipo_socio", "raiz_socio_pj", "qualificacao", "data_entrada", "pais", "nome",
)  # fmt: skip


def _nomes_que_podem_sair(restrita: Path, raiz: str) -> dict[str, str]:
    if not portao.nomes_liberados(FONTE, portao.PASTA_DAS_CONDICOES):
        return {}
    pessoas = porta.pessoas_da_raiz(restrita, raiz)
    pessoas = pessoas[~pessoas["id_pessoa"].isin(oposicoes.ids_opostos(restrita))]
    return dict(zip(pessoas["id_pessoa"], pessoas["nome"], strict=True))


def socios_da_empresa(pasta: Path, restrita: Path, cnpj: str) -> pd.DataFrame:
    """O quadro de sócios da empresa, com o nome só onde o portão e as oposições deixam."""
    raiz = oposicoes.raiz_do_cnpj(cnpj)
    socios = porta.qsa_da_raiz(
        pasta, raiz, [*COLUNAS_DE_SAIDA[:-1], "cnpj_basico", "id_pessoa"]
    )
    nomes = _nomes_que_podem_sair(restrita, raiz)
    saida = socios.assign(nome=socios["id_pessoa"].map(nomes))
    saida["nome"] = saida["nome"].astype(object).where(saida["nome"].notna(), None)
    return saida[list(COLUNAS_DE_SAIDA)].reset_index(drop=True)
