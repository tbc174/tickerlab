"""Catálogo do arquivista: cada fonte que só mostra o "agora" e como achar os seus arquivos.

Endereços conferidos em 14/10/2026. Licenças e motivos em `projeto-acoes/licencas-por-fonte.md`
(fora do repositório) e em `src/banco/coletas.py` (`LICENCAS`, `REVENDA`). Grupos: **diaria**
(2h), **semanal** (domingo) e **mensal** (dia 5: CNPJ; dia 6: PGFN).
"""

import base64
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from base import intradiario_b3
from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.obter import (
    csv_so_com_colunas,
    extrair_do_zip_remoto,
    json_so_com_campos,
    membros_do_zip_remoto,
    parquet_sem_colunas,
    zip_que_pode_faltar,
)

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

# "prévia do balanço" pelos reguladores (pesquisa de 14/10/2026, `tickerlab-fontes`
# `notas/previa-do-balanco/`): números mensais por empresa que saem antes do ITR
PORTAL_DO_ONS = "https://dados.ons.org.br"
PORTAL_DA_ANTT = "https://dados.antt.gov.br"
DADOS_DA_ANP = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
# a ANP não manda ETag nem Last-Modified (e recusa HEAD): o acervo guarda cada versão pelo SHA-256
VENDAS_DA_ANP = DADOS_DA_ANP + "arquivos/mdpg/{nome}.zip"
CONCESSIONARIOS_DA_ANP = DADOS_DA_ANP + "arquivos/rc/relacao-concessionarios.csv"
PAGINA_DA_PRODUCAO_DA_ANP = DADOS_DA_ANP + "fase-de-desenvolvimento-e-producao"
# produção por poço, um arquivo por ano (mar e terra); o nome muda de padrão (2024 é
# `producao_por_poco_2024.csv`), por isso os links saem da própria página
PRODUCAO_POR_POCO = re.compile(
    rb'href="([^"]*/arquivos-producao-de-petroleo-e-gas-natural-nacional/p[mt]/[^"]+\.csv)"'
)
# Comex Stat (MDIC): um CSV por ano desde 1997; o do ano corrente sai com janeiro, em fevereiro
COMEX = "https://balanca.mdic.gov.br/balanca/bd/"
PRIMEIRO_ANO_DO_COMEX = 1997
MES_DO_PRIMEIRO_ARQUIVO_DO_COMEX = 2
TABELAS_DO_COMEX = ("NCM", "PAIS", "UF", "URF", "VIA")
ESTATISTICO_DA_ANAC = "https://sistemas.anac.gov.br/dadosabertos/" + quote(
    "Voos e operações aéreas/Dados Estatísticos do Transporte Aéreo/Dados_Estatisticos.csv"
)
# a ANS regera o histórico inteiro a cada mês: só a nossa cópia guarda o "como era"; ~420 MB por
# mês, então só as duas safras mais recentes
BENEFICIARIOS_DA_ANS = "https://dadosabertos.ans.gov.br/FTP/PDA/informacoes_consolidadas_de_beneficiarios-024/"
PASTA_DO_MES = re.compile(rb'href="(\d{6})/"')
SAFRAS_DA_ANS = 2
BENEFICIARIOS_POR_OPERADORA_DA_ANS = (
    "https://dadosabertos.ans.gov.br/FTP/PDA/beneficiarios_vinculos_tipo_contratacao_vda/"
    "Beneficiarios_operadora_e_carteira.csv"
)
# SUSEP (série 4, PR 5b): o SES inteiro é um ZIP de ~580 MB regerado todo dia; saem de dentro dele só
# os prêmios e sinistros por seguradora e os cadastros. Nunca os CSVs com pessoas (administradores,
# contatos, acionistas): a lista é fechada
SES_DA_SUSEP = "https://www2.susep.gov.br/download/estatisticas/BaseCompleta.zip"
CSVS_DA_SUSEP = (
    "Ses_seguros.csv",
    "Ses_cias.csv",
    "Ses_ramos.csv",
    "ses_gruposramos.csv",
)
# cadastros com CNPJ para a B13 ligar a ANS e a SUSEP às companhias (16/10/2026). Só as colunas da
# lista: o da ANS traz o nome do representante, e-mail e telefone; o da SUSEP, endereço e telefone
CADASTRO_DA_ANS = "https://dadosabertos.ans.gov.br/FTP/PDA/operadoras_de_plano_de_saude_{situacao}/{arquivo}"
ARQUIVOS_DO_CADASTRO_DA_ANS = {
    "ativas": "Relatorio_cadop.csv",
    "canceladas": "Relatorio_cadop_canceladas.csv",
}
COLUNAS_DO_CADASTRO_DA_ANS = (
    "REGISTRO_OPERADORA", "CNPJ", "RAZAO_SOCIAL", "NOME_FANTASIA", "MODALIDADE", "UF",
    "DATA_REGISTRO_ANS", "DATA_DESCREDENCIAMENTO", "MOTIVO_DO_DESCREDENCIAMENTO",
)  # fmt: skip
CADASTRO_DA_SUSEP = "https://dados.susep.gov.br/olinda/servico/empresas/versao/v1/odata/DadosCadastrais?$format=json"
CAMPOS_DO_CADASTRO_DA_SUSEP = (
    "mercodigo",
    "entcodigofip",
    "entnome",
    "entcgc",
    "dataautorizacao",
)
# 2ª leva (14/10/2026)
# Anatel: só os CSVs de formato largo ("_Colunas", um por período) e os totais, lidos por partes de
# dentro dos ZIPs (o de telefonia móvel tem 3,2 GB; os "_Colunas" somam ~70 MB comprimidos)
ZIPS_DA_ANATEL = tuple(
    f"https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/{nome}.zip"
    for nome in (
        "acessos_telefonia_movel",
        "acessos_banda_larga_fixa",
        "acessos_tv_por_assinatura",
    )
)
CSV_DA_ANATEL = re.compile(r"(_Colunas|_Total)\.csv$", re.IGNORECASE)
# Pix: chaves por participante no fim de cada mês (API Olinda do BC); as três últimas datas cobrem o
# atraso de publicação (o fim de setembro já estava lá em 14/10)
CHAVES_PIX = (
    "https://olinda.bcb.gov.br/olinda/servico/Pix_DadosAbertos/versao/v1/odata/"
    "ChavesPix(Data=@Data)?@Data='{data}'&$format=json"
)
MESES_DO_PIX = 3
# SAMP (mercado por distribuidora): CPF e nome de quem compra energia saem antes de guardar (LGPD)
PORTAL_DA_ANEEL = "https://dadosabertos.aneel.gov.br"
COLUNAS_PESSOAIS_DO_SAMP = ("NumCNPJAgenteAcessante", "NomAgenteAcessante")
# negócios do pregão da B3 (ADR 0073; só pesquisa, ADR 0019): só os últimos ~20 pregões ficam no ar.
# Medido em 14/10/2026: dia fora da janela responde 200 com 0 bytes; feriado e dia que ainda não
# saiu, 404; HEAD dá 405 (sem ETag nem Last-Modified)
NEGOCIOS_DA_B3 = "https://arquivos.b3.com.br/rapinegocios/tickercsv/{dia}"
DIAS_DA_JANELA_DA_B3 = 30  # dias corridos, hoje incluído: cobre os 20 pregões
FUSO_DA_B3 = ZoneInfo("America/Sao_Paulo")
# um dia guardado vale se o selo (`base/intradiario_b3.py`, contra o boletim PR) diz `completo`;
# `incompleto` é baixado de novo a cada rodada, para ver se a B3 corrigiu (15/09, 22/09, 29/09 e
# 09/10/2026 vieram quebrados). Antes de o selo sair (o dia acabou de ser baixado, ou ainda sem
# boletim), a regra da ponte: um pregão inteiro tem de 80 a 200 MB, menor que 40 MB veio incompleto
TAMANHO_MINIMO_DE_UM_DIA_BOM = 40_000_000
# boletins oficiais do dia, para o selo: o PR (BVBG.086, todos os instrumentos; sai em várias versões
# até ~21h, um zip dentro de outro) e o COTAHIST do dia (houve pregão? quais são do mercado à vista?)
BOLETIM_PR_DA_B3 = (
    "https://www.b3.com.br/pesquisapregao/download?filelist=PR{aammdd}.zip"
)
COTAHIST_DO_DIA = (
    "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{ddmmaaaa}.ZIP"
)


