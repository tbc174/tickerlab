"""Lote EUA do arquivista (rodada 1 da pesquisa de dados escondidos, 22/10/2026).

Séries do governo dos EUA em domínio público que ainda não estavam na base: índices e conjuntos do
EDGAR (SEC), Data Download Program do Fed, Fiscal Data e curvas do Tesouro, arquivos planos da BLS,
planilhas semanais da EIA, OFR, NY Fed, TIC, PSD do USDA e indicadores do Census. Nenhuma pede chave
(a API do Census pede, e a da BLS com chave também: ficam de fora). Cada fonte é um `Fonte` do
arquivista (`base/arquivo/coleta.py`); aqui só se descobre o que baixar e se guarda como a fonte
publica.

Escolhas (testes em `tests/test_base_arquivo_lote_eua.py`):
- **ritmo pelo calendário:** o que muda todo dia útil e é pequeno é `diaria`; o que sai uma vez por
  mês ou trimestre é `semanal` com `pesada=True` (a coleta confere o ETag e só baixa quando mudou,
  então o `visto_em` fica com até uma semana de precisão sem repetir arquivo);
- **SEC:** o `User-Agent` é o de `cliente_http` (`AGENTE`); a lista de arquivos de cada índice vem
  do `index.json` do próprio EDGAR (o servidor responde 403, e não 404, em dia sem índice, e um 403
  de bloqueio não pode ser confundido com ele);
- **LGPD:** os conjuntos Form D e 13F trazem nomes de pessoas (pessoas relacionadas, signatários).
  O arquivo é guardado como a SEC publica; nenhuma tabela derivada leva pessoa física;
- **arquivos grandes demais ficam de fora** do 1º lote (BLS `ln.data.1.AllData` e
  `ce.data.0.AllCESSeries`, a pasta `la` inteira): ver a fila.
"""

import json
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import requests

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte

HTTP_NAO_ENCONTRADO = 404
SEMANAL = "semanal"
CARGA_UNICA = "carga-unica"

# ---- Fed: Data Download Program (um zip por lançamento, gerado na hora: sem ETag) ----
DDP_DO_FED = "https://www.federalreserve.gov/datadownload/Output.aspx?rel={lancamento}&filetype=zip"
LANCAMENTOS_DO_FED = {
    "H15": "diaria",  # taxas de juros de mercado
    "H10": SEMANAL,  # câmbio contra o dólar
    "H41": SEMANAL,  # balanço do Fed
    "H8": SEMANAL,  # ativos e passivos dos bancos
    "H6": SEMANAL,  # agregados monetários
    "G19": SEMANAL,  # crédito ao consumidor
    "Z1": SEMANAL,  # contas financeiras dos EUA (trimestral)
    "CHGDEL": SEMANAL,  # perdas e inadimplência dos bancos (trimestral)
}

# ---- Tesouro dos EUA: Fiscal Data (API sem chave, páginas de 10 mil linhas) ----
FISCAL_DATA = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
LINHAS_POR_PAGINA_DO_FISCAL_DATA = 10_000
# id da fonte → (caminho da tabela, grupo); a ordem crescente de data mantém estáveis as páginas
# antigas, e só a última muda quando sai dado novo
TABELAS_DO_FISCAL_DATA = {
    "treasury-fiscaldata-divida-total": ("v2/accounting/od/debt_to_penny", SEMANAL),
    "treasury-fiscaldata-juros-medios": (
        "v2/accounting/od/avg_interest_rates",
        SEMANAL,
    ),
    "treasury-fiscaldata-cambio-oficial": (
        "v1/accounting/od/rates_of_exchange",
        SEMANAL,
    ),
    "treasury-fiscaldata-leiloes": ("v1/accounting/od/auctions_query", SEMANAL),
    "treasury-fiscaldata-resultado-mensal": (
        "v1/accounting/mts/mts_table_1",
        SEMANAL,
    ),
    "treasury-fiscaldata-receitas-e-despesas": (
        "v1/accounting/mts/mts_table_5",
        SEMANAL,
    ),
    "treasury-fiscaldata-vendas-de-titulos": (
        "v1/accounting/od/securities_sales",
        SEMANAL,
    ),
}

