"""Roda o conector: `python -m conector_remoto` (no contêiner `tickerlab-mcp`, ou no PC para testar).

Escuta só em 127.0.0.1:8010 por padrão; no contêiner, o compose publica a porta só no 127.0.0.1 do VPS
e o túnel da Cloudflare é o único caminho de fora.
"""

import os

import uvicorn

from conector_remoto.configuracao import ler_configuracao
from conector_remoto.servidor import criar_app
from conector_remoto.uso import ligar_registro_de_uso

HOST_PADRAO = "127.0.0.1"
PORTA_PADRAO = 8010


def principal() -> None:
    """Lê a configuração do ambiente e sobe o servidor."""
    ligar_registro_de_uso()
    app = criar_app(ler_configuracao(os.environ))
    host = os.environ.get("TICKERLAB_MCP_ESCUTA", HOST_PADRAO)
    porta = int(os.environ.get("TICKERLAB_MCP_PORTA", str(PORTA_PADRAO)))
    # o proxy (cloudflared) fica na mesma máquina; os cabeçalhos de IP só valem vindos dele (PR 2)
    uvicorn.run(app, host=host, port=porta, proxy_headers=False, server_header=False)


if __name__ == "__main__":
    principal()
