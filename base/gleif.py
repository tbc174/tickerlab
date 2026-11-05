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

`montar` (linha 679) grava a ponte como tabela que só cresce, uma cópia do GLEIF por retrato
(`base/cadastros_em_retrato.py`): a cópia é o conjunto de páginas com a mesma `publishDate`, e a que ficou
incompleta (menos da metade da anterior) é pulada.
"""

import hashlib
import json
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import retratos as motor
from base.cnpj import completo, dv_confere, formatar

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


FONTE = "gleif-br"
TABELA = "gleif_ponte"
VALORES = ["nome", "autoridade", "categoria", "situacao_do_lei", "conflito", "consta"]
COLUNAS_DA_TABELA = (
    "id_na_fonte", "lei", "cnpj", "cnpj_basico", "nome", "autoridade", "categoria",
    "situacao_do_lei", "conflito",
)  # fmt: skip


@dataclass(frozen=True)
class CopiaDoGleif(motor.Retrato):
    """Uma cópia do GLEIF: as páginas guardadas com a mesma `publishDate` (o resto vem de `Retrato`)."""

    paginas: tuple[Path, ...] = ()


def _publicada_em(retrato: motor.Retrato) -> str:
    return json.loads(motor.original(retrato.caminho))["meta"]["goldenCopy"][
        "publishDate"
    ]


def _copia(publicada_em: str, paginas: list[motor.Retrato]) -> CopiaDoGleif:
    ordem = sorted(paginas, key=lambda p: p.url)
    assinatura = hashlib.sha256("|".join(p.sha256 for p in ordem).encode()).hexdigest()
    return CopiaDoGleif(
        url=f"{FONTE}:{publicada_em}",
        sha256=assinatura,
        caminho=ordem[0].caminho,
        baixado_em=max(p.baixado_em for p in ordem),
        paginas=tuple(p.caminho for p in ordem),
    )


def achar_copias(conexao: sa.Connection) -> tuple[list[motor.Retrato], int]:
    """As cópias guardadas, da mais antiga à mais nova (de cada página, a versão mais nova da cópia)."""
    por_copia: dict[str, dict[str, motor.Retrato]] = {}
    for pagina in motor.retratos(conexao, FONTE):
        paginas = por_copia.setdefault(_publicada_em(pagina), {})
        paginas[pagina.url] = (
            pagina  # a ordem é do mais antigo ao mais novo: a última vale
        )
    copias = [_copia(dia, list(p.values())) for dia, p in por_copia.items()]
    return sorted(copias, key=lambda c: pd.Timestamp(c.baixado_em)), 0


def ler_copia(copia: motor.Retrato) -> tuple[pd.DataFrame, dict[str, int]]:
    """A ponte de uma cópia inteira, no formato do motor de retratos (`id_na_fonte` = LEI + CNPJ)."""
    paginas = copia.paginas if isinstance(copia, CopiaDoGleif) else (copia.caminho,)
    ponte = juntar_paginas(motor.original(p) for p in paginas)
    tabela = ponte.assign(
        id_na_fonte=ponte["lei"] + "|" + ponte["cnpj"],
        cnpj_basico=ponte["cnpj"].str[:8],
        cnpj=ponte["cnpj"].map(formatar),
    )
    return tabela, {"leis": len(tabela)}


def _disponivel_no_primeiro(tabela: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """A data da cópia (`publishDate`), nunca depois do dia em que ela foi guardada."""
    return tabela["publico_em"].clip(upper=dia)


def juntar_copias(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    return motor.juntar(lidos, VALORES, _disponivel_no_primeiro)


CADASTROS = (
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome="ponte",
        fonte=FONTE,
        ler=ler_copia,
        juntar=juntar_copias,
        colunas=COLUNAS_DA_TABELA,
        datas=(),
        achar=achar_copias,
    ),
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/gleif_ponte/ponte.parquet`: a ponte LEI e CNPJ de todas as cópias guardadas."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
