"""Lote "Europa e RBA": institutos de estatística e banco central de países europeus e da Austrália
(linha 512 da fila; licenças lidas na fonte primária em 29/10/2026; ADR 0102: coleta com ritmo, uso
citando a fonte; ADR 0008, Emenda 4).

Cada série é um endereço público, sem chave, que o arquivista guarda como veio. Nada aqui é lido nem
tratado: o que sai de cada resposta é tarefa da extração.

Regras (testes em `tests/test_base_arquivo_lote_europa_rba.py`):
- **uma fonte por série**, com id "família-série" (a família decide a licença e a marca em
  `src/banco/coletas.py`): `statat` (Statistik Austria), `statbel` (Bélgica), `cbs` (Países Baixos),
  `cso` (Irlanda), `ines` (Espanha), `istat` (Itália) e `rba` (Austrália);
- só entra endereço que **respondeu 200 com dado** em 05/11/2026 e que o `AGENTE` do arquivista (com
  contato) consegue ler; nenhum contorno de bloqueio: a RBA recusa (403, Akamai) o robô sem
  identificação e deixa passar o nosso;
- séries pequenas e estáveis (nenhuma `pesada`): o SHA-256 decide se o retrato mudou;
- **fora daqui**, de propósito:
  - **SNB** (Suíça): o aviso do site só permite uso "for non-commercial purposes"; entra apenas a
    marca `nao_comercial` em `src/banco/coletas.py`, sem coleta;
  - **OeNB** (404 e 503 hoje), **DNB** (API 404; site fechado ao robô) e **Banco da Irlanda**
    (páginas em JavaScript, sem arquivo para baixar): viram linha da fila, não fonte;
  - tabelas da RBA com termos próprios (F1 traz a taxa oficial, o "Cash Rate") e as do ABS, que são de
    terceiro e têm a licença dele;
  - CPI da Irlanda por sdmx e a tabela ODataFeed do CBS (11 MB): pesadas demais para o ganho.
"""

from dataclasses import dataclass
from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, Fonte

PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS = 1.0  # APIs abertas, mas de terceiros (ADR 0082)

# ---- Statistik Austria (OGD, CC BY 4.0; citar "STATISTIK AUSTRIA") --------------------------------
OGD_DA_AUSTRIA = "https://data.statistik.gv.at/data"

# ---- Statbel, Bélgica (dados abertos CC BY 4.0; só a API bestat, o site é fechado ao robô) -------
BESTAT = "https://bestat.statbel.fgov.be/bestat/api/views"

# ---- CBS, Países Baixos (CC BY 4.0; citar Statistics Netherlands) ---------------------------------
# A API recusa consulta que devolva 10.000 registros ou mais: só tabelas anuais e curtas
CBS = "https://opendata.cbs.nl/ODataApi/odata"

# ---- CSO, Irlanda (PxStat, CC BY 4.0) -------------------------------------------------------------
CSO = "https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset"

# ---- INE, Espanha (wstempus, CC BY 4.0; "Source: INE website: www.ine.es") ------------------------
INE = "https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE"
HISTORICO_INTEIRO_DO_INE = (
    "nult=1000"  # sem `nult` a API dá 404; 1000 pontos cobrem tudo
)

# ---- Istat, Itália (aviso legal: CC BY 4.0, uso comercial ok) -------------------------------------
# `esploradati` é o serviço novo; `sdmx.istat.it` redireciona. Lento (15 a 20 s): período limitado
ISTAT = "https://esploradati.istat.it/SDMXWS/rest/data/IT1"

# ---- RBA, Austrália (maior parte CC BY 4.0; "Financial Data": uso pessoal ou comercial) -----------
RBA = "https://www.rba.gov.au/statistics/tables"


@dataclass(frozen=True)
class Serie:
    """Uma série de uma API: o id da fonte, o endereço e como (e quando) coletar."""

    id: str
    url: str
    extensao: str
    grupo: str = (
        "mensal"  # os órgãos publicam de dia a trimestre; o SHA-256 decide o que é novo
    )
    tipo: str = "arquivo"


def _bestat(visao: str) -> str:
    return f"{BESTAT}/{visao}/result/CSV"


def _cso(tabela: str) -> str:
    return f"{CSO}/{tabela}/CSV/1.0/en"


