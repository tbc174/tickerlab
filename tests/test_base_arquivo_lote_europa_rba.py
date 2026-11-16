"""Lote Europa e RBA (base/arquivo/lote_europa_rba.py): Statistik Austria, Statbel, CBS (Países Baixos),
CSO (Irlanda), INE (Espanha), Istat (Itália) e RBA (Austrália). Nada vai à internet: as descobertas são
endereços fixos e a conferência é sobre o que o catálogo, a licença e a marca dizem de cada um."""

import re
from datetime import UTC, datetime

from base.arquivo import fontes
from base.arquivo import lote_europa_rba as lote
from base.arquivo.orgaos import ORGAO_DA_FAMILIA
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco import coletas
from src.banco.coletas import (
    A_CONFIRMAR,
    NAO_COMERCIAL,
    SEM_LICENCA_CONHECIDA,
    VENDAVEL_COM_ATRIBUICAO,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
    revenda_da_fonte,
)

AGORA = datetime(2026, 11, 5, 23, tzinfo=UTC)
FAMILIAS = {"statat", "statbel", "cbs", "cso", "ines", "istat", "rba"}
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _fontes_do_lote():
    return lote.fontes()


def test_ids_sem_duplicata_no_lote_e_no_catalogo():
    ids = [f.id for f in _fontes_do_lote()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_as_familias_do_lote_estao_todas_representadas():
    familias = {f.id.split("-", 1)[0] for f in _fontes_do_lote()}
    assert familias == FAMILIAS


def test_toda_fonte_do_lote_tem_licenca_marca_orgao_e_data_da_leitura():
    for fonte in _fontes_do_lote():
        familia = fonte.id.split("-", 1)[0]
        assert licenca_da_fonte(fonte.id) != SEM_LICENCA_CONHECIDA, fonte.id
        assert marca_da_fonte(fonte.id) is not None, fonte.id
        assert TERMOS_LIDOS_EM[familia].year == 2026, fonte.id
        assert fonte.grupo in fontes.GRUPOS, fonte.id
        assert familia in ORGAO_DA_FAMILIA, fonte.id


def test_as_sete_familias_sao_vendaveis_com_atribuicao():
    """Licenças lidas na fonte primária em 29/10/2026 (CC BY 4.0, reuso citando a fonte)."""
    for fonte in _fontes_do_lote():
        assert revenda_da_fonte(fonte.id) == VENDAVEL_COM_ATRIBUICAO, fonte.id
        assert marca_da_fonte(fonte.id) == Marca.VENDAVEL, fonte.id


def test_snb_so_ganha_a_marca_nao_comercial_e_nao_entra_na_coleta():
    """Aviso do site: uso só "for non-commercial purposes". Sem pedir licença (ADR 0102, Emenda 2)."""
    assert revenda_da_fonte("snb-cubos") == NAO_COMERCIAL
    assert marca_da_fonte("snb-cubos") == Marca.NAO_COMERCIAL
    assert licenca_da_fonte("snb-cubos") != SEM_LICENCA_CONHECIDA
    assert TERMOS_LIDOS_EM["snb"].year == 2026
    assert not [f for f in fontes.FONTES if f.id.split("-", 1)[0] == "snb"]
    assert "snb" in coletas.COLETA_E_GUARDA


def test_o_que_ficou_de_fora_nao_esta_no_lote():
    """OeNB (404 hoje), DNB (API 404), Banco da Irlanda (páginas em JS) e as tabelas com termo próprio."""
    familias = {f.id.split("-", 1)[0] for f in _fontes_do_lote()}
    assert not familias & {"oenb", "dnb", "cbi", "snb", "abs"}
    assert "rba-taxa-oficial" not in {f.id for f in _fontes_do_lote()}
    assert all("f1-data" not in a.url for f in _fontes_do_lote() for a in _alvos(f))


def _alvos(fonte):
    return fonte.descobrir(None, AGORA)  # type: ignore[arg-type]


def test_cada_fonte_descobre_ao_menos_um_alvo_https_sem_internet():
    for fonte in _fontes_do_lote():
        alvos = _alvos(fonte)
        assert alvos, fonte.id
        assert all(a.url.startswith("https://") for a in alvos), fonte.id
        assert all(a.extensao.startswith(".") for a in alvos), fonte.id


def test_ritmo_pausa_e_tamanho():
    for fonte in _fontes_do_lote():
        assert not fonte.pesada, fonte.id
        assert fonte.pausa_minima >= 1.0, (
            fonte.id
        )  # APIs abertas, de terceiros (ADR 0082)
        assert fonte.grupo in {"semanal", "mensal"}, fonte.id


def test_extensao_e_tipo_batem_com_o_formato_de_cada_endereco():
    por_id = {f.id: f for f in _fontes_do_lote()}
    for serie in lote.SERIES:
        (alvo,) = _alvos(por_id[serie.id])
        assert alvo.url == serie.url
        assert alvo.extensao == serie.extensao
        assert por_id[serie.id].tipo == serie.tipo
        if "format=csv" in serie.url or serie.url.endswith(".csv"):
            assert serie.extensao == ".csv", serie.id
        if serie.url.endswith(".xlsx"):
            assert serie.extensao == ".xlsx", serie.id


def test_statistik_austria_so_os_csv_do_ogd():
    ids = {s.id for s in lote.SERIES if s.id.startswith("statat-")}
    assert ids == {"statat-ipc-base-2010", "statat-ipc-base-2020"}
    for s in lote.SERIES:
        if s.id.startswith("statat-"):
            assert s.url.startswith("https://data.statistik.gv.at/data/OGD_")
            assert s.extensao == ".csv"


def test_statbel_so_pela_api_bestat_com_visoes_publicadas():
    series = [s for s in lote.SERIES if s.id.startswith("statbel-")]
    assert len(series) == 3
    for s in series:
        base, _, resto = s.url.partition("/bestat/api/views/")
        assert base == "https://bestat.statbel.fgov.be"
        identificador, _, formato = resto.partition("/")
        assert UUID.match(identificador), s.id
        assert formato == "result/CSV", s.id
        assert s.extensao == ".csv"


def test_cbs_pede_tabelas_pequenas_abaixo_do_teto_de_dez_mil_registros():
    """A API do CBS recusa consulta com 10.000 registros ou mais: só tabelas anuais e curtas."""
    series = [s for s in lote.SERIES if s.id.startswith("cbs-")]
    assert {s.id for s in series} == {"cbs-inflacao-anual", "cbs-ipch-comparado"}
    for s in series:
        assert "/ODataApi/odata/" in s.url and s.url.endswith("/TypedDataSet")
        assert s.tipo == "json" and s.extensao == ".json"


def test_cso_pede_csv_do_pxstat_no_endereco_novo():
    ids = {s.id: s.url for s in lote.SERIES if s.id.startswith("cso-")}
    assert set(ids) == {"cso-ipc", "cso-preco-de-imoveis", "cso-desemprego"}
    for url in ids.values():
        assert url.startswith(
            "https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API."
        )
        assert url.endswith("/CSV/1.0/en")
    assert "ws-api.cso.ie" not in " ".join(
        ids.values()
    )  # o endereço antigo não responde


def test_ine_espanha_pede_o_historico_inteiro_pelo_wstempus():
    series = [s for s in lote.SERIES if s.id.startswith("ines-")]
    assert {s.id for s in series} == {"ines-ipc", "ines-ativos-epa"}
    for s in series:
        assert s.url.startswith("https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/")
        # sem `nult` a API dá 404; 1000 pontos cobrem o histórico inteiro (mensal desde 2002)
        assert s.url.endswith("?nult=1000")
        assert s.tipo == "json"


def test_istat_usa_o_servico_novo_e_limita_o_periodo_para_nao_travar():
    series = [s for s in lote.SERIES if s.id.startswith("istat-")]
    assert len(series) == 2
    for s in series:
        assert s.url.startswith("https://esploradati.istat.it/SDMXWS/rest/data/IT1,")
        assert "format=csv" in s.url
        assert "sdmx.istat.it" not in s.url  # o endereço antigo redireciona
    assert any("startPeriod=" in s.url for s in series)


def test_rba_so_tabelas_proprias_e_sem_a_taxa_oficial_nem_dado_de_terceiro():
    series = [s for s in lote.SERIES if s.id.startswith("rba-")]
    assert {s.id for s in series} == {
        "rba-cambio",
        "rba-rendimentos-dos-titulos",
        "rba-balanco",
    }
    for s in series:
        assert s.url.startswith("https://www.rba.gov.au/statistics/tables/")
    # a tabela F1 traz a taxa oficial (Cash Rate), de termos próprios; as tabelas do ABS são do ABS
    assert not [s for s in series if "f1-data" in s.url or "/abs" in s.url]
    assert {s.extensao for s in series} == {".csv", ".xlsx"}


def test_termos_do_lote_entram_no_catalogo_com_vigia():
    assert lote.termos().items() <= fontes.TERMOS.items()
    for chave, url in lote.termos().items():
        assert chave.startswith("termos-") and url.startswith("https://")
        assert fontes.POR_ID[chave].vigia is True
    assert len(set(lote.termos().values())) == len(lote.termos())
    assert set(lote.termos()) == {"termos-cbs", "termos-istat", "termos-rba"}


def test_a_coleta_e_guarda_das_familias_fecha():
    for familia in (*FAMILIAS, "snb"):
        resposta = coletas.COLETA_E_GUARDA[familia]
        assert resposta.coleta in coletas.Coleta
        assert resposta.guarda in coletas.Guarda


def test_snb_a_confirmar_nao_aparece_como_vendavel():
    assert marca_da_fonte("snb-cubos") != Marca.VENDAVEL
    assert A_CONFIRMAR != NAO_COMERCIAL
