"""Frescor das fontes: escreve em JSON se cada fonte trouxe dado novo dentro do prazo (painel das coletas).

    python -m scripts.frescor_das_fontes --saida frescor.json

Roda uma vez por dia na VPS, na imagem do app, com o banco de produção (`TICKERLAB_DATABASE_URL`).
Lê só a tabela `coletas` (`src/frescor_das_fontes.py`); o servidor manda o JSON ao Kuma, um monitor
por fonte. Sai com 0 quando consegue escrever o JSON: fonte velha é estado, não erro do script.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.banco.conexao import criar_engine
from src.frescor_das_fontes import FREQUENCIAS_DAS_FONTES, frescor_das_fontes


def main(argv: list[str] | None = None) -> int:
    """Escreve o frescor de cada fonte em `--saida` e devolve 0."""
    argumentos = _argumentos().parse_args(argv)
    agora = (
        datetime.fromisoformat(argumentos.agora)
        if argumentos.agora
        else datetime.now(UTC)
    )
    motor = criar_engine()
    try:
        with motor.connect() as conexao:
            fontes = frescor_das_fontes(conexao, FREQUENCIAS_DAS_FONTES, agora)
    finally:
        motor.dispose()
    conteudo = {
        "gerado_em": agora.isoformat(),
        "fontes": [fonte.como_dicionario() for fonte in fontes],
    }
    _escrever(
        Path(argumentos.saida), json.dumps(conteudo, ensure_ascii=False, indent=1)
    )
    return 0


def _escrever(destino: Path, texto: str) -> None:
    # escreve ao lado e troca de uma vez: quem lê o JSON nunca pega um arquivo pela metade
    provisorio = destino.with_name(destino.name + ".novo")
    provisorio.write_text(texto + "\n", encoding="utf-8")
    provisorio.replace(destino)


def _argumentos() -> argparse.ArgumentParser:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--saida", required=True, help="arquivo JSON do frescor")
    argumentos.add_argument("--agora", help=argparse.SUPPRESS)  # só para os testes
    return argumentos


if __name__ == "__main__":
    sys.exit(main())