def _ine(serie: str) -> str:
    return f"{INE}/{serie}?{HISTORICO_INTEIRO_DO_INE}"


SERIES_DA_AUSTRIA = (
    Serie("statat-ipc-base-2010", f"{OGD_DA_AUSTRIA}/OGD_vpi10_VPI_2010_1.csv", ".csv"),
    Serie("statat-ipc-base-2020", f"{OGD_DA_AUSTRIA}/OGD_vpi20_VPI_2020_1.csv", ".csv"),
)

SERIES_DA_BELGICA = (
    Serie(
        "statbel-ipch-anual",
        _bestat("b590cea9-ebe3-430a-a84a-639ac25d65d3"),
        ".csv",
        "semanal",
    ),
    Serie(
        "statbel-ipc-mensal",
        _bestat("208b69bd-05c5-4947-b7f9-2d2300f517b8"),
        ".csv",
        "semanal",
    ),
    Serie(
        "statbel-emprego-por-regiao",
        _bestat("f0fae533-cd23-40ee-94ff-37334303d057"),
        ".csv",
        "semanal",
    ),
)

SERIES_DOS_PAISES_BAIXOS = (
    Serie(
        "cbs-inflacao-anual",
        f"{CBS}/70936NED/TypedDataSet",
        ".json",
        "semanal",
        "json",
    ),
    Serie(
        "cbs-ipch-comparado",
        f"{CBS}/83135NED/TypedDataSet",
        ".json",
        "semanal",
        "json",
    ),
)

SERIES_DA_IRLANDA = (
    Serie("cso-ipc", _cso("CPM01"), ".csv"),
    Serie("cso-preco-de-imoveis", _cso("HPM09"), ".csv"),
    Serie("cso-desemprego", _cso("MUM01"), ".csv"),
)

SERIES_DA_ESPANHA = (
    Serie("ines-ipc", _ine("IPC251852"), ".json", "semanal", "json"),
    Serie("ines-ativos-epa", _ine("EPA387794"), ".json", "semanal", "json"),
)

SERIES_DA_ITALIA = (
    Serie(
        "istat-fluxo-143-497",
        f"{ISTAT},143_497,1.0/?format=csv",
        ".csv",
    ),
    Serie(
        "istat-fluxo-120-337",
        f"{ISTAT},120_337,1.0/?format=csv&startPeriod=2015",
        ".csv",
    ),
)

# a F1 (taxa oficial) e as tabelas do ABS ficam de fora: ver o texto do módulo
SERIES_DA_AUSTRALIA = (
    Serie("rba-cambio", f"{RBA}/csv/f11.1-data.csv", ".csv"),
    Serie("rba-rendimentos-dos-titulos", f"{RBA}/xls/f01d.xlsx", ".xlsx"),
    Serie("rba-balanco", f"{RBA}/csv/a1-data.csv", ".csv"),
)

SERIES = (
    *SERIES_DA_AUSTRIA,
    *SERIES_DA_BELGICA,
    *SERIES_DOS_PAISES_BAIXOS,
    *SERIES_DA_IRLANDA,
    *SERIES_DA_ESPANHA,
    *SERIES_DA_ITALIA,
    *SERIES_DA_AUSTRALIA,
)


def descobrir_serie(serie: Serie) -> Descobrir:
    """Um endereço por série: nada a descobrir, o que muda é o conteúdo."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [Alvo(serie.url, serie.extensao)]

    return _descobrir


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    return [
        Fonte(
            s.id,
            s.grupo,
            descobrir_serie(s),
            s.tipo,
            pausa_minima=PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS,
        )
        for s in SERIES
    ]


# páginas de termos que a vigia acompanha (avisa quando o texto muda). Só as três que respondem 200
# ao nosso robô em 05/11/2026; as da Áustria, da Irlanda e da Espanha deram 404 nos endereços
# conhecidos e a da Bélgica fica atrás de um desafio anti-robô (sem contorno): linha da fila
TERMOS_DOS_ORGAOS = {
    "termos-cbs": "https://www.cbs.nl/en-gb/about-us/website/copyright",
    "termos-istat": "https://www.istat.it/en/legal-notice/",
    "termos-rba": "https://www.rba.gov.au/copyright/",
}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DOS_ORGAOS)
