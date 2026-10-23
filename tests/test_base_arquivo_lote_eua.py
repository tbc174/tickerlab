"""Lote EUA do arquivista (base/arquivo/lote_eua.py): como cada fonte acha os seus arquivos."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests

from base.arquivo import lote_eua, registro
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from base.arquivo.fontes import FONTES, POR_ID, TERMOS
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte

AGORA = datetime(2026, 10, 22, 14, tzinfo=UTC)
DUBLES = Path(__file__).parent / "arquivos" / "eua"


class Paginas:
    """Responde `ler` com páginas fixas; um valor `int` vira erro HTTP com esse código."""

    def __init__(self, paginas: dict[str, bytes | int]):
        self.paginas = paginas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        self.pedidos.append(url)
        pagina = self.paginas[url]
        if isinstance(pagina, int):
            resposta = requests.Response()
            resposta.status_code = pagina
            raise requests.HTTPError(response=resposta)
        return Resposta(url, pagina, {})


def _urls(alvos):
    return [a.url for a in alvos]


def _dubles(nome: str) -> bytes:
    return (DUBLES / nome).read_bytes()


# ---------------------------------------------------------------- catálogo
def test_ids_do_lote_sao_unicos_e_estao_no_catalogo_geral():
    ids = [f.id for f in lote_eua.fontes()]
    assert len(ids) == len(set(ids))
    assert set(ids) <= set(POR_ID)
    assert len([f for f in FONTES if f.id in ids]) == len(ids)


def test_grupos_do_lote_sao_conhecidos_e_a_historia_so_roda_pelo_id():
    grupos = {f.id: f.grupo for f in lote_eua.fontes()}
    assert set(grupos.values()) <= {"diaria", "semanal", "mensal", "carga-unica"}
    historicas = {i for i, g in grupos.items() if g == "carga-unica"}
    assert historicas == {i for i in grupos if i.endswith("-historico")}


@pytest.mark.parametrize("fonte", [f.id for f in lote_eua.fontes()])
def test_toda_fonte_do_lote_tem_licenca_marca_e_data_dos_termos(fonte):
    assert not licenca_da_fonte(fonte).startswith("Desconhecida")
    familia = fonte.split("-", 1)[0]
    assert registro.TERMOS_LIDOS_EM[familia] >= date(2026, 10, 18)
    # só a SEC escreve o que publica (arquivos das empresas): uso interno; o resto é obra da agência
    esperada = Marca.USO_INTERNO if familia == "sec" else Marca.VENDAVEL
    assert marca_da_fonte(fonte) == esperada


def test_paginas_de_termos_das_agencias_sao_vigiadas():
    assert set(lote_eua.termos()) <= set(TERMOS)
    assert set(lote_eua.termos()) <= {f.id for f in FONTES if f.vigia}


def test_fontes_grandes_conferem_a_assinatura_antes_de_baixar():
    pesadas = {f.id for f in lote_eua.fontes() if f.pesada}
    assert {"usda-psd-todas", "sec-edgar-13f", "bls-cu", "eia-wpsr"} <= pesadas
    # o Data Download Program do Fed gera o zip na hora: sem ETag, a assinatura nunca repete
    assert not any(i.startswith("fed-ddp") for i in pesadas)


# --------------------------------------------------------------- Fiscal Data
def test_fiscal_data_pega_todas_as_paginas_que_a_primeira_anuncia():
    caminho = "v2/accounting/od/debt_to_penny"
    primeira = lote_eua.endereco_do_fiscal_data(caminho, 1)
    cliente = Paginas({primeira: json.dumps({"meta": {"total-pages": 3}}).encode()})
    alvos = lote_eua.descobrir_fiscal_data(caminho)(cliente, AGORA)
    assert _urls(alvos) == [
        lote_eua.endereco_do_fiscal_data(caminho, n) for n in (1, 2, 3)
    ]
    assert {a.extensao for a in alvos} == {".json"}
    assert "page%5Bsize%5D=10000" in alvos[0].url and "sort=record_date" in alvos[0].url


def test_fiscal_data_sem_contagem_de_paginas_e_falha():
    caminho = "v1/accounting/od/rates_of_exchange"
    primeira = lote_eua.endereco_do_fiscal_data(caminho, 1)
    cliente = Paginas({primeira: json.dumps({"meta": {}}).encode()})
    with pytest.raises(ErroDeDescoberta):
        lote_eua.descobrir_fiscal_data(caminho)(cliente, AGORA)


# ---------------------------------------------------------- curvas do Tesouro
def test_curvas_diarias_ficam_com_o_ano_corrente_e_o_anterior():
    alvos = lote_eua.descobrir_curvas_recentes(None, AGORA)
    assert len(alvos) == 2 * len(lote_eua.PRIMEIRO_ANO_DA_CURVA)
    assert {
        a.url.split("/")[-2]
        for a in alvos
        if "type=daily_treasury_yield_curve" in a.url
    } == {
        "2025",
        "2026",
    }


def test_curvas_historicas_vao_do_primeiro_ano_ate_antes_dos_recentes():
    alvos = lote_eua.descobrir_curvas_historicas(None, AGORA)
    anos = [
        int(a.url.split("/")[-2])
        for a in alvos
        if "type=daily_treasury_yield_curve" in a.url
    ]
    assert anos == list(range(1990, 2025))
    assert not any("/2025/" in a.url or "/2026/" in a.url for a in alvos)


# ------------------------------------------------------------------------ BLS
def test_pasta_da_bls_le_nome_caminho_e_tamanho_com_href_em_maiusculas():
    arquivos = lote_eua.arquivos_da_pasta_da_bls(_dubles("bls_pasta_cu.html"))
    assert arquivos["cu.data.0.Current"] == (
        "/pub/time.series/cu/cu.data.0.Current",
        4001322,
    )
    assert arquivos["cu.item"][1] == 9211
    assert "time.series" not in arquivos  # o link para a pasta de cima não é arquivo


def test_bls_pega_metadados_pequenos_e_so_os_dados_da_lista():
    cliente = Paginas(
        {lote_eua.PASTA_DA_BLS.format(codigo="cu"): _dubles("bls_pasta_cu.html")}
    )
    alvos = lote_eua.descobrir_bls("cu")(cliente, AGORA)
    assert _urls(alvos) == [
        lote_eua.RAIZ_DA_BLS + "/pub/time.series/cu/" + nome
        for nome in (
            "cu.area",
            "cu.item",
            "cu.data.0.Current",
            "cu.data.1.AllItems",
        )
    ]  # cu.aspect (31 MB) e cu.data.2.Summaries (fora da lista) ficam de fora


def test_bls_com_arquivo_de_dados_renomeado_e_falha():
    pasta = _dubles("bls_pasta_cu.html").replace(
        b"cu.data.1.AllItems", b"cu.data.1.Tudo"
    )
    cliente = Paginas({lote_eua.PASTA_DA_BLS.format(codigo="cu"): pasta})
    with pytest.raises(ErroDeDescoberta, match="cu.data.1.AllItems"):
        lote_eua.descobrir_bls("cu")(cliente, AGORA)


def test_toda_pasta_da_bls_tem_arquivos_de_dados_escolhidos():
    assert all(lote_eua.DADOS_DA_BLS[codigo] for codigo in lote_eua.DADOS_DA_BLS)
    assert {f"bls-{c}" for c in lote_eua.DADOS_DA_BLS} <= set(POR_ID)


# -------------------------------------------------------------------- EIA e TIC
def test_eia_pega_as_tabelas_1_a_9_do_relatorio_semanal():
    alvos = POR_ID["eia-wpsr"].descobrir(None, AGORA)
    assert _urls(alvos) == [
        f"https://ir.eia.gov/wpsr/psw{n:02d}.xls" for n in range(1, 10)
    ]


def test_tic_pega_os_arquivos_de_cada_familia():
    alvos = POR_ID["tic-posicoes-de-longo-prazo"].descobrir(None, AGORA)
    assert _urls(alvos)[0] == "https://ticdata.treasury.gov/Publish/slt_table1.txt"
    assert len(alvos) == 8
    assert _urls(POR_ID["tic-detentores-estrangeiros"].descobrir(None, AGORA)) == [
        "https://ticdata.treasury.gov/Publish/mfh.txt"
    ]


# ------------------------------------------------------------------------ OFR
def test_ofr_monitores_usam_um_endereco_por_conjunto_e_o_catalogo_de_series():
    funding = _urls(POR_ID["ofr-monitor-de-funding"].descobrir(None, AGORA))
    assert funding == [
        f"https://data.financialresearch.gov/v1/series/dataset?dataset={c}"
        for c in lote_eua.CONJUNTOS_DO_STFM
    ]
    hedge = _urls(POR_ID["ofr-monitor-de-hedge-funds"].descobrir(None, AGORA))
    assert (
        hedge[-1] == lote_eua.OFR_CATALOGO
        and len(hedge) == len(lote_eua.CONJUNTOS_DO_HFM) + 1
    )


# --------------------------------------------------------------------- NY Fed
def test_nyfed_diario_pega_o_ultimo_valor_e_os_dois_anos_recentes():
    urls = _urls(lote_eua.descobrir_juros_do_nyfed(None, AGORA))
    assert urls[0].endswith("rates/all/latest.json")
    assert [u.split("startDate=")[1][:4] for u in urls[1:]] == ["2025", "2026"]


def test_nyfed_historico_vai_de_2018_ate_antes_dos_recentes():
    urls = _urls(lote_eua.descobrir_juros_historicos_do_nyfed(None, AGORA))
    assert [u.split("startDate=")[1][:4] for u in urls] == [
        str(a) for a in range(2018, 2025)
    ]


# ------------------------------------------------------------------------ SEC
def test_indice_diario_lista_so_os_dias_recentes_que_o_edgar_ja_publicou():
    q4 = lote_eua.pasta_do_trimestre_da_sec(2026, 4, "daily-index")
    q3 = lote_eua.pasta_do_trimestre_da_sec(2026, 3, "daily-index")
    cliente = Paginas(
        {q4 + "index.json": _dubles("sec_indice_diario.json"), q3 + "index.json": 404}
    )
    alvos = lote_eua.descobrir_indice_diario_da_sec(cliente, AGORA)
    assert _urls(alvos) == [q4 + "master.20261015.idx", q4 + "master.20261016.idx"]
    assert {a.extensao for a in alvos} == {".idx"}


def test_indice_diario_no_primeiro_dia_do_trimestre_ignora_a_pasta_que_ainda_nao_existe():
    q4 = lote_eua.pasta_do_trimestre_da_sec(2026, 4, "daily-index")
    q3 = lote_eua.pasta_do_trimestre_da_sec(2026, 3, "daily-index")
    ultimos_dias = json.dumps(
        {
            "directory": {
                "item": [
                    {"name": "master.20260929.idx"},
                    {"name": "master.20260930.idx"},
                ]
            }
        }
    ).encode()
    cliente = Paginas({q3 + "index.json": ultimos_dias, q4 + "index.json": 404})
    alvos = lote_eua.descobrir_indice_diario_da_sec(
        cliente, datetime(2026, 10, 1, 14, tzinfo=UTC)
    )
    assert _urls(alvos) == [q3 + "master.20260929.idx", q3 + "master.20260930.idx"]


def test_indice_diario_com_bloqueio_da_sec_sobe_em_vez_de_virar_pasta_vazia():
    q3 = lote_eua.pasta_do_trimestre_da_sec(2026, 3, "daily-index")
    q4 = lote_eua.pasta_do_trimestre_da_sec(2026, 4, "daily-index")
    cliente = Paginas({q3 + "index.json": 403, q4 + "index.json": 403})
    with pytest.raises(requests.HTTPError):
        lote_eua.descobrir_indice_diario_da_sec(cliente, AGORA)


def test_indice_diario_sem_nenhum_dia_recente_e_falha():
    q4 = lote_eua.pasta_do_trimestre_da_sec(2026, 4, "daily-index")
    q3 = lote_eua.pasta_do_trimestre_da_sec(2026, 3, "daily-index")
    vazio = json.dumps({"directory": {"item": []}}).encode()
    cliente = Paginas({q3 + "index.json": vazio, q4 + "index.json": vazio})
    with pytest.raises(ErroDeDescoberta):
        lote_eua.descobrir_indice_diario_da_sec(cliente, AGORA)


def test_indice_trimestral_cobre_o_trimestre_anterior_e_o_atual():
    urls = _urls(lote_eua.descobrir_indice_trimestral_da_sec(None, AGORA))
    assert urls == [
        "https://www.sec.gov/Archives/edgar/full-index/2026/QTR3/master.idx",
        "https://www.sec.gov/Archives/edgar/full-index/2026/QTR4/master.idx",
    ]


def test_trimestre_de_janeiro_olha_o_quarto_trimestre_do_ano_anterior():
    anteriores = lote_eua._trimestres_recentes(datetime(2027, 1, 5, tzinfo=UTC))
    assert anteriores == [(2026, 4), (2027, 1)]


def test_conjuntos_da_sec_tem_os_dois_mais_novos_na_coleta_e_o_resto_na_carga_unica():
    pagina = {
        lote_eua.SEC + lote_eua.CONJUNTOS_DA_SEC["sec-edgar-form-d"]: _dubles(
            "sec_pagina_form_d.html"
        )
    }
    cliente = Paginas(pagina)
    recentes = POR_ID["sec-edgar-form-d"].descobrir(cliente, AGORA)
    antigos = POR_ID["sec-edgar-form-d-historico"].descobrir(cliente, AGORA)
    base = "https://www.sec.gov/files/structureddata/data/form-d-data-sets/"
    assert _urls(recentes) == [base + "2026q3_d.zip", base + "2026q2_d.zip"]
    assert _urls(antigos) == [
        base + "2026q1_d.zip",
        base + "2025q4_d.zip",
    ]  # sem repetir link


def test_pagina_da_sec_sem_zip_e_falha():
    pagina = {
        lote_eua.SEC + lote_eua.CONJUNTOS_DA_SEC["sec-edgar-13f"]: b"<html></html>"
    }
    with pytest.raises(ErroDeDescoberta):
        POR_ID["sec-edgar-13f"].descobrir(Paginas(pagina), AGORA)


def test_busca_de_texto_cobre_cada_emissora_nos_dois_meses_recentes():
    alvos = lote_eua.descobrir_busca_de_texto_da_sec(None, AGORA)
    assert len(alvos) == 2 * len(lote_eua.EMISSORAS_BRASILEIRAS_NA_SEC)
    primeira = alvos[0].url
    assert primeira.startswith("https://efts.sec.gov/LATEST/search-index?")
    assert "startdt=2026-09-01" in primeira and "enddt=2026-09-30" in primeira
    assert "forms=20-F%2C6-K" in primeira


def test_meses_da_busca_viram_o_ano_em_janeiro():
    meses = lote_eua._meses_da_busca(datetime(2027, 1, 20, tzinfo=UTC))
    assert meses == [
        (date(2026, 12, 1), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 31)),
    ]


def test_agente_da_sec_nao_leva_email_pessoal():
    """Regra do repositório (público): nada de e-mail no código do lote."""
    fonte = Path(lote_eua.__file__).read_text(encoding="utf-8")
    assert "@" not in fonte
