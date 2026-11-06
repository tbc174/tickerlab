"""Natureza jurídica e MEI nas entidades (ADR 0077, item 1; plano, D8 e tarefa 2.5).

Empresário individual (213-5), as naturezas de pessoa física (grupo 4) e o MEI são pessoas com CNPJ
(ADR 0075, Emenda 1): nunca recebem sinal negativo publicado e não levam nome. Natureza que nenhuma fonte
diz fica `nao_informada` e, para sinal negativo, conta como pessoa (o conservador).
"""

import pandas as pd

from base.rede import entidades


def _entidades():
    return pd.DataFrame(
        {
            "id_entidade": ["E1", "E2", "E3", "E4", "E5", "E6"],
            "tipo": ["empresa", "fundo", "empresa", "empresa", "empresa", "empresa"],
            "nome": [
                "PETRO SA",
                "FUNDO X",
                "FULANO DE TAL",
                "MEI DA SILVA",
                "SEM DADO SA",
                "RURAL",
            ],
            "raiz": ["33000167", "60872504", "11222333", "44555666", None, "77888999"],
            "natureza_da_fonte": ["2046", "2224", None, None, None, None],
        }
    )


def _receita():
    naturezas = pd.DataFrame(
        {
            "cnpj_basico": ["33000167", "11222333", "44555666", "77888999"],
            "natureza_juridica": ["2054", "2135", "2062", "4120"],
        }
    )
    meis = pd.DataFrame({"cnpj_basico": ["44555666"], "mei": [True]})
    return naturezas, meis


def test_entidade_tem_natureza_e_mei():
    tabela = entidades.com_natureza(_entidades(), *_receita()).set_index("id_entidade")
    for coluna in ("natureza_juridica", "natureza_fonte", "mei", "trata_como_pessoa"):
        assert tabela[coluna].notna().all(), coluna
    # a Receita manda; sem ela, a própria fonte (CVM, cadastro de fundos); sem nenhuma, nao_informada
    assert tabela.loc["E1", ["natureza_juridica", "natureza_fonte"]].tolist() == [
        "2054",
        "receita",
    ]
    assert tabela.loc["E2", ["natureza_juridica", "natureza_fonte"]].tolist() == [
        "2224",
        "fonte",
    ]
    assert tabela.loc["E5", ["natureza_juridica", "natureza_fonte"]].tolist() == [
        entidades.NAO_INFORMADA,
        entidades.NAO_INFORMADA,
    ]
    assert tabela["mei"].tolist() == [False, False, False, True, False, False]


def test_ei_213_5_e_mei_marcados_como_pessoa():
    tabela = entidades.com_natureza(_entidades(), *_receita()).set_index("id_entidade")
    assert tabela["trata_como_pessoa"].to_dict() == {
        "E1": False,
        "E2": False,
        "E3": True,  # 213-5, empresário individual
        "E4": True,  # MEI
        "E5": True,  # nao_informada: conservador
        "E6": True,  # 412-0, produtor rural (grupo 4, pessoa física)
    }


def test_pessoa_com_cnpj_nao_leva_nome():
    """EI, MEI e grupo 4: o nome é o da pessoa (nível 2 da ADR 0075: só id, nunca nome)."""
    tabela = entidades.com_natureza(_entidades(), *_receita()).set_index("id_entidade")
    assert tabela.loc[["E3", "E4", "E6"], "nome"].isna().all()
    assert (
        tabela.loc["E5", "nome"] == "SEM DADO SA"
    )  # nao_informada veio de fonte de empresa
