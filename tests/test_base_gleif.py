"""Ponte LEI ↔ CNPJ pelo GLEIF já guardado (`gleif-br`; PR 2 da rede de entidades, tarefa 2.4).

Conferido no servidor de casa em 15/10/2026 (só leitura, 23 páginas da cópia de 13/10, 4.459 LEIs): o
CNPJ vem em `entity.registeredAs`; a Receita é a autoridade `RA000681` (2.619 LEIs); outras autoridades
(juntas, CVM) também trazem CNPJ, mas às vezes um CPF ou um NIRE; 235 são `SOLE_PROPRIETOR`.
A página de teste é de mentira, no mesmo formato.
"""

import json
from pathlib import Path

import pandas as pd

from base import gleif

PAGINA = (Path(__file__).parent / "arquivos" / "gleif" / "pagina.json").read_bytes()


def _ponte() -> pd.DataFrame:
    return gleif.ler_gleif(PAGINA).set_index("lei")


def test_lei_com_cnpj_da_receita():
    linha = _ponte().loc["LEI0000000000000RFB1"]
    assert (linha["cnpj"], linha["nome"], linha["autoridade"]) == (
        "33000167000101", "EMPRESA DA RECEITA S.A.", "RA000681",
    )  # fmt: skip
    assert linha["publico_em"] == pd.Timestamp(
        "2026-10-13"
    )  # a cópia publicada, não o registro
    assert not linha["conflito"]


def test_cnpj_com_letras_e_de_outra_autoridade_entram():
    ponte = _ponte()
    assert ponte.loc["LEI0000000000000LET2", "cnpj"] == "12ABC34501DE35"
    assert ponte.loc["LEI0000000000000FUN3", "cnpj"] == "60872504000123"


def test_lei_sem_cnpj_fica_sem():
    """NIRE (ou nada) no lugar do CNPJ: o LEI não entra na ponte."""
    assert "LEI0000000000000NIR6" not in _ponte().index


def test_cpf_e_empresario_individual_nunca_entram():
    """LGPD (ADR 0075, Emenda 1): CPF no registeredAs e SOLE_PROPRIETOR são pessoas."""
    ponte = gleif.ler_gleif(PAGINA)
    texto = ponte.astype(str).to_string()
    assert (
        "529982247" not in texto and "FULANO" not in texto and "BELTRANO" not in texto
    )


def test_lei_duplicado_fica_fora():
    ponte = _ponte()
    assert "LEI0000000000000DUP7" not in ponte.index
    assert not ponte.loc["LEI0000000000000RFB1", "conflito"]


def test_cnpj_com_dois_lei_e_conflito():
    ponte = _ponte()
    assert (
        ponte.loc["LEI0000000000000DO18", "cnpj"] == "60746948000112"
    )  # "CNPJ 60..." também
    assert ponte.loc[["LEI0000000000000DO18", "LEI0000000000000DO29"], "conflito"].all()


def test_pagina_vazia():
    vazia = json.dumps(
        {"meta": {"goldenCopy": {"publishDate": "2026-10-13T16:00:00Z"}}, "data": []}
    )
    assert list(gleif.ler_gleif(vazia.encode()).columns) == list(gleif.COLUNAS)


def test_conflito_entre_paginas():
    """O mesmo CNPJ em duas páginas diferentes também é conflito (só se vê depois de juntar)."""
    pagina = json.loads(PAGINA)
    so_o_primeiro = dict(pagina, data=[pagina["data"][0]])
    outro_lei = json.loads(json.dumps(so_o_primeiro))
    outro_lei["data"][0]["attributes"]["lei"] = "LEI0000000000000OUT0"
    juntas = gleif.juntar_paginas(
        [json.dumps(so_o_primeiro).encode(), json.dumps(outro_lei).encode()]
    )
    assert len(juntas) == 2 and juntas["conflito"].all()
    assert gleif.juntar_paginas([]).empty
