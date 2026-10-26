"""Mede a base para a página Dados do site e grava `dados_de_exemplo/base/numeros.json`.

    TICKERLAB_ACERVO=/mnt/dados/tickerlab-acervo python -m scripts.medir_base_para_o_site

Roda no servidor de casa (ou na cópia do acervo no PC), **só leitura pela porta** (`base.porta`): nada
da base é alterado. O arquivo gravado é a fotografia que o `scripts/exportar_conteudo.py` leva para
`web/conteudo/base.json`; a data da medição vai junto e a página a mostra ("medido em DD/MM").
Plano do site para quem analisa, PR 4.
"""

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from base import porta, vitrine
from base.contrato import catalogo

BRASILIA = ZoneInfo("America/Sao_Paulo")


def medir(hoje: date | None = None) -> vitrine.NumerosDaBase:
    with porta.abrir() as aberta:
        return vitrine.numeros_da_base(
            aberta, catalogo(), hoje or datetime.now(BRASILIA).date()
        )


def gravar(numeros: vitrine.NumerosDaBase, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(asdict(numeros), ensure_ascii=False, indent=2, sort_keys=True)
    destino.write_text(texto + "\n", encoding="utf-8")


def main() -> None:
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--destino", type=Path, default=vitrine.FOTOGRAFIA)
    argumentos = analise.parse_args()
    numeros = medir()
    gravar(numeros, argumentos.destino)
    print(json.dumps(asdict(numeros), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
