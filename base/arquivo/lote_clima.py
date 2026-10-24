"""Lote "clima e fogo": queimadas, desmatamento, índices do oceano e da atmosfera, previsão do tempo,
clima de estação, uso da terra e emissões de gases (rodada 4 da pesquisa de dados escondidos,
23/10/2026; ADR 0102: licença lida vira marca, coleta com ritmo, uso citando a fonte).

Cada fonte guarda o arquivo como veio. Nada aqui é lido nem tratado: o que sai de cada arquivo
(focos, alertas, índices, grades) é tarefa da extração.

Regras (testes em `tests/test_base_arquivo_lote_clima.py`):
- **uma fonte por série**, com id "família-série"; a família decide a licença e a marca em
  `src/banco/coletas.py`: `inpe`, `firms`, `terrabrasilis`, `ecmwf`, `climatetrace`, `edgar` e
  `carbonmonitor` (novas), mais `noaa`, `mapbiomas`, `inmet` e `ons` (que já existiam);
- **o NASA FIRMS pede chave** (`MAP_KEY`): o código só a lê do ambiente (`FIRMS_MAP_KEY`), nunca a
  grava. O endereço do alvo leva o marcador `{MAP_KEY}` no lugar dela (é o que o registro e o
  manifesto guardam) e o texto de qualquer erro sai com a chave trocada por `***`. Sem a variável a
  fonte é pulada sem erro e o motivo vai ao registro da coleta;
- **TerraBrasilis só pelo WFS** (agregados, sem a geometria): a página de downloads tem spam (site ou
  plugin comprometido, 22/10/2026), então **nunca se baixa os zips dali**. O GeoServer corta a
  resposta em 50.000 linhas: cada ano é lido em páginas de `LINHAS_POR_PAGINA_DO_WFS`, com a ordem
  fixa pelo identificador do registro;
- o que já existia fica com quem já coleta, e não se repete aqui: INMET (ZIPs anuais, `inmet-bdmep`),
  CHIRPS (`chirps-*`), as teleconexões do NOAA CPC (`noaa-teleconexoes`, `-nao`, `-ao`, `-pna`), a
  NASA POWER e o ONS por subsistema (`ons-hidrologia`). Aqui entram o que falta: as estações do
  INMET, o ENA e o EAR por bacia, REE e reservatório, e o resto do NOAA (ONI, Niño, SOI, GHCN e OISST);
- **ECMWF open data recortado**: a previsão global inteira passa de 400 MB por passo; o índice do
  arquivo diz onde cada mensagem GRIB começa e quanto mede, então só as de chuva, temperatura a 2 m e
  pressão ao nível do mar são pedidas por trecho (HTTP Range);
- **IEA-EDGAR CO2 fica fora** (CC BY-NC-ND): só os conjuntos do JRC sob CC BY 4.0;
- **fora daqui, de propósito**: ERA5-Land (pede a chave do Copernicus CDS, que ainda não está no
  ambiente; linha própria no fim da fila).
"""

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests

from base.arquivo.coleta import (
    Alvo,
    Cliente,
    Descobrir,
    ErroDeDescoberta,
    Fonte,
    Obter,
    SemArquivo,
)
from base.arquivo.lote_organismos import Serie, descobrir_serie
from base.arquivo.lote_setoriais import FORMATOS_DO_ONS, PORTAL_DO_ONS, _ckan

PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS = (
    1.0  # sites de terceiros, um pedido por vez (ADR 0082)
)
HTTP_NAO_ENCONTRADO = 404
ANOS_DE_FOLGA_DAS_EMISSOES = 1  # o Climate TRACE fecha o ano passado, nunca o corrente

# ---- INPE Queimadas (focos de calor em CSV; sem licença escrita: a confirmar, citar o INPE) -------
PASTA_DOS_FOCOS_DO_INPE = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv"
)
DIAS_RECENTES_DO_INPE = (
    10  # o arquivo do dia fecha às 24 h; os dias passados viram "igual"
)
MESES_RECENTES_DO_INPE = 3


