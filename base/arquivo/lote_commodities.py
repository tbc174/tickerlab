"""Lote commodities do arquivista: mais conjuntos de café, commodities e clima (linha 204 da fila, item 13 do
lançamento; levantamento de 22/10/2026 na pasta privada, itens 1 a 13 do lote 1).

Cada fonte guarda o arquivo como a fonte publica (USDA, FAO, OIC e CONAB: dados abertos ou CC BY, citar a fonte;
CFTC: obra do governo dos EUA; CHC, INMET e MapBiomas já têm marca). As famílias do id (`usda`, `faostat`, `ico`,
`conab`, `cftc`, `chirps`, `inmet`, `mapbiomas`) já têm licença e revenda em `src/banco/coletas.py`. Nada aqui é
lido nem tratado: o que sai de cada arquivo é tarefa da extração.

Escolhas (testes em `tests/test_base_arquivo_lote_commodities.py`):
- **USDA PSD inteiro já estava** em `usda-psd-todas` (`lote_eua.py`, item 1 do levantamento): não se repete aqui, e
  os zips por grupo ficam de fora (seriam o mesmo dado duas vezes);
- **FAOSTAT:** preços ao produtor (12 MB) e comércio (274 MB, `pesada`), ambos como o FAO publica;
- **OIC I-CIP:** um PDF por mês (`I-CIP_MM.AAAA.pdf`), os últimos meses; o mês que ainda não saiu é 404 e vira
  "não encontrado". O portal `data.ico.org` pede cadastro e o COT da ICE Europe proíbe robô nos termos: ficam de fora
  (o COT da ICE vai para o plano manual, linha 276 da fila);
- **CONAB: só pelo `gov.br/conab`.** O portal de informações e as consultas web foram aposentados (404 em 29/10) e
  servem certificado de outro nome. As séries históricas são xls dentro da página de cada produto: lemos a página da
  família, depois a de cada produto, e guardamos o arquivo (o `/view` do Plone sai do endereço). Os boletins da safra
  de grãos vêm das páginas dos levantamentos das duas safras mais recentes;
- **CFTC:** as famílias `com_disagg_txt` (futuros e opções), `dea_cit_txt` (suplementar CIT) e `deacot` (legado), o
  histórico de cada uma e um zip por ano; a `fut_disagg` já está em `cftc-cot-disaggregated`;
- **CHC (CHIRTS, SPEI e SPI):** a temperatura máxima mensal em GeoTIFF (um por mês; o `.nc` de 7,9 GB não entra) e
  os índices de seca dos meses mais recentes. O servidor do CHC responde 429 a rajadas: `pausa_minima` em todas;
- **INMET:** as normais climatológicas (xls da página `/normais`). O catálogo de estações já está em `inmet-estacoes`;
- **MapBiomas:** a planilha de cobertura por bioma e estado (Google Drive, como a de município). AMACRO, áreas
  prioritárias e Mata Atlântica não têm link na página de estatísticas (linha 368 da fila).
"""

import re
from datetime import date, datetime
from urllib.parse import urljoin

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.obter import arquivo_do_google_drive, arquivo_que_pode_faltar

SEMANAL = "semanal"
MENSAL = "mensal"

# ---- FAOSTAT -------------------------------------------------------------------------
FAOSTAT = "https://bulks-faostat.fao.org/production/"
FAOSTAT_PRECOS = FAOSTAT + "Prices_E_All_Data_(Normalized).zip"
FAOSTAT_COMERCIO = FAOSTAT + "Trade_CropsLivestock_E_All_Data_(Normalized).zip"

# ---- OIC: preço indicativo composto (I-CIP), um PDF por mês ---------------------------------------------
ICIP_DO_MES = "https://ico.org/documents/prices/I-CIP_{mes:02d}.{ano}.pdf"
MESES_RECENTES_DO_ICIP = 6


def _meses_anteriores(hoje: date, quantos: int) -> list[tuple[int, int]]:
    """(ano, mês) do mês corrente e dos `quantos - 1` anteriores, do mais antigo ao mais novo."""
    base = hoje.year * 12 + hoje.month - 1
    return [divmod(base - n, 12) for n in reversed(range(quantos))]  # type: ignore[misc]


