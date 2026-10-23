"""Lote "atenção e texto" (rodada 4 da pesquisa de dados escondidos, linha 289 da fila): quanto se fala
de cada empresa e o que se diz (tema e tom), sem guardar texto de terceiros nem pessoa.

Fontes (ADR 0102: coleta com ritmo, uso citando a fonte; ADR 0088: **nunca pessoa física**):

- **Wikimedia, acessos por artigo** (CC0): um pedido por empresa e por mês, na API REST, com o agente
  do TickerLab. Os dumps horários (1,4 GB por dia) não valem;
- **GDELT GKG 2.1** (uso livre citando o GDELT): os arquivos brutos de 15 minutos de **ontem** (96
  ZIPs de 6 a 10 MB). Cada arquivo é filtrado antes de guardar: ficam só o dia, a organização que é
  uma das nossas empresas, os temas e o tom; `Persons`, o endereço da notícia e todo o resto saem;
- **Querido Diário** (CC BY 4.0): quantos diários oficiais municipais citam a empresa no mês, só com
  a cidade, a data e o link; o trecho do diário (`excerpts`, que pode trazer nome de servidor) sai;
- **Crossref e OpenAlex** (sem direitos / CC0): só contagens de obras por afiliação e por ano,
  nunca autores;
- **RSS das agências públicas** (Agência Brasil, Senado, Câmara): só índice (data, título e link); o
  resumo e o texto são de terceiros e não entram.

A lista de empresas vem do Wikidata ao vivo (as listadas na B3, Q796297, com artigo na Wikipédia em
português, sem gente): ela dá o título do artigo e o nome para a busca. O cruzamento LEI/ISIN/CNPJ do
lote cadastros fica para a carga na base (a dependência está na fila).

Limites que o dado tem e que ninguém deve esconder (testes em `tests/test_base_arquivo_lote_atencao.py`):
- o GKG casa o **nome** da organização com o da empresa (sem sufixo "S.A."); nome comum ("Vale",
  "Light") traz falso positivo, e quem usa decide com o tema que vem junto;
- o RSS só guarda a janela que o site mostra na hora (as últimas dezenas de itens): dia sem coleta
  é dia perdido;
- cada filtro de LGPD é uma função de arquivo para arquivo, testada com um dublê que traz pessoa;
- API que falha ou muda de formato é falha (`ErroDeDescoberta` ou erro), nunca "nada novo"; o que a
  fonte diz que não tem (404 de artigo sem acesso, GKG ainda não publicado) é `SemArquivo`.
"""

import csv
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode

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
from base.arquivo.lote_cadastros import ITEM_B3, SEM_GENTE, endereco_do_wikidata

PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS = 1.0
# o Querido Diário responde 429 e demora (23 s numa das sondas): espera maior
PAUSA_ENTRE_PEDIDOS_AO_QUERIDO_DIARIO_EM_SEGUNDOS = 5.0
HTTP_NAO_ENCONTRADO = 404

# ---- a lista de empresas (Wikidata) ----------------------------------------------------------
TAMANHO_MINIMO_DO_NOME_NO_GKG = 4  # "Gol" e "Oi" casam com tudo
SUFIXOS_SOCIETARIOS = frozenset(
    {
        "sa",
        "s.a.",
        "s.a",
        "ltda",
        "ltd",
        "inc",
        "corp",
        "co",
        "plc",
        "holding",
        "holdings",
        "cia",
    }
)


@dataclass(frozen=True)
class Empresa:
    titulo: str  # o título do artigo na Wikipédia em português
    nome: str  # o nome para as buscas (o rótulo em português, ou o título)


def consulta_das_empresas_da_b3() -> str:
    """As empresas listadas na B3 com artigo na Wikipédia em português: título e nome, sem gente, em
    ordem de item (a ordem fixa faz o SHA-256 dizer "igual" quando nada mudou)."""
    return (
        "SELECT ?item ?titulo ?nome WHERE { ?item p:P414 ?bolsa . "
        f"?bolsa ps:P414 wd:{ITEM_B3} . "
        "?artigo schema:about ?item ; schema:isPartOf <https://pt.wikipedia.org/> ; "
        "schema:name ?titulo . "
        'OPTIONAL { ?item rdfs:label ?nome FILTER(LANG(?nome) = "pt") } '
        f"{SEM_GENTE} }} ORDER BY ?item"
    )


