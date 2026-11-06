"""Lote nórdico (base/arquivo/lote_nordicos.py): bancos centrais e institutos de estatística. Nada vai à internet."""

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
CRLF = bytes([13, 10])
FAMILIAS = {"riksbank", "norges", "dst", "scb", "statfi", "statice"}


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
    fora = ("ssb", "nationalbank", "bankoffinland", "sedlabanki")
    assert not [i for i in ids if i.split("-")[0] in fora]


def test_paginas_de_termos_sao_vigiadas():
    assert set(lote.termos()) == {
        "termos-riksbank",
        "termos-norges",
        "termos-dst",
        "termos-scb",
        "termos-statfi",
        "termos-statice",
    }
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
        "https://api.statbank.dk/v1/data/AUS08/BULK?lang=en"
        "&OMR%C3%85DE=*&SAESONFAK=*&Tid=*"
    )
    assert alvo.extensao == ".csv"


def test_dst_usa_o_bulk_que_nao_tem_o_limite_de_celulas_do_csv():
    """O `CSV` comum recusa mais de 1 milhão de células (combinações x (variáveis + 1)) com 400; o IPC, com
    404 mil combinações e 3 variáveis, dá 1,6 milhão. O BULK entrega a tabela inteira (conferido em 05/11/2026)."""
    for serie in lote.SERIES_DA_DST:
        assert "/BULK" in serie.url and "/CSV" not in serie.url, serie.id
    cliente = TableinfoFixo(
        [
            {"id": "VAREGR", "values": [1] * 2018},
            {"id": "ENHED", "values": [1] * 3},
            {"id": "Tid", "values": [1] * 67},
        ]
    )
    (alvo,) = lote.descobrir_serie(_tabela_da_dst("ipc"))(cliente, AGORA)
    assert alvo.url.startswith("https://api.statbank.dk/v1/data/PRIS01/BULK?lang=en&")


def test_dst_tabela_sem_variaveis_e_falha():
    cliente = TableinfoFixo([])
    with pytest.raises(ErroDeDescoberta):
        lote.descobrir_serie(_tabela_da_dst("ipc"))(cliente, AGORA)


def test_dst_tableinfo_inesperado_e_falha():
    cliente = TableinfoFixo([])
    cliente.corpo = b'{"erro": 1}'
    with pytest.raises(ErroDeDescoberta):
        lote.descobrir_serie(_tabela_da_dst("ipc"))(cliente, AGORA)


class MetadadosFixos:
    """Responde os metadados do SCB (PxWebApi v2beta) com dimensões fixas e guarda os pedidos."""

    def __init__(self, ids: list[str], tamanhos: list[int]):
        self.corpo = json.dumps({"id": ids, "size": tamanhos}).encode()
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.corpo, {})


def _serie(identificador: str):
    return next(s for s in lote.SERIES if s.id == identificador)


def test_scb_e_cc0_e_vendavel():
    for fonte in lote.fontes():
        if fonte.id.startswith("scb-"):
            assert marca_da_fonte(fonte.id) == Marca.VENDAVEL, fonte.id
            assert revenda_da_fonte(fonte.id) == VENDAVEL_COM_ATRIBUICAO, fonte.id
    assert "CC0" in licenca_da_fonte("scb-ipc")


def test_scb_pede_todos_os_valores_de_cada_dimensao():
    cliente = MetadadosFixos(["ContentsCode", "Tid"], [1, 1353])
    (alvo,) = lote.descobrir_serie(_serie("scb-ipc"))(cliente, AGORA)
    assert cliente.pedidos == [
        "https://api.scb.se/OV0104/v2beta/api/v2/tables/TAB2075/metadata?lang=en"
    ]
    assert alvo.url == (
        "https://api.scb.se/OV0104/v2beta/api/v2/tables/TAB2075/data?lang=en"
        "&outputFormat=csv&valueCodes%5BContentsCode%5D=*&valueCodes%5BTid%5D=*"
    )
    assert alvo.extensao == ".csv"


def test_scb_tabela_acima_do_limite_de_celulas_da_api_e_falha():
    """A API recusa mais de 150 mil células; melhor falhar na descoberta que baixar um erro."""
    cliente = MetadadosFixos(["A", "Tid"], [1000, 151])
    with pytest.raises(ErroDeDescoberta):
        lote.descobrir_serie(_serie("scb-desemprego"))(cliente, AGORA)


def test_scb_metadados_inesperados_sao_falha():
    cliente = MetadadosFixos([], [])
    cliente.corpo = b'{"erro": 1}'
    with pytest.raises(ErroDeDescoberta):
        lote.descobrir_serie(_serie("scb-ipc"))(cliente, AGORA)


@pytest.mark.parametrize("familia", ["statfi", "statice"])
def test_institutos_com_credito_sao_vendaveis_citando_a_fonte(familia):
    ids = [f.id for f in lote.fontes() if f.id.startswith(f"{familia}-")]
    assert ids
    for identificador in ids:
        assert marca_da_fonte(identificador) == Marca.VENDAVEL, identificador
        assert revenda_da_fonte(identificador) == VENDAVEL_COM_ATRIBUICAO
        assert "CC BY 4.0" in licenca_da_fonte(identificador)


class PxWebFixo:
    """Guarda o POST feito ao PxWeb e devolve um CSV fixo."""

    def __init__(self):
        self.chamadas: list[tuple[str, str, bytes | None]] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.chamadas.append((url, metodo, corpo))
        csv = b'"Month","Valor"' + CRLF + b'"2026M01",1' + CRLF
        return Resposta(url, csv, {"ETag": "x"})


@pytest.mark.parametrize("identificador", ["statfi-ipc", "statice-ipc"])
def test_pxweb_pede_a_tabela_inteira_em_csv_por_post(tmp_path, identificador):
    (alvo,) = lote.descobrir_serie(_serie(identificador))(object(), AGORA)
    cliente = PxWebFixo()
    destino = tmp_path / "tabela.csv"
    cabecalhos = alvo.obter(cliente, destino)
    (url, metodo, corpo) = cliente.chamadas[0]
    assert (url, metodo) == (alvo.url, "POST")
    assert json.loads(corpo) == {"query": [], "response": {"format": "csv"}}
    assert destino.read_bytes().startswith(b'"Month"')
    assert cabecalhos == {"ETag": "x"}
