"""Lote do RAPP do IBAMA no arquivista (base/arquivo/lote_ibama_rapp.py, linha 1074). Sem internet."""

from datetime import UTC, datetime

from base import ibama_rapp
from base.arquivo import lote_ibama_rapp as lote
from base.arquivo.destinos import DESTINOS
from base.arquivo.fontes import FONTES, POR_ID
from src.banco.coletas import (
    INTEGRIDADE_SOB_CONTRATO,
    SEM_LICENCA_CONHECIDA,
    licenca_da_fonte,
    revenda_da_fonte,
)

AGORA = datetime(2026, 11, 25, 15, tzinfo=UTC)
IDS_DO_LOTE = [f.id for f in lote.fontes()]
PORTAL_DO_IBAMA = "https://dadosabertos.ibama.gov.br/dados/RAPP/"


class ClienteQueNaoPodeSerUsado:
    def ler(self, url, **_):
        raise AssertionError(f"o endereço é fixo; nada a pedir ao portal: {url}")


def test_o_lote_tem_uma_fonte_por_relatorio_sem_id_repetido_e_dentro_da_lista_do_arquivista():
    assert [r.fonte for r in ibama_rapp.RELATORIOS] == IDS_DO_LOTE
    ids = [f.id for f in FONTES]
    assert len(ids) == len(set(ids))
    assert set(IDS_DO_LOTE) <= set(ids)


def test_o_endereco_e_fixo_no_portal_do_ibama_e_sai_sem_perguntar_nada_ao_portal():
    for relatorio in ibama_rapp.RELATORIOS:
        alvos = POR_ID[relatorio.fonte].descobrir(ClienteQueNaoPodeSerUsado(), AGORA)
        assert [a.url for a in alvos] == [relatorio.url]
        assert relatorio.url.startswith(PORTAL_DO_IBAMA)
        assert relatorio.url.endswith("/relatorio.csv")


def test_cada_fonte_tem_a_licenca_da_familia_ibama_e_o_destino_na_sua_tabela():
    for relatorio in ibama_rapp.RELATORIOS:
        assert licenca_da_fonte(relatorio.fonte) != SEM_LICENCA_CONHECIDA
        assert "IBAMA" in licenca_da_fonte(relatorio.fonte)
        assert revenda_da_fonte(relatorio.fonte) == INTEGRIDADE_SOB_CONTRATO
        assert DESTINOS[relatorio.fonte].tabelas == (relatorio.tabela,)


def test_olha_todo_mes_e_so_os_dois_grandes_sao_pesados():
    assert {f.grupo for f in lote.fontes()} == {lote.MENSAL}
    assert {f.id for f in lote.fontes() if f.pesada} == {
        "ibama-rapp-efluentes-liquidos",
        "ibama-rapp-fontes-energeticas",
    }
