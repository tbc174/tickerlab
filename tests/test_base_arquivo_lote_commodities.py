"""Lote commodities (base/arquivo/lote_commodities.py): café, commodities e clima. Nada vai à internet: o cliente é
um dublê com as páginas escritas aqui (o formato é o do gov.br/conab, do CHC e do INMET lidos em 03/11/2026)."""

from datetime import UTC, datetime

import pytest

from base.arquivo import fontes
from base.arquivo import lote_commodities as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte, revenda_da_fonte

AGORA = datetime(2026, 11, 3, 22, tzinfo=UTC)
CONAB = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/"
SERIES = CONAB + "series-historicas/"
BOLETINS = CONAB + "safra-de-graos/boletim-da-safra-de-graos"
SEM_PAGINAS = {
    "faostat-precos-ao-produtor",
    "faostat-comercio",
    "ico-icip-mensal",
    "cftc-cot-futuros-e-opcoes",
    "cftc-cot-cit",
    "cftc-cot-legado",
    "chirps-chirts-tmax-mensal",
    "chirps-chirts-tmax-historico",
    "mapbiomas-bioma-e-estado",
}


class Paginas:
    """Responde com a página combinada pelo endereço exato; qualquer outro é erro do teste."""

    def __init__(self, paginas: dict[str, str]):
        self.paginas = paginas

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        return Resposta(url, self.paginas[url].encode(), {})


def _fonte(id_: str):
    return next(f for f in lote.fontes() if f.id == id_)


def _links(*urls: str) -> str:
    return "".join(f'<a href="{u}">x</a>' for u in urls)


def _nomes(alvos) -> list[str]:
    return [a.url.rsplit("/", 1)[-1] for a in alvos]


def test_nenhum_id_repetido_nem_igual_ao_de_outro_lote():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_id_comeca_pela_familia_que_ja_tem_licenca_e_revenda():
    for f in lote.fontes():
        assert licenca_da_fonte(f.id) != SEM_LICENCA_CONHECIDA, f.id
        assert revenda_da_fonte(f.id) is not None, f.id


def test_nada_da_ice_nem_do_portal_com_login():
    """O COT da ICE proíbe robô nos termos e o `data.ico.org` pede cadastro: nenhum alvo vai para lá."""
    for id_ in SEM_PAGINAS:
        for alvo in _fonte(id_).descobrir(Paginas({}), AGORA):
            assert "ice.com" not in alvo.url
            assert "data.ico.org" not in alvo.url


def test_faostat_comercio_e_pesado_e_usda_ja_estava_no_lote_eua():
    assert _fonte("faostat-comercio").pesada
    assert not _fonte("faostat-precos-ao-produtor").pesada
    assert "usda-psd-todas" not in {f.id for f in lote.fontes()}
    assert "usda-psd-todas" in {f.id for f in fontes.FONTES}


def test_icip_pega_os_ultimos_meses_e_o_que_falta_vira_sem_arquivo():
    alvos = _fonte("ico-icip-mensal").descobrir(Paginas({}), AGORA)
    assert len(alvos) == lote.MESES_RECENTES_DO_ICIP
    assert alvos[0].url.endswith("I-CIP_06.2026.pdf")
    assert alvos[-1].url.endswith("I-CIP_11.2026.pdf")
    assert all(a.obter is not None for a in alvos)


def test_icip_atravessa_a_virada_do_ano():
    alvos = _fonte("ico-icip-mensal").descobrir(
        Paginas({}), datetime(2026, 2, 5, tzinfo=UTC)
    )
    assert alvos[0].url.endswith("I-CIP_09.2025.pdf")
    assert alvos[-1].url.endswith("I-CIP_02.2026.pdf")


def test_conab_series_le_a_pagina_da_familia_e_a_de_cada_produto():
    familia = SERIES + "graos"
    paginas = {
        familia: _links(
            familia,
            familia + "/soja",
            familia + "/milho",
            familia + "/graos",
            familia + "/graos-por-unidades-da-federacao",
        )
        + f'<a href="http://www.facebook.com/sharer.php?u={familia}/graos">f</a>',
        familia + "/soja": _links(familia + "/soja/sojaseriehist.xls/view"),
        familia + "/milho": _links(familia + "/milho/milhoseriehist.xlsx"),
        familia + "/graos-por-unidades-da-federacao": _links(
            familia + "/graos-por-unidades-da-federacao/ufserie.xls/view"
        ),
    }
    alvos = _fonte("conab-series-graos").descobrir(Paginas(paginas), AGORA)
    assert [a.url for a in alvos] == [
        familia + "/soja/sojaseriehist.xls",
        familia + "/milho/milhoseriehist.xlsx",
        familia + "/graos-por-unidades-da-federacao/ufserie.xls",
    ]


def test_conab_series_sem_planilha_e_erro_com_o_nome_da_familia():
    familia = SERIES + "cana-de-acucar"
    paginas = {
        familia: _links(familia + "/agricola"),
        familia + "/agricola": "<html></html>",
    }
    with pytest.raises(ErroDeDescoberta, match="cana-de-acucar"):
        _fonte("conab-series-cana").descobrir(Paginas(paginas), AGORA)