def _nomes_da_pasta(cliente: Cliente, pasta: str, padrao: re.Pattern[str]) -> list[str]:
    """Os arquivos que o índice da pasta (Apache) lista, em ordem (o nome leva a data)."""
    pagina = cliente.ler(pasta).conteudo.decode("utf-8", "replace")
    return sorted(set(padrao.findall(pagina)))


def descobrir_focos_do_inpe(recorte: str, quantos: int | None) -> Descobrir:
    """Os `quantos` arquivos mais novos de focos do Brasil (`diario` ou `mensal`); `None` é todos."""
    pasta = f"{PASTA_DOS_FOCOS_DO_INPE}/{recorte}/Brasil/"
    padrao = re.compile(rf'href="(focos_{recorte}_br_\d+\.csv)"')

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        nomes = _nomes_da_pasta(cliente, pasta, padrao)
        if not nomes:
            raise ErroDeDescoberta(f"INPE Queimadas: nenhum arquivo em {pasta}")
        escolhidos = nomes if quantos is None else nomes[-quantos:]
        return [Alvo(pasta + nome, ".csv") for nome in escolhidos]

    return _descobrir


# ---- NASA FIRMS (focos de calor por satélite; MAP_KEY grátis, lida só do ambiente) ---------------
API_DO_FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/country/csv"
VARIAVEL_DA_CHAVE_DO_FIRMS = "FIRMS_MAP_KEY"
MARCADOR_DA_CHAVE = "{MAP_KEY}"  # o que o registro guarda no lugar da chave
DIAS_DA_JANELA_DO_FIRMS = 10  # o máximo que a API aceita por pedido
PRIMEIRA_COLUNA_DO_CSV_DO_FIRMS = "country_id"
SATELITES_DO_FIRMS = {
    "firms-viirs-snpp-brasil": "VIIRS_SNPP_NRT",
    "firms-viirs-noaa20-brasil": "VIIRS_NOAA20_NRT",
    "firms-modis-brasil": "MODIS_NRT",
}


class ErroDoFirms(ValueError):
    """Falha do FIRMS, com o texto já sem a chave."""


def sem_a_chave(texto: str, chave: str) -> str:
    """O texto com a chave trocada por `***` (o erro do `requests` traz o endereço inteiro)."""
    return texto.replace(chave, "***")


def obter_do_firms(url_com_marcador: str) -> Obter:
    """Baixa o CSV do FIRMS com a chave do ambiente; sem a chave, a fonte é pulada (`SemArquivo`).

    Qualquer erro sai como `ErroDoFirms` com o texto limpo da chave, e sem o erro original
    encadeado (que carregaria o endereço com ela)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        chave = os.environ.get(VARIAVEL_DA_CHAVE_DO_FIRMS, "").strip()
        if not chave:
            raise SemArquivo(
                f"{VARIAVEL_DA_CHAVE_DO_FIRMS} não está no ambiente: fonte pulada"
            )
        try:
            cabecalhos = cliente.baixar(
                url_com_marcador.replace(MARCADOR_DA_CHAVE, chave), destino
            )
            comeco = destino.read_bytes()[:200].decode("utf-8", "replace")
            if not comeco.startswith(PRIMEIRA_COLUNA_DO_CSV_DO_FIRMS):
                raise ErroDoFirms(f"resposta que não é o CSV do FIRMS: {comeco[:80]!r}")
        except Exception as erro:  # noqa: BLE001 (todo erro precisa sair sem a chave)
            raise ErroDoFirms(
                f"{type(erro).__name__}: {sem_a_chave(str(erro), chave)}"
            ) from None
        return cabecalhos

    return obter


def descobrir_firms(satelite: str) -> Descobrir:
    """A janela dos últimos dias de focos do Brasil num satélite; o endereço guarda o marcador."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        url = (
            f"{API_DO_FIRMS}/{MARCADOR_DA_CHAVE}/{satelite}/BRA/"
            f"{DIAS_DA_JANELA_DO_FIRMS}/{agora:%Y-%m-%d}"
        )
        return [Alvo(url, ".csv", obter=obter_do_firms(url))]

    return _descobrir


