"""Lote "nórdicos": séries abertas de bancos centrais e institutos de estatística da Suécia, Noruega,
Dinamarca, Finlândia e Islândia (linha 511 da fila; licenças lidas em 29/10/2026 na rodada recorrente
`pesquisas-recorrentes/2026-10-29-tema-2.md`; ADR 0102: coleta com ritmo, uso citando a fonte).

Cada série é um endereço de API pública, sem chave, que o arquivista guarda como veio. Nada aqui é
lido nem tratado: o que sai de cada resposta (valores, datas, séries) é tarefa da extração.

Regras (testes em `tests/test_base_arquivo_lote_nordicos.py`):
- **uma fonte por série**, com id "família-série" (a família decide a licença e a marca em
  `src/banco/coletas.py`): `riksbank` e `norges`; cada instituto de estatística entra no seu PR;
- série diária vira **duas janelas**: o histórico até o fim do ano passado (não muda mais, então o
  SHA-256 acusa "igual" e nada se acumula) e a janela que começa no ano passado (quase nada por dia);
- API que falha ou muda de formato é falha (`ErroDeDescoberta`), nunca "nada novo";
- nenhuma é `pesada` e todas têm pausa entre pedidos (APIs abertas de terceiros, ADR 0082);
- **Riksbank**: "freely available and may be further used without any special consent or agreement
  being required. Enter source, Sveriges riksbank and date" (lido em 29/10/2026): vendável com crédito.
  A API anônima limita o ritmo (5 pedidos por minuto na documentação do Riksbank), então a pausa é de 15 s;
- **Norges Bank**: "copies may be made ... provided that Norges Bank is quoted as the source" e "No changes
  may be made in the contents of the material" (lido em 29/10/2026). O texto não diz se um indicador
  calculado por nós conta como "mudança", e o `robots.txt` do `data.norges-bank.no` traz
  `Content-Signal: ai-train=no` (conferido em 05/11/2026). Por isso a marca é **a confirmar** (vale como não
  comercial, sem treino, rótulo nem exportação) até uma leitura humana, e a ADR 0102 Emenda 2 proíbe
  perguntar à fonte. O arquivista só guarda a cópia como veio.
- **Statistics Denmark** (StatBank): CC BY 4.0 (lido em 29/10/2026): vendável citando a fonte. A API exige
  nomear todas as variáveis da tabela; a descoberta lê o `tableinfo` e pede cada uma com `*`. O formato é o
  BULK (CSV por fluxo): o `CSV` comum recusa mais de 1 milhão de células contando a coluna de cada variável e a do
  valor (o IPC, com 404 mil combinações, dá 1,6 milhão) e o BULK não tem esse limite;
- **SCB** (Statistics Sweden): CC0 ("We use the licence CC0", lido em 29/10/2026). PxWebApi v2beta, por GET; a
  descoberta lê os metadados e pede todos os valores de cada dimensão (a API recusa mais de 150 mil células,
  então tabela maior é falha e não corte);
- **Statistics Finland** (StatFin) e **Statistics Iceland** (Hagstofa): CC BY 4.0, vendável citando a fonte (lido
  em 29/10/2026). PxWeb v1: a tabela inteira vem por POST com a consulta vazia e saída `csv`, e o arquivista
  guarda o CSV como veio (BOM e separador incluídos);
- **fora daqui**: SSB, Danmarks Nationalbank, Bank of Finland e Seðlabanki (licença ainda não lida).
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from base.arquivo.coleta import (
    Alvo,
    Cliente,
    Descobrir,
    ErroDeDescoberta,
    Fonte,
    Obter,
)

PRIMEIRO_ANO_DAS_SERIES_DIARIAS = (
    1980  # antes da primeira observação de qualquer série do lote
)
PAUSA_DO_RIKSBANK_EM_SEGUNDOS = 15.0  # 5 pedidos por minuto na API anônima
PAUSA_DO_NORGES_BANK_EM_SEGUNDOS = 2.0


@dataclass(frozen=True)
class Serie:
    """Uma série de uma API: o id da fonte, o endereço e como (e quando) coletar."""

    id: str
    url: str  # com `{inicio}` e `{fim}` quando a série é diária e vira duas janelas
    extensao: str
    grupo: str = "semanal"  # a API publica de dia, mas o SHA-256 decide o que é novo
    tipo: str = "arquivo"
    pausa: float = PAUSA_DO_NORGES_BANK_EM_SEGUNDOS


# ---- Riksbank (SWEA API; "Source: Sveriges riksbank" e a data) ---------------------------------
RIKSBANK = "https://api.riksbank.se/swea/v1"
# taxa de juros e câmbio: taxa diretriz, letra de 3 meses, títulos do governo e as moedas que a base já
# acompanha (o real, o dólar, o euro, a libra, a coroa norueguesa, o iene e o yuan)
SERIES_DE_JUROS_DO_RIKSBANK = {
    "juro-diretor": "SECBREPOEFF",
    "letra-3m": "SETB3MBENCH",
    "titulo-2a": "SEGVB2YC",
    "titulo-5a": "SEGVB5YC",
    "titulo-10a": "SEGVB10YC",
}
SERIES_DE_CAMBIO_DO_RIKSBANK = {
    "cambio-real": "SEKBRLPMI",
    "cambio-dolar": "SEKUSDPMI",
    "cambio-euro": "SEKEURPMI",
    "cambio-libra": "SEKGBPPMI",
    "cambio-coroa-norueguesa": "SEKNOKPMI",
    "cambio-iene": "SEKJPYPMI",
    "cambio-yuan": "SEKCNYPMI",
}


def _janela_do_riksbank(codigo: str) -> str:
    return f"{RIKSBANK}/Observations/{codigo}/{{inicio}}/{{fim}}"


SERIES_DO_RIKSBANK = (
    # os catálogos: quais séries e grupos existem (e até que data cada uma vai)
    Serie(
        "riksbank-catalogo-de-series",
        f"{RIKSBANK}/Series",
        ".json",
        "semanal",
        "json",
        PAUSA_DO_RIKSBANK_EM_SEGUNDOS,
    ),
    Serie(
        "riksbank-catalogo-de-grupos",
        f"{RIKSBANK}/Groups",
        ".json",
        "semanal",
        "json",
        PAUSA_DO_RIKSBANK_EM_SEGUNDOS,
    ),
    *(
        Serie(
            f"riksbank-{nome}",
            _janela_do_riksbank(codigo),
            ".json",
            "diaria",
            "json",
            PAUSA_DO_RIKSBANK_EM_SEGUNDOS,
        )
        for nome, codigo in (
            *SERIES_DE_JUROS_DO_RIKSBANK.items(),
            *SERIES_DE_CAMBIO_DO_RIKSBANK.items(),
        )
    ),
)

# ---- Norges Bank (SDMX; "Source: Norges Bank", sem alterar o conteúdo) -------------------------
NORGES_BANK = "https://data.norges-bank.no/api/data"
FORMATO_DO_NORGES_BANK = "format=csv&locale=en"
MOEDAS_DO_NORGES_BANK = "USD+EUR+BRL+GBP+SEK+JPY+CNY"


def _norges(chave: str, parametros: str = "") -> str:
    return f"{NORGES_BANK}/{chave}?{parametros}{FORMATO_DO_NORGES_BANK}"


SERIES_DO_NORGES_BANK = (
    # câmbio de referência (14h15 CET, como o BCE) em janelas: o histórico passa de 1 MB por moeda
    Serie(
        "norges-cambio",
        _norges(
            f"EXR/B.{MOEDAS_DO_NORGES_BANK}.NOK.SP",
            "startPeriod={inicio}&endPeriod={fim}&",
        ),
        ".csv",
        "diaria",
    ),
    # taxa diretriz (e as taxas de depósito e de empréstimo overnight) e juros do governo: pequenos
    Serie(
        "norges-juro-diretor",
        _norges("IR/B.KPRA.SD+OL+RR.R", "startPeriod={inicio}&endPeriod={fim}&"),
        ".csv",
        "diaria",
    ),
    Serie(
        "norges-letra-3m",
        _norges(
            "GOVT_GENERIC_RATES/B.3M.TBIL", "startPeriod={inicio}&endPeriod={fim}&"
        ),
        ".csv",
        "diaria",
    ),
    Serie(
        "norges-titulo-10a",
        _norges(
            "GOVT_GENERIC_RATES/B.10Y.GBON", "startPeriod={inicio}&endPeriod={fim}&"
        ),
        ".csv",
        "diaria",
    ),
)

# ---- Statistics Denmark (StatBank; CC BY 4.0, citar "Statistics Denmark") ----------------------
DST = "https://api.statbank.dk/v1"
# preços (IPC e IPCH), desemprego, contas nacionais trimestrais, juros do banco central e dos bancos.
# A tabela de câmbio diário (DNVALD) passa de 2,7 milhões de células: fica para uma janela por data.
TABELAS_DA_DST = {
    "ipc": "PRIS01",
    "ipch": "PRIS07",
    "desemprego": "AUS08",
    "contas-nacionais-trimestrais": "NKN1",
    "juros-de-mercado": "DNRENTM",
    "juros-por-tipo": "MPK3",
}
SERIES_DA_DST = tuple(
    Serie(f"dst-{nome}", f"{DST}/data/{tabela}/BULK", ".csv", "semanal")
    for nome, tabela in TABELAS_DA_DST.items()
)

# ---- SCB (Statistics Sweden; CC0) --------------------------------------------------------------
SCB = "https://api.scb.se/OV0104/v2beta/api/v2"
LIMITE_DE_CELULAS_DO_SCB = 150_000  # a API recusa pedidos maiores
# preços (IPC, IPCF com juros fixos e IPCH) e desemprego por duração; o PIB trimestral fica para outro PR
TABELAS_DO_SCB = {
    "ipc": "TAB2075",
    "ipc-juros-fixos": "TAB6601",
    "ipch": "TAB4602",
    "desemprego": "TAB2901",
}
SERIES_DO_SCB = tuple(
    Serie(f"scb-{nome}", f"{SCB}/tables/{tabela}/data", ".csv", "semanal")
    for nome, tabela in TABELAS_DO_SCB.items()
)

# ---- Statistics Finland e Statistics Iceland (PxWeb v1; CC BY 4.0) -------------------------------
STATFIN = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin"
HAGSTOFA = "https://px.hagstofa.is/pxen/api/v1/en"
TABELAS_DA_FINLANDIA = {
    "ipc": "khi/11xs.px",  # índices de preços ao consumidor, mensal
    "desemprego": "tyti/135z.px",  # pesquisa de força de trabalho, indicadores-chave
    "pib-trimestral": "ntp/132h.px",  # contas nacionais trimestrais
}
TABELAS_DA_ISLANDIA = {
    "ipc": "Efnahagur/visitolur/1_vnv/1_vnv/VIS01000.px",
    "pib-trimestral": "Efnahagur/thjodhagsreikningar/landsframl/2_landsframleidsla_arsfj/THJ01601.px",
    "desemprego": "Samfelag/vinnumarkadur/vinnumarkadsrannsokn/1_manadartolur/VIN00002.px",
}
SERIES_DO_PXWEB = (
    *(
        Serie(f"statfi-{nome}", f"{STATFIN}/{tabela}", ".csv", "semanal")
        for nome, tabela in TABELAS_DA_FINLANDIA.items()
    ),
    *(
        Serie(f"statice-{nome}", f"{HAGSTOFA}/{tabela}", ".csv", "semanal")
        for nome, tabela in TABELAS_DA_ISLANDIA.items()
    ),
)
CONSULTA_DA_TABELA_INTEIRA = json.dumps(
    {"query": [], "response": {"format": "csv"}}
).encode()

SERIES = (
    *SERIES_DO_RIKSBANK,
    *SERIES_DO_NORGES_BANK,
    *SERIES_DA_DST,
    *SERIES_DO_SCB,
    *SERIES_DO_PXWEB,
)


# ---- descobertas -------------------------------------------------------------------------------
def janelas_diarias(url: str, agora: datetime, extensao: str) -> list[Alvo]:
    """O histórico fechado (até o fim do ano passado) e a janela aberta (do início do ano passado em
    diante): o histórico fechado nunca muda, então vira "igual" a cada coleta."""
    ano = agora.year
    historico = url.format(
        inicio=f"{PRIMEIRO_ANO_DAS_SERIES_DIARIAS}-01-01", fim=f"{ano - 1}-12-31"
    )
    recente = url.format(inicio=f"{ano - 1}-01-01", fim=f"{ano}-12-31")
    return [Alvo(historico, extensao), Alvo(recente, extensao)]


def endereco_da_tabela_da_dst(cliente: Cliente, serie: Serie) -> str:
    """O CSV da tabela inteira: a API pede todas as variáveis nomeadas, então lê o `tableinfo` antes."""
    tabela = serie.url.rsplit("/", 2)[-2]
    resposta = cliente.ler(f"{DST}/tableinfo/{tabela}?format=JSON&lang=en")
    try:
        variaveis = json.loads(resposta.conteudo)["variables"]
        ids = [v["id"] for v in variaveis]
    except (ValueError, KeyError, TypeError) as erro:
        raise ErroDeDescoberta(f"DST: tableinfo inesperado de {tabela}") from erro
    if not ids:
        raise ErroDeDescoberta(f"DST: {tabela} sem variáveis no tableinfo")
    filtros = "&".join(f"{quote(v)}=*" for v in ids)
    return f"{serie.url}?lang=en&{filtros}"


def endereco_da_tabela_do_scb(cliente: Cliente, serie: Serie) -> str:
    """A tabela inteira: a API pede um seletor por dimensão, então lê os metadados antes."""
    tabela = serie.url.rsplit("/", 2)[-2]
    resposta = cliente.ler(f"{SCB}/tables/{tabela}/metadata?lang=en")
    try:
        corpo = json.loads(resposta.conteudo)
        dimensoes: list[str] = [str(d) for d in corpo["id"]]
        celulas = math.prod(int(n) for n in corpo["size"])
    except (ValueError, KeyError, TypeError) as erro:
        raise ErroDeDescoberta(f"SCB: metadados inesperados de {tabela}") from erro
    if not dimensoes:
        raise ErroDeDescoberta(f"SCB: {tabela} sem dimensões nos metadados")
    if celulas > LIMITE_DE_CELULAS_DO_SCB:
        raise ErroDeDescoberta(
            f"SCB: {tabela} tem {celulas} células, acima do que a API entrega"
        )
    filtros = "&".join(f"valueCodes%5B{quote(d)}%5D=*" for d in dimensoes)
    return f"{serie.url}?lang=en&outputFormat=csv&{filtros}"


def obter_tabela_pxweb(url: str) -> Obter:
    """POST com a consulta vazia: o PxWeb devolve a tabela inteira em CSV, gravado como veio."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        resposta = cliente.ler(
            url,
            metodo="POST",
            cabecalhos={"Content-Type": "application/json"},
            corpo=CONSULTA_DA_TABELA_INTEIRA,
        )
        destino.write_bytes(resposta.conteudo)
        return resposta.cabecalhos

    return obter


