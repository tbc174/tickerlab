"""A tabela `entidades` da rede (ADR 0077, item 1): natureza jurídica e MEI (plano, D8 e tarefa 2.5).

`natureza_juridica` e `mei` são obrigatórios. A natureza vem da Receita (`base/receita_natureza.py`);
sem ela, da própria fonte (companhia aberta da CVM = 204-6, fundo = 222-4); sem nenhuma, `nao_informada`.

**Pessoas com CNPJ** (ADR 0075, Emenda 1): empresário individual (213-5), as naturezas do grupo 4
("pessoas físicas": produtor rural, candidato, leiloeiro...) e o MEI. `trata_como_pessoa` marca essas
e também `nao_informada` (o conservador: nada negativo publicado sobre quem pode ser pessoa). Pessoa
com CNPJ não leva nome (a razão social é o nome dela): nível 2, só id.
"""

import pandas as pd

NAO_INFORMADA = "nao_informada"
PELA_RECEITA, PELA_FONTE = "receita", "fonte"
EMPRESARIO_INDIVIDUAL = "2135"
GRUPO_DAS_PESSOAS_FISICAS = "4"
COMPANHIA_ABERTA, FUNDO_DE_INVESTIMENTO = "2046", "2224"


def natureza_de_pessoa(natureza: str) -> bool:
    """213-5 ou grupo 4 da tabela de naturezas da Receita."""
    return natureza == EMPRESARIO_INDIVIDUAL or natureza.startswith(
        GRUPO_DAS_PESSOAS_FISICAS
    )


def com_natureza(
    entidades: pd.DataFrame, naturezas: pd.DataFrame, meis: pd.DataFrame
) -> pd.DataFrame:
    """As entidades com `natureza_juridica`, `natureza_fonte`, `mei` e `trata_como_pessoa`.

    `entidades` traz `raiz` (pode ser vazia) e `natureza_da_fonte` (a que a fonte diz, ou vazia);
    `naturezas` e `meis` são as saídas de `base/receita_natureza.py`.
    """
    pela_receita = entidades["raiz"].map(
        naturezas.set_index("cnpj_basico")["natureza_juridica"]
    )
    natureza = pela_receita.fillna(entidades["natureza_da_fonte"])
    fonte = (
        pd.Series(NAO_INFORMADA, index=entidades.index)
        .mask(entidades["natureza_da_fonte"].notna(), PELA_FONTE)
        .mask(pela_receita.notna(), PELA_RECEITA)
    )
    mei = (
        entidades["raiz"]
        .map(meis.set_index("cnpj_basico")["mei"])
        .fillna(False)
        .astype(bool)
    )
    natureza = natureza.fillna(NAO_INFORMADA)
    pessoa_com_cnpj = natureza.map(natureza_de_pessoa) | mei
    return entidades.drop(columns=["natureza_da_fonte"]).assign(
        nome=entidades["nome"].where(~pessoa_com_cnpj, None),
        natureza_juridica=natureza,
        natureza_fonte=fonte,
        mei=mei,
        trata_como_pessoa=pessoa_com_cnpj | (natureza == NAO_INFORMADA),
    )
