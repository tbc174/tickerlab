"""Lote commodities oficiais (base/arquivo/lote_commodities_oficiais.py): DG AGRI e, nos PRs seguintes, as outras
fontes oficiais da linha 396 da fila. Nada vai à internet: a descoberta só monta endereços e não pede nada."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from base.arquivo import coleta, fontes, lote_organismos
from base.arquivo import lote_commodities_oficiais as lote
from base.arquivo.coleta import Fonte
from base.arquivo.lote_organismos import (
    FILTRO_DE_PAIS_DO_EUROSTAT,
    PAISES_DO_EUROSTAT,
)
from src.banco.coletas import SEM_LICENCA_CONHECIDA, licenca_da_fonte, revenda_da_fonte

AGORA = datetime(2026, 11, 5, 22, tzinfo=UTC)
PORTAL = "https://ec.europa.eu/agrifood/api"


def _fonte(id_: str) -> Fonte:
    return next(f for f in lote.fontes() if f.id == id_)


def _alvos(id_: str):
    # a descoberta do DG AGRI só monta endereços: o cliente nunca é chamado
    return _fonte(id_).descobrir(None, AGORA)  # type: ignore[arg-type]


def test_nenhum_id_repetido_e_todos_estao_no_registro_do_arquivista():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_do_lote_tem_licenca_e_revenda_conhecidas():
    for f in lote.fontes():
        assert licenca_da_fonte(f.id) != SEM_LICENCA_CONHECIDA, f.id
        assert revenda_da_fonte(f.id) is not None, f.id


@pytest.mark.parametrize(
    ("produto", "primeiro_ano"), [("cereal", 2015), ("oilseeds", 2021), ("dairy", 1991)]
)
def test_dgagri_vira_uma_janela_por_ano_do_primeiro_dado_ate_o_ano_da_coleta(
    produto, primeiro_ano
):
    urls = [a.url for a in _alvos(f"dgagri-{produto}")]
    assert urls[0] == (
        f"{PORTAL}/{produto}/prices?beginDate=01/01/{primeiro_ano}"
        f"&endDate=10/01/{primeiro_ano + 1}"
    )
    assert urls[-1].endswith(
        f"beginDate=01/01/{AGORA.year}&endDate=10/01/{AGORA.year + 1}"
    )
    assert len(urls) == AGORA.year - primeiro_ano + 1
    assert len(set(urls)) == len(urls)


def test_dgagri_janela_vai_ate_10_01_porque_a_semana_da_virada_so_cabe_inteira_ali():
    """O portal só devolve a semana que cabe inteira na janela (conferido ao vivo em 05/11/2026): com
    `endDate=31/12`, a semana de 29/12 a 04/01 sumia de todas as janelas."""
    urls = [a.url for a in _alvos("dgagri-dairy")]
    assert all(
        f"beginDate=01/01/{ano}&endDate=10/01/{ano + 1}" in url
        for ano, url in zip(range(1991, AGORA.year + 1), urls, strict=True)
    )


def _linha(url: str, baixado_em: datetime):
    return SimpleNamespace(url=url, baixado_em=baixado_em)


def test_dgagri_ano_fechado_so_vale_se_baixado_depois_de_janeiro_do_ano_seguinte():
    url = lote.endereco_do_dg_agri("cereal", 2024)
    valida = lote.janela_fechada_ja_guardada
    assert valida(_linha(url, datetime(2025, 2, 1, tzinfo=UTC)))
    assert valida(_linha(url, datetime(2026, 3, 1)))  # noqa: DTZ001  # SQLite dos testes: sem fuso
    # baixada durante o ano ou em janeiro: falta a última semana e as correções
    assert not valida(_linha(url, datetime(2024, 11, 5, tzinfo=UTC)))
    assert not valida(_linha(url, datetime(2025, 1, 31, tzinfo=UTC)))
    # o ano corrente nunca vale, e o açúcar (sem janela) é lido toda vez
    corrente = lote.endereco_do_dg_agri("cereal", AGORA.year)
    assert not valida(_linha(corrente, AGORA))
    assert not valida(_linha(lote.endereco_do_dg_agri("sugar"), AGORA))


class _Portal:
    """Cliente que só conta o que foi baixado (a descoberta do DG AGRI nunca chama `ler`)."""

    def __init__(self):
        self.baixados: list[str] = []

    def cabecalhos(self, url):
        return {"Content-Type": "application/json"}

    def baixar(self, url, destino: Path):
        self.baixados.append(url)
        destino.write_bytes(b'[{"price": "EUR 229,29"}]')
        return {"Content-Type": "application/json"}


def test_dgagri_na_semana_seguinte_so_baixa_o_ano_corrente(banco, tmp_path):
    """Regressão do P1 da revisão cruzada: a janela fechada, já guardada depois do fechamento, não é baixada de
    novo (a `versao` do `Alvo` nunca batia: o arquivista só grava os cabeçalhos como versão)."""
    fonte = _fonte("dgagri-cereal")
    portal = _Portal()
    depois_de_janeiro = datetime(2026, 11, 5, 22, tzinfo=UTC)
    coleta.arquivar(fonte, portal, depois_de_janeiro, tmp_path / "t", pausa=0)
    # a 1ª rodada baixa tudo (nada estava guardado); na 2ª, os anos fechados já valem
    primeira = len(portal.baixados)
    assert primeira == AGORA.year - 2015 + 1
    coleta.arquivar(
        fonte, portal, depois_de_janeiro + timedelta(days=7), tmp_path / "t", pausa=0
    )
    assert portal.baixados[primeira:] == [
        lote.endereco_do_dg_agri("cereal", AGORA.year)
    ]


def test_dgagri_ano_sem_dado_e_nao_encontrado_e_nunca_falha():
    """O portal responde 404 para o ano em que o produto ainda não existe: é `SemArquivo`, não falha."""
    for id_ in ("dgagri-cereal", "dgagri-oilseeds", "dgagri-dairy"):
        assert all(a.obter is not None for a in _alvos(id_)), id_


def test_dgagri_acucar_e_um_retrato_so_porque_a_api_ignora_as_datas():
    alvos = _alvos("dgagri-sugar")
    assert [a.url for a in alvos] == [f"{PORTAL}/sugar/prices"]


def test_dgagri_nao_leva_carne_porque_o_endereco_dela_responde_404():
    assert "dgagri-meat" not in {f.id for f in lote.fontes()}
    assert "dgagri-beef" not in {f.id for f in lote.fontes()}


def test_dgagri_e_json_leve_semanal_e_com_pausa_entre_pedidos():
    for f in (f for f in lote.fontes() if f.id.startswith("dgagri-")):
        assert f.tipo == "json", f.id
        assert f.grupo == "semanal", f.id
        assert not f.pesada, f.id
        assert f.pausa_minima >= 1.0, f.id


def test_dgagri_nao_filtra_por_pais_porque_a_licenca_e_da_comissao_para_todos_os_estados():
    for f in (f for f in lote.fontes() if f.id.startswith("dgagri-")):
        for a in f.descobrir(None, AGORA):  # type: ignore[arg-type]
            assert "memberStateCodes" not in a.url


# ---- Bank of Canada BCPI (Valet) -------------------------------------------------------------
VALET = "https://www.bankofcanada.ca/valet"
GRUPOS_DO_BCPI = {
    "boc-bcpi-semanal": "BCPI_WEEKLY",
    "boc-bcpi-mensal": "BCPI_MONTHLY",
    "boc-bcpi-anual": "BCPI_ANNUAL",
    "boc-bcpi-pesos": "BCPI_WEIGHTS",
}


@pytest.mark.parametrize(("id_", "grupo"), GRUPOS_DO_BCPI.items())
def test_bcpi_guarda_as_observacoes_e_a_descricao_das_series_de_cada_grupo(id_, grupo):
    assert [a.url for a in _alvos(id_)] == [
        f"{VALET}/observations/group/{grupo}/json",
        f"{VALET}/groups/{grupo}/json",
    ]


def test_bcpi_tem_os_quatro_grupos_e_nenhum_a_mais():
    assert {f.id for f in lote.fontes() if f.id.startswith("boc-")} == set(
        GRUPOS_DO_BCPI
    )


def test_bcpi_respeita_o_limite_de_frequencia_da_valet():
    """Os termos do Banco proíbem burlar o limite de pedidos da Valet: poucos pedidos e com pausa."""
    for id_ in GRUPOS_DO_BCPI:
        fonte = _fonte(id_)
        assert fonte.pausa_minima >= 2.0, id_
        assert len(_alvos(id_)) == 2, id_
        assert not fonte.pesada, id_
        assert fonte.tipo == "json", id_


def test_bcpi_semanal_roda_toda_semana_e_o_resto_uma_vez_por_mes():
    assert _fonte("boc-bcpi-semanal").grupo == "semanal"
    for id_ in ("boc-bcpi-mensal", "boc-bcpi-anual", "boc-bcpi-pesos"):
        assert _fonte(id_).grupo == "mensal", id_


def test_bcpi_vigia_os_termos_do_banco():
    assert lote.termos()["termos-boc"] == "https://www.bankofcanada.ca/terms/"


# ---- Eurostat: preços agrícolas e de energia (família `eurostat`, só a UE) -----------------------
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
CONJUNTOS_DO_EUROSTAT = {
    "eurostat-precos-agricolas": "apri_ap_crpouta",
    "eurostat-preco-do-gas": "nrg_pc_202",
}


@pytest.mark.parametrize(("id_", "conjunto"), CONJUNTOS_DO_EUROSTAT.items())
def test_eurostat_guarda_so_os_paises_da_ue_que_a_licenca_cobre(id_, conjunto):
    (alvo,) = _alvos(id_)
    assert alvo.url.startswith(f"{EUROSTAT}/{conjunto}?")
    paises = set(re.findall(r"geo=([A-Z0-9_]+)", alvo.url))
    assert paises == set(PAISES_DO_EUROSTAT)
    assert alvo.url.endswith("&lang=EN")


def test_eurostat_usa_o_mesmo_filtro_de_pais_das_outras_series_da_familia():
    """Um lugar só para a lista de países: quem muda a lista em lote_organismos muda aqui também."""
    for id_ in CONJUNTOS_DO_EUROSTAT:
        assert FILTRO_DE_PAIS_DO_EUROSTAT in _alvos(id_)[0].url


def test_eurostat_e_json_leve_com_pausa_e_sem_repetir_id_de_outro_lote():
    organismos = {f.id for f in lote_organismos.fontes()}
    for id_ in CONJUNTOS_DO_EUROSTAT:
        fonte = _fonte(id_)
        assert id_ not in organismos
        assert fonte.tipo == "json"
        assert not fonte.pesada
        assert fonte.pausa_minima >= 2.0
        assert fonte.grupo == "mensal"  # os dois conjuntos saem por ano ou semestre


# ---- SSB (Statistics Norway): exportação semanal de salmão, tabela 03024 -----------------------
SSB = "https://data.ssb.no/api/pxwebapi/v2/tables/03024/data"


def test_ssb_pede_a_tabela_inteira_de_salmao_numa_resposta_so():
    """O endereço sem `valueCodes` devolve só a semana mais recente: o histórico (2000 até hoje, 80 KB) pede
    todos os valores de cada dimensão. É GET porque o cliente do arquivista não manda corpo."""
    (alvo,) = _alvos("ssb-salmao-semanal")
    assert alvo.url.startswith(f"{SSB}?lang=en&outputFormat=json-stat2")
    for dimensao in ("VareGrupper2", "ContentsCode", "Tid"):
        assert f"valueCodes%5B{dimensao}%5D=*" in alvo.url


def test_ssb_e_json_leve_semanal_e_com_pausa():
    fonte = _fonte("ssb-salmao-semanal")
    assert fonte.tipo == "json"
    assert fonte.grupo == "semanal"
    assert not fonte.pesada
    assert fonte.pausa_minima >= 2.0


def test_ssb_vigia_a_licenca_do_instituto():
    assert lote.termos()["termos-ssb"] == "https://www.ssb.no/en/diverse/lisens"


# ---- Weekly Oil Bulletin (DG ENER): XLSX descobertos pela página do boletim ----------------------
PAGINA_DO_WOB = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
DOWNLOAD_DO_WOB = "https://energy.ec.europa.eu/document/download"
# trecho real da página (conferida em 06/11/2026): o endereço do preço semanal muda a cada semana
HTML_DO_WOB = b"""
<a href="/document/download/264c2d0f-f161-4ea3-a777-78faae59bea0_en?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices%20with%20Taxes%20-%202026-09-21.xlsx">com</a>
<a href="/document/download/78311f92-68f8-4b82-b5cf-1293beeaae77_en?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices%20without%20taxes%20-%202024-02-19.xlsx">sem</a>
<a href="/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx">historico</a>
<a href="/document/download/ccdc6e96-6792-40cb-b0b4-b6609f1e30d0_en?filename=Oil_Bulletin_Duties_and_taxes.xlsx">impostos</a>
<a href="/document/download/0241d6bb-e34f-46bb-a75e-5a99a8b3db26_en?filename=WOB%20-%20map%20-%20diesel%20-%202024-04-22.pdf">mapa</a>
<a href="/document/download/a99a3695-dfa9-49bf-98b4-192a97f19b7b_en?filename=2018_austria_notes.pdf">notas</a>
<a href="/document/download/78311f92-68f8-4b82-b5cf-1293beeaae77_en?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices%20without%20taxes%20-%202024-02-19.xlsx">repetido</a>
"""


class _ClienteDaPaginaDoWob:
    def __init__(self, html: bytes = HTML_DO_WOB):
        self.html = html
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        self.pedidos.append(url)
        return SimpleNamespace(url=url, conteudo=self.html, cabecalhos={})


def _alvos_do_wob(html: bytes = HTML_DO_WOB):
    cliente = _ClienteDaPaginaDoWob(html)
    return cliente, _fonte("dgener-oil-bulletin").descobrir(cliente, AGORA)  # type: ignore[arg-type]


def test_wob_pega_so_as_planilhas_da_pagina_sem_repetir_e_com_endereco_inteiro():
    cliente, alvos = _alvos_do_wob()
    assert cliente.pedidos == [
        PAGINA_DO_WOB
    ]  # um pedido só, à página que a Comissão publica
    assert [a.url for a in alvos] == [
        f"{DOWNLOAD_DO_WOB}/264c2d0f-f161-4ea3-a777-78faae59bea0_en",
        f"{DOWNLOAD_DO_WOB}/78311f92-68f8-4b82-b5cf-1293beeaae77_en",
        f"{DOWNLOAD_DO_WOB}/906e60ca-8b6a-44e7-8589-652854d2fd3f_en",
        f"{DOWNLOAD_DO_WOB}/ccdc6e96-6792-40cb-b0b4-b6609f1e30d0_en",
    ]
    assert {a.extensao for a in alvos} == {".xlsx"}


def test_wob_nao_adivinha_endereco_quando_a_pagina_nao_traz_planilha():
    """O endereço do histórico adivinhado redireciona para a home: sem link na página, não há alvo."""
    _, alvos = _alvos_do_wob(b"<html><a href='/outra'>nada</a></html>")
    assert alvos == []


def test_wob_e_semanal_leve_e_com_pausa():
    fonte = _fonte("dgener-oil-bulletin")
    assert fonte.grupo == "semanal"
    assert (
        fonte.tipo == "zip"
    )  # XLSX é um zip: barra a página HTML que a Comissão devolve no lugar do arquivo
    assert not fonte.pesada
    assert (
        fonte.pausa_minima >= 2.0
    )  # o histórico tem 4,5 MB; sem pressa com a Comissão


def test_wob_vigia_o_aviso_legal_da_comissao():
    assert (
        lote.termos()["termos-dgener"] == "https://commission.europa.eu/legal-notice_en"
    )
