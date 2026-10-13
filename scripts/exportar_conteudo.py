"""Exporta o conteúdo do Python para o site em React (web/conteudo/*.json).

O Python continua a fonte da verdade (ADR 0048, item 3): módulos (`src/modulos.py`), páginas do app
(`src/paginas.py`), planos (`src/planos.py`) e marca (`src/marca.py`). O React lê estes JSON no build;
há teste que acusa quando um deles fica velho.

Uso: python -m scripts.exportar_conteudo
"""

import json
from dataclasses import asdict
from pathlib import Path

from src import marca, modulos, paginas, planos

DESTINO = Path(__file__).resolve().parent.parent / "web" / "conteudo"


def _modulos() -> list[dict]:
    return [
        {
            "chave": m.chave,
            "nome": m.nome,
            "objetivo": m.objetivo,
            "frase": m.frase,
            "funcionalidades": [
                {
                    "nome": f.nome,
                    "descricao": f.descricao,
                    "pagina_do_app": f.pagina_do_app,
                    "ticker": f.ticker,
                    "disponivel": f.disponivel,
                }
                for f in m.funcionalidades
            ],
        }
        for m in modulos.MODULOS
    ]


def _paginas() -> list[dict]:
    return [
        {
            "chave": p.chave,
            "titulo": p.titulo,
            "url": p.url,
            "grupo": p.grupo,
            "descricao": p.descricao,
            "e_pro": p.e_pro,
            "no_menu": p.no_menu,
            "somente_admin": p.somente_admin,
        }
        for p in paginas.PAGINAS
    ]


def _marca() -> dict:
    return {
        "fonte": marca.FONTE,
        "fonte_mono": marca.FONTE_MONO,
        "marinho": marca.MARINHO,
        "azul": marca.AZUL,
        "claro": marca.CLARO,
        "azul_claro": marca.AZUL_CLARO,
        "paleta_clara": asdict(marca.PALETA_CLARA),
        "paleta_escura": asdict(marca.PALETA_ESCURA),
        "simbolo_svg": marca.simbolo_svg(topo="currentColor"),
    }


def _planos() -> dict:
    return {
        "tabela": planos.tabela_de_planos(),
        "com_cobranca": list(planos.COM_COBRANCA),
    }


def conteudo() -> dict[str, object]:
    """{nome do arquivo: dados}."""
    return {
        "marca": _marca(),
        "modulos": _modulos(),
        "paginas": _paginas(),
        "planos": _planos(),
    }


def em_json(dados: object) -> str:
    """Texto estável (chaves em ordem, acentos legíveis), para o diff do PR mostrar só o que mudou."""
    return json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, dados in conteudo().items():
        (DESTINO / f"{nome}.json").write_text(em_json(dados), encoding="utf-8")
    print(f"Conteúdo exportado para {DESTINO}")


if __name__ == "__main__":
    main()
