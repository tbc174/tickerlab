"""Mede a base para o site e grava `dados_de_exemplo/base/numeros.json` e `fatos.json`.

    TICKERLAB_ACERVO=/mnt/dados/tickerlab-acervo python -m scripts.medir_base_para_o_site

Roda no servidor de casa (ou na cópia do acervo no PC), **só leitura pela porta** (`base.porta`): nada
da base é alterado. O arquivo gravado é a fotografia que o `scripts/exportar_conteudo.py` leva para
`web/conteudo/base.json`; a data da medição vai junto e a página a mostra ("medido em DD/MM").
Os cruzamentos da página inicial (`fatos.json`, só contagens) vão para `web/conteudo/fatos_da_base.json`.
Plano do site para quem analisa, PRs 4 e 6.
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


def medir(
    hoje: date | None = None,
) -> tuple[vitrine.NumerosDaBase, vitrine.Cruzamentos]:
    dia = hoje or datetime.now(BRASILIA).date()
    with porta.abrir() as aberta:
        numeros = vitrine.numeros_da_base(aberta, catalogo(), dia)
        cruzamentos = vitrine.medir_cruzamentos(aberta, catalogo(), dia)
    return numeros, cruzamentos


def gravar(medida: vitrine.NumerosDaBase | vitrine.Cruzamentos, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(asdict(medida), ensure_ascii=False, indent=2, sort_keys=True)
    destino.write_text(texto + "\n", encoding="utf-8")


def main() -> None:
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--destino", type=Path, default=vitrine.FOTOGRAFIA)
    analise.add_argument(
        "--destino-dos-fatos", type=Path, default=vitrine.FOTOGRAFIA_DOS_CRUZAMENTOS
    )
    argumentos = analise.parse_args()
    numeros, cruzamentos = medir()
    gravar(numeros, argumentos.destino)
    gravar(cruzamentos, argumentos.destino_dos_fatos)
    for medida in (numeros, cruzamentos):
        print(json.dumps(asdict(medida), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
