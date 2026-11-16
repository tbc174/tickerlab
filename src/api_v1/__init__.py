"""API de leitura do TickerLab, versão 1 (ADR 0048): as análises para a interface nova.

Está no ar em produção e serve o app. As rotas só são montadas com `TICKERLAB_API_V1=1`: sem a
variável, a API nem monta estas rotas (respondem 404) e não carrega o pandas, porque o contêiner da
API é pequeno.
"""

import os
from collections.abc import Mapping

VARIAVEL_DA_CHAVE = "TICKERLAB_API_V1"


def api_v1_ligada(ambiente: Mapping[str, str] | None = None) -> bool:
    texto = (ambiente if ambiente is not None else os.environ).get(
        VARIAVEL_DA_CHAVE, ""
    )
    return texto.strip() == "1"
