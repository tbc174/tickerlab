"""Catálogo do arquivista: cada fonte que só mostra o "agora" e como achar os seus arquivos.

Endereços conferidos em 14/10/2026. Licenças e motivos em `projeto-acoes/licencas-por-fonte.md`
(fora do repositório) e em `src/banco/coletas.py` (`LICENCAS`, `REVENDA`). Grupos: **diaria**
(2h), **semanal** (domingo) e **mensal** (dia 5: CNPJ; dia 6: PGFN).
"""

import base64
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte

PORTAL_DA_CVM = "https://dados.cvm.gov.br"
PORTAL_DO_IBAMA = "https://dadosabertos.ibama.gov.br"
PORTAL_DO_BC = "https://dadosabertos.bcb.gov.br"
PORTAL_DO_TESOURO = "https://www.tesourotransparente.gov.br/ckan"

PAGINA_DA_CGU = "https://portaldatransparencia.gov.br/download-de-dados/{conjunto}"
DOWNLOAD_DA_CGU = PAGINA_DA_CGU + "/{dia}"
DATA_DA_CGU = re.compile(
    rb'"ano"\s*:\s*"(\d{4})",\s*"mes"\s*:\s*"(\d{2})",\s*"dia"\s*:\s*"(\d{2})"'
)
PAGINA_DA_LISTA_SUJA = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/areas-de-atuacao/"
    "combate-ao-trabalho-escravo-e-analogo-ao-de-escravo"
)
LINK_DA_LISTA_SUJA = re.compile(
    rb'href="([^"]*cadastro[_-]de[_-]empregadores[^"]*\.(?:csv|pdf|xlsx))"'
)
GLEIF_DO_BRASIL = (
    "https://api.gleif.org/api/v1/lei-records?filter%5Bentity.legalAddress.country%5D=BR"
    "&page%5Bsize%5D=200&page%5Bnumber%5D={pagina}"
)
RAIZ_DA_PGFN = "https://dadosabertos.pgfn.gov.br/"
PASTA_DO_TRIMESTRE = re.compile(rb'href="(\d{4}_trimestre_\d{2})/"')
ZIP_NA_PASTA = re.compile(rb'href="([^"/]+\.zip)"')
# pastas da CVM (listagem do servidor web): o catálogo CKAN só mostra os últimos 5 anos
ARQUIVO_NA_PASTA = re.compile(rb'href="([^"?/]+\.(?:zip|csv))"')
PASTAS_DA_CVM = "https://dados.cvm.gov.br/dados/"
# o CNPJ fica num compartilhamento público do Nextcloud da Receita: o token sai do redirecionamento
RAIZ_DO_CNPJ = "https://arquivos.receitafederal.gov.br/"
WEBDAV_DA_RECEITA = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
DOWNLOAD_DA_RECEITA = (
    "https://arquivos.receitafederal.gov.br/public.php/dav/files/{token}/{caminho}"
)
PASTA_DO_CNPJ = "Dados/Cadastros/CNPJ"
TOKEN_DO_COMPARTILHAMENTO = re.compile(r"/s/([A-Za-z0-9]+)")
MES = re.compile(r"^\d{4}-\d{2}$")
# SCR.data versão 2, um zip por ano desde 2012 (o mesmo de `base/bcb_scr.py`): o firewall do BC
# recusa a API do CKAN, os arquivos baixam; janeiro sai no fim de fevereiro
SCR_DO_ANO = "https://www.bcb.gov.br/pda/desig/scrdata_{ano}.zip"
PRIMEIRO_ANO_DO_SCR = 2012
MES_DO_PRIMEIRO_ARQUIVO_DO_SCR = 3

# termos de uso que decidem o que o TickerLab pode fazer (vigia: avisa quando o texto muda)
TERMOS = {
    "termos-b3-politica": "https://www.b3.com.br/data/files/0D/97/1F/B7/4CCFF91094DCD8F9AC094EA8/"
    "Politica%20de%20Consumo%20de%20Market%20Data%20B3%20V1.1.pdf",
    "termos-b3-distribuidores": "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/"
    "market-data/distribuidores/distribuidores-licenciados/",
    "termos-finra": "https://www.finra.org/terms-of-use",
    "termos-fred": "https://fred.stlouisfed.org/legal/terms/",
    "termos-datajud": "https://datajud-wiki.cnj.jus.br/api-publica/termo-uso",
    "termos-sec": "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
}
CATALOGOS = {
    "catalogo-cvm": PORTAL_DA_CVM,
    # o firewall do BC bloqueia por alguns minutos de vez em quando ("Requisição inválida"): a nova
    # tentativa do `scripts/arquivar_fontes.py` cobre (14/10/2026)
    "catalogo-bc": PORTAL_DO_BC,
    "catalogo-tesouro": PORTAL_DO_TESOURO,
    "catalogo-ibama": PORTAL_DO_IBAMA,
}


