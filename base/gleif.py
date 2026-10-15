"""Ponte LEI ↔ CNPJ pelo GLEIF já guardado pelo arquivista (`gleif-br`, semanal; licença CC0).

Cada página guardada é uma resposta da API `lei-records` filtrada pelo Brasil (200 LEIs). Conferido no
servidor de casa em 15/10/2026, na cópia de 13/10 (4.459 LEIs): o CNPJ vem em `entity.registeredAs`; a
Receita é a autoridade de registro `RA000681` (2.619 LEIs); outras autoridades (juntas comerciais, a
CVM nos fundos) também trazem CNPJ, mas às vezes um CPF, um NIRE ou nada.

- Só entra **CNPJ de 14 com o DV conferido** (com letras, se tiver): CPF, NIRE e vazio ficam fora, e o
  LEI fica sem ponte. A coluna `autoridade` diz de quem veio.
- **`SOLE_PROPRIETOR` fica fora inteiro:** empresário individual é pessoa (ADR 0075, Emenda 1).
- LEI marcado `DUPLICATE` pelo próprio GLEIF fica fora (é a mesma entidade com outro código).
- `publico_em` = data da cópia publicada (`goldenCopy.publishDate`): antes da 1ª cópia guardada a
  ponte não é conhecida (o registro do LEI pode ser antigo, mas o CNPJ dele pode ter mudado).
- Um CNPJ com dois LEIs vivos é **conflito** (as duas linhas): a resolução não liga por eles.
"""

import json
import re
from collections.abc import Iterable

import pandas as pd

from base.cnpj import completo, dv_confere

COLUNAS = (
    "lei", "cnpj", "nome", "autoridade", "categoria", "situacao_do_lei", "publico_em", "conflito",
)  # fmt: skip
AUTORIDADE_DA_RECEITA = "RA000681"
EMPRESARIO_INDIVIDUAL = "SOLE_PROPRIETOR"
DUPLICADO = "DUPLICATE"
PREFIXO_CNPJ = re.compile(r"^\s*CNPJ\s*:?\s*", re.IGNORECASE)


def _cnpj(registrado: object) -> str | None:
    if not isinstance(registrado, str):
        return None
    cnpj = completo(PREFIXO_CNPJ.sub("", registrado))
    return cnpj if cnpj and dv_confere(cnpj) else None


def _linha(registro: dict, publico_em: pd.Timestamp) -> dict | None:
    atributos = registro["attributes"]
    entidade = atributos["entity"]
    situacao = (atributos.get("registration") or {}).get("status")
    cnpj = _cnpj(entidade.get("registeredAs"))
    if (
        cnpj is None
        or entidade.get("category") == EMPRESARIO_INDIVIDUAL
        or situacao == DUPLICADO
    ):
        return None
    return {
        "lei": atributos["lei"],
        "cnpj": cnpj,
        "nome": (entidade.get("legalName") or {}).get("name"),
        "autoridade": (entidade.get("registeredAt") or {}).get("id"),
        "categoria": entidade.get("category"),
        "situacao_do_lei": situacao,
        "publico_em": publico_em,
    }


def marcar_conflitos(ponte: pd.DataFrame) -> pd.DataFrame:
    """`conflito` = o CNPJ aparece em mais de um LEI (recalcular depois de juntar as páginas)."""
    return ponte.assign(conflito=ponte["cnpj"].duplicated(keep=False))


def ler_gleif(conteudo_json: bytes) -> pd.DataFrame:
    """LEI, CNPJ, nome e autoridade de uma página guardada; só os LEIs com CNPJ conferido."""
    pagina = json.loads(conteudo_json)
    publico_em = (
        pd.Timestamp(pagina["meta"]["goldenCopy"]["publishDate"])
        .tz_localize(None)
        .normalize()
    )
    linhas = [linha for r in pagina.get("data", []) if (linha := _linha(r, publico_em))]
    ponte = pd.DataFrame(linhas, columns=list(COLUNAS[:-1]))
    return pd.DataFrame(marcar_conflitos(ponte)[list(COLUNAS)])


def juntar_paginas(paginas: Iterable[bytes]) -> pd.DataFrame:
    """A ponte inteira de uma cópia (todas as páginas), com os conflitos entre páginas."""
    tabelas = [ler_gleif(p) for p in paginas]
    if not tabelas:
        return pd.DataFrame(columns=list(COLUNAS))
    juntas = pd.concat(tabelas, ignore_index=True).drop_duplicates(
        subset=["lei", "cnpj"]
    )
    return pd.DataFrame(marcar_conflitos(juntas)[list(COLUNAS)]).reset_index(drop=True)