# ---- INMET (apitempo: estações; as séries por hora vêm dos ZIPs anuais de `inmet-bdmep`) ---------
APITEMPO_DO_INMET = "https://apitempo.inmet.gov.br"
TIPOS_DE_ESTACAO_DO_INMET = ("T", "M")  # automáticas e convencionais


def descobrir_estacoes_do_inmet(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(f"{APITEMPO_DO_INMET}/estacoes/{tipo}", ".json")
        for tipo in TIPOS_DE_ESTACAO_DO_INMET
    ]


# ---- NOAA (domínio público; GHCN é CC0) --------------------------------------------------------
CPC = "https://www.cpc.ncep.noaa.gov/data/indices"
GHCN_DIARIO = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
GHCN_MENSAL = "https://www.ncei.noaa.gov/pub/data/ghcn/v4"
OISST = "https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr"
SERIES_DO_NOAA = (
    # ENSO: anomalia da temperatura do Pacífico (ONI), regiões Niño e índice de oscilação do Sul
    Serie("noaa-oni", f"{CPC}/oni.ascii.txt", ".txt"),
    Serie("noaa-nino", f"{CPC}/sstoi.indices", ".txt"),
    Serie("noaa-soi", f"{CPC}/soi", ".txt"),
    # GHCN-Diário: o cadastro das estações e dos países (o dado de cada estação é outra fonte)
    Serie("noaa-ghcn-estacoes", f"{GHCN_DIARIO}/ghcnd-stations.txt", ".txt"),
    Serie("noaa-ghcn-paises", f"{GHCN_DIARIO}/ghcnd-countries.txt", ".txt"),
)
COLUNAS_DO_CODIGO_WMO_NO_GHCN = slice(
    80, 85
)  # posições 81 a 85 do cadastro de estações
PREFIXO_DO_BRASIL_NO_GHCN = "BR"
DIAS_RECENTES_DO_OISST = 10
PADRAO_DO_OISST = re.compile(
    r'href="(oisst-avhrr-v02r01\.(\d{8})(?:_preliminary)?\.nc)"'
)


def estacoes_do_brasil_no_ghcn(cadastro: str) -> list[str]:
    """Os ids das estações do Brasil que têm código WMO (as de verdade: o resto são pluviômetros)."""
    return [
        linha[:11]
        for linha in cadastro.splitlines()
        if linha.startswith(PREFIXO_DO_BRASIL_NO_GHCN)
        and linha[COLUNAS_DO_CODIGO_WMO_NO_GHCN].strip()
    ]


def descobrir_ghcn_do_brasil(cliente: Cliente, agora: datetime) -> list[Alvo]:
    cadastro = cliente.ler(f"{GHCN_DIARIO}/ghcnd-stations.txt").conteudo
    ids = estacoes_do_brasil_no_ghcn(cadastro.decode("utf-8", "replace"))
    if not ids:
        raise ErroDeDescoberta("GHCN: nenhuma estação do Brasil no cadastro")
    return [Alvo(f"{GHCN_DIARIO}/all/{id_}.dly", ".txt") for id_ in ids]


