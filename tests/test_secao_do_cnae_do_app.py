"""A tabela divisão -> seção do CNAE do app (React) é a mesma de `base/cnae.py`: a busca "Encontrar empresas"
filtra pela seção, e o Setor abre a busca já na seção do CNAE dele."""

import re
from pathlib import Path

from base import cnae

ARQUIVO = (
    Path(__file__).resolve().parent.parent / "web" / "src" / "app" / "secaoDoCnae.ts"
)
LINHA = re.compile(r"^\s+([A-U]): \[(\d+), (\d+)\],$", re.MULTILINE)


def test_tabela_do_app_e_a_mesma_de_base_cnae() -> None:
    do_app = {
        letra: (int(primeira), int(ultima))
        for letra, primeira, ultima in LINHA.findall(
            ARQUIVO.read_text(encoding="utf-8")
        )
    }
    # a tabela de base/cnae.py é a verdade; o teste só a compara com a do app
    assert do_app == cnae._DIVISOES
