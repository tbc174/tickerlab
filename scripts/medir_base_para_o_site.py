"""Mede a base para o site e grava `dados_de_exemplo/base/numeros.json` e `fatos.json`.

    TICKERLAB_ACERVO=/mnt/dados/tickerlab-acervo python -m scripts.medir_base_para_o_site

Roda no servidor de casa (ou na cópia do acervo no PC), **só leitura pela porta** (`base.porta`): nada
da base é alterado. O arquivo gravado é a fotografia que o `scripts/exportar_conteudo.py` leva para
`web/conteudo/base.json`; a data da medição vai junto e a página a mostra ("medido em DD/MM").
Os cruzamentos da página inicial (`fatos.json`, só contagens) vão para `web/conteudo/fatos_da_base.json`;
os de empresa fechada (`base/cruzamentos_das_fechadas.py`, linha 925) vão na chave `fechadas` do mesmo
arquivo. Com menos cartões de pé que o mínimo, nada é gravado e os caídos saem na tela com o motivo.
Plano do site para quem analisa, PRs 4 e 6.

Roda: manual no servidor (registro na pasta privada); citado em vitrine.py.
"""

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from base import cruzamentos_das_fechadas as fechadas
from base import porta, vitrine
from base.contrato import catalogo

BRASILIA = ZoneInfo("America/Sao_Paulo")


def medir(
    hoje: date | None = None,
) -> tuple[vitrine.NumerosDaBase, vitrine.Cruzamentos, fechadas.MedicaoDasFechadas]:
    dia = hoje or datetime.now(BRASILIA).date()
    with porta.abrir() as aberta:
        numeros = vitrine.numeros_da_base(aberta, catalogo(), dia)
        cruzamentos = vitrine.medir_cruzamentos(aberta, catalogo(), dia)
        das_fechadas = fechadas.medir_fechadas(aberta, catalogo(), dia)
    return numeros, cruzamentos, das_fechadas


def gravar(medida: vitrine.NumerosDaBase | dict, destino: Path) -> None:
    """Grava a medida (os números da base ou o dicionário dos fatos) como JSON ordenado."""
    dados = medida if isinstance(medida, dict) else asdict(medida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True)
    destino.write_text(texto + "\n", encoding="utf-8")


def fatos_com_as_fechadas(
    cruzamentos: vitrine.Cruzamentos, das_fechadas: fechadas.MedicaoDasFechadas
) -> dict:
    """O `fatos.json`: os cruzamentos das abertas e, na chave `fechadas`, a medição das fechadas."""
    return {
        **asdict(cruzamentos),
        vitrine.CHAVE_DAS_FECHADAS: fechadas.para_a_fotografia(das_fechadas),
    }


def main() -> None:
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--destino", type=Path, default=vitrine.FOTOGRAFIA)
    analise.add_argument(
        "--destino-dos-fatos", type=Path, default=vitrine.FOTOGRAFIA_DOS_CRUZAMENTOS
    )
    argumentos = analise.parse_args()
    numeros, cruzamentos, das_fechadas = medir()
    for caido in das_fechadas.caidos:
        print(f"caiu {caido.chave}: {caido.motivo}")
    if not fechadas.de_pe_o_bastante(das_fechadas):
        raise SystemExit(
            f"só {len(das_fechadas.cartoes)} cartões de empresa fechada de pé "
            f"(mínimo {fechadas.MINIMO_DE_CARTOES}): nada foi gravado"
        )
    fatos = fatos_com_as_fechadas(cruzamentos, das_fechadas)
    gravar(numeros, argumentos.destino)
    gravar(fatos, argumentos.destino_dos_fatos)
    for medida in (asdict(numeros), fatos):
        print(json.dumps(medida, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
