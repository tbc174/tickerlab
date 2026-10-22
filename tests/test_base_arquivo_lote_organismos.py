"""Lote organismos (base/arquivo/lote_organismos.py): BCE, OCDE, Eurostat, BIS, FMI, Banco Mundial,
NASA POWER, NOAA CPC e GLEIF. Nada vai à internet: as respostas são dublês de `tests/arquivos/`."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import fontes
from base.arquivo import lote_organismos as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)
from src.commodities.cafe import regioes

AGORA = datetime(2026, 10, 22, 13, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "organismos"
PAGINA_DO_BANCO_MUNDIAL = (PASTA / "banco_mundial_pagina.json").read_bytes()
EMISSORES_DO_GLEIF = (PASTA / "gleif_emissores.json").read_bytes()
FAMILIAS_NAO_COMERCIAIS = {"fmi", "bis"}
FAMILIAS = {"bce", "ocde", "eurostat", "worldbank", "bis", "fmi", "nasa", "noaa"}


class Paginas:
    """Responde `ler` com páginas fixas (por endereço) e guarda os pedidos."""

    def __init__(self, paginas: dict[str, bytes]):
        self.paginas = paginas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.paginas[url], {})


def _fontes_do_lote():
    return lote.fontes()


def test_ids_sem_duplicata_no_lote_e_no_catalogo():
    ids = [f.id for f in _fontes_do_lote()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_do_lote_tem_licenca_marca_e_data_da_leitura():
    for fonte in _fontes_do_lote():
        familia = fonte.id.split("-", 1)[0]
        assert licenca_da_fonte(fonte.id) != SEM_LICENCA_CONHECIDA, fonte.id
        assert marca_da_fonte(fonte.id) is not None, fonte.id
        assert TERMOS_LIDOS_EM[familia].year == 2026, fonte.id
        assert fonte.grupo in fontes.GRUPOS, fonte.id


def test_fmi_e_bis_sao_nao_comercial_e_o_resto_e_vendavel():
    for fonte in _fontes_do_lote():
        familia = fonte.id.split("-", 1)[0]
        esperada = (
            Marca.NAO_COMERCIAL
            if familia in FAMILIAS_NAO_COMERCIAIS
            else Marca.VENDAVEL
        )
        assert marca_da_fonte(fonte.id) == esperada, fonte.id


def test_as_familias_do_lote_estao_todas_representadas():
    familias = {f.id.split("-", 1)[0] for f in _fontes_do_lote()}
    assert familias == FAMILIAS | {"gleif"}


def test_o_lote_nao_pega_o_que_e_de_outras_linhas_da_fila():
    ids = {f.id for f in _fontes_do_lote()}
    # ENSO, GHCN e OISST (linha 290), golden copy do GLEIF (287) e o grupo "depois" da rodada 1
    proibidas = (
        "oni",
        "enso",
        "nino",
        "soi",
        "ghcn",
        "oisst",
        "golden",
        "snb",
        "chirps",
    )
    assert not [i for i in ids if any(p in i.split("-") for p in proibidas)]
    assert "gleif-br" not in ids  # já existia em `fontes.py`


def test_ritmo_segue_o_calendario_de_cada_serie():
    por_id = {f.id: f for f in _fontes_do_lote()}
    assert por_id["bce-cambio-dolar"].grupo == "diaria"
    assert por_id["bce-inflacao-ipch"].grupo == "semanal"
    assert por_id["worldbank-brasil"].grupo == "mensal"
    assert all(not f.pesada for f in _fontes_do_lote())
    assert all(f.pausa_minima > 0 for f in _fontes_do_lote())


def test_serie_diaria_do_bce_vira_historico_fechado_e_janela_aberta():
    serie = next(s for s in lote.SERIES_DO_BCE if s.id == "bce-cambio-dolar")
    alvos = lote.descobrir_serie(serie)(None, AGORA)  # type: ignore[arg-type]
    assert [a.url for a in alvos] == [
        (
            "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
            "?startPeriod=1999-01-01&endPeriod=2025-12-31&format=csvdata"
        ),
        (
            "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
            "?startPeriod=2025-01-01&format=csvdata"
        ),
    ]
    assert all(a.extensao == ".csv" for a in alvos)


def test_serie_mensal_do_bce_e_um_endereco_so_com_csvdata():
    serie = next(s for s in lote.SERIES_DO_BCE if s.id == "bce-inflacao-ipch")
    (alvo,) = lote.descobrir_serie(serie)(None, AGORA)  # type: ignore[arg-type]
    assert alvo.url.endswith("ICP/M.U2.N.000000.4.ANR?format=csvdata")


def test_ocde_pede_o_brasil_primeiro():
    (serie,) = lote.SERIES_DA_OCDE
    assert "/BRA+" in serie.url and "csvfilewithlabels" in serie.url


def test_eurostat_sempre_filtra_pais_e_so_da_uniao_europeia():
    fora_da_ue = {"US", "JP", "CN", "BR", "UK", "GB"}
    assert not fora_da_ue & set(lote.PAISES_DO_EUROSTAT)
    for serie in lote.SERIES_DO_EUROSTAT:
        for pais in lote.PAISES_DO_EUROSTAT:
            assert f"geo={pais}" in serie.url, serie.id
        assert serie.tipo == "json" and serie.extensao == ".json"


def test_cada_serie_do_bis_e_do_fmi_tem_endereco_https_e_extensao():
    for serie in (*lote.SERIES_DO_BIS, *lote.SERIES_DO_FMI):
        assert serie.url.startswith("https://"), serie.id
        assert serie.extensao in {".csv", ".xml", ".json"}, serie.id
    assert {s.extensao for s in lote.SERIES_DO_BIS} == {".csv"}


def test_banco_mundial_devolve_todas_as_paginas_do_cabecalho():
    url = lote._indicadores_do_banco_mundial("BRA", ("NY.GDP.MKTP.CD",))
    cliente = Paginas({url.format(pagina=1): PAGINA_DO_BANCO_MUNDIAL})
    alvos = lote.descobrir_banco_mundial("BRA", ("NY.GDP.MKTP.CD",))(cliente, AGORA)
    assert [a.url for a in alvos] == [url.format(pagina=n) for n in (1, 2, 3)]
    assert all(a.extensao == ".json" for a in alvos)
    assert "country/BRA/indicator/NY.GDP.MKTP.CD" in alvos[0].url
    assert cliente.pedidos == [url.format(pagina=1)]  # só a primeira página foi pedida


def test_banco_mundial_junta_os_indicadores_do_brasil_no_mesmo_pedido():
    url = lote._indicadores_do_banco_mundial("BRA", lote.INDICADORES_DO_BRASIL)
    assert url.count(";") == len(lote.INDICADORES_DO_BRASIL) - 1
    assert "source=2" in url and "format=json" in url


def test_banco_mundial_com_resposta_de_erro_e_falha_nao_nada_novo():
    url = lote._indicadores_do_banco_mundial("BRA", ("X",)).format(pagina=1)
    erro = json.dumps([{"message": [{"id": "120", "key": "Invalid value"}]}]).encode()
    with pytest.raises(ErroDeDescoberta):
        lote.descobrir_banco_mundial("BRA", ("X",))(Paginas({url: erro}), AGORA)


def test_banco_mundial_pede_o_mundo_todo_so_para_os_indicadores_de_comparacao():
    ids = {f.id for f in _fontes_do_lote() if f.id.startswith("worldbank-")}
    assert "worldbank-brasil" in ids
    assert len(ids) == 1 + len(lote.INDICADORES_DO_MUNDO)


def test_gleif_novas_listas_andam_ate_a_ultima_pagina():
    def pagina(n):
        return json.dumps(
            {"meta": {"pagination": {"currentPage": n, "lastPage": 2}}}
        ).encode()

    paginas = {lote.endereco_do_gleif("lei-issuers", n): pagina(n) for n in (1, 2)}
    alvos = lote.descobrir_gleif("lei-issuers")(Paginas(paginas), AGORA)
    assert [a.url for a in alvos] == list(paginas)


def test_gleif_emissores_cabem_em_uma_pagina():
    url = lote.endereco_do_gleif("lei-issuers", 1)
    cliente = Paginas({url: EMISSORES_DO_GLEIF})
    alvos = lote.descobrir_gleif("lei-issuers")(cliente, AGORA)
    assert [a.url for a in alvos] == [url]


def test_gleif_br_continua_a_fonte_antiga_e_as_novas_so_acrescentam():
    ids = [f.id for f in fontes.FONTES if f.id.startswith("gleif-")]
    assert sorted(ids) == sorted(["gleif-br", *lote.ENDPOINTS_DO_GLEIF])


def test_todas_as_regioes_do_cafe_tem_ponto_na_nasa_e_so_elas():
    assert lote.regioes_sem_ponto() == set()
    assert set(lote.COORDENADAS_DAS_REGIOES) == {d.id for d in regioes.DEFINICOES}


def test_os_pontos_da_nasa_ficam_no_brasil():
    for regiao, (latitude, longitude) in lote.COORDENADAS_DAS_REGIOES.items():
        assert -34 < latitude < 6, regiao
        assert -74 < longitude < -34, regiao


def test_nasa_pede_o_ponto_da_regiao_de_1990_ate_o_ano_da_coleta():
    (alvo,) = lote.descobrir_nasa("sul-de-minas")(None, AGORA)  # type: ignore[arg-type]
    assert "longitude=-45.5&latitude=-21.5" in alvo.url
    assert "start=1990&end=2026" in alvo.url
    assert "community=AG" in alvo.url and alvo.extensao == ".json"


def test_noaa_nao_traz_enso():
    urls = " ".join(s.url for s in lote.SERIES_DO_NOAA)
    for proibido in ("oni", "sstoi", "/soi", "ersst", "oisst", "ghcn"):
        assert proibido not in urls


def test_termos_do_lote_entram_no_catalogo_com_vigia():
    assert lote.termos().items() <= fontes.TERMOS.items()
    for chave, url in lote.termos().items():
        assert chave.startswith("termos-") and url.startswith("https://")
        assert fontes.POR_ID[chave].vigia is True
    assert len(set(lote.termos().values())) == len(lote.termos())


def test_cada_fonte_do_lote_descobre_ao_menos_um_alvo_sem_internet():
    for fonte in _fontes_do_lote():
        if fonte.id.startswith(("worldbank-", "gleif-")):
            continue  # paginadas: têm teste próprio acima
        alvos = fonte.descobrir(None, AGORA)  # type: ignore[arg-type]
        assert alvos, fonte.id
        assert all(a.url.startswith("https://") for a in alvos), fonte.id