def _json(cliente: Cliente, url: str) -> dict:
    return json.loads(cliente.ler(url).conteudo)


def _e_arquivo(recurso: dict) -> bool:
    """Recurso que é arquivo de dados (não painel nem página: a ANTT lista um Power BI)."""
    url = recurso.get("url") or ""
    formato = (recurso.get("format") or "").lower()
    return bool(url) and formato != "html" and not any(p in url for p in PAINEIS)


def descobrir_ckan(
    cliente: Cliente, portal: str, *pacotes: str, formatos: tuple[str, ...] = ()
) -> list[Alvo]:
    """Os arquivos (recursos) dos pacotes de um portal CKAN (CVM, IBAMA, CCEE, ANTT...).

    `formatos` ("parquet", "pdf") escolhe um só formato quando o portal publica o mesmo dado em
    vários (o ONS põe cada mês em CSV, XLSX e Parquet).
    """
    alvos: list[Alvo] = []
    for pacote in pacotes:
        resposta = _json(cliente, f"{portal}/api/3/action/package_show?id={pacote}")
        recursos = [
            r
            for r in resposta.get("result", {}).get("resources", [])
            if _e_arquivo(r)
            and (not formatos or (r.get("format") or "").lower() in formatos)
        ]
        if not recursos:
            raise ErroDeDescoberta(f"{pacote}: pacote sem arquivos em {portal}")
        alvos += [Alvo(r["url"]) for r in recursos]
    return alvos


