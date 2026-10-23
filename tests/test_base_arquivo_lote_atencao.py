"""Lote atenção e texto (base/arquivo/lote_atencao.py): acessos da Wikimedia, GDELT GKG, Querido Diário,
Crossref, OpenAlex e RSS das agências. Nada vai à internet: as respostas são dublês de
`tests/arquivos/atencao/`. O que não pode faltar aqui é a LGPD: pessoa e texto de terceiros nunca
chegam ao acervo."""

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from base.arquivo import destinos, fontes
from base.arquivo import lote_atencao as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta, SemArquivo
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)

AGORA = datetime(2026, 10, 23, 4, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "atencao"
FAMILIAS_NOVAS = {
    "wiki",
    "gdelt",
    "querido",
    "openalex",
    "crossref",
    "ebc",
    "senado",
    "camara",
}
PESSOAS_DO_DUBLE = ("Maria Souza Pessoa", "João Dono Silva", "Carlos Pessoa Terceiro")


class Cliente:
    """Um cliente de mentira: `ler` por endereço; `baixar` grava os bytes de `arquivos`."""

    def __init__(self, paginas=None, arquivos=None, erro_404=()):
        self.paginas = paginas or {}
        self.arquivos = arquivos or {}
        self.erro_404 = set(erro_404)
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        return Resposta(url, self.paginas[url], {})

    def baixar(self, url, destino: Path):
        self.pedidos.append(url)
        if url in self.erro_404:
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404", response=resposta)
        destino.write_bytes(self.arquivos[url])
        return {"ETag": '"x"'}


def _fixture(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _cliente_com_empresas() -> Cliente:
    url = lote.endereco_do_wikidata(lote.consulta_das_empresas_da_b3())
    return Cliente(paginas={url: _fixture("wikidata_empresas_duble.json")})


def _por_id():
    return {f.id: f for f in lote.fontes()}


def _csv(caminho: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(caminho.read_text(encoding="utf-8"))))


def _obter_de(alvo, cliente, tmp_path) -> Path:
    destino = tmp_path / "guardado"
    alvo.obter(cliente, destino)
    assert not list(tmp_path.glob("*.bruto")), "o arquivo bruto precisa sumir"
    return destino


# ---- o lote como um todo ---------------------------------------------------------------------
def test_ids_sem_duplicata_no_lote_e_no_catalogo():
    ids = [f.id for f in lote.fontes()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_do_lote_tem_licenca_marca_data_da_leitura_e_destino():
    for fonte in lote.fontes():
        familia = fonte.id.split("-", 1)[0]
        assert licenca_da_fonte(fonte.id) != SEM_LICENCA_CONHECIDA, fonte.id
        assert len(licenca_da_fonte(fonte.id)) <= 80, fonte.id
        assert TERMOS_LIDOS_EM[familia].year == 2026, fonte.id
        assert fonte.grupo in fontes.GRUPOS, fonte.id
        assert fonte.id in destinos.DESTINOS, fonte.id
        assert fonte.pausa_minima > 0, fonte.id


def test_as_familias_do_lote():
    assert {f.id.split("-", 1)[0] for f in lote.fontes()} == FAMILIAS_NOVAS


def test_marcas_contagem_cc0_e_cc_by_sao_vendaveis_e_indice_de_rss_fica_a_confirmar():
    vendaveis = {
        "wiki-pageviews-empresas",
        "gdelt-gkg",
        "querido-diario-empresas",
        "openalex-afiliacoes",
        "crossref-afiliacoes",
    }
    for fonte in lote.fontes():
        esperada = Marca.VENDAVEL if fonte.id in vendaveis else Marca.A_CONFIRMAR
        assert marca_da_fonte(fonte.id) == esperada, fonte.id


def test_as_marcas_antigas_da_cripto_nao_mudaram():
    # `wiki-acessos` e `gdelt-cripto` seguem com a marca de antes (a lista de usos sem cobrança depende)
    assert marca_da_fonte("wiki-acessos") == Marca.USO_INTERNO
    assert marca_da_fonte("gdelt-cripto") == Marca.A_CONFIRMAR


def test_o_agente_com_contato_e_a_pausa_do_querido_diario():
    assert _por_id()["querido-diario-empresas"].pausa_minima >= 5


# ---- a lista de empresas ---------------------------------------------------------------------
def test_a_consulta_da_lista_nao_traz_gente_e_tem_ordem_fixa():
    consulta = lote.consulta_das_empresas_da_b3()
    assert "FILTER NOT EXISTS { ?item wdt:P31 wd:Q5 }" in consulta
    assert f"wd:{lote.ITEM_B3}" in consulta and "pt.wikipedia.org" in consulta
    assert "ORDER BY ?item" in consulta


def test_titulo_repetido_conta_uma_vez_e_sem_nome_vale_o_titulo():
    empresas = lote.empresas_do_wikidata(_fixture("wikidata_empresas_duble.json"))
    assert [e.titulo for e in empresas] == [
        "Petrobras",
        "Magazine Luiza",
        "Gol Linhas Aéreas",
    ]
    assert empresas[0].nome == "Petróleo Brasileiro S.A."
    assert empresas[2].nome == "Gol Linhas Aéreas"


def test_lista_vazia_ou_fora_do_formato_e_falha_nunca_nada_novo():
    with pytest.raises(ErroDeDescoberta):
        lote.empresas_do_wikidata(b'{"results": {"bindings": []}}')
    with pytest.raises(ErroDeDescoberta):
        lote.empresas_do_wikidata(b"<html>")


def test_a_lista_e_pedida_uma_vez_para_as_cinco_descobertas():
    cliente = _cliente_com_empresas()
    for fonte in lote.fontes()[:5]:
        fonte.descobrir(cliente, AGORA)
    assert len(cliente.pedidos) == 1


# ---- Wikimedia -------------------------------------------------------------------------------
def test_acessos_um_pedido_por_empresa_no_mes_que_fechou():
    (alvos) = _por_id()["wiki-pageviews-empresas"].descobrir(
        _cliente_com_empresas(), AGORA
    )
    assert [a.url for a in alvos] == [
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/pt.wikipedia/"
        f"all-access/user/{artigo}/daily/20260901/20260930"
        for artigo in ("Petrobras", "Magazine_Luiza", "Gol_Linhas_A%C3%A9reas")
    ]


def test_mes_anterior_em_janeiro_e_o_dezembro_do_ano_passado():
    inicio, fim = lote.mes_anterior(datetime(2027, 1, 5, tzinfo=UTC))
    assert (inicio.isoformat(), fim.isoformat()) == ("2026-12-01", "2026-12-31")


def test_artigo_sem_acesso_no_mes_e_sem_arquivo_nao_falha(tmp_path):
    (alvo, *_) = _por_id()["wiki-pageviews-empresas"].descobrir(
        _cliente_com_empresas(), AGORA
    )
    with pytest.raises(SemArquivo):
        alvo.obter(Cliente(erro_404={alvo.url}), tmp_path / "x")


# ---- GDELT GKG: LGPD -------------------------------------------------------------------------
def test_o_gkg_de_ontem_tem_96_arquivos_de_15_minutos():
    alvos = _por_id()["gdelt-gkg"].descobrir(_cliente_com_empresas(), AGORA)
    assert len(alvos) == 96
    assert (
        alvos[0].url
        == "https://data.gdeltproject.org/gdeltv2/20261022000000.gkg.csv.zip"
    )
    assert alvos[1].url.endswith("20261022001500.gkg.csv.zip")
    assert alvos[-1].url.endswith("20261022234500.gkg.csv.zip")
    assert len({a.url for a in alvos}) == 96
    assert _por_id()["gdelt-gkg"].pesada


def test_gkg_guarda_so_dia_empresa_tema_e_tom_e_nunca_pessoa(tmp_path):
    cliente = _cliente_com_empresas()
    (alvo, *_) = _por_id()["gdelt-gkg"].descobrir(cliente, AGORA)
    cliente.arquivos[alvo.url] = _fixture("gkg_duble.csv.zip")
    destino = _obter_de(alvo, cliente, tmp_path)
    texto = destino.read_text(encoding="utf-8")
    for pessoa in PESSOAS_DO_DUBLE:
        assert pessoa not in texto
    for resto in (
        "exemplo.com",
        "noticia-secreta",
        "PAGE_LINKS",
        "Banco Central",
        "Universidade",
    ):
        assert resto not in texto
    assert _csv(destino) == [
        ["data", "empresa", "temas", "tom", "positivo", "negativo"],
        ["20261022", "Petrobras", "ECON_STOCKMARKET|TAX_FNCACT", "-2.5", "1.0", "3.5"],
        ["20261022", "Magazine Luiza", "ENV_OIL", "1.5", "3.0", "1.5"],
        ["20261022", "Petrobras", "ENV_OIL", "1.5", "3.0", "1.5"],
    ]


def test_gkg_linhas_do_dublê_viram_uma_linha_por_empresa_citada(tmp_path):
    cliente = _cliente_com_empresas()
    (alvo, *_) = _por_id()["gdelt-gkg"].descobrir(cliente, AGORA)
    cliente.arquivos[alvo.url] = _fixture("gkg_duble.csv.zip")
    linhas = _csv(_obter_de(alvo, cliente, tmp_path))[1:]
    assert sorted((l[1], l[2]) for l in linhas) == [
        ("Magazine Luiza", "ENV_OIL"),
        ("Petrobras", "ECON_STOCKMARKET|TAX_FNCACT"),
        ("Petrobras", "ENV_OIL"),
    ]


def test_gkg_que_a_fonte_ainda_nao_publicou_e_sem_arquivo(tmp_path):
    cliente = _cliente_com_empresas()
    (alvo, *_) = _por_id()["gdelt-gkg"].descobrir(cliente, AGORA)
    cliente.erro_404.add(alvo.url)
    with pytest.raises(SemArquivo):
        alvo.obter(cliente, tmp_path / "x")


def test_nomes_para_o_gkg_tiram_sufixo_acento_e_nome_curto():
    empresas = lote.empresas_do_wikidata(_fixture("wikidata_empresas_duble.json"))
    nomes = lote.nomes_para_o_gkg(empresas)
    assert nomes["petroleo brasileiro"] == "Petrobras"
    assert nomes["petrobras"] == "Petrobras"
    assert nomes["gol linhas aereas"] == "Gol Linhas Aéreas"
    assert all(len(n) >= lote.TAMANHO_MINIMO_DO_NOME_NO_GKG for n in nomes)


# ---- Querido Diário: LGPD --------------------------------------------------------------------
def test_querido_diario_um_pedido_por_empresa_com_frase_exata():
    cliente = _cliente_com_empresas()
    alvos = _por_id()["querido-diario-empresas"].descobrir(cliente, AGORA)
    assert len(alvos) == 3
    assert alvos[0].url.startswith(
        lote.QUERIDO_DIARIO + "?querystring=%22Petr%C3%B3leo"
    )
    assert "published_since=2026-09-01" in alvos[0].url
    assert "published_until=2026-09-30" in alvos[0].url


def test_querido_diario_nunca_guarda_o_trecho_do_diario(tmp_path):
    cliente = _cliente_com_empresas()
    (alvo, *_) = _por_id()["querido-diario-empresas"].descobrir(cliente, AGORA)
    cliente.arquivos[alvo.url] = _fixture("querido_diario_duble.json")
    destino = _obter_de(alvo, cliente, tmp_path)
    texto = destino.read_text(encoding="utf-8")
    for proibido in ("excerpts", "José Fulano", "CPF", "txt_url", "scraped_at"):
        assert proibido not in texto
    guardado = json.loads(texto)
    assert guardado["total_gazettes"] == 2
    assert guardado["gazettes"][0] == {
        "territory_id": "5004403",
        "territory_name": "Inocência",
        "state_code": "MS",
        "date": "2026-09-25",
        "edition": "3331",
        "is_extra_edition": False,
        "url": "https://data.queridodiario.ok.org.br/a.pdf",
    }


def test_querido_diario_que_mudou_de_formato_e_falha(tmp_path):
    bruto = tmp_path / "b"
    bruto.write_text('{"outra": 1}')
    with pytest.raises(ValueError):
        lote.diarios_sem_trecho(bruto, tmp_path / "d")


# ---- Crossref e OpenAlex: só contagens -------------------------------------------------------
def test_openalex_agrupa_por_ano_e_limpa_o_nome():
    url = lote.endereco_do_openalex("Banco, do: Brasil|S.A.")
    assert "group_by=publication_year" in url
    assert "%2C" not in url.split("filter=")[1].split("&")[0].replace("%3A", "", 1)
    assert "Banco+do+Brasil+S.A." in url


def test_crossref_pede_zero_obras_e_a_faceta_por_ano():
    url = lote.endereco_do_crossref("Petrobras")
    assert "rows=0" in url and "facet=published%3A100" in url


def test_contagens_so_levam_total_e_ano(tmp_path):
    cliente = _cliente_com_empresas()
    for id_, fixture, esperado in (
        (
            "openalex-afiliacoes",
            "openalex_duble.json",
            {
                "total": 18700,
                "por_ano": [
                    {"ano": "2025", "obras": 803},
                    {"ano": "2024", "obras": 643},
                ],
            },
        ),
        (
            "crossref-afiliacoes",
            "crossref_duble.json",
            {"total": 958, "por_ano": {"2025": 508, "2024": 450}},
        ),
    ):
        (alvo, *_) = _por_id()[id_].descobrir(cliente, AGORA)
        cliente.arquivos[alvo.url] = _fixture(fixture)
        destino = tmp_path / f"{id_}.json"
        alvo.obter(cliente, destino)
        assert json.loads(destino.read_text()) == esperado


def test_obra_com_autor_na_resposta_nao_passa(tmp_path):
    bruto = tmp_path / "b"
    bruto.write_text(
        json.dumps(
            {
                "message": {
                    "total-results": 1,
                    "facets": {"published": {"values": {"2025": 1}}},
                    "items": [{"author": [{"given": "Maria", "family": "Souza"}]}],
                }
            }
        )
    )
    lote.contagens_do_crossref(bruto, tmp_path / "d")
    assert (
        "Maria" not in (tmp_path / "d").read_text()
        and "author" not in (tmp_path / "d").read_text()
    )


# ---- RSS: só índice --------------------------------------------------------------------------
def test_rss_guarda_so_data_titulo_e_link_nunca_o_resumo(tmp_path):
    fonte = _por_id()["ebc-rss-ultimas"]
    (alvo,) = fonte.descobrir(None, AGORA)  # type: ignore[arg-type]
    cliente = Cliente(arquivos={alvo.url: _fixture("rss_duble.xml")})
    destino = _obter_de(alvo, cliente, tmp_path)
    assert "RESUMO" not in destino.read_text(encoding="utf-8")
    assert _csv(destino) == [
        ["data", "titulo", "link"],
        [
            "Thu, 22 Oct 2026 21:16:46 GMT",
            "Projeto cria carteira do cuidador",
            "https://exemplo.gov.br/n/1",
        ],
        [
            "Thu, 22 Oct 2026 20:00:00 GMT",
            "Selic fica em 10%",
            "https://exemplo.gov.br/n/2",
        ],
    ]
    assert fonte.grupo == "diaria"


def test_rss_sem_item_ou_quebrado_e_falha(tmp_path):
    bruto = tmp_path / "b"
    bruto.write_text("<rss><channel></channel></rss>")
    with pytest.raises(ValueError):
        lote.indice_do_rss(bruto, tmp_path / "d")
    bruto.write_text("<html>nao e xml")
    with pytest.raises(ValueError):
        lote.indice_do_rss(bruto, tmp_path / "d")


def test_as_quatro_agencias_e_seus_endereco():
    assert set(lote.RSS_DAS_AGENCIAS) == {
        "ebc-rss-ultimas",
        "ebc-rss-economia",
        "senado-rss-noticias",
        "camara-rss-noticias",
    }
    for url in lote.RSS_DAS_AGENCIAS.values():
        assert url.startswith("https://")


# ---- vigias ----------------------------------------------------------------------------------
def test_os_termos_do_lote_entram_no_catalogo_como_vigia():
    for id_, url in lote.termos().items():
        fonte = fontes.POR_ID[id_]
        assert fonte.vigia
        assert url
    assert "termos-querido" in lote.termos()