# ---- Tesouro dos EUA: curvas de juros diárias (um CSV por tipo e por ano) ----
CURVA_DO_TESOURO = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{ano}/all?type={tipo}&field_tdr_date_value={ano}&_format=csv"
)
# tipo da curva → primeiro ano com dado (verificado em 22/10/2026)
PRIMEIRO_ANO_DA_CURVA = {
    "daily_treasury_yield_curve": 1990,
    "daily_treasury_real_yield_curve": 2003,
    "daily_treasury_bill_rates": 2002,
    "daily_treasury_long_term_rate": 2000,
    "daily_treasury_real_long_term": 2000,
}

# ---- BLS: arquivos planos (sem chave) ----
RAIZ_DA_BLS = "https://download.bls.gov"
PASTA_DA_BLS = RAIZ_DA_BLS + "/pub/time.series/{codigo}/"
# a listagem da pasta traz, em cada linha, o tamanho e o link do arquivo (o HTML escreve HREF em
# maiúsculas)
ARQUIVO_NA_PASTA_DA_BLS = re.compile(
    rb'(\d+)\s+<A HREF="(/pub/time\.series/[a-z]+/[^"/]+)"', re.IGNORECASE
)
# arquivo de metadados (sem ".data.") só entra até este tamanho: o `cu.aspect` tem 31 MB de ruído
LIMITE_DO_METADADO_DA_BLS = 20 * 1024**2
# pasta → arquivos de dados que entram; os outros "data.N" só repartem o mesmo conteúdo por área ou
# setor (e multiplicariam o disco por mês)
DADOS_DA_BLS = {
    "cu": ("cu.data.0.Current", "cu.data.1.AllItems"),  # preços ao consumidor (CPI-U)
    "cw": ("cw.data.0.Current", "cw.data.1.AllItems"),  # CPI-W
    "ce": (  # emprego e salários por setor (folha de pagamento)
        "ce.data.00a.TotalNonfarm.Employment",
        "ce.data.01a.CurrentSeasAE",
        "ce.data.05a.TotalPrivate.Employment",
        "ce.data.05b.TotalPrivate.AllEmployeeHoursAndEarnings",
        "ce.data.05c.TotalPrivate.ProductionEmployeeHoursAndEarnings",
    ),
    "wp": (  # preços ao produtor por mercadoria
        "wp.data.0.Current",
        "wp.data.1.AllCommodities",
        "wp.data.22.FD-ID",
    ),
    "pc": ("pc.data.0.Current",),  # preços ao produtor por indústria
    "pr": ("pr.data.0.Current", "pr.data.1.AllData"),  # produtividade
    "ip": ("ip.data.0.Current", "ip.data.1.AllData"),  # produtividade por indústria
    "jt": ("jt.data.0.Current", "jt.data.1.AllItems"),  # vagas e rotatividade (JOLTS)
    "ap": ("ap.data.0.Current",),  # preços médios (gasolina, comida)
    "ei": ("ei.data.0.Current",),  # preços de importação e exportação
    "la": (  # desemprego por estado (as pastas por município pesam 2,5 GB e ficam de fora)
        "la.data.2.AllStatesU",
        "la.data.3.AllStatesS",
    ),
}

# ---- EIA: relatório semanal de petróleo (WPSR), tabelas 1 a 9 ----
WPSR_DA_EIA = "https://ir.eia.gov/wpsr/psw{numero:02d}.xls"
TABELAS_DO_WPSR = range(1, 10)  # a psw10.xls responde 403

# ---- OFR (Tesouro dos EUA): índice de estresse e monitores ----
OFR_FSI = "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
OFR_STFM = "https://data.financialresearch.gov/v1/series/dataset?dataset={conjunto}"
OFR_HFM = "https://data.financialresearch.gov/hf/v1/series/dataset?dataset={conjunto}"
OFR_CATALOGO = (
    "https://data.financialresearch.gov/v1/metadata/mnemonics?output=by_dataset"
)
CONJUNTOS_DO_STFM = (
    "fnyr",
    "mmf",
    "nypd",
    "repo",
    "tyld",
)  # monitor de funding de curto prazo
CONJUNTOS_DO_HFM = ("fpf", "tff", "scoos", "ficc")  # monitor de hedge funds

# ---- NY Fed ----
NYFED = "https://markets.newyorkfed.org/api/"
JUROS_DE_REFERENCIA_DO_NYFED = (
    NYFED + "rates/all/search.json?startDate={ano}-01-01&endDate={ano}-12-31&type=rate"
)
PRIMEIRO_ANO_DO_NYFED = 2018  # o SOFR começou em abril de 2018
DEALERS_DO_NYFED = (
    NYFED + "pd/list/timeseries.json",
    NYFED + "pd/get/all/timeseries.csv",
)

