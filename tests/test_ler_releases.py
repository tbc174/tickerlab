"""A medição dos releases de resultado (vitrine, PR 1, sem API)."""

import pandas as pd

from base import releases
from scripts import ler_releases


def _release(cnpj, referencia, entrega, protocolo):
    return {
        "cnpj": cnpj, "codigo_cvm": "1", "periodo": "x", "referencia": pd.Timestamp(referencia),
        "data_entrega": pd.Timestamp(entrega), "protocolo": protocolo, "versao": 1, "link": "l",
    }  # fmt: skip


def test_medir_conta_por_ano_e_casa_com_itr():
    achados = pd.DataFrame(
        [
            _release("11.111.111/0001-11", "2024-09-30", "2024-11-05", "a"),
            _release("11.111.111/0001-11", "2025-09-30", "2025-11-05", "b"),
            _release("22.222.222/0001-22", "2025-09-30", "2025-11-06", "c"),
            _release("22.222.222/0001-22", "2025-12-31", "2026-02-20", "d"),
        ],
        columns=list(releases.COLUNAS),
    )
    demonstracoes = pd.DataFrame(
        {
            "cnpj": ["11111111000111", "11111111000111", "22222222000122"],
            "documento": ["ITR", "ITR", "ITR"],
            "referencia": pd.to_datetime(["2024-09-30", "2025-09-30", "2025-09-30"]),
        }
    )
    medida = ler_releases.medir(achados, demonstracoes).set_index("ano")
    assert medida.loc[2024, "releases"] == 1 and medida.loc[2024, "com_itr_dfp"] == 1
    assert medida.loc[2025, "releases"] == 2 and medida.loc[2025, "com_itr_dfp"] == 2
    assert medida.loc[2026, "releases"] == 1 and medida.loc[2026, "com_itr_dfp"] == 0
    assert medida.loc[2025, "empresas"] == 2
    assert medida.loc[2026, "percentual_com_itr_dfp"] == 0.0