def descobrir_serie(serie: Serie) -> Descobrir:
    """Um endereço por série; as diárias (`{inicio}` no endereço) viram duas janelas."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        if serie.id.startswith("dst-"):
            return [Alvo(endereco_da_tabela_da_dst(cliente, serie), serie.extensao)]
        if serie.id.startswith("scb-"):
            return [Alvo(endereco_da_tabela_do_scb(cliente, serie), serie.extensao)]
        if serie.id.startswith(("statfi-", "statice-")):
            return [
                Alvo(serie.url, serie.extensao, obter=obter_tabela_pxweb(serie.url))
            ]
        if "{inicio}" in serie.url:
            return janelas_diarias(serie.url, agora, serie.extensao)
        return [Alvo(serie.url, serie.extensao)]

    return _descobrir


# ---- as fontes ---------------------------------------------------------------------------------
def _fonte_da_serie(serie: Serie) -> Fonte:
    return Fonte(
        serie.id,
        serie.grupo,
        descobrir_serie(serie),
        serie.tipo,
        pausa_minima=serie.pausa,
    )


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    return [_fonte_da_serie(s) for s in SERIES]


# páginas de termos que a vigia acompanha (avisa quando o texto muda)
TERMOS_DOS_NORDICOS = {
    "termos-riksbank": "https://www.riksbank.se/en-gb/about-the-riksbank/about-the-website/"
    "open-data--information-available-for-re-use/",
    "termos-norges": "https://www.norges-bank.no/en/disclaimer/",
    "termos-dst": "https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api",
    "termos-scb": "https://www.scb.se/en/services/open-data-api/",
    "termos-statfi": "https://stat.fi/en/about-us/get-to-know-statistics-finland/legislation/terms-of-use",
    "termos-statice": "https://www.statice.is/publications/open-data-access/",
}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DOS_NORDICOS)