# ---- TIC (Tesouro dos EUA): fluxos de capital e detentores estrangeiros ----
TIC = "https://ticdata.treasury.gov/Publish/"
ARQUIVOS_DO_TIC = {
    "tic-detentores-estrangeiros": ("mfh.txt",),  # principais detentores de Treasuries
    "tic-posicoes-de-longo-prazo": (
        *(f"slt_table{n}.txt" for n in range(1, 7)),
        "slt2d.txt",
        "slt3d.txt",
    ),
    "tic-carteira-global": ("s1_globl.csv",),  # série mensal por país
}

# ---- USDA: PSD Online, todas as commodities (o café já tem fonte própria) ----
PSD_DO_USDA = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"

# ---- Census: comunicados de indicadores (a API pede chave; os PDFs não) ----
CENSUS = "https://www.census.gov/"
PDFS_DO_CENSUS = {
    "census-comercio-exterior": CENSUS
    + "foreign-trade/Press-Release/current_press_release/ft900.pdf",
    "census-varejo": CENSUS + "retail/marts/www/marts_current.pdf",
    "census-construcao": CENSUS + "construction/c30/pdf/release.pdf",
    "census-industria": CENSUS + "manufacturing/m3/prel/pdf/s-i-o.pdf",
}

# ---- SEC (EDGAR) ----
EDGAR = "https://www.sec.gov/Archives/edgar/"
SEC = "https://www.sec.gov"
DIAS_DO_INDICE_DIARIO = (
    10  # janela de dias corridos; só os que o EDGAR já listou entram
)
INDICE_DIARIO_NA_LISTAGEM = re.compile(r"^master\.\d{8}\.idx$")
CONJUNTOS_DA_SEC = {
    "sec-edgar-form-d": "/data-research/sec-markets-data/form-d-data-sets",
    "sec-edgar-13f": "/data-research/sec-markets-data/form-13f-data-sets",
}
ZIP_NA_PAGINA_DA_SEC = re.compile(rb'href="(/files/[^"]+\.zip)"')
CONJUNTOS_RECENTES_DA_SEC = 2  # a página lista do mais novo ao mais antigo
BUSCA_DE_TEXTO_DA_SEC = "https://efts.sec.gov/LATEST/search-index"
FORMULARIOS_DA_BUSCA = "20-F,6-K"
# emissoras brasileiras com ADR na bolsa dos EUA; a busca guarda a 1ª página (100 resultados) de
# cada mês, que serve de prova de "visto em" ao lado do índice diário
EMISSORAS_BRASILEIRAS_NA_SEC = (
    "Petrobras",
    "Vale S.A.",
    "Itaú Unibanco",
    "Banco Bradesco",
    "Ambev",
    "Embraer",
    "Gerdau",
    "Suzano",
    "Braskem",
    "Sabesp",
    "Cemig",
    "Copel",
)

# páginas de termos que a vigia acompanha (lidas em 22/10/2026; a da SEC já está em `fontes.TERMOS`)
TERMOS_DAS_AGENCIAS = {
    "termos-fed": "https://www.federalreserve.gov/disclaimer.htm",
    "termos-bls": "https://www.bls.gov/opub/copyright-information.htm",
    "termos-eia": "https://www.eia.gov/about/copyrights_reuse.php",
    "termos-nyfed": "https://www.newyorkfed.org/terms-of-use",
}


def _um(*urls: str, extensao: str | None = None) -> Descobrir:
    return lambda cliente, agora: [Alvo(url, extensao) for url in urls]


def _json(cliente: Cliente, url: str) -> dict:
    return json.loads(cliente.ler(url).conteudo)


def _anos_recentes(agora: datetime) -> list[int]:
    """O ano da coleta e o anterior: o ano corrente cresce, o anterior ainda recebe revisão."""
    return [agora.year - 1, agora.year]


# ---------------------------------------------------------------- Fiscal Data
def endereco_do_fiscal_data(caminho: str, pagina: int) -> str:
    """Uma página da tabela, em ordem crescente de data."""
    consulta = urlencode(
        {
            "page[size]": LINHAS_POR_PAGINA_DO_FISCAL_DATA,
            "page[number]": pagina,
            "sort": "record_date",
        }
    )
    return f"{FISCAL_DATA}{caminho}?{consulta}"


