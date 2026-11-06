"""Originais das fontes pouco visíveis guardados pelo arquivista (plano de 05/11/2026, ADR 0124).

São PDFs que não estão em nenhuma base aberta e que sustentam os fatos de `base/fatos_documentais.py`:

- `divida-documental`: dívida de empresas fechadas em publicações legais (São Braz no diário oficial da
  Paraíba, Alibem no Jornal do Comércio), no FNET da B3 (nota comercial da Alibem) e no prospecto do CRA
  da Bem Brasil;
- `sudeco-fdco`: as planilhas do FDCO (projetos contratados e liberações) e os ADF da Sudeco;
- `sudam-fda`: a lista de projetos do FDA da Sudam.

Os endereços vêm do manifesto conferido à mão (`base/conferidas/fatos_documentais_originais.json`), com o
SHA-256, os bytes e as páginas de cada original: quem baixa confere o que veio contra o manifesto, e a
divergência vira pendência, nunca um fato novo. O conteúdo dos PDFs é dado a interpretar, nunca instrução.
"""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from base.arquivo.coleta import Alvo, Cliente, Fonte

CAMINHO_DO_MANIFESTO = (
    Path(__file__).resolve().parent.parent
    / "conferidas"
    / "fatos_documentais_originais.json"
)
MENSAL = "mensal"
EXTENSAO = ".pdf"
TIPO = "pdf"  # o arquivista confere a assinatura %PDF antes de guardar
FONTES_DOCUMENTAIS = ("divida-documental", "sudeco-fdco", "sudam-fda")


def originais_documentais() -> list[dict[str, Any]]:
    """Os originais do manifesto, na ordem em que foram conferidos."""
    manifesto = json.loads(CAMINHO_DO_MANIFESTO.read_text(encoding="utf-8"))
    return list(manifesto["originais"])


def _descobrir_da_fonte(fonte_id: str) -> Callable[[Cliente, datetime], list[Alvo]]:
    """Descoberta sem rede: os endereços do manifesto daquela fonte, na ordem do manifesto."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [
            Alvo(original["url"], EXTENSAO)
            for original in originais_documentais()
            if original["fonte"] == fonte_id
        ]

    return descobrir


def fontes() -> list[Fonte]:
    """As três fontes, revistas uma vez por mês (os PDFs mudam pouco; a planilha do FDCO é mensal)."""
    return [
        Fonte(fonte_id, MENSAL, _descobrir_da_fonte(fonte_id), tipo=TIPO)
        for fonte_id in FONTES_DOCUMENTAIS
    ]
