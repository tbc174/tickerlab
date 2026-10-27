"""Instala um pacote agregado previamente preparado e validado."""

import argparse
import os
import tempfile
from pathlib import Path

from src.radar_imobiliario import MAX_BYTES, Pacote, caminho_do_pacote


def instalar(origem: Path, destino: Path) -> None:
    """Instala somente depois de validar todo o conteúdo."""
    with origem.open("rb") as arquivo:
        corpo = arquivo.read(MAX_BYTES + 1)
    if len(corpo) > MAX_BYTES:
        raise ValueError("Pacote maior que o limite permitido.")
    pacote = Pacote.model_validate_json(corpo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destino.parent, delete=False
        ) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(pacote.model_dump_json())
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def main() -> None:
    """Recebe o pacote preparado e grava no caminho configurado pelo operador."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origem", type=Path)
    parser.add_argument("--destino", type=Path, default=caminho_do_pacote())
    argumentos = parser.parse_args()
    instalar(argumentos.origem, argumentos.destino)
    print("Pacote do radar validado e instalado.")


if __name__ == "__main__":
    main()