def empresas_do_wikidata(resposta: bytes) -> list[Empresa]:
    """Lê a resposta do SPARQL; título repetido (empresa com mais de um item) conta uma vez."""
    try:
        linhas = json.loads(resposta)["results"]["bindings"]
    except (ValueError, KeyError, TypeError) as erro:
        raise ErroDeDescoberta("Wikidata: resposta fora do formato SPARQL") from erro
    vistos: dict[str, Empresa] = {}
    for linha in linhas:
        titulo = linha["titulo"]["value"].strip()
        nome = linha.get("nome", {}).get("value", titulo).strip()
        vistos.setdefault(titulo, Empresa(titulo, nome or titulo))
    if not vistos:
        raise ErroDeDescoberta("Wikidata: nenhuma empresa da B3 com artigo em pt")
    return list(vistos.values())


def _empresas_com_memoria() -> Callable[[Cliente], list[Empresa]]:
    """Uma consulta ao Wikidata por montagem das fontes: as cinco descobertas dividem a lista."""
    guardada: list[list[Empresa]] = []

    def empresas(cliente: Cliente) -> list[Empresa]:
        if not guardada:
            url = endereco_do_wikidata(consulta_das_empresas_da_b3())
            guardada.append(empresas_do_wikidata(cliente.ler(url).conteudo))
        return guardada[0]

    return empresas


# ---- janelas de tempo ------------------------------------------------------------------------
def mes_anterior(agora: datetime) -> tuple[date, date]:
    """Primeiro e último dia do mês que já fechou (o dado dele não muda mais)."""
    ultimo = agora.date().replace(day=1) - timedelta(days=1)
    return ultimo.replace(day=1), ultimo


# ---- baixar, ou dizer que a fonte não tem ----------------------------------------------------
def _baixar_ou_sem_arquivo(
    cliente: Cliente, url: str, bruto: Path, motivo: str
) -> Mapping[str, str]:
    try:
        return cliente.baixar(url, bruto)
    except requests.HTTPError as erro:
        resposta = erro.response
        if resposta is not None and resposta.status_code == HTTP_NAO_ENCONTRADO:
            raise SemArquivo(f"HTTP 404 ({motivo})") from erro
        raise


