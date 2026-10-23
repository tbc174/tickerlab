"""Lote "organismos": séries abertas de bancos centrais e organismos internacionais (rodada 1 da
pesquisa de dados escondidos, 22/10/2026; ADR 0102: coleta com ritmo, uso citando a fonte).

Cada série é um endereço de API pública, sem chave, que o arquivista guarda como veio. Nada aqui é
lido nem tratado: o que sai de cada resposta (valores, datas, séries) é tarefa da extração.

Regras (testes em `tests/test_base_arquivo_lote_organismos.py`):
- **uma fonte por série**, com id "família-série" (a família decide a licença e a marca em
  `src/banco/coletas.py`): `bce`, `ocde`, `worldbank`, `eurostat`, `nasa`, `noaa`, `fmi` e `bis`; o
  GLEIF entra na família `gleif` que já existia;
- série diária do BCE vira **duas janelas**: o histórico até o fim do ano passado (não muda mais,
  então o SHA-256 acusa "igual" e nada se acumula) e a janela que começa no ano passado (quase
  nada por dia); baixar o histórico inteiro todo dia guardaria 1,5 MB repetidos por série;
- API paginada (Banco Mundial, GLEIF) lê a primeira página, confere quantas existem e devolve todas;
  nunca se confia que "tudo cabe numa página";
- API que falha ou muda de formato é falha (`ErroDeDescoberta`), nunca "nada novo";
- nenhuma é `pesada`: a maior tem poucos MB e as APIs não mandam `ETag` nem `Last-Modified`, então
  o SHA-256 decide se o retrato mudou;
- o **FMI** e o **BIS** entram com a marca `nao_comercial` (termos lidos em 22/10/2026: uso comercial só
  com permissão) e a fonte citada; o dado fica para pesquisa e para a tela com a fonte, nunca vai
  para venda (ADR 0102);
- **fora daqui**: ENSO, GHCN e OISST do NOAA (linha 290 da fila), o golden copy do GLEIF (287) e as
  fontes do grupo "depois" da rodada 1 (SNB, Riksbank, ABS, ILO, Companies House, INMET, CHIRPS e UNCTAD:
  a licença ainda não foi lida).
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from src.commodities.cafe import regioes

PRIMEIRO_ANO_DAS_SERIES_DIARIAS = (
    1999  # o euro nasce em 1/1/1999: nada do BCE vem antes
)
PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS = (
    1.0  # APIs abertas, mas de terceiros (ADR 0082)
)
POR_PAGINA_DO_BANCO_MUNDIAL = 1000
POR_PAGINA_DO_GLEIF = 200

# ---- BCE (Data Portal, SDMX; "Source: ECB statistics") -----------------------------------------
BCE = "https://data-api.ecb.europa.eu/service/data"
FORMATO_DO_BCE = "format=csvdata"


@dataclass(frozen=True)
class Serie:
    """Uma série de uma API: o id da fonte, o endereço e como (e quando) coletar."""

    id: str
    url: str  # com `{periodo}` quando a série é diária e vira duas janelas (`janelas_diarias`)
    extensao: str
    grupo: str = (
        "semanal"  # a API publica de dia ou de mês, mas o SHA-256 decide o que é novo
    )
    tipo: str = "arquivo"


def _bce(chave: str, parametros: str = "") -> str:
    return f"{BCE}/{chave}?{parametros}{FORMATO_DO_BCE}"


SERIES_DO_BCE = (
    # câmbio de referência e curva de juros: diários, em janelas (o histórico passa de 1 MB)
    Serie(
        "bce-cambio-dolar",
        _bce("EXR/D.USD.EUR.SP00.A", "{periodo}&"),
        ".csv",
        "diaria",
    ),
    Serie(
        "bce-cambio-real",
        _bce("EXR/D.BRL.EUR.SP00.A", "{periodo}&"),
        ".csv",
        "diaria",
    ),
    Serie(
        "bce-curva-10a",
        _bce("YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", "{periodo}&"),
        ".csv",
        "diaria",
    ),
    # taxa principal de refinanciamento, inflação (IPCH), balanço agregado dos bancos da zona do
    # euro e juro do crédito às empresas: pequenos, histórico inteiro
    Serie("bce-juro-principal", _bce("FM/B.U2.EUR.4F.KR.MRR_FR.LEV"), ".csv"),
    Serie("bce-inflacao-ipch", _bce("ICP/M.U2.N.000000.4.ANR"), ".csv"),
    Serie("bce-balanco-bancos", _bce("BSI/M.U2.N.A.A20.A.1.U2.2250.Z01.E"), ".csv"),
    Serie("bce-juro-credito", _bce("MIR/M.U2.B.A2A.A.R.A.2240.EUR.N"), ".csv"),
)

# ---- OCDE (SDMX; citar "OECD (ano), (conjunto), DOI ou URL, acessado em…") ----------------------
OCDE = "https://sdmx.oecd.org/public/rest/data"
FORMATO_DA_OCDE = "format=csvfilewithlabels"
# indicador antecedente composto (CLI): Brasil primeiro, depois os maiores parceiros e pares
PAISES_DO_CLI = "BRA+USA+CHN+DEU+IND+JPN+GBR+FRA+ITA+MEX+ARG+ZAF"
SERIES_DA_OCDE = (
    Serie(
        "ocde-cli",
        f"{OCDE}/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/{PAISES_DO_CLI}.M.LI...AA...H"
        f"?startPeriod=1990-01&{FORMATO_DA_OCDE}",
        ".csv",
    ),
)

# ---- Eurostat (CC BY 4.0; só a UE: o reuso comercial pede tirar os países de fora dela) ---------
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
# o filtro de país é o que impede de baixar a UE inteira (e traz só quem a licença cobre)
PAISES_DO_EUROSTAT = ("EA20", "EU27_2020", "DE", "FR", "IT", "ES", "PT", "NL")
FILTRO_DE_PAIS_DO_EUROSTAT = "&".join(f"geo={p}" for p in PAISES_DO_EUROSTAT)


def _eurostat(conjunto: str, filtros: str = "") -> str:
    return f"{EUROSTAT}/{conjunto}?{FILTRO_DE_PAIS_DO_EUROSTAT}{filtros}&lang=EN"


SERIES_DO_EUROSTAT = (
    Serie("eurostat-confianca", _eurostat("ei_bsco_m"), ".json", tipo="json"),
    Serie(
        "eurostat-ipch",
        _eurostat("prc_hicp_manr", "&coicop=CP00"),
        ".json",
        tipo="json",
    ),
    Serie(
        "eurostat-desemprego",
        _eurostat("une_rt_m", "&s_adj=SA&age=TOTAL&sex=T&unit=PC_ACT"),
        ".json",
        tipo="json",
    ),
    Serie(
        "eurostat-pib",
        _eurostat("namq_10_gdp", "&s_adj=SCA&unit=CLV_PCH_PRE&na_item=B1GQ"),
        ".json",
        tipo="json",
    ),
    Serie("eurostat-juro-longo", _eurostat("irt_lt_mcby_m"), ".json", tipo="json"),
    Serie(
        "eurostat-producao-industrial",
        _eurostat("sts_inpr_m", "&s_adj=SCA&nace_r2=B-D&unit=I21"),
        ".json",
        tipo="json",
    ),
)

# ---- BIS (estatísticas em CSV; termos: só uso não comercial sem permissão) -----------------------
BIS = "https://stats.bis.org/api/v2/data/dataflow/BIS"
PAISES_DO_BIS = "BR+US+XM+CN"  # XM: área do euro
SERIES_DO_BIS = (
    Serie(
        "bis-cambio-efetivo-nominal",
        f"{BIS}/WS_EER/1.0/M.N.B.{PAISES_DO_BIS}?format=csv",
        ".csv",
    ),
    Serie(
        "bis-cambio-efetivo-real",
        f"{BIS}/WS_EER/1.0/M.R.B.{PAISES_DO_BIS}?format=csv",
        ".csv",
    ),
    Serie(
        "bis-juro-dos-bancos-centrais",
        f"{BIS}/WS_CBPOL/1.0/M.{PAISES_DO_BIS}?format=csv",
        ".csv",
    ),
    Serie(
        "bis-preco-de-imoveis", f"{BIS}/WS_SPP/1.0/Q.{PAISES_DO_BIS}?format=csv", ".csv"
    ),
    Serie(
        "bis-inflacao-longa",
        f"{BIS}/WS_LONG_CPI/1.0/M.{PAISES_DO_BIS}?format=csv",
        ".csv",
    ),
    Serie("bis-cambio", f"{BIS}/WS_XRU/1.0/M.BR?format=csv", ".csv"),
    Serie(
        "bis-lacuna-de-credito",
        f"{BIS}/WS_CREDIT_GAP/1.0/Q.BR.P.A.C?format=csv",
        ".csv",
    ),
)

# ---- FMI (SDMX novo e Data Mapper; © FMI: uso comercial só com permissão) -----------------------
FMI_SDMX = "https://api.imf.org/external/sdmx/2.1/data"
FMI_PERSPECTIVAS = "https://www.imf.org/external/datamapper/api/v1"
# o Data Mapper devolve as Perspectivas da Economia Mundial (WEO): crescimento, inflação, conta
# corrente e dívida bruta em % do PIB, por país, com as projeções do FMI
INDICADORES_DO_WEO = ("NGDP_RPCH", "PCPIPCH", "BCA_NGDPD", "GGXWDG_NGDP")
SERIES_DO_FMI = (
    Serie("fmi-cambio", f"{FMI_SDMX}/IMF.STA,ER/BRA..?startPeriod=2000", ".xml"),
    Serie("fmi-inflacao", f"{FMI_SDMX}/IMF.STA,CPI/BRA..?startPeriod=2000", ".xml"),
    Serie("fmi-reservas-do-mundo", f"{FMI_SDMX}/IMF.STA,COFER/all", ".xml"),
    *(
        Serie(
            f"fmi-weo-{indicador.lower()}",
            f"{FMI_PERSPECTIVAS}/{indicador}",
            ".json",
            tipo="json",
        )
        for indicador in INDICADORES_DO_WEO
    ),
)

# ---- NASA POWER (domínio público; clima de ponto, nas regiões de café que a base já usa) --------
NASA_POWER = "https://power.larc.nasa.gov/api/temporal/monthly/point"
PARAMETROS_DA_NASA = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN"
PRIMEIRO_ANO_DA_NASA = 1990
# centro aproximado (grau cheio e meio, a grade da NASA é de 0,5° × 0,625°) da área de café de cada
# região de `src/commodities/cafe/regioes.py`: o ponto do município-sede da região, não a média
COORDENADAS_DAS_REGIOES = {
    "sul-de-minas": (-21.5, -45.5),
    "cerrado-mineiro": (-18.9, -47.0),
    "matas-de-minas": (-20.3, -42.0),
    "chapada-de-minas": (-17.5, -43.0),
    "mogiana": (-20.9, -47.5),
    "alta-paulista": (-22.2, -49.7),
    "norte-do-parana": (-23.3, -50.7),
    "oeste-da-bahia": (-12.1, -45.0),
    "planalto-da-bahia": (-14.9, -40.8),
    "es-montanhas": (-20.4, -41.1),
    "es-norte": (-18.7, -40.4),
    "rondonia": (-10.9, -61.9),
    "bahia-atlantico": (-14.8, -39.3),
}

# ---- NOAA CPC (domínio público; teleconexões que movem o clima do Hemisfério Norte) ---------------
# ENSO (ONI, Niño, SOI), GHCN e OISST são da linha 290 da fila: não entram aqui
CPC = "https://www.cpc.ncep.noaa.gov"
SERIES_DO_NOAA = (
    Serie("noaa-teleconexoes", f"{CPC}/data/indices/tele_index.nh", ".txt"),
    Serie(
        "noaa-nao",
        f"{CPC}/products/precip/CWlink/pna/norm.nao.monthly.b5001.current.ascii.table",
        ".txt",
    ),
    Serie(
        "noaa-ao",
        f"{CPC}/products/precip/CWlink/daily_ao_index/monthly.ao.index.b50.current.ascii.table",
        ".txt",
    ),
    Serie(
        "noaa-pna",
        f"{CPC}/products/precip/CWlink/pna/norm.pna.monthly.b5001.current.ascii.table",
        ".txt",
    ),
)

# ---- Banco Mundial (CC BY 4.0 na maioria; os indicadores abaixo são do WDI, fonte 2) -------------
BANCO_MUNDIAL = "https://api.worldbank.org/v2"
# Brasil primeiro: PIB, crescimento, inflação, desemprego, dívida externa, comércio e população
INDICADORES_DO_BRASIL = (
    "NY.GDP.MKTP.CD",
    "NY.GDP.MKTP.KD.ZG",
    "FP.CPI.TOTL.ZG",
    "SL.UEM.TOTL.ZS",
    "DT.DOD.DECT.CD",
    "NE.EXP.GNFS.ZS",
    "NE.IMP.GNFS.ZS",
    "SP.POP.TOTL",
    "FR.INR.RINR",
    "BN.CAB.XOKA.GD.ZS",
)
# o mundo inteiro (todos os países) só para os indicadores de comparação
INDICADORES_DO_MUNDO = ("NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG", "SP.POP.TOTL")
# GLEIF: quem emite LEI e as autoridades de registro (o que falta além da família `gleif-br`)
GLEIF = "https://api.gleif.org/api/v1"
ENDPOINTS_DO_GLEIF = {
    "gleif-emissores": "lei-issuers",
    "gleif-autoridades-de-registro": "registration-authorities",
}


# ---- descobertas ---------------------------------------------------------------------------------
def janelas_diarias(url: str, agora: datetime) -> list[Alvo]:
    """O histórico fechado (do euro ao fim do ano passado) e a janela aberta (do início do ano
    passado em diante): o histórico fechado nunca muda, então vira "igual" a cada coleta."""
    ano = agora.year
    historico = (
        f"startPeriod={PRIMEIRO_ANO_DAS_SERIES_DIARIAS}-01-01&endPeriod={ano - 1}-12-31"
    )
    recente = f"startPeriod={ano - 1}-01-01"
    return [Alvo(url.format(periodo=p), ".csv") for p in (historico, recente)]


def descobrir_serie(serie: Serie) -> Descobrir:
    """Um endereço por série; as diárias do BCE (`{periodo}` no endereço) viram duas janelas."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        if "{periodo}" in serie.url:
            return janelas_diarias(serie.url, agora)
        return [Alvo(serie.url, serie.extensao)]

    return _descobrir


