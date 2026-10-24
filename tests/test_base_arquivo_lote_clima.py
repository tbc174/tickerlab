"""Lote clima e fogo (base/arquivo/lote_clima.py): INPE Queimadas, NASA FIRMS, TerraBrasilis, NOAA,
ECMWF, MapBiomas, ONS, Climate TRACE, EDGAR e Carbon Monitor. Nada vai à internet: as respostas são
dublês de `tests/arquivos/clima/`."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from base.arquivo import coleta, fontes
from base.arquivo import lote_clima as lote
from base.arquivo.coleta import ErroDeDescoberta, Resposta, SemArquivo
from base.arquivo.destinos import DESTINOS
from base.arquivo.lote_setoriais import PACOTES_DO_ONS
from base.arquivo.registro import TERMOS_LIDOS_EM
from src.banco import coletas
from src.banco.coletas import (
    SEM_LICENCA_CONHECIDA,
    Marca,
    licenca_da_fonte,
    marca_da_fonte,
)

AGORA = datetime(2026, 10, 23, 13, tzinfo=UTC)
PASTA = Path(__file__).parent / "arquivos" / "clima"
DIA_DA_PREVISAO = date(2026, 10, 22)  # ontem em relação a AGORA
CHAVE_DE_TESTE = "chave-falsa-de-teste-0123456789"
FAMILIAS = {
    "inpe",
    "firms",
    "inmet",
    "noaa",
    "ecmwf",
    "mapbiomas",
    "terrabrasilis",
    "ons",
    "climatetrace",
    "edgar",
    "carbonmonitor",
}


def _arquivo(nome: str) -> bytes:
    return (PASTA / nome).read_bytes()


def _erro_http(codigo: int) -> requests.HTTPError:
    resposta = requests.Response()
    resposta.status_code = codigo
    return requests.HTTPError(f"{codigo} Client Error", response=resposta)


class Paginas:
    """Responde `ler` com páginas fixas (por endereço); endereço desconhecido é 404."""

    def __init__(self, paginas: dict[str, bytes]):
        self.paginas = paginas
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        if url not in self.paginas:
            raise _erro_http(404)
        return Resposta(url, self.paginas[url], {})


class ComTrechos(Paginas):
    """Também serve trechos de um arquivo em memória."""

    def __init__(self, paginas: dict[str, bytes], arquivos: dict[str, bytes]):
        super().__init__(paginas)
        self.arquivos = arquivos
        self.trechos: list[tuple[int, int]] = []

    def ler_trecho(self, url, inicio, fim):
        self.trechos.append((inicio, fim))
        return self.arquivos[url][inicio : fim + 1]


def _fontes_do_lote():
    return lote.fontes()


def _por_id():
    return {f.id: f for f in _fontes_do_lote()}


# ---- o lote como um todo -----------------------------------------------------------------------
def test_ids_sem_duplicata_no_lote_e_no_catalogo():
    ids = [f.id for f in _fontes_do_lote()]
    assert len(ids) == len(set(ids))
    todos = [f.id for f in fontes.FONTES]
    assert len(todos) == len(set(todos))
    assert set(ids) <= set(todos)


def test_toda_fonte_do_lote_tem_licenca_marca_data_e_destino():
    for fonte in _fontes_do_lote():
        familia = fonte.id.split("-", 1)[0]
        assert licenca_da_fonte(fonte.id) != SEM_LICENCA_CONHECIDA, fonte.id
        assert len(licenca_da_fonte(fonte.id)) <= 80, fonte.id
        assert marca_da_fonte(fonte.id) is not None, fonte.id
        assert TERMOS_LIDOS_EM[familia].year == 2026, fonte.id
        assert fonte.grupo in (*fontes.GRUPOS, "carga-unica"), fonte.id
        assert fonte.id in DESTINOS, fonte.id


def test_as_familias_do_lote_estao_todas_representadas():
    assert {f.id.split("-", 1)[0] for f in _fontes_do_lote()} == FAMILIAS


def test_marcas_inpe_a_confirmar_terrabrasilis_so_uso_interno_e_o_resto_vendavel():
    especiais = {"inpe": Marca.A_CONFIRMAR, "terrabrasilis": Marca.USO_INTERNO}
    for fonte in _fontes_do_lote():
        familia = fonte.id.split("-", 1)[0]
        esperada = especiais.get(familia, Marca.VENDAVEL)
        assert marca_da_fonte(fonte.id) == esperada, fonte.id


def test_o_lote_nao_repete_o_que_ja_existe_nem_traz_o_que_ficou_de_fora():
    ids = {f.id for f in _fontes_do_lote()}
    existentes = {
        "inmet-bdmep",
        "chirps-mensal",
        "chirps-historico",
        "noaa-teleconexoes",
        "mapbiomas-cafe",
    }
    assert not ids & existentes
    for proibida in ("era5", "iea", "co2"):
        assert not [i for i in ids if proibida in i.split("-")], proibida
    nao_repetir = {p for pacotes in PACOTES_DO_ONS.values() for p in pacotes}
    assert not nao_repetir & set(lote.PACOTES_DE_HIDROLOGIA_DETALHADA_DO_ONS)


def test_ritmo_segue_o_calendario_de_cada_fonte():
    por_id = _por_id()
    assert por_id["inpe-queimadas-diario"].grupo == "diaria"
    assert por_id["noaa-oisst-diario"].grupo == "diaria"
    assert por_id["ecmwf-previsao-recortada"].grupo == "diaria"
    assert por_id["noaa-ghcn-diario-brasil"].grupo == "mensal"
    assert por_id["climatetrace-paises"].grupo == "mensal"
    assert por_id["ons-hidrologia-detalhada"].grupo == "semanal"
    assert {f.id for f in _fontes_do_lote() if f.grupo == "carga-unica"} == {
        "inpe-queimadas-historico",
        "terrabrasilis-prodes-historico",
    }


def test_os_grandes_sao_pesados_e_os_pequenos_nao():
    pesadas = {f.id for f in _fontes_do_lote() if f.pesada}
    assert {
        "noaa-ghcn-diario-brasil",
        "noaa-ghcn-mensal-temperatura",
        "noaa-oisst-diario",
        "mapbiomas-estatisticas",
        "ons-hidrologia-detalhada",
        "edgar-ghg-ar5",
        "edgar-ch4",
        "edgar-n2o",
        "inpe-queimadas-historico",
        "terrabrasilis-prodes-historico",
    } <= pesadas
    assert not pesadas & {"noaa-oni", "firms-modis-brasil", "climatetrace-paises"}


def test_termos_do_lote_entram_no_catalogo_com_vigia():
    assert lote.termos().items() <= fontes.TERMOS.items()
    for chave, url in lote.termos().items():
        assert chave.startswith("termos-") and url.startswith("https://")
        assert fontes.POR_ID[chave].vigia is True
    assert len(set(lote.termos().values())) == len(lote.termos())


def test_as_fontes_simples_descobrem_alvos_https_sem_internet():
    simples = (
        "inmet-estacoes",
        "noaa-oni",
        "noaa-nino",
        "noaa-soi",
        "noaa-ghcn-estacoes",
        "noaa-ghcn-paises",
        "noaa-ghcn-mensal-temperatura",
        "edgar-ghg-ar5",
        "edgar-ch4",
        "edgar-n2o",
        "carbonmonitor-global",
    )
    for id_ in simples:
        alvos = _por_id()[id_].descobrir(None, AGORA)  # type: ignore[arg-type]
        assert alvos, id_
        assert all(a.url.startswith("https://") for a in alvos), id_


def test_edgar_nao_traz_o_co2_da_iea():
    for alvo in (
        a
        for id_ in lote.ARQUIVOS_DO_EDGAR
        for a in _por_id()[id_].descobrir(None, AGORA)  # type: ignore[arg-type]
    ):
        assert "IEA" not in alvo.url and "CO2" not in alvo.url


# ---- INPE Queimadas -----------------------------------------------------------------------------
def test_inpe_diario_pega_os_dias_mais_recentes_do_indice():
    pasta = f"{lote.PASTA_DOS_FOCOS_DO_INPE}/diario/Brasil/"
    cliente = Paginas({pasta: _arquivo("inpe_indice_diario.html")})
    alvos = _por_id()["inpe-queimadas-diario"].descobrir(cliente, AGORA)
    assert len(alvos) == lote.DIAS_RECENTES_DO_INPE
    assert alvos[-1].url == pasta + "focos_diario_br_20261015.csv"
    assert alvos[0].url == pasta + "focos_diario_br_20261006.csv"
    assert all(a.extensao == ".csv" for a in alvos)


def test_inpe_historico_pega_a_serie_mensal_inteira_e_o_mensal_so_os_ultimos():
    pasta = f"{lote.PASTA_DOS_FOCOS_DO_INPE}/mensal/Brasil/"
    cliente = Paginas({pasta: _arquivo("inpe_indice_mensal.html")})
    todos = _por_id()["inpe-queimadas-historico"].descobrir(cliente, AGORA)
    recentes = _por_id()["inpe-queimadas-mensal"].descobrir(cliente, AGORA)
    assert len(todos) == 24
    assert [a.url for a in recentes] == [a.url for a in todos[-3:]]


def test_inpe_com_indice_vazio_e_erro_de_descoberta():
    pasta = f"{lote.PASTA_DOS_FOCOS_DO_INPE}/diario/Brasil/"
    with pytest.raises(ErroDeDescoberta):
        _por_id()["inpe-queimadas-diario"].descobrir(
            Paginas({pasta: b"<html></html>"}), AGORA
        )


# ---- NASA FIRMS: a chave nunca vai para o registro --------------------------------------------
class ServidorDoFirms:
    """Baixa o CSV do FIRMS; guarda o endereço pedido (com a chave, como o servidor o vê)."""

    def __init__(self, corpo: bytes | None = None, erro: Exception | None = None):
        self.corpo = corpo if corpo is not None else _arquivo("firms.csv")
        self.erro = erro
        self.pedidos: list[str] = []

    def baixar(self, url, destino: Path):
        self.pedidos.append(url)
        if self.erro is not None:
            raise self.erro
        destino.write_bytes(self.corpo)
        return {"ETag": '"f"'}


def _fonte_do_firms():
    return _por_id()["firms-viirs-snpp-brasil"]


def test_firms_guarda_o_marcador_no_endereco_e_nunca_a_chave(monkeypatch):
    monkeypatch.setenv(lote.VARIAVEL_DA_CHAVE_DO_FIRMS, CHAVE_DE_TESTE)
    alvos = _fonte_do_firms().descobrir(None, AGORA)  # type: ignore[arg-type]
    assert len(alvos) == 1
    assert alvos[0].url == (
        f"{lote.API_DO_FIRMS}/{{MAP_KEY}}/VIIRS_SNPP_NRT/BRA/"
        f"{lote.DIAS_DA_JANELA_DO_FIRMS}/2026-10-23"
    )
    assert CHAVE_DE_TESTE not in alvos[0].url


def test_firms_pede_um_satelite_por_fonte():
    urls = {
        id_: _por_id()[id_].descobrir(None, AGORA)[0].url  # type: ignore[arg-type]
        for id_ in (
            "firms-viirs-snpp-brasil",
            "firms-viirs-noaa20-brasil",
            "firms-modis-brasil",
        )
    }
    assert "/VIIRS_SNPP_NRT/" in urls["firms-viirs-snpp-brasil"]
    assert "/VIIRS_NOAA20_NRT/" in urls["firms-viirs-noaa20-brasil"]
    assert "/MODIS_NRT/" in urls["firms-modis-brasil"]


def test_firms_sem_a_variavel_pula_a_fonte_com_o_motivo_no_registro(
    banco, tmp_path, monkeypatch
):
    monkeypatch.delenv(lote.VARIAVEL_DA_CHAVE_DO_FIRMS, raising=False)
    servidor = ServidorDoFirms()
    resultado = coleta.arquivar(
        _fonte_do_firms(), servidor, AGORA, tmp_path / "t", pausa=0
    )
    assert (resultado.novos, resultado.falhas, resultado.sem_arquivo) == (0, [], 1)
    assert servidor.pedidos == []  # nem tentou o servidor
    with banco.connect() as conexao:
        linhas = coletas.ultimas(conexao, "firms-viirs-snpp-brasil")
    assert [l.situacao for l in linhas] == ["nao_encontrado"]
    assert lote.VARIAVEL_DA_CHAVE_DO_FIRMS in linhas[0].detalhe


def test_firms_com_a_chave_baixa_com_ela_e_o_acervo_nao_a_guarda(
    banco, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv(lote.VARIAVEL_DA_CHAVE_DO_FIRMS, CHAVE_DE_TESTE)
    servidor = ServidorDoFirms()
    with caplog.at_level("DEBUG"):
        resultado = coleta.arquivar(
            _fonte_do_firms(), servidor, AGORA, tmp_path / "t", pausa=0
        )
    assert (resultado.novos, resultado.falhas) == (1, [])
    assert CHAVE_DE_TESTE in servidor.pedidos[0]  # o servidor recebe a chave
    assert "{MAP_KEY}" not in servidor.pedidos[0]
    with banco.connect() as conexao:
        linhas = coletas.ultimas(conexao, "firms-viirs-snpp-brasil")
    assert linhas[0].situacao == "ok" and "{MAP_KEY}" in linhas[0].url
    _confere_que_a_chave_nao_esta_em_lugar_nenhum(tmp_path, caplog)


def test_firms_com_erro_do_servidor_registra_sem_a_chave(
    banco, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv(lote.VARIAVEL_DA_CHAVE_DO_FIRMS, CHAVE_DE_TESTE)
    url_com_a_chave = (
        f"{lote.API_DO_FIRMS}/{CHAVE_DE_TESTE}/VIIRS_SNPP_NRT/BRA/10/2026-10-23"
    )
    erro = _erro_http(401)
    erro.args = (f"401 Client Error: Unauthorized for url: {url_com_a_chave}",)
    servidor = ServidorDoFirms(erro=erro)
    with caplog.at_level("DEBUG"):
        resultado = coleta.arquivar(
            _fonte_do_firms(), servidor, AGORA, tmp_path / "t", pausa=0
        )
    assert len(resultado.falhas) == 1 and CHAVE_DE_TESTE not in resultado.falhas[0]
    with banco.connect() as conexao:
        linha = coletas.ultimas(conexao, "firms-viirs-snpp-brasil")[0]
    assert linha.situacao == "falhou"
    assert "***" in linha.detalhe and "HTTPError" in linha.detalhe
    _confere_que_a_chave_nao_esta_em_lugar_nenhum(tmp_path, caplog)


def test_firms_com_resposta_que_nao_e_csv_falha_sem_a_chave(
    banco, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv(lote.VARIAVEL_DA_CHAVE_DO_FIRMS, CHAVE_DE_TESTE)
    servidor = ServidorDoFirms(corpo=f"Invalid MAP_KEY {CHAVE_DE_TESTE}".encode())
    with caplog.at_level("DEBUG"):
        resultado = coleta.arquivar(
            _fonte_do_firms(), servidor, AGORA, tmp_path / "t", pausa=0
        )
    assert len(resultado.falhas) == 1
    with banco.connect() as conexao:
        linha = coletas.ultimas(conexao, "firms-viirs-snpp-brasil")[0]
    assert linha.situacao == "falhou"
    _confere_que_a_chave_nao_esta_em_lugar_nenhum(tmp_path, caplog)


def _confere_que_a_chave_nao_esta_em_lugar_nenhum(pasta: Path, caplog) -> None:
    """Nem no banco, nem no manifesto, nem no acervo, nem nos logs."""
    chave = CHAVE_DE_TESTE.encode()
    for arquivo in pasta.rglob("*"):
        if arquivo.is_file():
            assert chave not in arquivo.read_bytes(), arquivo.name
    assert CHAVE_DE_TESTE not in caplog.text


def test_o_erro_do_firms_sai_sem_o_erro_original_encadeado(tmp_path, monkeypatch):
    monkeypatch.setenv(lote.VARIAVEL_DA_CHAVE_DO_FIRMS, CHAVE_DE_TESTE)
    obter = lote.obter_do_firms(
        f"{lote.API_DO_FIRMS}/{{MAP_KEY}}/MODIS_NRT/BRA/10/2026-10-23"
    )
    servidor = ServidorDoFirms(erro=RuntimeError(f"falhou {CHAVE_DE_TESTE}"))
    with pytest.raises(lote.ErroDoFirms) as erro:
        obter(servidor, tmp_path / "x")  # type: ignore[arg-type]
    assert CHAVE_DE_TESTE not in str(erro.value)
    assert erro.value.__cause__ is None and erro.value.__suppress_context__


def test_sem_a_chave_o_obter_do_firms_levanta_sem_arquivo(tmp_path, monkeypatch):
    monkeypatch.setenv(lote.VARIAVEL_DA_CHAVE_DO_FIRMS, "   ")
    obter = lote.obter_do_firms(
        f"{lote.API_DO_FIRMS}/{{MAP_KEY}}/MODIS_NRT/BRA/10/2026-10-23"
    )
    with pytest.raises(SemArquivo):
        obter(ServidorDoFirms(), tmp_path / "x")  # type: ignore[arg-type]


# ---- NOAA: GHCN e OISST ------------------------------------------------------------------------
def test_ghcn_do_brasil_so_pega_estacoes_com_codigo_wmo():
    cadastro = _arquivo("ghcn_estacoes.txt").decode()
    assert lote.estacoes_do_brasil_no_ghcn(cadastro) == [
        "BR000082400",
        "BRM00083377",
    ]


def test_ghcn_diario_vira_um_alvo_por_estacao_do_brasil():
    cliente = Paginas(
        {f"{lote.GHCN_DIARIO}/ghcnd-stations.txt": _arquivo("ghcn_estacoes.txt")}
    )
    alvos = _por_id()["noaa-ghcn-diario-brasil"].descobrir(cliente, AGORA)
    assert [a.url for a in alvos] == [
        f"{lote.GHCN_DIARIO}/all/BR000082400.dly",
        f"{lote.GHCN_DIARIO}/all/BRM00083377.dly",
    ]


def test_ghcn_sem_estacao_do_brasil_e_erro_de_descoberta():
    cliente = Paginas(
        {f"{lote.GHCN_DIARIO}/ghcnd-stations.txt": b"USW00094728  40.8 -74.0\n"}
    )
    with pytest.raises(ErroDeDescoberta):
        _por_id()["noaa-ghcn-diario-brasil"].descobrir(cliente, AGORA)


def test_oisst_pega_os_ultimos_dias_e_o_definitivo_vence_o_preliminar():
    mes = _arquivo("oisst_mes.html")
    cliente = Paginas({f"{lote.OISST}/202610/": mes})
    alvos = _por_id()["noaa-oisst-diario"].descobrir(cliente, AGORA)
    assert len(alvos) == lote.DIAS_RECENTES_DO_OISST
    nomes = [a.url.rsplit("/", 1)[1] for a in alvos]
    assert nomes[-1] == "oisst-avhrr-v02r01.20261019_preliminary.nc"
    assert "oisst-avhrr-v02r01.20261018.nc" in nomes  # o definitivo, não o preliminar
    assert "oisst-avhrr-v02r01.20261018_preliminary.nc" not in nomes
    assert all(a.extensao == ".nc" for a in alvos)


def test_oisst_na_virada_do_mes_ignora_o_mes_que_ainda_nao_tem_arquivo():
    cliente = Paginas({f"{lote.OISST}/202609/": _arquivo("oisst_mes.html")})
    agora = datetime(2026, 10, 3, 13, tzinfo=UTC)  # outubro ainda não abriu (404)
    alvos = _por_id()["noaa-oisst-diario"].descobrir(cliente, agora)
    assert alvos and all("/202609/" in a.url for a in alvos)


# ---- ECMWF open data ---------------------------------------------------------------------------
def _servidor_do_ecmwf():
    url = lote.endereco_do_ecmwf(DIA_DA_PREVISAO, 24)
    grib = bytes(range(256)) * 2  # 512 bytes: o conteúdo é só para conferir os trechos
    indice = url.removesuffix(".grib2") + ".index"
    return url, grib, ComTrechos({indice: _arquivo("ecmwf_indice.index")}, {url: grib})


def test_ecmwf_pede_a_previsao_de_ontem_em_tres_passos():
    alvos = _por_id()["ecmwf-previsao-recortada"].descobrir(None, AGORA)  # type: ignore[arg-type]
    assert [a.url for a in alvos] == [
        lote.endereco_do_ecmwf(DIA_DA_PREVISAO, p) for p in lote.PASSOS_DO_ECMWF
    ]
    assert alvos[0].url.endswith("20261022000000-24h-oper-fc.grib2")
    assert all(a.obter is not None for a in alvos)


def test_ecmwf_baixa_so_as_mensagens_de_chuva_temperatura_e_pressao(tmp_path):
    url, grib, servidor = _servidor_do_ecmwf()
    destino = tmp_path / "recorte.grib2"
    lote.recorte_do_ecmwf(url)(servidor, destino)
    # 2t (0-99), msl (100-179) e tp (180-299); o vento e a altura geopotencial ficam de fora
    assert destino.read_bytes() == grib[0:300]
    assert servidor.trechos == [(0, 99), (100, 179), (180, 299)]


def test_ecmwf_previsao_que_ainda_nao_saiu_e_sem_arquivo(tmp_path):
    url, _, _ = _servidor_do_ecmwf()
    with pytest.raises(SemArquivo):
        lote.recorte_do_ecmwf(url)(ComTrechos({}, {}), tmp_path / "x")  # type: ignore[arg-type]


def test_ecmwf_com_indice_sem_um_dos_parametros_e_erro(tmp_path):
    url, grib, _ = _servidor_do_ecmwf()
    indice = url.removesuffix(".grib2") + ".index"
    sem_chuva = "".join(
        linha + "\n"
        for linha in _arquivo("ecmwf_indice.index").decode().splitlines()
        if '"tp"' not in linha
    )
    servidor = ComTrechos({indice: sem_chuva.encode()}, {url: grib})
    with pytest.raises(ValueError, match="faltam parâmetros"):
        lote.recorte_do_ecmwf(url)(servidor, tmp_path / "x")  # type: ignore[arg-type]


# ---- MapBiomas ---------------------------------------------------------------------------------
def test_mapbiomas_pega_as_planilhas_por_municipio_e_por_bioma_e_estado():
    pagina = lote.PAGINA_DAS_ESTATISTICAS_DO_MAPBIOMAS
    cliente = Paginas({pagina: _arquivo("mapbiomas_estatisticas.html")})
    alvos = _por_id()["mapbiomas-estatisticas"].descobrir(cliente, AGORA)
    assert [a.url for a in alvos] == [
        "https://brasil.mapbiomas.org/wp-content/uploads/COL.11-BIOME_STATE.xlsx",
        "https://storage.googleapis.com/mapbiomas-public/COLECAO_11/TABELA/MUNICIPALITY_deforestation.xlsx",
        "https://storage.googleapis.com/mapbiomas-public/COLECAO_11/TABELA/MUNICIPALITY_mining.xlsx",
    ]


def test_mapbiomas_sem_planilha_na_pagina_e_erro_de_descoberta():
    pagina = lote.PAGINA_DAS_ESTATISTICAS_DO_MAPBIOMAS
    with pytest.raises(ErroDeDescoberta):
        _por_id()["mapbiomas-estatisticas"].descobrir(
            Paginas({pagina: b"<html/>"}), AGORA
        )


# ---- TerraBrasilis: só o WFS -------------------------------------------------------------------
class ServidorDoWfs:
    """Responde `resultType=hits` com a contagem que o teste definir (por camada e ano)."""

    def __init__(self, contagens: dict[tuple[str, int], int]):
        self.contagens = contagens
        self.pedidos: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None, corpo=None):
        self.pedidos.append(url)
        consulta = parse_qs(urlsplit(url).query)
        assert consulta["resultType"] == ["hits"]
        camada = consulta["typeName"][0]
        filtro = consulta["cql_filter"][0]
        ano = (
            int(filtro.split("-")[0].split()[-1])
            if "view_date" in filtro
            else int(filtro.split("=")[1])
        )
        total = self.contagens.get((camada, ano), 0)
        return Resposta(url, f'<c numberOfFeatures="{total}"/>'.encode(), {})


def test_wfs_pagina_o_ano_para_nao_bater_no_teto_de_cinquenta_mil_linhas():
    servidor = ServidorDoWfs({(lote.PRODES_CERRADO.nome, 2024): 62_372})
    alvos = lote.alvos_do_ano(servidor, lote.PRODES_CERRADO, 2024)  # type: ignore[arg-type]
    assert len(alvos) == 3
    inicios = [int(parse_qs(urlsplit(a.url).query)["startIndex"][0]) for a in alvos]
    assert inicios == [0, 25_000, 50_000]
    for alvo in alvos:
        consulta = parse_qs(urlsplit(alvo.url).query)
        assert consulta["maxFeatures"] == [str(lote.LINHAS_POR_PAGINA_DO_WFS)]
        assert consulta["sortBy"] == [
            "uuid"
        ]  # ordem fixa: a página não repete nem perde linha
        assert consulta["outputFormat"] == ["csv"]
        assert consulta["version"] == ["1.1.0"]
        assert alvo.extensao == ".csv"


def test_wfs_nunca_pede_a_geometria_e_o_endereco_cabe_no_registro():
    servidor = ServidorDoWfs({(lote.DETER_AMAZONIA.nome, 2024): 10})
    (alvo,) = lote.alvos_do_ano(servidor, lote.DETER_AMAZONIA, 2024)  # type: ignore[arg-type]
    colunas = parse_qs(urlsplit(alvo.url).query)["propertyName"][0].split(",")
    assert "geom" not in colunas and "the_geom" not in colunas
    assert len(alvo.url) <= 1000  # coluna `url` de `coletas`


def test_wfs_ano_sem_registro_nao_gera_alvo():
    assert lote.alvos_do_ano(ServidorDoWfs({}), lote.DETER_CERRADO, 2019) == []  # type: ignore[arg-type]


def test_wfs_sem_contagem_na_resposta_e_erro_de_descoberta():
    cliente = Paginas({})
    cliente.ler = lambda url, **_: Resposta(url, b"<ExceptionReport/>", {})  # type: ignore[method-assign]
    with pytest.raises(ErroDeDescoberta):
        lote.linhas_do_ano(cliente, lote.PRODES_CERRADO, 2024)  # type: ignore[arg-type]


def test_deter_vai_do_primeiro_ano_da_camada_ao_ano_corrente():
    servidor = ServidorDoWfs({})
    _por_id()["terrabrasilis-deter-amazonia"].descobrir(servidor, AGORA)
    anos = {
        parse_qs(urlsplit(u).query)["cql_filter"][0].split("view_date >= ")[1][:4]
        for u in servidor.pedidos
    }
    assert anos == {str(a) for a in range(2015, 2027)}
    servidor = ServidorDoWfs({})
    _por_id()["terrabrasilis-deter-cerrado"].descobrir(servidor, AGORA)
    assert len(servidor.pedidos) == 2026 - 2018 + 1


def test_prodes_recente_e_historico_nao_se_sobrepoem():
    contagens = {
        (camada.nome, ano): 1
        for camada in (lote.PRODES_AMAZONIA_LEGAL, lote.PRODES_CERRADO)
        for ano in range(2000, 2027)
    }
    recente = _por_id()["terrabrasilis-prodes-recente"].descobrir(
        ServidorDoWfs(contagens),
        AGORA,  # type: ignore[arg-type]
    )
    historico = _por_id()["terrabrasilis-prodes-historico"].descobrir(
        ServidorDoWfs(contagens),
        AGORA,  # type: ignore[arg-type]
    )
    assert len(recente) == 2 * lote.ANOS_RECENTES_DO_PRODES
    assert len(historico) == 2 * (2026 - lote.ANOS_RECENTES_DO_PRODES - 2000 + 1)
    assert not {a.url for a in recente} & {a.url for a in historico}


def test_terrabrasilis_so_pelo_wfs_nunca_os_zips_da_pagina_de_downloads():
    contagens = {
        (c.nome, ano): 1
        for c in (
            lote.DETER_AMAZONIA,
            lote.DETER_CERRADO,
            lote.PRODES_AMAZONIA_LEGAL,
            lote.PRODES_CERRADO,
        )
        for ano in range(2000, 2027)
    }
    for id_ in (i for i in _por_id() if i.startswith("terrabrasilis-")):
        alvos = _por_id()[id_].descobrir(ServidorDoWfs(contagens), AGORA)  # type: ignore[arg-type]
        assert alvos, id_
        for alvo in alvos:
            assert alvo.url.startswith(lote.WFS_DO_TERRABRASILIS + "?"), alvo.url
            assert ".zip" not in alvo.url and "download" not in alvo.url.lower()


# ---- Climate TRACE -----------------------------------------------------------------------------
def test_climate_trace_todos_os_paises_um_ano_por_alvo():
    cliente = Paginas(
        {
            f"{lote.API_DO_CLIMATE_TRACE}/definitions/countries": _arquivo(
                "climatetrace_paises.json"
            )
        }
    )
    alvos = _por_id()["climatetrace-paises"].descobrir(cliente, AGORA)
    assert (
        len(alvos) == 2025 - lote.PRIMEIRO_ANO_DO_CLIMATE_TRACE + 1
    )  # nunca o ano corrente
    primeiro = urlsplit(alvos[0].url).query
    assert primeiro == "since=2015&to=2015&countries=ARG,BRA,USA"
    assert all(a.extensao == ".json" for a in alvos)


def test_climate_trace_brasil_por_setor():
    alvos = _por_id()["climatetrace-brasil-setores"].descobrir(None, AGORA)  # type: ignore[arg-type]
    anos = 2025 - lote.PRIMEIRO_ANO_DO_CLIMATE_TRACE + 1
    assert len(alvos) == len(lote.SETORES_DO_CLIMATE_TRACE) * anos
    assert len({a.url for a in alvos}) == len(alvos)
    consulta = parse_qs(urlsplit(alvos[0].url).query)
    assert consulta["countries"] == ["BRA"] and consulta["sectors"] == ["agriculture"]


def test_climate_trace_com_lista_de_paises_vazia_e_erro_de_descoberta():
    cliente = Paginas(
        {f"{lote.API_DO_CLIMATE_TRACE}/definitions/countries": json.dumps([]).encode()}
    )
    with pytest.raises(ErroDeDescoberta):
        _por_id()["climatetrace-paises"].descobrir(cliente, AGORA)