def _filtrado(url: str, motivo: str, filtro: Callable[[Path, Path], object]) -> Obter:
    """Baixa para `.bruto`, grava em `destino` só o que o `filtro` deixa passar e apaga o bruto."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = _baixar_ou_sem_arquivo(cliente, url, bruto, motivo)
            filtro(bruto, destino)
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


# ---- Wikimedia -------------------------------------------------------------------------------
ACESSOS_DA_WIKIMEDIA = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/pt.wikipedia/"
    "all-access/user/{artigo}/daily/{inicio}/{fim}"
)


def endereco_dos_acessos(titulo: str, inicio: date, fim: date) -> str:
    artigo = quote(titulo.replace(" ", "_"), safe="")
    return ACESSOS_DA_WIKIMEDIA.format(
        artigo=artigo, inicio=f"{inicio:%Y%m%d}", fim=f"{fim:%Y%m%d}"
    )


def descobrir_acessos(
    empresas: Callable[[Cliente], list[Empresa]],
) -> Descobrir:
    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        inicio, fim = mes_anterior(agora)
        return [
            Alvo(
                url := endereco_dos_acessos(e.titulo, inicio, fim),
                ".json",
                _com_404_sem_arquivo(url, "artigo sem acesso no mês"),
            )
            for e in empresas(cliente)
        ]

    return _descobrir


def _com_404_sem_arquivo(url: str, motivo: str) -> Obter:
    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        return _baixar_ou_sem_arquivo(cliente, url, destino, motivo)

    return obter


# ---- GDELT GKG 2.1 ---------------------------------------------------------------------------
ARQUIVO_DO_GKG = "https://data.gdeltproject.org/gdeltv2/{momento}.gkg.csv.zip"
ARQUIVOS_DO_GKG_POR_DIA = 96  # um a cada 15 minutos
MINUTOS_ENTRE_ARQUIVOS_DO_GKG = 15
# colunas do GKG 2.1 (27, separadas por tabulação, sem cabeçalho). `Persons` (11 e 12) nunca é lida
COLUNA_DA_DATA_NO_GKG = 1
COLUNA_DOS_TEMAS_NO_GKG = 8  # V2Themes: "TEMA,posição;TEMA,posição"
COLUNA_DAS_ORGANIZACOES_NO_GKG = 14  # V2Organizations: "nome,posição;nome,posição"
COLUNA_DO_TOM_NO_GKG = 15  # V2Tone: tom, positivo, negativo, polaridade, atividade, ...
COLUNAS_DO_GKG = 27
CABECALHO_DO_GKG_FILTRADO = ("data", "empresa", "temas", "tom", "positivo", "negativo")
SEPARADOR_DOS_TEMAS = "|"


def _sem_acento_e_minusculo(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def chave_do_nome(texto: str) -> str:
    """O nome sem acento, minúsculo e sem sufixo societário ("Petrobras S.A." → "petrobras"): a
    mesma chave para o nome da empresa e para a organização que o GKG cita."""
    partes = _sem_acento_e_minusculo(texto).replace(",", " ").split()
    while partes and partes[-1] in SUFIXOS_SOCIETARIOS:
        partes.pop()
    return " ".join(partes)


def nomes_para_o_gkg(empresas: list[Empresa]) -> dict[str, str]:
    """Chave do nome → título da empresa. Nome curto demais fica fora: casaria com palavra comum."""
    nomes: dict[str, str] = {}
    for empresa in empresas:
        for candidato in (empresa.nome, empresa.titulo):
            chave = chave_do_nome(candidato)
            if len(chave) >= TAMANHO_MINIMO_DO_NOME_NO_GKG:
                nomes.setdefault(chave, empresa.titulo)
    return nomes


def _sem_posicao(lista: str) -> list[str]:
    """ "nome,123;outro,456" → ["nome", "outro"] (a posição no texto da notícia não interessa)."""
    return [item.rsplit(",", 1)[0] for item in lista.split(";") if item]


def gkg_so_com_as_empresas(
    bruto: Path, destino: Path, nomes: dict[str, str]
) -> tuple[int, int]:
    """Regrava o ZIP do GKG como um CSV só com (dia, empresa, temas, tom): uma linha por empresa
    citada em cada registro. Nada mais passa: `Persons`, o endereço e o texto da notícia ficam para
    trás (ADR 0088). Devolve (registros lidos, linhas gravadas). Lê em fluxo."""
    lidos = gravados = 0
    with (
        zipfile.ZipFile(bruto) as entrada,
        destino.open("w", encoding="utf-8", newline="") as saida,
    ):
        escritor = csv.writer(saida, lineterminator="\n")
        escritor.writerow(CABECALHO_DO_GKG_FILTRADO)
        (membro,) = [m for m in entrada.infolist() if m.filename.endswith(".csv")]
        with (
            entrada.open(membro) as bytes_do_csv,
            io.TextIOWrapper(bytes_do_csv, encoding="utf-8", errors="replace") as texto,
        ):
            for linha in texto:
                campos = linha.rstrip("\r\n").split("\t")
                if len(campos) < COLUNAS_DO_GKG:
                    continue  # linha cortada: nunca adivinhar a coluna
                lidos += 1
                citadas = {
                    nomes[chave]
                    for organizacao in _sem_posicao(
                        campos[COLUNA_DAS_ORGANIZACOES_NO_GKG]
                    )
                    if (chave := chave_do_nome(organizacao)) in nomes
                }
                if not citadas:
                    continue
                temas = SEPARADOR_DOS_TEMAS.join(
                    dict.fromkeys(_sem_posicao(campos[COLUNA_DOS_TEMAS_NO_GKG]))
                )
                tom = (campos[COLUNA_DO_TOM_NO_GKG].split(",") + ["", "", ""])[:3]
                for empresa in sorted(citadas):
                    escritor.writerow(
                        [campos[COLUNA_DA_DATA_NO_GKG][:8], empresa, temas, *tom]
                    )
                    gravados += 1
    return lidos, gravados


def endereco_do_gkg(momento: datetime) -> str:
    return ARQUIVO_DO_GKG.format(momento=f"{momento:%Y%m%d%H%M%S}")


def momentos_do_dia(dia: date) -> list[datetime]:
    """Os 96 arquivos de 15 minutos do dia (de 00:00:00 a 23:45:00)."""
    primeiro = datetime(dia.year, dia.month, dia.day, tzinfo=UTC)
    passo = timedelta(minutes=MINUTOS_ENTRE_ARQUIVOS_DO_GKG)
    return [primeiro + i * passo for i in range(ARQUIVOS_DO_GKG_POR_DIA)]


def descobrir_gkg(
    empresas: Callable[[Cliente], list[Empresa]],
) -> Descobrir:
    """Os 96 arquivos de ontem (o dia já fechou). Dia perdido não se recupera sozinho: carga de
    história é outra fila (`masterfilelist`)."""

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        nomes = nomes_para_o_gkg(empresas(cliente))
        ontem = agora.date() - timedelta(days=1)
        return [
            Alvo(
                url := endereco_do_gkg(momento),
                ".csv",
                _filtrado(
                    url,
                    "arquivo de 15 minutos que o GDELT ainda não publicou",
                    lambda bruto, destino: gkg_so_com_as_empresas(
                        bruto, destino, nomes
                    ),
                ),
            )
            for momento in momentos_do_dia(ontem)
        ]

    return _descobrir


# ---- Querido Diário --------------------------------------------------------------------------
QUERIDO_DIARIO = "https://api.queridodiario.org.br/gazettes"
DIARIOS_POR_PEDIDO = 100
CAMPOS_DO_DIARIO_QUE_FICAM = (
    "territory_id",
    "territory_name",
    "state_code",
    "date",
    "edition",
    "is_extra_edition",
    "url",
)


def endereco_do_querido_diario(nome: str, inicio: date, fim: date) -> str:
    consulta = {
        "querystring": f'"{nome}"',
        "published_since": inicio.isoformat(),
        "published_until": fim.isoformat(),
        "size": DIARIOS_POR_PEDIDO,
        "sort_by": "descending_date",
    }
    return f"{QUERIDO_DIARIO}?{urlencode(consulta)}"


def diarios_sem_trecho(bruto: Path, destino: Path) -> None:
    """Guarda o total e, de cada diário, só a cidade, a data, a edição e o link. O `excerpts` (texto
    do diário, que traz nome de servidor e de morador) e a `txt_url` ficam de fora (ADR 0088)."""
    try:
        resposta = json.loads(bruto.read_bytes())
        diarios = resposta["gazettes"]
        total = resposta["total_gazettes"]
    except (ValueError, KeyError, TypeError) as erro:
        raise ValueError("o Querido Diário não devolveu `gazettes`") from erro
    enxutos = [
        {campo: d.get(campo) for campo in CAMPOS_DO_DIARIO_QUE_FICAM} for d in diarios
    ]
    destino.write_text(
        json.dumps({"total_gazettes": total, "gazettes": enxutos}, ensure_ascii=False),
        encoding="utf-8",
    )


def descobrir_querido_diario(
    empresas: Callable[[Cliente], list[Empresa]],
) -> Descobrir:
    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        inicio, fim = mes_anterior(agora)
        return [
            Alvo(
                url := endereco_do_querido_diario(e.nome, inicio, fim),
                ".json",
                _filtrado(url, "busca sem retorno", diarios_sem_trecho),
            )
            for e in empresas(cliente)
        ]

    return _descobrir


# ---- Crossref e OpenAlex ---------------------------------------------------------------------
OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
ANOS_NA_FACETA_DO_CROSSREF = 100
# vírgula, dois-pontos e barra vertical quebram o filtro do OpenAlex
CARACTERES_DO_FILTRO_DO_OPENALEX = re.compile(r"[,:|]")


def endereco_do_openalex(nome: str) -> str:
    limpo = " ".join(CARACTERES_DO_FILTRO_DO_OPENALEX.sub(" ", nome).split())
    filtro = f"raw_affiliation_strings.search:{limpo}"
    consulta = {"filter": filtro, "group_by": "publication_year", "per-page": 200}
    return f"{OPENALEX}?{urlencode(consulta)}"


def endereco_do_crossref(nome: str) -> str:
    consulta = {
        "query.affiliation": nome,
        "rows": 0,
        "facet": f"published:{ANOS_NA_FACETA_DO_CROSSREF}",
    }
    return f"{CROSSREF}?{urlencode(consulta)}"


def contagens_do_openalex(bruto: Path, destino: Path) -> None:
    """Só o total e as obras por ano. A consulta é agrupada: autor não vem, e aqui não passa."""
    try:
        resposta = json.loads(bruto.read_bytes())
        por_ano = [{"ano": g["key"], "obras": g["count"]} for g in resposta["group_by"]]
        total = resposta["meta"]["count"]
    except (ValueError, KeyError, TypeError) as erro:
        raise ValueError("o OpenAlex não devolveu `group_by` e `meta.count`") from erro
    destino.write_text(
        json.dumps({"total": total, "por_ano": por_ano}, ensure_ascii=False),
        encoding="utf-8",
    )


def contagens_do_crossref(bruto: Path, destino: Path) -> None:
    """Só o total e as obras por ano de publicação (`rows=0`: nenhuma obra, nenhum autor)."""
    try:
        mensagem = json.loads(bruto.read_bytes())["message"]
        total = mensagem["total-results"]
        por_ano = mensagem["facets"]["published"]["values"]
    except (ValueError, KeyError, TypeError) as erro:
        raise ValueError("o Crossref não devolveu `total-results` e a faceta") from erro
    destino.write_text(
        json.dumps({"total": total, "por_ano": por_ano}, ensure_ascii=False),
        encoding="utf-8",
    )


def _descobrir_contagens(
    empresas: Callable[[Cliente], list[Empresa]],
    endereco: Callable[[str], str],
    filtro: Callable[[Path, Path], None],
) -> Descobrir:
    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [
            Alvo(
                url := endereco(e.nome),
                ".json",
                _filtrado(url, "busca sem retorno", filtro),
            )
            for e in empresas(cliente)
        ]

    return _descobrir


# ---- RSS das agências públicas (só índice) ---------------------------------------------------
RSS_DAS_AGENCIAS = {
    "ebc-rss-ultimas": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",
    "ebc-rss-economia": "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml",
    "senado-rss-noticias": "https://www12.senado.leg.br/noticias/rss",
    "camara-rss-noticias": "https://www.camara.leg.br/noticias/rss/ultimas-noticias",
}
CABECALHO_DO_INDICE = ("data", "titulo", "link")


def indice_do_rss(bruto: Path, destino: Path) -> int:
    """Regrava o feed como um CSV de (data, título, link). A descrição e o conteúdo (texto de
    terceiros; a EBC restringe a reprodução a veículos jornalísticos) ficam de fora. Devolve quantos
    itens entraram; feed sem item é erro (o formato mudou), nunca "nada novo"."""
    try:
        itens = ET.parse(bruto).getroot().findall("./channel/item")
    except ET.ParseError as erro:
        raise ValueError("o RSS não é um XML válido") from erro
    if not itens:
        raise ValueError("o RSS não trouxe nenhum item")
    with destino.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida, lineterminator="\n")
        escritor.writerow(CABECALHO_DO_INDICE)
        for item in itens:
            escritor.writerow(
                [
                    (item.findtext("pubDate") or "").strip(),
                    (item.findtext("title") or "").strip(),
                    (item.findtext("link") or "").strip(),
                ]
            )
    return len(itens)


def _descobrir_rss(url: str) -> Descobrir:
    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [Alvo(url, ".csv", _filtrado(url, "feed fora do ar", indice_do_rss))]

    return _descobrir


# ---- as fontes -------------------------------------------------------------------------------
def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    pausa = PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS
    empresas = _empresas_com_memoria()
    das_empresas = [
        Fonte(
            "wiki-pageviews-empresas",
            "mensal",
            descobrir_acessos(empresas),
            "json",
            pausa_minima=pausa,
        ),
        Fonte(
            "gdelt-gkg",
            "diaria",
            descobrir_gkg(empresas),
            "arquivo",
            pesada=True,
            pausa_minima=pausa,
        ),
        Fonte(
            "querido-diario-empresas",
            "mensal",
            descobrir_querido_diario(empresas),
            "json",
            pausa_minima=PAUSA_ENTRE_PEDIDOS_AO_QUERIDO_DIARIO_EM_SEGUNDOS,
        ),
        Fonte(
            "openalex-afiliacoes",
            "mensal",
            _descobrir_contagens(empresas, endereco_do_openalex, contagens_do_openalex),
            "json",
            pausa_minima=pausa,
        ),
        Fonte(
            "crossref-afiliacoes",
            "mensal",
            _descobrir_contagens(empresas, endereco_do_crossref, contagens_do_crossref),
            "json",
            pausa_minima=pausa,
        ),
    ]
    dos_feeds = [
        Fonte(id_, "diaria", _descobrir_rss(url), "arquivo", pausa_minima=pausa)
        for id_, url in RSS_DAS_AGENCIAS.items()
    ]
    return [*das_empresas, *dos_feeds]


# páginas de termos que a vigia acompanha (avisa quando o texto muda). O GDELT já tem `termos-gdelt`;
# a EBC e a Câmara não têm página de termos (404 na sonda de 22/10/2026)
TERMOS_DA_ATENCAO = {
    "termos-querido": "https://queridodiario.ok.org.br/sobre",
    "termos-crossref": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
    "termos-openalex": "https://help.openalex.org/",
    "termos-senado": "https://www12.senado.leg.br/noticias/politica-de-uso",
}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DA_ATENCAO)