def _paginas_do_banco_mundial(cliente: Cliente, url: str) -> int:
    """Quantas páginas a API devolve (o cabeçalho do JSON, `[{"pages": n, ...}, [...]]`)."""
    resposta = json.loads(cliente.ler(url.format(pagina=1)).conteudo)
    if not isinstance(resposta, list) or "pages" not in resposta[0]:
        raise ErroDeDescoberta(f"Banco Mundial: resposta inesperada em {url}")
    return int(resposta[0]["pages"])


def _indicadores_do_banco_mundial(pais: str, indicadores: Iterable[str]) -> str:
    return (
        f"{BANCO_MUNDIAL}/country/{pais}/indicator/{';'.join(indicadores)}"
        f"?format=json&source=2&per_page={POR_PAGINA_DO_BANCO_MUNDIAL}&page={{pagina}}"
    )


def descobrir_banco_mundial(pais: str, indicadores: Iterable[str]) -> Descobrir:
    """Todas as páginas dos indicadores do país (`all` é o mundo todo): cada página vira um JSON."""
    url = _indicadores_do_banco_mundial(pais, indicadores)

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        paginas = _paginas_do_banco_mundial(cliente, url)
        return [Alvo(url.format(pagina=n), ".json") for n in range(1, paginas + 1)]

    return _descobrir


