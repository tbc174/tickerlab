"""Leitor comum do COT da CFTC (`base/commodities/cftc_cot.py`): o Bitcoin não muda de resultado."""

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from base.cripto.cftc import ler_tff

AMOSTRA_TFF = (
    Path(__file__).parent / "arquivos" / "cripto" / "cftc" / "FinFutYY_amostra.txt"
)


def _zip(texto: bytes) -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr("arquivo.txt", texto)
    return memoria.getvalue()


def test_cripto_continua_igual():
    # resultado do leitor do Bitcoin, gravado antes de o leitor virar comum ao café
    esperado = pd.DataFrame(
        {
            "relatorio": [date(2026, 9, 29)] * 2 + [date(2026, 10, 6)] * 2,
            "contratos_em_aberto": [19596, 26320, 21432, 34582],
            "gestores_comprados": [5069, 2258, 5174, 2404],
            "gestores_vendidos": [1483, 67, 1642, 76],
            "alavancados_comprados": [4980, 9896, 5731, 13371],
            "alavancados_vendidos": [11836, 21256, 12583, 29798],
            "contrato": ["bitcoin", "micro_bitcoin"] * 2,
            "divulgado_em": pd.to_datetime(
                [datetime(2026, 10, 5, 19, 30, tzinfo=UTC)] * 2
                + [datetime(2026, 10, 12, 19, 30, tzinfo=UTC)] * 2
            ),
        }
    )

    obtido = ler_tff(_zip(AMOSTRA_TFF.read_bytes()))

    pd.testing.assert_frame_equal(obtido, esperado, check_dtype=False)
