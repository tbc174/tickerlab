"""A lista de estados das ferramentas do app (React) é a mesma de `base/cnes.py`, a que a busca de empresas
(`src/analista/busca.py`) aceita: um estado a mais no app seria um pedido recusado; um a menos, um estado que
o analista não consegue escolher."""

import re
from pathlib import Path

from base import cnes

ARQUIVO = Path(__file__).resolve().parent.parent / "web" / "src" / "app" / "ufs.ts"


def test_ufs_do_app_sao_as_mesmas_de_base_cnes() -> None:
    texto = ARQUIVO.read_text(encoding="utf-8")
    lista = texto[texto.index("UFS = [") : texto.index("] as const")]
    assert tuple(re.findall(r'"([A-Z]{2})"', lista)) == cnes.UFS