def endereco_do_gleif(endpoint: str, pagina: int) -> str:
    return (
        f"{GLEIF}/{endpoint}?page%5Bsize%5D={POR_PAGINA_DO_GLEIF}"
        f"&page%5Bnumber%5D={pagina}"
    )


def descobrir_gleif(endpoint: str) -> Descobrir:
    """Todas as páginas de uma lista do GLEIF (a paginação vem em `meta.pagination.lastPage`)."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        primeira = json.loads(cliente.ler(endereco_do_gleif(endpoint, 1)).conteudo)
        ultima = int(primeira["meta"]["pagination"]["lastPage"])
        return [
            Alvo(endereco_do_gleif(endpoint, n), ".json") for n in range(1, ultima + 1)
        ]

    return _descobrir


def endereco_da_nasa(latitude: float, longitude: float, agora: datetime) -> str:
    return (
        f"{NASA_POWER}?parameters={PARAMETROS_DA_NASA}&community=AG"
        f"&longitude={longitude}&latitude={latitude}"
        f"&start={PRIMEIRO_ANO_DA_NASA}&end={agora.year}&format=JSON"
    )


def descobrir_nasa(regiao: str) -> Descobrir:
    """O clima mensal do ponto da região, de 1990 até o ano da coleta."""
    latitude, longitude = COORDENADAS_DAS_REGIOES[regiao]

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [Alvo(endereco_da_nasa(latitude, longitude, agora), ".json")]

    return _descobrir


def regioes_sem_ponto() -> set[str]:
    """As regiões do café sem coordenada aqui (o teste exige que seja vazio)."""
    return {d.id for d in regioes.DEFINICOES} - COORDENADAS_DAS_REGIOES.keys()


# ---- as fontes -----------------------------------------------------------------------------------
SERIES = (
    *SERIES_DO_BCE,
    *SERIES_DA_OCDE,
    *SERIES_DO_EUROSTAT,
    *SERIES_DO_BIS,
    *SERIES_DO_FMI,
    *SERIES_DO_NOAA,
)


def _fonte_da_serie(serie: Serie) -> Fonte:
    return Fonte(
        serie.id,
        serie.grupo,
        descobrir_serie(serie),
        serie.tipo,
        pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
    )


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    do_banco_mundial = [
        Fonte(
            "worldbank-brasil",
            "mensal",
            descobrir_banco_mundial("BRA", INDICADORES_DO_BRASIL),
            "json",
            pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
        ),
        *(
            Fonte(
                f"worldbank-mundo-{indicador.lower().replace('.', '-')}",
                "mensal",
                descobrir_banco_mundial("all", (indicador,)),
                "json",
                pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
            )
            for indicador in INDICADORES_DO_MUNDO
        ),
    ]
    do_gleif = [
        Fonte(
            id_,
            "semanal",
            descobrir_gleif(endpoint),
            "json",
            pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
        )
        for id_, endpoint in ENDPOINTS_DO_GLEIF.items()
    ]
    da_nasa = [
        Fonte(
            f"nasa-power-{regiao}",
            "mensal",
            descobrir_nasa(regiao),
            "json",
            pausa_minima=PAUSA_ENTRE_PEDIDOS_A_ORGAOS_EM_SEGUNDOS,
        )
        for regiao in COORDENADAS_DAS_REGIOES
    ]
    return [
        *(_fonte_da_serie(s) for s in SERIES),
        *do_banco_mundial,
        *do_gleif,
        *da_nasa,
    ]


# páginas de termos que a vigia acompanha (avisa quando o texto muda); FMI, GLEIF e Banco Mundial
# ficam com o PR dos vigias de termos. A OCDE responde com o desafio anti-robô da Cloudflare (403,
# 22/10/2026): a página de termos dela espera outra via, sem contorno
TERMOS_DOS_ORGAOS = {
    "termos-bce": "https://www.ecb.europa.eu/services/disclaimer/html/index.en.html",
    "termos-eurostat": "https://ec.europa.eu/eurostat/web/main/help/copyright-notice",
    "termos-bis": "https://www.bis.org/terms_conditions.htm",
    "termos-nasa-power": "https://power.larc.nasa.gov/docs/referencing/",
    "termos-noaa": "https://www.weather.gov/disclaimer",  # o CPC é do Serviço Meteorológico dos EUA
}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DOS_ORGAOS)