def descobrir_ghcn_mensal(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [Alvo(f"{GHCN_MENSAL}/ghcnm.tavg.latest.qcf.tar.gz", ".tar.gz")]


def _arquivos_do_oisst_no_mes(cliente: Cliente, mes: str) -> dict[str, str]:
    """data (AAAAMMDD) → nome do arquivo daquele mês; o definitivo vence o preliminar."""
    try:
        pagina = cliente.ler(f"{OISST}/{mes}/").conteudo.decode("utf-8", "replace")
    except requests.HTTPError as erro:
        if (
            erro.response is not None
            and erro.response.status_code == HTTP_NAO_ENCONTRADO
        ):
            return {}  # o mês que ainda não tem nenhum arquivo
        raise
    arquivos: dict[str, str] = {}
    for nome, dia in PADRAO_DO_OISST.findall(pagina):
        if dia not in arquivos or "_preliminary" in arquivos[dia]:
            arquivos[dia] = nome
    return arquivos


def descobrir_oisst(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os últimos dias da temperatura do mar (grade global de 0,25°), um arquivo por dia."""
    meses = {
        f"{agora - timedelta(days=dias):%Y%m}"
        for dias in range(DIAS_RECENTES_DO_OISST + 1)
    }
    por_dia: dict[str, str] = {}
    for mes in sorted(meses):
        por_dia |= {
            dia: f"{OISST}/{mes}/{nome}"
            for dia, nome in _arquivos_do_oisst_no_mes(cliente, mes).items()
        }
    if not por_dia:
        raise ErroDeDescoberta(f"OISST: nenhum arquivo em {sorted(meses)}")
    recentes = sorted(por_dia)[-DIAS_RECENTES_DO_OISST:]
    return [Alvo(por_dia[dia], ".nc") for dia in recentes]


# ---- ECMWF open data (CC BY 4.0, sem conta): só chuva, temperatura a 2 m e pressão --------------
ECMWF = "https://data.ecmwf.int/forecasts"
PASSOS_DO_ECMWF = (24, 72, 120)  # horas à frente: 1, 3 e 5 dias
PARAMETROS_DO_ECMWF = frozenset({"tp", "2t", "msl"})


def endereco_do_ecmwf(dia: date, passo: int) -> str:
    """O arquivo GRIB2 da previsão operacional das 00 UTC, grade de 0,25°, para o passo em horas."""
    texto = f"{dia:%Y%m%d}"
    return f"{ECMWF}/{texto}/00z/ifs/0p25/oper/{texto}000000-{passo}h-oper-fc.grib2"


def recorte_do_ecmwf(url: str) -> Obter:
    """Grava em `destino` só as mensagens dos parâmetros da lista, lidas por trecho (HTTP Range).

    Mensagens GRIB coladas uma na outra são um GRIB válido. A previsão que ainda não saiu (índice
    404) é `SemArquivo`; índice sem um dos parâmetros é erro (o ECMWF mudou o formato)."""
    indice = url.removesuffix(".grib2") + ".index"

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        try:
            texto = cliente.ler(indice).conteudo.decode("utf-8")
        except requests.HTTPError as erro:
            if (
                erro.response is not None
                and erro.response.status_code == HTTP_NAO_ENCONTRADO
            ):
                raise SemArquivo(
                    "HTTP 404 (a previsão do dia ainda não saiu)"
                ) from erro
            raise
        mensagens = [json.loads(linha) for linha in texto.splitlines() if linha.strip()]
        escolhidas = [
            m
            for m in mensagens
            if m.get("levtype") == "sfc" and m.get("param") in PARAMETROS_DO_ECMWF
        ]
        if {m["param"] for m in escolhidas} != PARAMETROS_DO_ECMWF:
            raise ValueError(f"{indice}: faltam parâmetros no índice do ECMWF")
        with destino.open("wb") as saida:
            for mensagem in escolhidas:
                inicio = int(mensagem["_offset"])
                saida.write(
                    cliente.ler_trecho(
                        url, inicio, inicio + int(mensagem["_length"]) - 1
                    )
                )
        return {}

    return obter


def descobrir_ecmwf(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """A previsão de ontem às 00 UTC (a de hoje só sai de manhã), um arquivo por passo."""
    ontem = agora.date() - timedelta(days=1)
    urls = [endereco_do_ecmwf(ontem, passo) for passo in PASSOS_DO_ECMWF]
    return [Alvo(url, ".grib2", obter=recorte_do_ecmwf(url)) for url in urls]


# ---- MapBiomas (CC BY 4.0): estatísticas da Coleção 11 por município e por bioma e estado -------
PAGINA_DAS_ESTATISTICAS_DO_MAPBIOMAS = "https://brasil.mapbiomas.org/estatisticas/"
PLANILHAS_DO_MAPBIOMAS = re.compile(
    r'href="([^"]*(?:MUNICIPALITY[^"/]*|COL\.11-BIOME_STATE)\.xlsx)"', re.IGNORECASE
)


def descobrir_planilhas_do_mapbiomas(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """As planilhas por município (desmatamento, mineração, vegetação secundária, irrigação, safras)
    e a cobertura por bioma e estado, pelos links da página de estatísticas."""
    pagina = cliente.ler(PAGINA_DAS_ESTATISTICAS_DO_MAPBIOMAS).conteudo.decode(
        "utf-8", "replace"
    )
    links = sorted(set(PLANILHAS_DO_MAPBIOMAS.findall(pagina)))
    if not links:
        raise ErroDeDescoberta("MapBiomas: nenhuma planilha na página de estatísticas")
    return [
        Alvo(urljoin(PAGINA_DAS_ESTATISTICAS_DO_MAPBIOMAS, link), ".xlsx")
        for link in links
    ]


# ---- TerraBrasilis (PRODES e DETER, do INPE; CC BY-SA 4.0) só pelo WFS, sem a geometria --------
WFS_DO_TERRABRASILIS = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
LINHAS_POR_PAGINA_DO_WFS = (
    25_000  # o GeoServer corta em 50.000; o PRODES do Cerrado de 2024 tem 62.372
)
PRIMEIRO_ANO_DO_DETER_NA_AMAZONIA = 2015
PRIMEIRO_ANO_DO_DETER_NO_CERRADO = 2018
PRIMEIRO_ANO_DO_PRODES = 2000
ANOS_RECENTES_DO_PRODES = 3  # os anos fechados não mudam: a carga única guarda o resto
PADRAO_DA_CONTAGEM_DO_WFS = re.compile(r'numberOfFeatures="(\d+)"')


@dataclass(frozen=True)
class Camada:
    """Uma camada do WFS: o nome, as colunas que ficam (sem a geometria) e como filtrar um ano."""

    nome: str
    campos: tuple[str, ...]
    ordem: str  # coluna única, para a paginação não repetir nem perder linha
    por_data: bool  # DETER filtra `view_date`; PRODES filtra `year`


DETER_AMAZONIA = Camada(
    "deter-amz:deter_amz",
    (
        "gid",
        "classname",
        "view_date",
        "areauckm",
        "areamunkm",
        "municipality",
        "mun_geocod",
        "uf",
        "publish_month",
    ),
    "gid",
    True,
)
DETER_CERRADO = Camada(
    "deter-cerrado-nb:deter_cerrado",
    (
        "gid",
        "classname",
        "view_date",
        "areatotalkm",
        "areauckm",
        "areamunkm",
        "municipality",
        "uf",
        "publish_month",
    ),
    "gid",
    True,
)
CAMPOS_DO_PRODES = (
    "uuid",
    "state",
    "path_row",
    "main_class",
    "class_name",
    "year",
    "area_km",
    "image_date",
    "source",
    "satellite",
    "sensor",
    "publish_year",
)
PRODES_AMAZONIA_LEGAL = Camada(
    "prodes-legal-amz:yearly_deforestation", CAMPOS_DO_PRODES, "uuid", False
)
PRODES_CERRADO = Camada(
    "prodes-cerrado-nb:yearly_deforestation", CAMPOS_DO_PRODES, "uuid", False
)


def filtro_do_ano(camada: Camada, ano: int) -> str:
    if camada.por_data:
        return f"view_date >= {ano}-01-01 AND view_date < {ano + 1}-01-01"
    return f"year = {ano}"


def _consulta_do_wfs(camada: Camada, ano: int, **extras: str | int) -> str:
    parametros = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": camada.nome,
        "cql_filter": filtro_do_ano(camada, ano),
        **extras,
    }
    return f"{WFS_DO_TERRABRASILIS}?{urlencode(parametros)}"


def linhas_do_ano(cliente: Cliente, camada: Camada, ano: int) -> int:
    """Quantos registros a camada tem no ano (`resultType=hits`: a contagem, sem baixar nada)."""
    resposta = cliente.ler(_consulta_do_wfs(camada, ano, resultType="hits"))
    achado = PADRAO_DA_CONTAGEM_DO_WFS.search(
        resposta.conteudo.decode("utf-8", "replace")
    )
    if achado is None:
        raise ErroDeDescoberta(
            f"TerraBrasilis: sem contagem para {camada.nome} em {ano}"
        )
    return int(achado.group(1))


def alvos_do_ano(cliente: Cliente, camada: Camada, ano: int) -> list[Alvo]:
    """Um CSV por página de `LINHAS_POR_PAGINA_DO_WFS` registros do ano (nenhum, se o ano é vazio)."""
    total = linhas_do_ano(cliente, camada, ano)
    return [
        Alvo(
            _consulta_do_wfs(
                camada,
                ano,
                outputFormat="csv",
                propertyName=",".join(camada.campos),
                sortBy=camada.ordem,
                startIndex=inicio,
                maxFeatures=LINHAS_POR_PAGINA_DO_WFS,
            ),
            ".csv",
        )
        for inicio in range(0, total, LINHAS_POR_PAGINA_DO_WFS)
    ]


def descobrir_deter(camada: Camada, primeiro_ano: int) -> Descobrir:
    """Todos os anos do DETER, do primeiro ao corrente (cada ano é um conjunto de páginas)."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [
            alvo
            for ano in range(primeiro_ano, agora.year + 1)
            for alvo in alvos_do_ano(cliente, camada, ano)
        ]

    return _descobrir


def descobrir_prodes_recente(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os últimos anos do PRODES nas duas camadas (o PRODES do ano fecha no fim do ano seguinte)."""
    primeiro = agora.year - ANOS_RECENTES_DO_PRODES + 1
    return [
        alvo
        for camada in (PRODES_AMAZONIA_LEGAL, PRODES_CERRADO)
        for ano in range(primeiro, agora.year + 1)
        for alvo in alvos_do_ano(cliente, camada, ano)
    ]


def descobrir_prodes_historico(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os anos do PRODES anteriores à janela recente: a carga única, que só roda pelo id."""
    ultimo = agora.year - ANOS_RECENTES_DO_PRODES
    return [
        alvo
        for camada in (PRODES_AMAZONIA_LEGAL, PRODES_CERRADO)
        for ano in range(PRIMEIRO_ANO_DO_PRODES, ultimo + 1)
        for alvo in alvos_do_ano(cliente, camada, ano)
    ]


# ---- ONS: o ENA e o EAR por bacia, REE e reservatório (por subsistema já é de `ons-hidrologia`) --
PACOTES_DE_HIDROLOGIA_DETALHADA_DO_ONS = (
    "ear-diario-por-bacia",
    "ear-diario-por-ree-reservatorio-equivalente-de-energia",
    "ear-diario-por-reservatorio",
    "ena-diario-por-bacia",
    "ena-diario-por-ree-reservatorio-equivalente-de-energia",
    "ena-diario-por-reservatorio",
)

# ---- Climate TRACE (CC BY 4.0): emissões por país e setor, em JSON da API ------------------------
API_DO_CLIMATE_TRACE = "https://api.climatetrace.org/v6"
PRIMEIRO_ANO_DO_CLIMATE_TRACE = 2015
SETORES_DO_CLIMATE_TRACE = (
    "agriculture",
    "buildings",
    "fluorinated-gases",
    "forestry-and-land-use",
    "fossil-fuel-operations",
    "manufacturing",
    "mineral-extraction",
    "power",
    "transportation",
    "waste",
)


def _emissoes(ano: int, paises: str, setor: str = "") -> str:
    parametros = {"since": ano, "to": ano, "countries": paises}
    if setor:
        parametros["sectors"] = setor
    return f"{API_DO_CLIMATE_TRACE}/country/emissions?{urlencode(parametros, safe=',')}"


def _anos_do_climate_trace(agora: datetime) -> range:
    return range(
        PRIMEIRO_ANO_DO_CLIMATE_TRACE, agora.year - ANOS_DE_FOLGA_DAS_EMISSOES + 1
    )


def descobrir_emissoes_dos_paises(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """O total de cada ano, de todos os países (a lista de países vem da própria API)."""
    paises = json.loads(
        cliente.ler(f"{API_DO_CLIMATE_TRACE}/definitions/countries").conteudo
    )
    codigos = ",".join(sorted(p["alpha3"] for p in paises))
    if not codigos:
        raise ErroDeDescoberta("Climate TRACE: lista de países vazia")
    return [
        Alvo(_emissoes(ano, codigos), ".json") for ano in _anos_do_climate_trace(agora)
    ]


def descobrir_emissoes_do_brasil_por_setor(
    cliente: Cliente, agora: datetime
) -> list[Alvo]:
    return [
        Alvo(_emissoes(ano, "BRA", setor), ".json")
        for setor in SETORES_DO_CLIMATE_TRACE
        for ano in _anos_do_climate_trace(agora)
    ]


# ---- EDGAR (JRC, CC BY 4.0) e Carbon Monitor (CC BY 4.0) ----------------------------------------
EDGAR = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EDGAR/datasets/EDGAR_2025_GHG"
# o IEA_EDGAR_CO2 (CC BY-NC-ND) fica de fora; estes são do JRC, sob CC BY 4.0
ARQUIVOS_DO_EDGAR = {
    "edgar-ghg-ar5": "EDGAR_AR5_GHG_1970_2024.zip",
    "edgar-ch4": "EDGAR_CH4_1970_2024.zip",
    "edgar-n2o": "EDGAR_N2O_1970_2024.zip",
}
CARBON_MONITOR_GLOBAL = (
    "https://datas.carbonmonitor.org/API/downloadFullDataset.php?source=carbon_global"
)


def _um_arquivo(url: str, extensao: str) -> Descobrir:
    return lambda cliente, agora: [Alvo(url, extensao)]


# ---- as fontes -----------------------------------------------------------------------------------
def _fonte_da_serie(serie: Serie) -> Fonte:
    return Fonte(
        serie.id,
        serie.grupo,
        descobrir_serie(serie),
        serie.tipo,
        pausa_minima=PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS,
    )


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    pausa = PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS
    do_inpe = [
        Fonte(
            "inpe-queimadas-diario",
            "diaria",
            descobrir_focos_do_inpe("diario", DIAS_RECENTES_DO_INPE),
            pausa_minima=pausa,
        ),
        Fonte(
            "inpe-queimadas-mensal",
            "mensal",
            descobrir_focos_do_inpe("mensal", MESES_RECENTES_DO_INPE),
            pausa_minima=pausa,
        ),
        # a série mensal inteira (1998 em diante): grupo fora do cron, só roda pelo id
        Fonte(
            "inpe-queimadas-historico",
            "carga-unica",
            descobrir_focos_do_inpe("mensal", None),
            pesada=True,
            pausa_minima=pausa,
        ),
    ]
    do_firms = [
        Fonte(id_, "diaria", descobrir_firms(satelite), pausa_minima=pausa)
        for id_, satelite in SATELITES_DO_FIRMS.items()
    ]
    do_terrabrasilis = [
        Fonte(
            "terrabrasilis-deter-amazonia",
            "mensal",
            descobrir_deter(DETER_AMAZONIA, PRIMEIRO_ANO_DO_DETER_NA_AMAZONIA),
            pausa_minima=pausa,
        ),
        Fonte(
            "terrabrasilis-deter-cerrado",
            "mensal",
            descobrir_deter(DETER_CERRADO, PRIMEIRO_ANO_DO_DETER_NO_CERRADO),
            pausa_minima=pausa,
        ),
        Fonte(
            "terrabrasilis-prodes-recente",
            "mensal",
            descobrir_prodes_recente,
            pausa_minima=pausa,
        ),
        Fonte(
            "terrabrasilis-prodes-historico",
            "carga-unica",
            descobrir_prodes_historico,
            pesada=True,
            pausa_minima=pausa,
        ),
    ]
    do_noaa = [
        *(_fonte_da_serie(s) for s in SERIES_DO_NOAA),
        Fonte(
            "noaa-ghcn-diario-brasil",
            "mensal",
            descobrir_ghcn_do_brasil,
            pesada=True,
            pausa_minima=pausa,
        ),
        Fonte(
            "noaa-ghcn-mensal-temperatura",
            "mensal",
            descobrir_ghcn_mensal,
            pesada=True,
            pausa_minima=pausa,
        ),
        Fonte(
            "noaa-oisst-diario",
            "diaria",
            descobrir_oisst,
            pesada=True,
            pausa_minima=pausa,
        ),
    ]
    return [
        *do_inpe,
        *do_firms,
        Fonte(
            "inmet-estacoes",
            "mensal",
            descobrir_estacoes_do_inmet,
            "json",
            pausa_minima=pausa,
        ),
        *do_noaa,
        Fonte(
            "ecmwf-previsao-recortada",
            "diaria",
            descobrir_ecmwf,
            pausa_minima=pausa,
        ),
        Fonte(
            "mapbiomas-estatisticas",
            "mensal",
            descobrir_planilhas_do_mapbiomas,
            pesada=True,
            pausa_minima=pausa,
        ),
        *do_terrabrasilis,
        Fonte(
            "ons-hidrologia-detalhada",
            "semanal",
            _ckan(
                PORTAL_DO_ONS,
                *PACOTES_DE_HIDROLOGIA_DETALHADA_DO_ONS,
                formatos=FORMATOS_DO_ONS,
            ),
            pesada=True,
        ),
        Fonte(
            "climatetrace-paises",
            "mensal",
            descobrir_emissoes_dos_paises,
            "json",
            pausa_minima=pausa,
        ),
        Fonte(
            "climatetrace-brasil-setores",
            "mensal",
            descobrir_emissoes_do_brasil_por_setor,
            "json",
            pausa_minima=pausa,
        ),
        *(
            Fonte(
                id_,
                "mensal",
                _um_arquivo(f"{EDGAR}/{arquivo}", ".zip"),
                "zip",
                pesada=True,
                pausa_minima=pausa,
            )
            for id_, arquivo in ARQUIVOS_DO_EDGAR.items()
        ),
        Fonte(
            "carbonmonitor-global",
            "mensal",
            _um_arquivo(CARBON_MONITOR_GLOBAL, ".csv"),
            pausa_minima=pausa,
        ),
    ]


# páginas de termos que a vigia acompanha (avisa quando o texto muda); INPE, TerraBrasilis e EDGAR
# não têm página estável de termos (motivos em `_SEM_VIGIA`)
TERMOS_DO_CLIMA = {
    "termos-firms": "https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-information-policy",
    "termos-ecmwf": "https://www.ecmwf.int/en/forecasts/datasets/open-data",
    "termos-climatetrace": "https://climatetrace.org/terms",
    "termos-carbonmonitor": "https://carbonmonitor.org/about",
}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DO_CLIMA)