def descobrir_fiscal_data(caminho: str) -> Descobrir:
    """Todas as páginas da tabela: a primeira diz quantas existem (`meta.total-pages`)."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        meta = _json(cliente, endereco_do_fiscal_data(caminho, 1)).get("meta", {})
        paginas = meta.get("total-pages")
        if not isinstance(paginas, int) or paginas < 1:
            raise ErroDeDescoberta(
                f"{caminho}: o Fiscal Data não disse quantas páginas há"
            )
        return [
            Alvo(endereco_do_fiscal_data(caminho, n), ".json")
            for n in range(1, paginas + 1)
        ]

    return descobrir


# ------------------------------------------------------------ Curvas do Tesouro
def endereco_da_curva(tipo: str, ano: int) -> str:
    return CURVA_DO_TESOURO.format(tipo=tipo, ano=ano)


def descobrir_curvas_recentes(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(endereco_da_curva(tipo, ano), ".csv")
        for tipo in PRIMEIRO_ANO_DA_CURVA
        for ano in _anos_recentes(agora)
    ]


def descobrir_curvas_historicas(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os anos de cada curva antes dos dois recentes (que a fonte diária já coleta)."""
    return [
        Alvo(endereco_da_curva(tipo, ano), ".csv")
        for tipo, primeiro in PRIMEIRO_ANO_DA_CURVA.items()
        for ano in range(primeiro, agora.year - 1)
    ]


# ------------------------------------------------------------------------ BLS
def arquivos_da_pasta_da_bls(pagina: bytes) -> dict[str, tuple[str, int]]:
    """Nome → (caminho, tamanho em bytes) de cada arquivo da listagem da pasta."""
    return {
        caminho.decode().rsplit("/", 1)[1]: (caminho.decode(), int(tamanho))
        for tamanho, caminho in ARQUIVO_NA_PASTA_DA_BLS.findall(pagina)
    }


def descobrir_bls(codigo: str) -> Descobrir:
    """Os metadados pequenos da pasta e os arquivos de dados de `DADOS_DA_BLS`.

    Arquivo de dados da lista que sumiu da pasta é erro (a BLS renomeou: alguém precisa olhar), em
    vez de a coleta seguir sem ele."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        pasta = PASTA_DA_BLS.format(codigo=codigo)
        arquivos = arquivos_da_pasta_da_bls(cliente.ler(pasta).conteudo)
        faltam = [nome for nome in DADOS_DA_BLS[codigo] if nome not in arquivos]
        if faltam:
            raise ErroDeDescoberta(f"bls-{codigo}: faltam na pasta {pasta}: {faltam}")
        metadados = [
            caminho
            for nome, (caminho, tamanho) in arquivos.items()
            if ".data." not in nome and tamanho <= LIMITE_DO_METADADO_DA_BLS
        ]
        dados = [arquivos[nome][0] for nome in DADOS_DA_BLS[codigo]]
        return [Alvo(RAIZ_DA_BLS + caminho) for caminho in (*metadados, *dados)]

    return descobrir


# ------------------------------------------------------------------------ OFR
def endereco_do_conjunto_da_ofr(modelo: str, conjunto: str) -> str:
    return modelo.format(conjunto=conjunto)


# --------------------------------------------------------------------- NY Fed
def descobrir_juros_do_nyfed(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os juros de referência de hoje (SOFR, EFFR, OBFR...) e o ano corrente e o anterior."""
    return [Alvo(NYFED + "rates/all/latest.json", ".json")] + [
        Alvo(JUROS_DE_REFERENCIA_DO_NYFED.format(ano=ano), ".json")
        for ano in _anos_recentes(agora)
    ]


def descobrir_juros_historicos_do_nyfed(
    cliente: Cliente, agora: datetime
) -> list[Alvo]:
    return [
        Alvo(JUROS_DE_REFERENCIA_DO_NYFED.format(ano=ano), ".json")
        for ano in range(PRIMEIRO_ANO_DO_NYFED, agora.year - 1)
    ]


# ------------------------------------------------------------------------ SEC
def _trimestre(dia: date) -> tuple[int, int]:
    return dia.year, (dia.month - 1) // 3 + 1


def _trimestres_recentes(agora: datetime) -> list[tuple[int, int]]:
    """O trimestre da coleta e o anterior (o índice do anterior ainda ganha o último dia útil)."""
    ano, trimestre = _trimestre(agora.date())
    anterior = (ano, trimestre - 1) if trimestre > 1 else (ano - 1, 4)
    return [anterior, (ano, trimestre)]


def pasta_do_trimestre_da_sec(ano: int, trimestre: int, pasta: str) -> str:
    return f"{EDGAR}{pasta}/{ano}/QTR{trimestre}/"