PAINEIS = ("powerbi.com", "app.powerbi", "lookerstudio.google", "datastudio.google")


def _json(cliente: Cliente, url: str) -> dict:
    return json.loads(cliente.ler(url).conteudo)


def _e_arquivo(recurso: dict) -> bool:
    """Recurso que é arquivo de dados (não painel nem página: a ANTT lista um Power BI)."""
    url = recurso.get("url") or ""
    formato = (recurso.get("format") or "").lower()
    return bool(url) and formato != "html" and not any(p in url for p in PAINEIS)


def descobrir_ckan(cliente: Cliente, portal: str, *pacotes: str) -> list[Alvo]:
    """Os arquivos (recursos) dos pacotes de um portal CKAN (CVM, IBAMA, CCEE, ANTT...)."""
    alvos: list[Alvo] = []
    for pacote in pacotes:
        resposta = _json(cliente, f"{portal}/api/3/action/package_show?id={pacote}")
        recursos = [
            r for r in resposta.get("result", {}).get("resources", []) if _e_arquivo(r)
        ]
        if not recursos:
            raise ErroDeDescoberta(f"{pacote}: pacote sem arquivos em {portal}")
        alvos += [Alvo(r["url"]) for r in recursos]
    return alvos


def _ckan(portal: str, *pacotes: str) -> Descobrir:
    return lambda cliente, agora: descobrir_ckan(cliente, portal, *pacotes)


def descobrir_pasta(cliente: Cliente, *pastas: str) -> list[Alvo]:
    """Os arquivos (.zip e .csv) listados em pastas do servidor de dados (todos os anos)."""
    alvos: list[Alvo] = []
    for pasta in pastas:
        pagina = cliente.ler(pasta).conteudo
        nomes = dict.fromkeys(m.decode() for m in ARQUIVO_NA_PASTA.findall(pagina))
        if not nomes:
            raise ErroDeDescoberta(f"nenhum arquivo na pasta {pasta}")
        alvos += [Alvo(pasta + nome) for nome in nomes]
    return alvos


def _pastas_da_cvm(*caminhos: str) -> Descobrir:
    pastas = [PASTAS_DA_CVM + caminho for caminho in caminhos]
    return lambda cliente, agora: descobrir_pasta(cliente, *pastas)


def descobrir_cgu(conjunto: str) -> Descobrir:
    """O arquivo mais recente do download de dados do Portal da Transparência (sem chave).

    Cada conjunto sai em dias diferentes (o CEPIM não é diário): a própria página de download lista
    as datas publicadas (`arquivos.push({"ano": ..., "mes": ..., "dia": ...})`).
    """

    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        pagina = cliente.ler(PAGINA_DA_CGU.format(conjunto=conjunto)).conteudo
        datas = sorted(b"".join(d) for d in DATA_DA_CGU.findall(pagina))
        if not datas:
            raise ErroDeDescoberta(f"CGU {conjunto}: nenhuma data publicada na página")
        return [
            Alvo(
                DOWNLOAD_DA_CGU.format(conjunto=conjunto, dia=datas[-1].decode()),
                ".zip",
            )
        ]

    return descobrir


