"""Ponto de entrada do servidor MCP: `python -I pesquisa/iniciar_servidor.py [pasta]`.

Com `-I` o Python ignora PYTHONPATH e a pasta atual; por isso este arquivo acrescenta a raiz do
repositório ao `sys.path` (para importar `base.arquivo`, o cliente de rede do arquivista, e
`pesquisa`). A pasta de dados (memória e documentos) vem do argumento ou da variável
`TICKERLAB_PESQUISA`; sem nenhum dos dois, `~/TickerLab-Pesquisa`.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADRAO = Path.home() / "TickerLab-Pesquisa"


def pasta_de_dados(argumentos: list[str]) -> Path:
    if argumentos:
        return Path(argumentos[0])
    return Path(os.environ.get("TICKERLAB_PESQUISA") or PASTA_PADRAO)


def principal() -> None:
    sys.path.insert(0, str(RAIZ))
    from pesquisa.servidor_mcp import rodar

    rodar(pasta_de_dados(sys.argv[1:]))


if __name__ == "__main__":
    principal()