def indices_diarios_listados(listagem: bytes) -> list[str]:
    """Os nomes `master.AAAAMMDD.idx` do `index.json` de uma pasta do EDGAR, em ordem."""
    itens = json.loads(listagem).get("directory", {}).get("item", [])
    nomes = (item.get("name", "") for item in itens)
    return sorted(n for n in nomes if INDICE_DIARIO_NA_LISTAGEM.match(n))


def _listagem_do_trimestre(cliente: Cliente, pasta: str) -> bytes | None:
    """O `index.json` da pasta; `None` quando o EDGAR ainda não criou a pasta (404, 1º dia do
    trimestre). Outro erro (403 de bloqueio, rede) sobe: não pode passar por pasta vazia."""
    try:
        return cliente.ler(pasta + "index.json").conteudo
    except requests.HTTPError as erro:
        if (
            erro.response is not None
            and erro.response.status_code == HTTP_NAO_ENCONTRADO
        ):
            return None
        raise


def descobrir_indice_diario_da_sec(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os índices dos últimos `DIAS_DO_INDICE_DIARIO` dias que o EDGAR já publicou."""
    corte = (agora - timedelta(days=DIAS_DO_INDICE_DIARIO)).strftime("%Y%m%d")
    alvos = []
    for ano, trimestre in _trimestres_recentes(agora):
        pasta = pasta_do_trimestre_da_sec(ano, trimestre, "daily-index")
        listagem = _listagem_do_trimestre(cliente, pasta)
        if listagem is None:
            continue
        alvos += [
            Alvo(pasta + nome, ".idx")
            for nome in indices_diarios_listados(listagem)
            if nome.split(".")[1] >= corte
        ]
    if not alvos:
        raise ErroDeDescoberta("o EDGAR não listou nenhum índice diário recente")
    return alvos


def descobrir_indice_trimestral_da_sec(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(pasta_do_trimestre_da_sec(ano, trimestre, "full-index") + "master.idx")
        for ano, trimestre in _trimestres_recentes(agora)
    ]


def zips_da_pagina_da_sec(pagina: bytes) -> list[str]:
    """Os zips linkados na página, sem repetir e na ordem dela (do mais novo ao mais antigo)."""
    return list(dict.fromkeys(m.decode() for m in ZIP_NA_PAGINA_DA_SEC.findall(pagina)))


def _conjuntos_da_sec(
    caminho: str, recorte: Callable[[list[str]], list[str]]
) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        zips = zips_da_pagina_da_sec(cliente.ler(SEC + caminho).conteudo)
        if not zips:
            raise ErroDeDescoberta(f"nenhum zip linkado em {SEC + caminho}")
        return [Alvo(SEC + zip_, ".zip") for zip_ in recorte(zips)]

    return descobrir


def _recentes(zips: list[str]) -> list[str]:
    return zips[:CONJUNTOS_RECENTES_DA_SEC]


def _antigos(zips: list[str]) -> list[str]:
    return zips[CONJUNTOS_RECENTES_DA_SEC:]


def _meses_da_busca(agora: datetime) -> list[tuple[date, date]]:
    """O mês da coleta e o anterior, do primeiro ao último dia de cada um."""
    primeiro = agora.date().replace(day=1)
    meses = []
    for _ in range(2):
        proximo = (primeiro.replace(day=28) + timedelta(days=4)).replace(day=1)
        meses.append((primeiro, proximo - timedelta(days=1)))
        primeiro = (primeiro - timedelta(days=1)).replace(day=1)
    return meses[::-1]


def endereco_da_busca_de_texto(emissora: str, inicio: date, fim: date) -> str:
    consulta = urlencode(
        {
            "q": f'"{emissora}"',
            "forms": FORMULARIOS_DA_BUSCA,
            "dateRange": "custom",
            "startdt": inicio.isoformat(),
            "enddt": fim.isoformat(),
        }
    )
    return f"{BUSCA_DE_TEXTO_DA_SEC}?{consulta}"


def descobrir_busca_de_texto_da_sec(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(endereco_da_busca_de_texto(emissora, inicio, fim), ".json")
        for emissora in EMISSORAS_BRASILEIRAS_NA_SEC
        for inicio, fim in _meses_da_busca(agora)
    ]


# ------------------------------------------------------------------- as fontes
def _fed() -> list[Fonte]:
    return [
        Fonte(
            f"fed-ddp-{lancamento.lower()}",
            grupo,
            _um(DDP_DO_FED.format(lancamento=lancamento), extensao=".zip"),
            "zip",
        )
        for lancamento, grupo in LANCAMENTOS_DO_FED.items()
    ]


def _treasury() -> list[Fonte]:
    return [
        Fonte(id_, grupo, descobrir_fiscal_data(caminho), "json")
        for id_, (caminho, grupo) in TABELAS_DO_FISCAL_DATA.items()
    ] + [
        Fonte("treasury-curva-juros", "diaria", descobrir_curvas_recentes),
        # a carga única da história (1990 em diante): só roda pelo id
        Fonte(
            "treasury-curva-juros-historico",
            CARGA_UNICA,
            descobrir_curvas_historicas,
        ),
    ]


def _bls() -> list[Fonte]:
    return [
        Fonte(f"bls-{codigo}", SEMANAL, descobrir_bls(codigo), pesada=True)
        for codigo in DADOS_DA_BLS
    ]


def _eia() -> list[Fonte]:
    return [
        Fonte(
            "eia-wpsr",
            SEMANAL,
            _um(*(WPSR_DA_EIA.format(numero=n) for n in TABELAS_DO_WPSR)),
            pesada=True,
        )
    ]


def _ofr() -> list[Fonte]:
    return [
        Fonte("ofr-estresse-financeiro", "diaria", _um(OFR_FSI), pesada=True),
        Fonte(
            "ofr-monitor-de-funding",
            SEMANAL,
            _um(
                *(OFR_STFM.format(conjunto=c) for c in CONJUNTOS_DO_STFM),
                extensao=".json",
            ),
            "json",
        ),
        Fonte(
            "ofr-monitor-de-hedge-funds",
            "mensal",
            _um(
                *(OFR_HFM.format(conjunto=c) for c in CONJUNTOS_DO_HFM),
                OFR_CATALOGO,
                extensao=".json",
            ),
            "json",
        ),
    ]


def _nyfed() -> list[Fonte]:
    return [
        Fonte("nyfed-juros-referencia", "diaria", descobrir_juros_do_nyfed, "json"),
        Fonte(
            "nyfed-juros-referencia-historico",
            CARGA_UNICA,
            descobrir_juros_historicos_do_nyfed,
            "json",
        ),
        Fonte("nyfed-dealers-primarios", SEMANAL, _um(*DEALERS_DO_NYFED)),
    ]


def _tic() -> list[Fonte]:
    return [
        Fonte(id_, SEMANAL, _um(*(TIC + nome for nome in nomes)), pesada=True)
        for id_, nomes in ARQUIVOS_DO_TIC.items()
    ]


def _usda() -> list[Fonte]:
    return [
        Fonte("usda-psd-todas", SEMANAL, _um(PSD_DO_USDA), "zip", pesada=True),
    ]


def _census() -> list[Fonte]:
    return [
        Fonte(id_, SEMANAL, _um(url), "pdf", pesada=True)
        for id_, url in PDFS_DO_CENSUS.items()
    ]


def _sec() -> list[Fonte]:
    return [
        Fonte("sec-edgar-indice-diario", "diaria", descobrir_indice_diario_da_sec),
        Fonte(
            "sec-edgar-indice-trimestral",
            SEMANAL,
            descobrir_indice_trimestral_da_sec,
            pesada=True,
        ),
        *(
            Fonte(
                id_, SEMANAL, _conjuntos_da_sec(caminho, _recentes), "zip", pesada=True
            )
            for id_, caminho in CONJUNTOS_DA_SEC.items()
        ),
        # a carga única dos conjuntos antigos (Form D desde 2008, 13F desde 2013; ~3 GB): só pelo id
        *(
            Fonte(
                f"{id_}-historico",
                CARGA_UNICA,
                _conjuntos_da_sec(caminho, _antigos),
                "zip",
                pesada=True,
            )
            for id_, caminho in CONJUNTOS_DA_SEC.items()
        ),
        Fonte(
            "sec-edgar-busca-texto",
            SEMANAL,
            descobrir_busca_de_texto_da_sec,
            "json",
        ),
    ]


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, na ordem das famílias."""
    return [
        *_sec(),
        *_fed(),
        *_treasury(),
        *_bls(),
        *_eia(),
        *_ofr(),
        *_nyfed(),
        *_tic(),
        *_usda(),
        *_census(),
    ]


def termos() -> dict[str, str]:
    """As páginas de termos das agências que a vigia acompanha."""
    return dict(TERMOS_DAS_AGENCIAS)