def descobrir_lista_suja(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """O cadastro de empregadores (CSV, PDF, planilha) linkado na página do MTE."""
    pagina = cliente.ler(PAGINA_DA_LISTA_SUJA).conteudo
    links = dict.fromkeys(m.decode() for m in LINK_DA_LISTA_SUJA.findall(pagina))
    return [Alvo(link) for link in links]


def endereco_gleif(pagina: int) -> str:
    return GLEIF_DO_BRASIL.format(pagina=pagina)


def descobrir_gleif(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Todas as páginas de registros LEI com endereço no Brasil (cada uma vira um JSON guardado)."""
    ultima = _json(cliente, endereco_gleif(1))["meta"]["pagination"]["lastPage"]
    return [Alvo(endereco_gleif(n), ".json") for n in range(1, int(ultima) + 1)]


def descobrir_pgfn(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os ZIPs do trimestre mais recente da dívida ativa (as pastas antigas ficam lá)."""
    raiz = cliente.ler(RAIZ_DA_PGFN).conteudo
    trimestres = sorted(m.decode() for m in PASTA_DO_TRIMESTRE.findall(raiz))
    if not trimestres:
        raise ErroDeDescoberta("PGFN: nenhuma pasta de trimestre na página")
    pasta = f"{RAIZ_DA_PGFN}{trimestres[-1]}/"
    zips = dict.fromkeys(
        m.decode() for m in ZIP_NA_PASTA.findall(cliente.ler(pasta).conteudo)
    )
    return [Alvo(pasta + nome) for nome in zips]


def _propfind(cliente: Cliente, token: str, caminho: str) -> list[str]:
    """Os nomes dentro de uma pasta do compartilhamento (WebDAV), sem a própria pasta."""
    chave = base64.b64encode(f"{token}:".encode()).decode()
    cabecalhos = {"Authorization": f"Basic {chave}", "Depth": "1"}
    resposta = cliente.ler(
        WEBDAV_DA_RECEITA + caminho + "/", metodo="PROPFIND", cabecalhos=cabecalhos
    )
    hrefs = [h.text or "" for h in ET.fromstring(resposta.conteudo).iter("{DAV:}href")]
    pasta = f"/public.php/webdav/{caminho}/"
    return [
        h.rstrip("/").rsplit("/", 1)[-1]
        for h in hrefs
        if h and h.rstrip("/") != pasta.rstrip("/")
    ]


def descobrir_cnpj(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os ZIPs do mês mais recente do CNPJ (Empresas, Estabelecimentos, Sócios, Simples...)."""
    final = cliente.ler(RAIZ_DO_CNPJ).url
    achado = TOKEN_DO_COMPARTILHAMENTO.search(final)
    if not achado:
        raise ErroDeDescoberta(f"CNPJ: sem o token do compartilhamento em {final}")
    token = achado.group(1)
    meses = sorted(n for n in _propfind(cliente, token, PASTA_DO_CNPJ) if MES.match(n))
    if not meses:
        raise ErroDeDescoberta("CNPJ: nenhuma pasta AAAA-MM no compartilhamento")
    pasta = f"{PASTA_DO_CNPJ}/{meses[-1]}"
    arquivos = [
        n for n in _propfind(cliente, token, pasta) if n.lower().endswith(".zip")
    ]
    return [
        Alvo(DOWNLOAD_DA_RECEITA.format(token=token, caminho=f"{pasta}/{n}"))
        for n in arquivos
    ]


def descobrir_scr(cliente: Cliente, agora: datetime) -> list[Alvo]:
    ultimo = (
        agora.year if agora.month >= MES_DO_PRIMEIRO_ARQUIVO_DO_SCR else agora.year - 1
    )
    return [
        Alvo(SCR_DO_ANO.format(ano=ano))
        for ano in range(PRIMEIRO_ANO_DO_SCR, ultimo + 1)
    ]


def _um(url: str, extensao: str | None = None) -> Descobrir:
    return lambda cliente, agora: [Alvo(url, extensao)]


def _catalogo(portal: str) -> Descobrir:
    return _um(f"{portal}/api/3/action/package_list", ".json")


FONTES: list[Fonte] = [
    # CVM: eventos e cadastros que só mostram o último dia útil
    Fonte("cvm-sancionador", "diaria", _ckan(PORTAL_DA_CVM, "processo-sancionador")),
    Fonte(
        "cvm-recompra",
        "diaria",
        _ckan(PORTAL_DA_CVM, "cia_aberta-eventos-recompra_acoes"),
    ),
    Fonte("cvm-ofertas", "diaria", _ckan(PORTAL_DA_CVM, "oferta-distrib")),
    Fonte(
        "cvm-cadastros",
        "diaria",
        _ckan(
            PORTAL_DA_CVM,
            "cia_aberta-cad",
            "auditor-cad",
            "cia_estrang-cad",
            "coord_oferta-cad",
            "intermed-cad",
            "agente_fiduc-cad",
        ),
    ),
    # CGU: sanções e leniência (sem chave, o arquivo de ontem)
    *(
        Fonte(f"cgu-{nome}", "diaria", descobrir_cgu(conjunto))
        for nome, conjunto in (
            ("ceis", "ceis"),
            ("cnep", "cnep"),
            ("cepim", "cepim"),
            ("leniencia", "acordos-leniencia"),
        )
    ),
    # termos de uso e catálogos (vigia: avisa quando mudam)
    *(
        Fonte(i, "diaria", _um(u), "pdf" if u.endswith(".pdf") else "html", vigia=True)
        for i, u in TERMOS.items()
    ),
    *(
        Fonte(i, "diaria", _catalogo(p), "json", vigia=True)
        for i, p in CATALOGOS.items()
    ),
    # semanais: a CVM só guarda os meses recentes do FIAGRO e reescreve o FIDC
    Fonte("cvm-fiagro", "semanal", _ckan(PORTAL_DA_CVM, "fiagro-doc-inf_mensal")),
    Fonte("cvm-fidc", "semanal", _ckan(PORTAL_DA_CVM, "fidc-doc-inf_mensal")),
    Fonte(
        "cvm-cri",
        "semanal",
        _ckan(PORTAL_DA_CVM, "securit-doc-inf_mensal_cri", "securit-doc-dfin_cri"),
    ),
    Fonte(
        "cvm-cra",
        "semanal",
        _ckan(PORTAL_DA_CVM, "securit-doc-inf_mensal_cra", "securit-doc-dfin_cra"),
    ),
    Fonte("cvm-cgvn", "semanal", _ckan(PORTAL_DA_CVM, "cia_aberta-doc-cgvn")),
    Fonte(
        "ibama-autos",
        "semanal",
        _ckan(PORTAL_DO_IBAMA, "fiscalizacao-auto-de-infracao"),
        pesada=True,
    ),
    Fonte(
        "ibama-embargos",
        "semanal",
        _ckan(PORTAL_DO_IBAMA, "fiscalizacao-termo-de-embargo"),
        pesada=True,
    ),
    Fonte("mte-lista-suja", "semanal", descobrir_lista_suja),
    Fonte("gleif-br", "semanal", descobrir_gleif, "json"),
    # mensais e pesadas (GBs)
    Fonte("rfb-cnpj", "mensal", descobrir_cnpj, pesada=True),
    Fonte("pgfn-divida", "mensal", descobrir_pgfn, pesada=True),
    # histórico completo da CVM (a CVM reescreve os anos antigos com reapresentações): todos os
    # anos, mas só baixa de novo o arquivo cujos cabeçalhos mudaram
    *(
        Fonte(f"cvm-hist-{nome}", "mensal", _pastas_da_cvm(*caminhos), pesada=True)
        for nome, caminhos in (
            ("ipe", ("CIA_ABERTA/DOC/IPE/DADOS/",)),  # desde 2003
            ("itr", ("CIA_ABERTA/DOC/ITR/DADOS/",)),  # desde 2011
            ("dfp", ("CIA_ABERTA/DOC/DFP/DADOS/",)),  # desde 2010
            ("fre", ("CIA_ABERTA/DOC/FRE/DADOS/",)),  # desde 2010
            ("fca", ("CIA_ABERTA/DOC/FCA/DADOS/",)),  # desde 2010: auditores, tickers
            ("vlmo", ("CIA_ABERTA/DOC/VLMO/DADOS/",)),  # desde 2018
            ("cda", ("FI/DOC/CDA/DADOS/", "FI/DOC/CDA/DADOS/HIST/")),  # desde 2005
        )
    ),
    # fontes abertas novas (pesquisa de 13–14/10/2026)
    Fonte("bcb-scr", "semanal", descobrir_scr, pesada=True),
    Fonte(
        "ccee-pld",
        "semanal",
        _ckan(
            "https://dadosabertos.ccee.org.br",
            "pld_horario",
            "pld_media_diaria",
            "pld_media_mensal",
        ),
    ),
    Fonte(
        "antt-pedagio",
        "semanal",
        _ckan("https://dados.antt.gov.br", "volume-trafego-praca-pedagio"),
    ),
    Fonte(
        "tesouro-br-divida",
        "semanal",
        _ckan(
            PORTAL_DO_TESOURO,
            "estoque-da-divida-publica-federal",
            "emissoes-e-resgates-divida-publica-federal",
            "capag-estados",
            "divida-consolidada-estados",
        ),
    ),
]

POR_ID = {fonte.id: fonte for fonte in FONTES}
GRUPOS = ("diaria", "semanal", "mensal")
