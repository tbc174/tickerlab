"""Gera `site-api/catalogo.json`: o que a API externa entrega, lido do portão de direitos.

    python -m scripts.gerar_site_api

O site da TickerLab Data (`site-api/`) é escrito à mão, mas os fatos que ele repete (conjuntos, fontes,
licenças e campos) vêm do código: `tests/test_site_api.py` confere o HTML contra este arquivo, e confere
o arquivo contra o portão. Um conjunto que entra ou sai da API faz o teste falhar até o site acompanhar.

Roda: manual (python -m scripts.gerar_site_api); coberto por test_site_api.py.
"""

import json
from pathlib import Path

from src.banco.coletas import licenca_da_fonte
from src.portao_externo import Canal, regras_vigentes

DESTINO = Path(__file__).resolve().parent.parent / "site-api" / "catalogo.json"


def catalogo_do_site() -> dict[str, dict[str, object]]:
    """Por conjunto da API externa: as fontes (com a licença) e os campos que o portão libera."""
    conjuntos: dict[str, dict[str, object]] = {}
    for linha in regras_vigentes().linhas:
        if linha.canal != Canal.API_EXTERNA:
            continue
        dono = conjuntos.setdefault(linha.conjunto, {"fontes": {}, "campos": set()})
        fontes = dono["fontes"]
        assert isinstance(fontes, dict)
        fontes[linha.fonte] = licenca_da_fonte(linha.fonte)
        campos = dono["campos"]
        assert isinstance(campos, set)
        campos.add(linha.campo)
    return {
        nome: {
            "fontes": dict(sorted(dono["fontes"].items())),
            "campos": sorted(dono["campos"]),
        }  # type: ignore[union-attr]
        for nome, dono in sorted(conjuntos.items())
    }


def main() -> None:
    DESTINO.write_text(
        json.dumps(catalogo_do_site(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
