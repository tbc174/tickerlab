"""Lote SEC do arquivista (base/arquivo/lote_sec.py): como cada fonte acha os seus arquivos."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from base.arquivo import destinos, lote_eua, lote_sec
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 10, 23, 14, tzinfo=UTC)
DUBLES = Path(__file__).parent / "arquivos" / "sec"
RAIZ = "https://www.sec.gov"


class Paginas:
    """Responde `ler` com páginas fixas; um valor `int` vira erro HTTP com esse código."""

    def __init__(self, paginas: dict[str, bytes | int]):
        self.paginas = paginas

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        pagina = self.paginas[url]
        if isinstance(pagina, int):
            resposta = requests.Response()
            resposta.status_code = pagina
            raise requests.HTTPError(response=resposta)
        return Resposta(url, pagina, {})


def _dubles(nome: str) -> bytes:
    return (DUBLES / nome).read_bytes()


def _urls(alvos):
    return [a.url for a in alvos]


def _descobrir(id_: str, paginas: dict[str, bytes | int]):
    return POR_ID[id_].descobrir(Paginas(paginas), AGORA)


# ---------------------------------------------------------------- catálogo
def test_ids_do_lote_sao_unicos_e_estao_no_catalogo_geral():
    ids = [f.id for f in lote_sec.fontes()]
    assert len(ids) == len(set(ids))
    assert set(ids) <= set(POR_ID)
    assert len([f for f in FONTES if f.id in ids]) == len(ids)


def test_ids_nao_repetem_os_do_lote_eua():
    assert not {f.id for f in lote_sec.fontes()} & {f.id for f in lote_eua.fontes()}


def test_historia_so_roda_pelo_id_e_os_pacotes_sao_diarios_e_pesados():
    grupos = {f.id: f.grupo for f in lote_sec.fontes()}
    historicas = {i for i, g in grupos.items() if g == "carga-unica"}
    assert historicas == {i for i in grupos if i.endswith("-historico")}
    for id_ in lote_sec.PACOTES_DO_EDGAR:
        assert grupos[id_] == "diaria"
        assert POR_ID[id_].pesada


@pytest.mark.parametrize("fonte", [f.id for f in lote_sec.fontes()])
def test_toda_fonte_do_lote_tem_licenca_marca_e_destino(fonte):
    assert licenca_da_fonte(fonte) == licenca_da_fonte("sec-edgar-13f")
    assert marca_da_fonte(fonte) is Marca.USO_INTERNO
    assert fonte in destinos.DESTINOS


# ------------------------------------------------------------- descoberta
def test_conjunto_trimestral_leva_os_dois_mais_novos_e_o_historico_o_resto():
    pagina = {
        RAIZ
        + lote_sec.CONJUNTOS_DA_DATA_LIBRARY["sec-demonstracoes-financeiras"][
            0
        ]: _dubles("pagina_demonstracoes.html")
    }
    recentes = _descobrir("sec-demonstracoes-financeiras", pagina)
    antigos = _descobrir("sec-demonstracoes-financeiras-historico", pagina)
    assert _urls(recentes)[0].endswith("/financial-statement-data-sets/2026q3.zip")
    assert len(recentes) == 2 and len(antigos) == 3
    assert not set(_urls(recentes)) & set(_urls(antigos))


def test_form_adv_traz_exempt_e_registered_do_mes_mais_novo():
    caminho = lote_sec.CONJUNTOS_DA_DATA_LIBRARY["sec-form-adv"][0]
    urls = _urls(
        _descobrir("sec-form-adv", {RAIZ + caminho: _dubles("pagina_form_adv.html")})
    )
    assert [u.rsplit("/", 1)[1] for u in urls] == [
        "ia100226-exempt.zip",
        "ia100226.zip",
    ]


def test_corretoras_e_registros_foia_nao_sao_zip():
    corretoras = lote_sec.CONJUNTOS_DA_DATA_LIBRARY["sec-corretoras"][0]
    foia = lote_sec.CONJUNTOS_DA_DATA_LIBRARY["sec-foia-registros"][0]
    c = _descobrir(
        "sec-corretoras", {RAIZ + corretoras: _dubles("pagina_corretoras.html")}
    )
    f = _descobrir("sec-foia-registros", {RAIZ + foia: _dubles("pagina_foia.html")})
    assert all(a.url.endswith(".txt") for a in c) and len(c) == 2
    assert all(a.url.endswith(".csv") for a in f) and len(f) == 4


def test_pacote_diario_e_um_zip_so():
    alvos = POR_ID["sec-bulk-submissions"].descobrir(Paginas({}), AGORA)
    assert _urls(alvos) == [lote_sec.PACOTES_DO_EDGAR["sec-bulk-submissions"]]
    assert alvos[0].extensao == ".zip"


def test_pagina_sem_arquivo_e_erro_e_403_de_bloqueio_sobe_como_http():
    caminho = RAIZ + lote_sec.CONJUNTOS_DA_DATA_LIBRARY["sec-insiders"][0]
    with pytest.raises(ErroDeDescoberta):
        _descobrir("sec-insiders", {caminho: b"<html>sem zip</html>"})
    with pytest.raises(requests.HTTPError):
        _descobrir("sec-insiders", {caminho: 403})
