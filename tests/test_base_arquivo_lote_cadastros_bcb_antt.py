"""Lote 3 do arquivista (base/arquivo/lote_cadastros_bcb_antt.py): cadastros do Banco Central e da ANTT.
Sem internet, com dublês."""

import json
from datetime import UTC, datetime

import pytest

from base.arquivo import lote_cadastros_bcb_antt as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)

AGORA = datetime(2026, 11, 14, 15, tzinfo=UTC)
IDS_DO_LOTE = [f.id for f in lote.fontes()]
DA_ANTT = "https://dados.antt.gov.br/dataset/x/resource/y/download/"


class Cliente:
    def __init__(self, resposta: dict):
        self.resposta = resposta
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, json.dumps(self.resposta).encode(), {})


def _pacote(*urls: str) -> dict:
    return {"result": {"resources": [{"url": u, "format": "CSV"} for u in urls]}}


def test_o_endereco_do_bcbase_leva_o_dia_da_coleta_com_o_mes_na_frente():
    endereco = lote.endereco_do_dia(lote.SUPERVISIONADAS, AGORA)
    assert "@d='11-14-2026'" in endereco
    assert endereco.startswith("https://olinda.bcb.gov.br/olinda/servico/BcBase/")
    assert endereco.endswith("$format=json")


def test_as_fontes_do_bcbase_pedem_o_dia_e_as_demais_um_endereco_fixo():
    do_dia = POR_ID["bcb-supervisionadas"].descobrir(Cliente({}), AGORA)
    outro_dia = POR_ID["bcb-supervisionadas"].descobrir(
        Cliente({}), datetime(2026, 12, 1, tzinfo=UTC)
    )
    assert do_dia[0].url != outro_dia[0].url
    fixo = POR_ID["bcb-correspondentes"].descobrir(Cliente({}), AGORA)
    assert fixo[0].url == lote.CORRESPONDENTES
    assert (
        fixo[0].url
        == POR_ID["bcb-correspondentes"].descobrir(Cliente({}), AGORA)[0].url
    )


def test_o_seguro_pega_so_o_csv_atual_do_pacote_e_nao_os_mensais():
    cliente = Cliente(
        _pacote(
            DA_ANTT + "seguro-responsabilidade-civil-2022-01.csv",
            DA_ANTT + "seguro-responsabilidade-civil.csv",
            DA_ANTT + "dicionario.pdf",
        )
    )
    alvos = lote.descobrir_seguro(cliente, AGORA)
    assert [a.url for a in alvos] == [DA_ANTT + "seguro-responsabilidade-civil.csv"]
    assert cliente.pedidos == [
        "https://dados.antt.gov.br/api/3/action/package_show?id=seguro-responsabilidade-civil"
    ]


def test_o_seguro_sem_o_csv_atual_e_erro_de_descoberta_nunca_lista_vazia():
    with pytest.raises(ErroDeDescoberta, match="sem o CSV atual"):
        lote.descobrir_seguro(
            Cliente(_pacote(DA_ANTT + "seguro-responsabilidade-civil-2022-01.csv")),
            AGORA,
        )


def test_o_lote_tem_sete_fontes_sem_id_repetido_e_dentro_da_lista_do_arquivista():
    assert len(IDS_DO_LOTE) == 7 == len(set(IDS_DO_LOTE))
    ids = [f.id for f in FONTES]
    assert len(ids) == len(set(ids))
    assert set(IDS_DO_LOTE) <= set(ids)


def test_cada_fonte_do_lote_tem_licenca_da_sua_familia():
    for id_ in IDS_DO_LOTE:
        licenca = licenca_da_fonte(id_)
        assert licenca != SEM_LICENCA_CONHECIDA, id_
        assert marca_da_fonte(id_) is Marca.VENDAVEL, id_
        assert ("ODbL" if id_.startswith("bcb-") else "CC BY") in licenca, id_


def test_so_as_duas_grandes_sao_pesadas():
    pesadas = {f.id for f in lote.fontes() if f.pesada}
    assert pesadas == {"bcb-correspondentes", "antt-seguro-de-responsabilidade-civil"}