def _ckan(portal: str, *pacotes: str, formatos: tuple[str, ...] = ()) -> Descobrir:
    return lambda cliente, agora: descobrir_ckan(
        cliente, portal, *pacotes, formatos=formatos
    )


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


def descobrir_links(
    cliente: Cliente, pagina: str, padrao: re.Pattern[bytes]
) -> list[Alvo]:
    """Os arquivos linkados numa página (sem repetir), quando o nome muda e não há catálogo."""
    achados = padrao.findall(cliente.ler(pagina).conteudo)
    links = dict.fromkeys(m.decode() for m in achados)
    if not links:
        raise ErroDeDescoberta(f"nenhum arquivo linkado em {pagina}")
    return [Alvo(link) for link in links]


def descobrir_comex(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Exportação e importação por NCM e por município (um CSV por ano), totais e tabelas."""
    ultimo = (
        agora.year
        if agora.month >= MES_DO_PRIMEIRO_ARQUIVO_DO_COMEX
        else agora.year - 1
    )
    anos = range(PRIMEIRO_ANO_DO_COMEX, ultimo + 1)
    alvos = [
        Alvo(f"{COMEX}comexstat-bd/{pasta}/{fluxo}_{ano}{sufixo}.csv")
        for pasta, sufixo in (("ncm", ""), ("mun", "_MUN"))
        for fluxo in ("EXP", "IMP")
        for ano in anos
    ]
    alvos += [
        Alvo(f"{COMEX}comexstat-bd/ncm/{fluxo}_TOTAIS_CONFERENCIA.csv")
        for fluxo in ("EXP", "IMP")
    ]
    return alvos + [Alvo(f"{COMEX}tabelas/{nome}.csv") for nome in TABELAS_DO_COMEX]


def descobrir_beneficiarios_ans(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os ZIPs das duas safras mais recentes das informações consolidadas de beneficiários."""
    raiz = cliente.ler(BENEFICIARIOS_DA_ANS).conteudo
    meses = sorted(m.decode() for m in PASTA_DO_MES.findall(raiz))
    if not meses:
        raise ErroDeDescoberta("ANS: nenhuma pasta AAAAMM de beneficiários")
    alvos: list[Alvo] = []
    for mes in meses[-SAFRAS_DA_ANS:]:
        pasta = f"{BENEFICIARIOS_DA_ANS}{mes}/"
        zips = dict.fromkeys(
            m.decode() for m in ZIP_NA_PASTA.findall(cliente.ler(pasta).conteudo)
        )
        alvos += [Alvo(pasta + nome) for nome in zips]
    return alvos


def descobrir_vendas_anp(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Vendas por distribuidora: combustíveis líquidos, GLP e aviação (um ZIP cada)."""
    return [
        Alvo(VENDAS_DA_ANP.format(nome=nome)) for nome in ("liquidos", "glp", "aviacao")
    ]


def descobrir_producao_anp(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return descobrir_links(cliente, PAGINA_DA_PRODUCAO_DA_ANP, PRODUCAO_POR_POCO)


def descobrir_anatel(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os CSVs "_Colunas" e "_Total" de cada ZIP de acessos (o endereço guarda `zip#arquivo`)."""
    alvos: list[Alvo] = []
    for url in ZIPS_DA_ANATEL:
        membros = [
            m for m in membros_do_zip_remoto(cliente, url) if CSV_DA_ANATEL.search(m)
        ]
        if not membros:
            raise ErroDeDescoberta(f"Anatel: nenhum CSV de acessos em {url}")
        alvos += [
            Alvo(f"{url}#{membro}", ".csv", extrair_do_zip_remoto(url, membro))
            for membro in membros
        ]
    return alvos


def descobrir_susep(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Os CSVs escolhidos de dentro do ZIP do SES (o endereço guarda `zip#arquivo`)."""
    membros = set(membros_do_zip_remoto(cliente, SES_DA_SUSEP))
    if faltam := [m for m in CSVS_DA_SUSEP if m not in membros]:
        raise ErroDeDescoberta(f"SUSEP: o ZIP do SES não tem {', '.join(faltam)}")
    return [
        Alvo(
            f"{SES_DA_SUSEP}#{membro}",
            ".csv",
            extrair_do_zip_remoto(SES_DA_SUSEP, membro),
        )
        for membro in CSVS_DA_SUSEP
    ]


def descobrir_cadastro_da_ans(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """As operadoras ativas e as canceladas (com CNPJ), sem as colunas de contato e representante."""
    return [
        Alvo(url, ".csv", csv_so_com_colunas(url, COLUNAS_DO_CADASTRO_DA_ANS, "utf-8"))
        for url in (
            CADASTRO_DA_ANS.format(situacao=situacao, arquivo=arquivo)
            for situacao, arquivo in ARQUIVOS_DO_CADASTRO_DA_ANS.items()
        )
    ]


def descobrir_cadastro_da_susep(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """As entidades autorizadas pela SUSEP (código FIP e CNPJ), sem endereço nem telefone."""
    return [
        Alvo(
            CADASTRO_DA_SUSEP,
            ".json",
            json_so_com_campos(CADASTRO_DA_SUSEP, CAMPOS_DO_CADASTRO_DA_SUSEP),
        )
    ]


def _fim_dos_meses(agora: datetime, quantos: int) -> list[date]:
    """O último dia de cada um dos `quantos` meses fechados antes de `agora`."""
    dias: list[date] = []
    primeiro = agora.date().replace(day=1)
    for _ in range(quantos):
        fim = primeiro - timedelta(days=1)
        dias.append(fim)
        primeiro = fim.replace(day=1)
    return sorted(dias)


def descobrir_pix(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        Alvo(CHAVES_PIX.format(data=dia.isoformat()), ".json")
        for dia in _fim_dos_meses(agora, MESES_DO_PIX)
    ]


def descobrir_samp(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um Parquet por ano desde 2003 (o CSV é o mesmo dado, 30 vezes maior), sem as colunas
    pessoais."""
    return [
        Alvo(
            alvo.url,
            ".parquet",
            parquet_sem_colunas(alvo.url, COLUNAS_PESSOAIS_DO_SAMP),
        )
        for alvo in descobrir_ckan(
            cliente, PORTAL_DA_ANEEL, "samp", formatos=("parquet",)
        )
    ]


def alvo_dos_negocios_b3(dia: date) -> Alvo:
    url = NEGOCIOS_DA_B3.format(dia=dia.isoformat())
    return Alvo(url, ".zip", zip_que_pode_faltar(url))


def _dias_da_janela_da_b3(agora: datetime) -> list[date]:
    """Os dias úteis da janela da B3, do mais antigo a hoje (no fuso de São Paulo: a rodada das 22h
    já é o dia seguinte em UTC). Feriado entra e responde 404: o calendário fica com a B3."""
    hoje = agora.astimezone(FUSO_DA_B3).date()
    dias = (hoje - timedelta(days=n) for n in range(DIAS_DA_JANELA_DA_B3 - 1, -1, -1))
    return [dia for dia in dias if dia.weekday() < 5]


def descobrir_negocios_b3(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [alvo_dos_negocios_b3(dia) for dia in _dias_da_janela_da_b3(agora)]


def _zip_do_dia(endereco: str) -> Alvo:
    return Alvo(endereco, ".zip", zip_que_pode_faltar(endereco))


def descobrir_boletim_pr(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        _zip_do_dia(BOLETIM_PR_DA_B3.format(aammdd=f"{dia:%y%m%d}"))
        for dia in _dias_da_janela_da_b3(agora)
    ]


def descobrir_cotahist_do_dia(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [
        _zip_do_dia(COTAHIST_DO_DIA.format(ddmmaaaa=f"{dia:%d%m%Y}"))
        for dia in _dias_da_janela_da_b3(agora)
    ]


def _pregao_inteiro_ja_guardado(anterior: sa.Row) -> bool:
    resumo = intradiario_b3.resumo_guardado(
        intradiario_b3.pregao_do_endereco(anterior.url)
    )
    if (
        resumo is not None
        and resumo.get("sha256_do_arquivo") == anterior.sha256
        and resumo.get("selo_do_dia") != intradiario_b3.SELO_SEM_BOLETIM
    ):
        return resumo.get("selo_do_dia") == intradiario_b3.SELO_COMPLETO
    return (anterior.bytes or 0) >= TAMANHO_MINIMO_DE_UM_DIA_BOM


def _boletim_final_ja_guardado(anterior: sa.Row) -> bool:
    """Baixado depois do dia do pregão (rodada das 2h): já é a última versão da noite."""
    baixado = anterior.baixado_em
    if baixado.tzinfo is None:  # o SQLite dos testes devolve sem fuso
        baixado = baixado.replace(tzinfo=UTC)
    pregao = intradiario_b3.pregao_do_endereco(anterior.url)
    return baixado.astimezone(FUSO_DA_B3).date() > pregao


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
        _ckan(PORTAL_DA_ANTT, "volume-trafego-praca-pedagio"),
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
    # curva de juros própria sem B3 nem ANBIMA (série B12, 14/10/2026): taxas e PUs de todos os
    # títulos do Tesouro Direto desde 2004 (CSV republicado todo dia útil) e os leilões desde 2000
    Fonte(
        "tesouro-br-direto",
        "diaria",
        _ckan(PORTAL_DO_TESOURO, "taxas-dos-titulos-ofertados-pelo-tesouro-direto"),
    ),
    Fonte("tesouro-br-leiloes", "semanal", _ckan(PORTAL_DO_TESOURO, "ds013")),
    # prévia do balanço, 1ª leva (14/10/2026): licença lida no catálogo nacional (dados.gov.br)
    Fonte("anp-vendas-distribuidora", "semanal", descobrir_vendas_anp),
    Fonte("anp-producao-poco", "mensal", descobrir_producao_anp),
    Fonte("anp-concessionarios", "mensal", _um(CONCESSIONARIOS_DA_ANP)),
    # ONS: um arquivo por mês (desde 2000 na geração); só baixa o que mudou de ETag
    Fonte(
        "ons-geracao-usina",
        "semanal",
        _ckan(PORTAL_DO_ONS, "geracao-usina-2", formatos=("parquet", "pdf")),
        pesada=True,
    ),
    Fonte(
        "ons-restricao-eolica-solar",
        "semanal",
        _ckan(
            PORTAL_DO_ONS,
            "restricao_coff_eolica_usi",
            "restricao_coff_fotovoltaica",
            formatos=("parquet", "pdf"),
        ),
        pesada=True,
    ),
    Fonte(
        "ons-capacidade-geracao",
        "semanal",
        _ckan(PORTAL_DO_ONS, "capacidade-geracao", formatos=("parquet", "pdf")),
    ),
    Fonte(
        "antt-siade",
        "semanal",
        _ckan(
            PORTAL_DA_ANTT,
            "sistema-de-acompanhamento-do-desempenho-operacional-das-concessionarias-siade",
            formatos=("csv", "pdf"),
        ),
        pesada=True,
    ),
    Fonte("comexstat", "semanal", descobrir_comex, pesada=True),
    Fonte("anac-estatistico", "mensal", _um(ESTATISTICO_DA_ANAC), pesada=True),
    Fonte("ans-beneficiarios", "semanal", descobrir_beneficiarios_ans, pesada=True),
    # série 4, PR 5: beneficiários por operadora e mês desde 2017 (57 MB; as consolidadas, acima,
    # só começam em 05/2021 e pesam ~135 MB por UF e mês); a ANS regrava o arquivo e revisa meses
    Fonte(
        "ans-beneficiarios-operadora", "mensal", _um(BENEFICIARIOS_POR_OPERADORA_DA_ANS)
    ),
    # 2ª leva: formas especiais de obter (`base/arquivo/obter.py`)
    Fonte("anatel-acessos", "mensal", descobrir_anatel, pesada=True),
    Fonte("bcb-pix-chaves", "mensal", descobrir_pix, "json"),
    Fonte("aneel-samp", "mensal", descobrir_samp, pesada=True),
    Fonte("susep-ses", "mensal", descobrir_susep, pesada=True),
    Fonte("ans-operadoras", "mensal", descobrir_cadastro_da_ans),
    Fonte("susep-cadastro", "mensal", descobrir_cadastro_da_susep),
    # intradiários da B3 (ADR 0073): também às 22h, só ela (cron do servidor de casa)
    Fonte(
        "b3-negocios",
        "diaria",
        descobrir_negocios_b3,
        "zip",
        pesada=True,
        guardado_vale=_pregao_inteiro_ja_guardado,
    ),
    Fonte(
        "b3-boletim-pr",
        "diaria",
        descobrir_boletim_pr,
        "zip",
        guardado_vale=_boletim_final_ja_guardado,
    ),
    Fonte(
        "b3-cotahist-dia",
        "diaria",
        descobrir_cotahist_do_dia,
        "zip",
        guardado_vale=_boletim_final_ja_guardado,
    ),
]

POR_ID = {fonte.id: fonte for fonte in FONTES}
GRUPOS = ("diaria", "semanal", "mensal")
