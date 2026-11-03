"""O órgão de cada família de fonte, como a página Dados o escreve (linha 592 da fila, plano de 03/11/2026).

A família é o começo do id da coleta ("cvm-sancionador" → "cvm"). Aqui fica só o que o código não sabe
sozinho: o nome que uma pessoa reconhece e o endereço oficial de quem publica. A licença, a marca e o
uso saem de `src/banco/coletas.py` e de `base/arquivo/registro.py`. Família nova sem linha aqui **dá
erro** no teste e no build, em vez de aparecer crua ou sumir da página.

O link é a página de dados (ou a página inicial) do próprio órgão, num domínio de onde o TickerLab já
coleta (um teste confere). Sem endereço oficial conhecido, fica `None`: a página não inventa link.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Orgao:
    nome: str
    link: str | None


# famílias que não são fonte de dado: cópias dos termos de uso (prova interna da versão lida) e a lista
# de conjuntos dos portais (metadados para achar fonte nova). Ficam fora da lista pública.
NAO_SAO_FONTE = ("termos", "catalogo")

ORGAO_DA_FAMILIA: dict[str, Orgao] = {
    # Brasil: reguladores e agências
    "anac": Orgao("ANAC (aviação civil)", "https://sistemas.anac.gov.br/dadosabertos/"),
    "anatel": Orgao(
        "Anatel (telecomunicações)", "https://www.anatel.gov.br/dadosabertos/"
    ),
    "ancine": Orgao("Ancine (audiovisual)", "https://dados.ancine.gov.br/"),
    "aneel": Orgao("ANEEL (energia elétrica)", "https://dadosabertos.aneel.gov.br/"),
    "anm": Orgao("ANM (mineração)", "https://dadosabertos.anm.gov.br/"),
    "anp": Orgao(
        "ANP (petróleo, gás e combustíveis)",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos",
    ),
    "ans": Orgao("ANS (planos de saúde)", "https://dadosabertos.ans.gov.br/"),
    "antt": Orgao("ANTT (transportes terrestres)", "https://dados.antt.gov.br/"),
    "anvisa": Orgao("Anvisa (vigilância sanitária)", "https://dados.anvisa.gov.br/"),
    "ccee": Orgao(
        "CCEE (comercialização de energia)", "https://dadosabertos.ccee.org.br/"
    ),
    "cvm": Orgao("CVM (mercado de capitais)", "https://dados.cvm.gov.br/"),
    "epe": Orgao("EPE (pesquisa energética)", "https://www.epe.gov.br/"),
    "ons": Orgao("ONS (operador do sistema elétrico)", "https://dados.ons.org.br/"),
    "susep": Orgao("SUSEP (seguros)", "https://dados.susep.gov.br/"),
    # Brasil: governo federal, bancos públicos e tribunais
    "bcb": Orgao("Banco Central do Brasil", "https://dadosabertos.bcb.gov.br/"),
    "bndes": Orgao("BNDES", "https://dadosabertos.bndes.gov.br/"),
    "cgu": Orgao("CGU (cadastros de sanções)", "https://portaldatransparencia.gov.br/"),
    "comexstat": Orgao("Comex Stat (MDIC)", "https://balanca.mdic.gov.br/balanca/bd/"),
    "comprasgov": Orgao(
        "Compras.gov.br (Ministério da Gestão)", "https://dadosabertos.compras.gov.br/"
    ),
    "conab": Orgao("Conab (safras)", "https://www.gov.br/conab/"),
    "ibama": Orgao("IBAMA (autos e embargos)", "https://dadosabertos.ibama.gov.br/"),
    "ibge": Orgao("IBGE", "https://www.ibge.gov.br/"),
    "inep": Orgao("INEP (educação)", "https://www.gov.br/inep/"),
    "inmet": Orgao("INMET (meteorologia)", "https://portal.inmet.gov.br/"),
    "inpe": Orgao(
        "INPE (queimadas)", "https://terrabrasilis.dpi.inpe.br/queimadas/portal/"
    ),
    "inpi": Orgao("INPI (patentes e marcas)", "https://dadosabertos.inpi.gov.br/"),
    "inss": Orgao("INSS", "https://dadosabertos.inss.gov.br/"),
    "ipea": Orgao("Ipea (IPEADATA)", "https://www.ipeadata.gov.br/"),
    "mapa": Orgao(
        "Ministério da Agricultura (SIPEAGRO)", "https://dados.agricultura.gov.br/"
    ),
    "mme": Orgao(
        "Ministério de Minas e Energia (REIDI)", "https://dadosabertos.mme.gov.br/"
    ),
    "mte": Orgao(
        "Ministério do Trabalho (Lista Suja)", "https://www.gov.br/trabalho-e-emprego/"
    ),
    "pgfn": Orgao("PGFN (dívida ativa)", "https://dadosabertos.pgfn.gov.br/"),
    "pncp": Orgao("PNCP (contratações públicas)", "https://pncp.gov.br/"),
    "rfb": Orgao("Receita Federal (CNPJ)", "https://www.gov.br/receitafederal/"),
    "seges": Orgao(
        "SEGES (compras públicas, Ministério da Gestão)", "https://www.gov.br/compras/"
    ),
    "senatran": Orgao(
        "Senatran (frota de veículos)", "https://www.gov.br/transportes/"
    ),
    "tcu": Orgao("TCU (Tribunal de Contas da União)", "https://contas.tcu.gov.br/"),
    "terrabrasilis": Orgao(
        "INPE (TerraBrasilis, desmatamento)", "https://terrabrasilis.dpi.inpe.br/"
    ),
    "tesouro": Orgao("Tesouro Nacional", "https://www.tesourotransparente.gov.br/"),
    "transferegov": Orgao(
        "Transferegov (Ministério da Gestão)", "https://www.gov.br/transferegov/"
    ),
    "transparencia": Orgao(
        "Portal da Transparência (CGU)", "https://portaldatransparencia.gov.br/"
    ),
    # Brasil: estados, Legislativo, imprensa pública e mercado
    "b3": Orgao("B3 (bolsa)", "https://www.b3.com.br/"),
    "camara": Orgao(
        "Câmara dos Deputados (Agência Câmara)", "https://www.camara.leg.br/"
    ),
    "ebc": Orgao("EBC (Agência Brasil)", "https://agenciabrasil.ebc.com.br/"),
    "govmg": Orgao(
        "Governo de Minas Gerais (dados abertos)", "https://dados.mg.gov.br/"
    ),
    "govsc": Orgao(
        "Governo de Santa Catarina (dados abertos)", "https://dados.sc.gov.br/"
    ),
    "querido": Orgao(
        "Querido Diário (Open Knowledge Brasil)", "https://queridodiario.ok.org.br/"
    ),
    "senado": Orgao("Senado Federal (Agência Senado)", "https://www12.senado.leg.br/"),
    "tce": Orgao("TCE-PR (Tribunal de Contas do Paraná)", "https://pit.tce.pr.gov.br/"),
    "mapbiomas": Orgao("MapBiomas (uso da terra)", "https://brasil.mapbiomas.org/"),
    # café e agricultura
    "cecafe": Orgao("Cecafé (exportadores de café)", "https://www.cecafe.com.br/"),
    "faostat": Orgao("FAO (FAOSTAT)", "https://www.fao.org/faostat/"),
    "fnc": Orgao(
        "FNC (cafeicultores da Colômbia)", "https://federaciondecafeteros.org/"
    ),
    "ico": Orgao("OIC (Organização Internacional do Café)", "https://ico.org/"),
    "usda": Orgao("USDA (agricultura dos EUA)", "https://apps.fas.usda.gov/psdonline/"),
    # clima e meio ambiente
    "carbonmonitor": Orgao("Carbon Monitor (emissões)", "https://carbonmonitor.org/"),
    "chirps": Orgao(
        "CHIRPS v2 (chuva por satélite, UCSB)", "https://www.chc.ucsb.edu/data/chirps"
    ),
    "chirps3": Orgao(
        "CHIRPS v3 (chuva por satélite, UCSB)", "https://www.chc.ucsb.edu/data"
    ),
    "climatetrace": Orgao("Climate TRACE (emissões)", "https://climatetrace.org/"),
    "ecmwf": Orgao("ECMWF (previsão do tempo europeia)", "https://www.ecmwf.int/"),
    "edgar": Orgao(
        "EDGAR (emissões, Comissão Europeia)",
        "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EDGAR/",
    ),
    "firms": Orgao(
        "NASA FIRMS (focos de incêndio)", "https://firms.modaps.eosdis.nasa.gov/"
    ),
    "nasa": Orgao("NASA POWER (clima)", "https://power.larc.nasa.gov/"),
    "noaa": Orgao("NOAA (clima, EUA)", "https://www.cpc.ncep.noaa.gov/"),
    # EUA
    "bls": Orgao("BLS (estatísticas do trabalho, EUA)", "https://www.bls.gov/"),
    "census": Orgao("U.S. Census Bureau", "https://www.census.gov/"),
    "cftc": Orgao("CFTC (derivativos, EUA)", "https://www.cftc.gov/"),
    "eia": Orgao("EIA (energia, EUA)", "https://www.eia.gov/"),
    "fed": Orgao("Federal Reserve", "https://www.federalreserve.gov/"),
    "iex": Orgao("IEX (bolsa dos EUA)", "https://iextrading.com/"),
    "nyfed": Orgao("Federal Reserve de Nova York", "https://www.newyorkfed.org/"),
    "ofac": Orgao("OFAC (sanções, EUA)", "https://ofac.treasury.gov/"),
    "ofr": Orgao(
        "OFR (pesquisa financeira, Tesouro dos EUA)",
        "https://www.financialresearch.gov/",
    ),
    "sec": Orgao("SEC (EDGAR, empresas dos EUA)", "https://www.sec.gov/"),
    "tic": Orgao(
        "TIC (capital estrangeiro, Tesouro dos EUA)",
        "https://home.treasury.gov/data/treasury-international-capital-tic-system",
    ),
    "treasury": Orgao(
        "Tesouro dos EUA (Fiscal Data)", "https://fiscaldata.treasury.gov/"
    ),
    "yahoo": Orgao("Yahoo Finance (preços)", "https://finance.yahoo.com/"),
    # Europa e organismos internacionais
    "bce": Orgao("Banco Central Europeu", "https://data.ecb.europa.eu/"),
    "bis": Orgao(
        "BIS (Banco de Compensações Internacionais)", "https://www.bis.org/statistics/"
    ),
    "bm": Orgao(
        "Banco Mundial (Pink Sheet, preços de commodities)",
        "https://www.worldbank.org/en/research/commodity-markets",
    ),
    "epo": Orgao("EPO (patentes europeias)", "https://data.epo.org/"),
    "eufsf": Orgao(
        "União Europeia (sanções financeiras)", "https://webgate.ec.europa.eu/fsd/fsf"
    ),
    "eurostat": Orgao("Eurostat", "https://ec.europa.eu/eurostat"),
    "fmi": Orgao("FMI", "https://www.imf.org/"),
    "gleif": Orgao("GLEIF (identificador LEI)", "https://www.gleif.org/"),
    "ocde": Orgao("OCDE", "https://www.oecd.org/"),
    "ofsi": Orgao("OFSI (sanções, Reino Unido)", "https://sanctionslist.fcdo.gov.uk/"),
    "wipo": Orgao("OMPI (WIPO, propriedade intelectual)", "https://www.wipo.int/"),
    "worldbank": Orgao("Banco Mundial (indicadores)", "https://data.worldbank.org/"),
    # pesquisa, enciclopédias e notícias
    "crossref": Orgao("Crossref (artigos científicos)", "https://www.crossref.org/"),
    "gdelt": Orgao("GDELT Project (notícias)", "https://www.gdeltproject.org/"),
    "openalex": Orgao("OpenAlex (artigos científicos)", "https://openalex.org/"),
    "wiki": Orgao("Wikimedia (acessos à Wikipédia)", "https://wikimedia.org/"),
    "wikidata": Orgao("Wikidata", "https://www.wikidata.org/"),
    # cripto
    "btc": Orgao("Rede Bitcoin (lida por nó próprio)", None),
    "kraken": Orgao("Kraken (corretora de cripto)", "https://www.kraken.com/"),
    "mb": Orgao("Mercado Bitcoin (corretora de cripto)", None),
    # páginas públicas guardadas como prova
    "assessoria": Orgao("Assessorias de M&A (páginas públicas)", None),
    "contrapartes": Orgao("Imprensa e páginas públicas", None),
    "wayback": Orgao("Internet Archive (Wayback Machine)", "https://web.archive.org/"),
}
