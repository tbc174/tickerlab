"""Lote nórdico (base/arquivo/lote_nordicos.py): Riksbank e Norges Bank. Nada vai à internet."""

import json
from datetime import UTC, datetime

import pytest

from base.arquivo import fontes
from base.arquivo import lote_nordicos as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    VENDAVEL_COM_ATRIBUICAO,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
    revenda_da_fonte,
)

AGORA = datetime(2026, 11, 5, 13, tzinfo=UTC)
FAMILIAS = {"riksbank", "norges", "dst"}


def test_ids_sem_duplicata_no_lote_e_no_catalogo():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    assert set(ids) <= {f.id for f in fontes.FONTES}


def test_as_familias_do_lote_sao_so_as_escolhidas():
    assert {f.id.split("-", 1)[0] for f in lote.fontes()} == FAMILIAS


def test_toda_fonte_tem_licenca_marca_e_data_da_leitura_dos_termos():
    for fonte in lote.fontes():
        familia = fonte.id.split("-", 1)[0]
        assert licenca_da_fonte(fonte.id) != SEM_LICENCA_CONHECIDA, fonte.id
        assert marca_da_fonte(fonte.id) is not None, fonte.id
        assert TERMOS_LIDOS_EM[familia].year == 2026, fonte.id
        assert fonte.grupo in fontes.GRUPOS, fonte.id


def test_riksbank_e_vendavel_citando_a_fonte_e_a_data():
    for fonte in lote.fontes():
        if fonte.id.startswith("riksbank-"):
            assert revenda_da_fonte(fonte.id) == VENDAVEL_COM_ATRIBUICAO, fonte.id
            assert marca_da_fonte(fonte.id) == Marca.VENDAVEL, fonte.id
    assert "Sveriges riksbank" in licenca_da_fonte("riksbank-juro-diretor")


def test_norges_bank_fica_a_confirmar_por_causa_do_sem_alteracao():
    """ "No changes may be made" e `ai-train=no`: sem leitura humana não é vendável (ADR 0102 Emenda 2)."""
    for fonte in lote.fontes():
        if fonte.id.startswith("norges-"):
            assert marca_da_fonte(fonte.id) == Marca.A_CONFIRMAR, fonte.id
    licenca = licenca_da_fonte("norges-cambio")
    assert "Norges Bank" in licenca and "sem alterar" in licenca


def test_serie_diaria_vira_historico_fechado_e_janela_aberta():
    alvos = lote.descobrir_serie(
        next(s for s in lote.SERIES if s.id == "riksbank-cambio-real")
    )(None, AGORA)  # type: ignore[arg-type]
    assert [a.url for a in alvos] == [
        "https://api.riksbank.se/swea/v1/Observations/SEKBRLPMI/1980-01-01/2025-12-31",
        "https://api.riksbank.se/swea/v1/Observations/SEKBRLPMI/2025-01-01/2026-12-31",
    ]
    assert all(a.extensao == ".json" for a in alvos)


def test_serie_diaria_do_norges_bank_pede_csv_em_duas_janelas():
    serie = next(s for s in lote.SERIES if s.id == "norges-cambio")
    alvos = lote.descobrir_serie(serie)(None, AGORA)  # type: ignore[arg-type]
    assert len(alvos) == 2
    assert "startPeriod=1980-01-01&endPeriod=2025-12-31" in alvos[0].url
    assert "startPeriod=2025-01-01&endPeriod=2026-12-31" in alvos[1].url
    assert all("format=csv" in a.url and a.extensao == ".csv" for a in alvos)
    assert "BRL" in alvos[0].url


def test_catalogos_do_riksbank_sao_um_endereco_so():
    serie = next(s for s in lote.SERIES if s.id == "riksbank-catalogo-de-series")
    (alvo,) = lote.descobrir_serie(serie)(None, AGORA)  # type: ignore[arg-type]
    assert alvo.url == "https://api.riksbank.se/swea/v1/Series"


def test_ritmo_respeita_a_api_anonima_do_riksbank():
    for fonte in lote.fontes():
        assert not fonte.pesada, fonte.id
        minimo = 15.0 if fonte.id.startswith("riksbank-") else 1.0
        assert fonte.pausa_minima >= minimo, fonte.id


def test_o_lote_nao_pega_o_que_esta_fora_do_escopo():
    ids = {f.id for f in lote.fontes()}
    fora = ("ssb", "nationalbank", "bankoffinland", "sedlabanki", "scb")
    assert not [i for i in ids if i.split("-")[0] in fora]


def test_paginas_de_termos_sao_vigiadas():
    assert set(lote.termos()) == {"termos-riksbank", "termos-norges", "termos-dst"}
    assert set(lote.termos()) <= set(fontes.TERMOS)


class TableinfoFixo:
    """Responde o `tableinfo` da DST com variáveis fixas e guarda os pedidos."""

    def __init__(self, variaveis: list[dict]):
        self.corpo = json.dumps({"variables": variaveis}).encode()
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.corpo, {})


def _tabela_da_dst(nome: str):
    return next(s for s in lote.SERIES if s.id == f"dst-{nome}")


def test_dst_e_vendavel_citando_a_statistics_denmark():
    for fonte in lote.fontes():
        if fonte.id.startswith("dst-"):
            assert marca_da_fonte(fonte.id) == Marca.VENDAVEL, fonte.id
            assert revenda_da_fonte(fonte.id) == VENDAVEL_COM_ATRIBUICAO, fonte.id
    assert "CC BY 4.0" in licenca_da_fonte("dst-ipc")


def test_dst_pede_todas_as_variaveis_da_tabela_com_asterisco():
    cliente = TableinfoFixo(
        [
            {"id": "OMRÅDE", "values": [1] * 117},
            {"id": "SAESONFAK", "values": [1] * 4},
            {"id": "Tid", "values": [1] * 237},
        ]
    )
    (alvo,) = lote.descobrir_serie(_tabela_da_dst("desemprego"))(cliente, AGORA)
    assert cliente.pedidos == [
        "https://api.statbank.dk/v1/tableinfo/AUS08?format=JSON&lang=en"
    ]
    assert alvo.url == (
        "https://api.statbank.dk/v1/data/AUS08/CSV?lang=en&delimiter=Semicolon"
        "&OMR%C3%85DE=*&SAESONFAK=*&Tid=*"
    )
    assert alvo.extensao == ".csv"


def test_dst_tabela_grande_demais_e_falha_e_nao_corte_silencioso():
    cliente = TableinfoFixo(
        [{"id": "A", "values": [1] * 2000}, {"id": "Tid", "values": [1] * 2000}]
    )
    with pytest.raises(ErroDeDescoberta):
        lote.descobrir_serie(_tabela_da_dst("ipc"))(cliente, AGORA)


def test_dst_tableinfo_inesperado_e_falha():
    cliente = TableinfoFixo([])
    cliente.corpo = b'{"erro": 1}'
    with pytest.raises(ErroDeDescoberta):
        lote.descobrir_serie(_tabela_da_dst("ipc"))(cliente, AGORA)