def descobrir_icip(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os PDFs do I-CIP dos últimos meses; o que a OIC ainda não publicou é 404 (`SemArquivo`)."""
    alvos = []
    for ano, mes in _meses_anteriores(agora.date(), MESES_RECENTES_DO_ICIP):
        url = ICIP_DO_MES.format(ano=ano, mes=mes + 1)
        alvos.append(Alvo(url, ".pdf", arquivo_que_pode_faltar(url)))
    return alvos


# ---- CONAB: séries históricas e boletins, pelo gov.br ---------------------------------------------------
RAIZ_DA_CONAB = (
    "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/"
)
SERIES_DA_CONAB = RAIZ_DA_CONAB + "series-historicas/"
BOLETINS_DA_CONAB = RAIZ_DA_CONAB + "safra-de-graos/boletim-da-safra-de-graos"
PLANILHA_DA_CONAB = re.compile(
    rb'href="(https://www\.gov\.br/conab/[^"]+?\.xlsx?)(?:/view)?"'
)
ARQUIVO_DO_BOLETIM = re.compile(
    rb'href="(https://www\.gov\.br/conab/[^"]+?\.(?:pdf|xlsx?))"'
)
PAGINAS_DO_BOLETIM = 3  # a listagem pagina de 30 em 30 (`b_start:int=`)
POR_PAGINA_DOS_BOLETINS = 30
SAFRAS_DOS_BOLETINS = 2
LEVANTAMENTO_DA_SAFRA = re.compile(
    rb'href="(https://www\.gov\.br/conab/[^"]*/boletim-da-safra-de-graos/'
    rb'(\d+)o-levantamento-safra-(\d{4})-\d{2,4}/[^"?/]+)"'
)


def _paginas_dos_produtos(cliente: Cliente, familia: str) -> list[str]:
    """As páginas de produto da família (`graos/soja`...): os endereços um nível abaixo da página da família."""
    raiz = f"{SERIES_DA_CONAB}{familia}"
    padrao = re.compile(rf'href="({re.escape(raiz)}/[^"/?#.]+(?:/[^"/?#.]+)?)"')
    pagina = cliente.ler(raiz).conteudo.decode("utf-8", "replace")
    achadas = dict.fromkeys(padrao.findall(pagina))
    # `graos/graos` e `cafe/cafe` são a própria página da família (o botão de compartilhar repete)
    return [p for p in achadas if p.rsplit("/", 1)[-1] != familia]


def descobrir_series_da_conab(familia: str) -> Descobrir:
    """As planilhas (xls) da família de séries históricas: uma por produto, mais as de "por UF" e "por produto"."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        planilhas: dict[str, None] = {}
        for pagina in _paginas_dos_produtos(cliente, familia):
            html = cliente.ler(pagina).conteudo
            planilhas |= dict.fromkeys(
                m.decode() for m in PLANILHA_DA_CONAB.findall(html)
            )
        if not planilhas:
            raise ErroDeDescoberta(
                f"CONAB: nenhuma planilha em series-historicas/{familia}"
            )
        return [Alvo(url) for url in planilhas]

    return descobrir


def _levantamentos_das_safras_recentes(cliente: Cliente) -> list[str]:
    """As páginas dos levantamentos das `SAFRAS_DOS_BOLETINS` safras mais novas (a safra é o ano de início)."""
    paginas: dict[str, int] = {}
    for n in range(PAGINAS_DO_BOLETIM):
        url = f"{BOLETINS_DA_CONAB}?b_start:int={n * POR_PAGINA_DOS_BOLETINS}"
        for pagina, _levantamento, ano in LEVANTAMENTO_DA_SAFRA.findall(
            cliente.ler(url).conteudo
        ):
            paginas[pagina.decode()] = int(ano)
    recentes = sorted(set(paginas.values()))[-SAFRAS_DOS_BOLETINS:]
    return [p for p, ano in paginas.items() if ano in recentes]


def descobrir_boletins_da_conab(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os PDFs e xlsx do boletim da safra de grãos (e da apresentação) dos levantamentos das safras recentes."""
    levantamentos = _levantamentos_das_safras_recentes(cliente)
    arquivos: dict[str, None] = {}
    for pagina in levantamentos:
        html = cliente.ler(pagina).conteudo
        arquivos |= dict.fromkeys(m.decode() for m in ARQUIVO_DO_BOLETIM.findall(html))
    if not arquivos:
        raise ErroDeDescoberta("CONAB: nenhum arquivo nos boletins da safra de grãos")
    return [Alvo(url) for url in arquivos]


# ---- CFTC: as outras famílias do COT --------------------------------------------------------------------
CFTC = "https://www.cftc.gov/files/dea/history/"
PRIMEIRO_ANO_SEPARADO_DO_COT = 2017  # até 2016 o histórico vem junto, num zip só
FAMILIAS_DO_COT = {
    # id: (nome do ano, nome do histórico) com `{ano}` no primeiro
    "cftc-cot-futuros-e-opcoes": (
        "com_disagg_txt_{ano}.zip",
        "com_disagg_txt_hist_2006_2016.zip",
    ),
    "cftc-cot-cit": ("dea_cit_txt_{ano}.zip", "dea_cit_txt_2006_2016.zip"),
    "cftc-cot-legado": ("deacot{ano}.zip", "deacot1986_2016.zip"),
}


def descobrir_cot(ano: str, historico: str) -> Descobrir:
    """O histórico e um zip por ano desde 2017 até o corrente (o do ano corrente a CFTC refaz toda semana)."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        anos = range(PRIMEIRO_ANO_SEPARADO_DO_COT, agora.year + 1)
        return [Alvo(CFTC + historico, ".zip")] + [
            Alvo(CFTC + ano.format(ano=a), ".zip") for a in anos
        ]

    return descobrir


# ---- CHC: temperatura (CHIRTS) e secas (SPEI e SPI) -----------------------------------------------------
CHC = "https://data.chc.ucsb.edu/products/"
PAUSA_DO_CHC_EM_SEGUNDOS = 3.0  # o servidor responde 429 a rajadas
CHIRTS_TMAX_MENSAL = CHC + "CHIRTS/monthly/CHIRTSmax.CDR/CHIRTSmax.{ano}.{mes:02d}.tif"
PRIMEIRO_ANO_DO_CHIRTS = 1983
MESES_RECENTES_DO_CHIRTS = 3
SPEI_DO_CHC = CHC + "SPEI/C3_FLDAS_SPEI/{janela:02d}_month/"
SPI_DO_CHC = CHC + "SPI/CHIRPS3/{janela:02d}_month/"
JANELAS_DO_SPEI = (3, 12)
JANELAS_DO_SPI = (3, 12)
ARQUIVOS_RECENTES_DE_SECA = 3
ARQUIVO_DE_SECA = re.compile(r'href="([^"?/][^"?]*\.(?:tif|nc))"')


def _meses_do_chirts(hoje: date, ate: int, desde: int) -> list[Alvo]:
    alvos = []
    base = hoje.year * 12 + hoje.month - 1
    for n in reversed(range(desde, ate + 1)):
        ano, mes = divmod(base - n, 12)
        url = CHIRTS_TMAX_MENSAL.format(ano=ano, mes=mes + 1)
        alvos.append(Alvo(url, ".tif", arquivo_que_pode_faltar(url)))
    return alvos


def descobrir_chirts_recentes(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os GeoTIFFs de temperatura máxima dos meses recentes; o que ainda não saiu é 404."""
    return _meses_do_chirts(agora.date(), MESES_RECENTES_DO_CHIRTS, 1)


def descobrir_chirts_historico(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """De janeiro de 1983 até o mês anterior aos recentes."""
    hoje = agora.date()
    desde_1983 = (hoje.year - PRIMEIRO_ANO_DO_CHIRTS) * 12 + hoje.month - 1
    return _meses_do_chirts(hoje, desde_1983, MESES_RECENTES_DO_CHIRTS + 1)


def descobrir_seca(
    pasta: str, janelas: tuple[int, ...], recentes: int | None
) -> Descobrir:
    """Os `recentes` arquivos mais novos (o nome leva o mês; `None` é todos) de cada janela da pasta do índice.

    O SPEI vem um GeoTIFF por mês (os mais novos importam); o SPI do CHC vem um NetCDF por mês do ano (a
    climatologia), então são todos."""

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        alvos: list[Alvo] = []
        for janela in janelas:
            endereco = pasta.format(janela=janela)
            pagina = cliente.ler(endereco).conteudo.decode("utf-8", "replace")
            nomes = sorted(set(ARQUIVO_DE_SECA.findall(pagina)))
            if not nomes:
                raise ErroDeDescoberta(f"CHC: nenhum arquivo em {endereco}")
            escolhidos = nomes[-recentes:] if recentes else nomes
            alvos += [Alvo(urljoin(endereco, n)) for n in escolhidos]
        return alvos

    return descobrir


# ---- INMET: normais climatológicas ----------------------------------------------------------------------
PAGINA_DAS_NORMAIS_DO_INMET = "https://portal.inmet.gov.br/normais"
XLS_DAS_NORMAIS = re.compile(
    r'href="(https://portal\.inmet\.gov\.br/uploads/normais/[^"]+\.xlsx?)"'
)


def descobrir_normais_do_inmet(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Todas as planilhas de normais linkadas na página (o nome tem acentos; o endereço fica como está)."""
    pagina = cliente.ler(PAGINA_DAS_NORMAIS_DO_INMET).conteudo.decode(
        "utf-8", "replace"
    )
    links = dict.fromkeys(XLS_DAS_NORMAIS.findall(pagina))
    if not links:
        raise ErroDeDescoberta(
            f"INMET: nenhuma planilha de normais em {PAGINA_DAS_NORMAIS_DO_INMET}"
        )
    return [Alvo(link) for link in links]


# ---- MapBiomas: cobertura por bioma e estado ------------------------------------------------------------
MAPBIOMAS_BIOMA_E_ESTADO = (
    "https://drive.google.com/uc?id=1at35OL5mvqyDeTCBCC8yHC0uJrIdGvZX&export=download"
)


def descobrir_mapbiomas_bioma_e_estado(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(
            MAPBIOMAS_BIOMA_E_ESTADO,
            ".xlsx",
            arquivo_do_google_drive(MAPBIOMAS_BIOMA_E_ESTADO),
        )
    ]


def _um(url: str, extensao: str | None = None) -> Descobrir:
    return lambda cliente, agora: [Alvo(url, extensao)]


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    return [
        Fonte("faostat-precos-ao-produtor", MENSAL, _um(FAOSTAT_PRECOS), "zip"),
        Fonte("faostat-comercio", MENSAL, _um(FAOSTAT_COMERCIO), "zip", pesada=True),
        Fonte("ico-icip-mensal", MENSAL, descobrir_icip, "pdf"),
        *(
            Fonte(
                f"conab-series-{familia}",
                SEMANAL,
                descobrir_series_da_conab(pasta),
                pausa_minima=1.0,
            )
            for familia, pasta in (
                ("graos", "graos"),
                ("cana", "cana-de-acucar"),
                ("cafe", "cafe"),
            )
        ),
        Fonte(
            "conab-boletins-graos",
            SEMANAL,
            descobrir_boletins_da_conab,
            pausa_minima=1.0,
        ),
        *(
            Fonte(id_, SEMANAL, descobrir_cot(ano, historico), "zip")
            for id_, (ano, historico) in FAMILIAS_DO_COT.items()
        ),
        Fonte(
            "chirps-chirts-tmax-mensal",
            MENSAL,
            descobrir_chirts_recentes,
            pesada=True,
            pausa_minima=PAUSA_DO_CHC_EM_SEGUNDOS,
        ),
        # a carga única (1983 em diante): grupo fora do cron, só roda pelo id, como o `chirps-historico`
        Fonte(
            "chirps-chirts-tmax-historico",
            "carga-unica",
            descobrir_chirts_historico,
            pesada=True,
            pausa_minima=PAUSA_DO_CHC_EM_SEGUNDOS,
        ),
        Fonte(
            "chirps-spei-fldas",
            MENSAL,
            descobrir_seca(SPEI_DO_CHC, JANELAS_DO_SPEI, ARQUIVOS_RECENTES_DE_SECA),
            pesada=True,
            pausa_minima=PAUSA_DO_CHC_EM_SEGUNDOS,
        ),
        Fonte(
            "chirps-spi-chirps3",
            MENSAL,
            descobrir_seca(SPI_DO_CHC, JANELAS_DO_SPI, None),
            pesada=True,
            pausa_minima=PAUSA_DO_CHC_EM_SEGUNDOS,
        ),
        Fonte("inmet-normais", MENSAL, descobrir_normais_do_inmet),
        Fonte(
            "mapbiomas-bioma-e-estado",
            MENSAL,
            descobrir_mapbiomas_bioma_e_estado,
            "arquivo",
            pesada=True,
        ),
    ]
