"""A lista única de palavras vedadas do TickerLab (ADR 0103, item 7).

A ficha descreve, não julga: estas palavras não aparecem em texto nosso. É a união da lista do
café (`base/contrapartes/cafe.py`) com a da ADR 0085. O café, o dossiê e as contestações conferem
os textos por aqui, e o teste do dossiê usa a mesma `VEDADAS`.
"""

from __future__ import annotations

import re
import unicodedata

VEDADAS = (
    # a do café
    "quebrou",
    "quebrada",
    "calote",
    "golpe",
    "fraude",
    "não confiável",
    "evite",
    "recomendamos",
    "seguro",
    "confiável",
    # a da ADR 0085
    "fraudador",
    "corrupção",
    "cartel",
    "conluio",
    "laranja",
    "superfaturamento",
    "direcionamento",
    "suspeito",
)


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in normal if not unicodedata.combining(c))


def palavras_vedadas_em(texto: str) -> list[str]:
    """As palavras de `VEDADAS` que aparecem no texto (palavra inteira, sem acento nem caixa)."""
    limpo = _sem_acento(texto)
    return [v for v in VEDADAS if re.search(rf"\b{re.escape(_sem_acento(v))}\b", limpo)]
