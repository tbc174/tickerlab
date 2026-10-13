"""Grava o contrato da API v1 em docs/api/openapi-v1.json (há teste que confere se está em dia).

Uso: python -m scripts.gerar_openapi
"""

import json
from pathlib import Path

from src.api_v1.rotas import openapi_v1

ARQUIVO = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi-v1.json"


def main() -> None:
    texto = json.dumps(openapi_v1(), ensure_ascii=False, indent=2, sort_keys=True)
    ARQUIVO.write_text(texto + "\n", encoding="utf-8")
    print(f"Gravado: {ARQUIVO}")


if __name__ == "__main__":
    main()