def test_conab_boletins_so_das_duas_safras_mais_novas():
    def lev(n, safra, nome):
        return f"{BOLETINS}/{n}o-levantamento-safra-{safra}/{nome}"

    paginas = {
        f"{BOLETINS}?b_start:int=0": _links(
            lev(1, "2026-27", "apresentacao"),
            lev(12, "2024-25", "x"),
            lev(3, "2025-26", "y"),
        ),
        f"{BOLETINS}?b_start:int=30": "",
        f"{BOLETINS}?b_start:int=60": "",
        lev(1, "2026-27", "apresentacao"): _links(
            lev(1, "2026-27", "boletim-1.pdf"), lev(1, "2026-27", "dados.xlsx")
        ),
        lev(3, "2025-26", "y"): _links(lev(3, "2025-26", "boletim-3.pdf")),
    }
    alvos = _fonte("conab-boletins-graos").descobrir(Paginas(paginas), AGORA)
    assert sorted(_nomes(alvos)) == ["boletim-1.pdf", "boletim-3.pdf", "dados.xlsx"]


def test_cftc_tem_historico_e_um_zip_por_ano_ate_o_corrente():
    cit = _nomes(_fonte("cftc-cot-cit").descobrir(Paginas({}), AGORA))
    assert cit[:2] == ["dea_cit_txt_2006_2016.zip", "dea_cit_txt_2017.zip"]
    assert cit[-1] == "dea_cit_txt_2026.zip"
    legado = _nomes(_fonte("cftc-cot-legado").descobrir(Paginas({}), AGORA))
    assert legado[0] == "deacot1986_2016.zip" and legado[-1] == "deacot2026.zip"


def test_chirts_recentes_e_historico_nao_se_repetem():
    recentes = {
        a.url for a in _fonte("chirps-chirts-tmax-mensal").descobrir(Paginas({}), AGORA)
    }
    historico = [
        a.url
        for a in _fonte("chirps-chirts-tmax-historico").descobrir(Paginas({}), AGORA)
    ]
    assert not recentes & set(historico)
    assert historico[0].endswith("CHIRTSmax.1983.01.tif")
    assert any(u.endswith("CHIRTSmax.2026.10.tif") for u in recentes)
    assert len(recentes) + len(historico) == (2026 - 1983) * 12 + 10


def test_todo_o_chc_tem_pausa_entre_pedidos():
    for f in lote.fontes():
        if f.id.startswith("chirps-"):
            assert f.pausa_minima >= 3, f.id


def test_spei_leva_os_mais_novos_de_cada_janela_e_spi_todos():
    pasta = lote.SPEI_DO_CHC.format(janela=3)
    pagina = '<a href="../">p</a><a href="README.txt">r</a>' + _links(
        *(f"SPEI_C3_FLDAS_Global_03_2026{m:02d}.tif" for m in range(1, 10))
    )
    paginas = {pasta: pagina, lote.SPEI_DO_CHC.format(janela=12): pagina}
    alvos = _fonte("chirps-spei-fldas").descobrir(Paginas(paginas), AGORA)
    assert len(alvos) == 2 * lote.ARQUIVOS_RECENTES_DE_SECA
    assert alvos[2].url == pasta + "SPEI_C3_FLDAS_Global_03_202609.tif"
    nc = _links(*(f"SPI_{m:02d}.nc" for m in range(1, 13)))
    spi = {lote.SPI_DO_CHC.format(janela=j): nc for j in (3, 12)}
    assert len(_fonte("chirps-spi-chirps3").descobrir(Paginas(spi), AGORA)) == 24


def test_seca_sem_arquivo_e_erro():
    vazio = {lote.SPEI_DO_CHC.format(janela=3): '<a href="../">p</a>'}
    with pytest.raises(ErroDeDescoberta, match="CHC"):
        _fonte("chirps-spei-fldas").descobrir(Paginas(vazio), AGORA)


def test_inmet_normais_pega_todas_as_planilhas_da_pagina():
    base = "https://portal.inmet.gov.br/uploads/normais/"
    pagina = _links(
        base + "01-Média-1981-2010.xls", base + "02-Chuva.xlsx", "https://x.org/a.pdf"
    )
    paginas = {lote.PAGINA_DAS_NORMAIS_DO_INMET: pagina}
    alvos = _fonte("inmet-normais").descobrir(Paginas(paginas), AGORA)
    assert _nomes(alvos) == ["01-Média-1981-2010.xls", "02-Chuva.xlsx"]
    vazia = {lote.PAGINA_DAS_NORMAIS_DO_INMET: "<html/>"}
    with pytest.raises(ErroDeDescoberta):
        _fonte("inmet-normais").descobrir(Paginas(vazia), AGORA)


def test_mapbiomas_bioma_e_estado_usa_o_drive_e_nao_repete_o_de_municipio():
    alvo = _fonte("mapbiomas-bioma-e-estado").descobrir(Paginas({}), AGORA)[0]
    assert alvo.url == lote.MAPBIOMAS_BIOMA_E_ESTADO and alvo.obter is not None
    assert alvo.url != fontes.MAPBIOMAS_COBERTURA_MUNICIPAL
