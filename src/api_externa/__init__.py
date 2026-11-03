"""API externa do TickerLab Data (ADR 0108): o dado para quem integra, pela chave da organização.

A porta de entrada é a N7 (`acesso.py`); as rotas são da B-32a (`rotas.py`). Fica **desligada** até o
"pode" do Tiago para ligar: sem `TICKERLAB_API_EXTERNA=1`, a API nem monta estas rotas (respondem 404).
O MCP é a B-32b, depois do beta.
"""

import os
from collections.abc import Mapping

VARIAVEL_DA_CHAVE = "TICKERLAB_API_EXTERNA"


def api_externa_ligada(ambiente: Mapping[str, str] | None = None) -> bool:
    texto = (ambiente if ambiente is not None else os.environ).get(
        VARIAVEL_DA_CHAVE, ""
    )
    return texto.strip() == "1"
