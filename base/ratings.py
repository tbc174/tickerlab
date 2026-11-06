"""Ratings pelos documentos da CVM: notas das agências que as companhias entregam no IPE.

Prova e plano: `reports/2026-10-16-provas-gdelt-e-ratings.md` e
`planos/2026-10-16-ratings-pelos-documentos-da-cvm.md` (pasta privada). O IPE (`cvm-hist-ipe`, desde
2003) tem um tipo próprio, "Relatório de Agência de Rating" (~4 mil documentos), e comunicados, fatos
relevantes e editais de assembleia que falam do rating no assunto (~1.900). Cada documento é baixado
do sistema da CVM (fonte `cvm-ipe-rating`) e a nota sai do texto.

**Data pública** (`publico_em`) = data de entrega à CVM daquela versão do documento. A data do
relatório da agência (`Data_Referencia`) costuma ser um dia antes, mas há entregas meses depois e
referências depois da entrega (erro de preenchimento): nunca é usada como data pública. Cada versão
reapresentada é um documento à parte, com a própria data, para que a base "como era na data" use só
o que já tinha sido entregue. Licença: ODbL (CVM).
"""

import io
import logging
import re
import unicodedata
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.parquet import LINHAGEM, gravar_se_mudou
from src import acervo, eventos
from src.banco.coletas import originais_mais_recentes
from src.leitura import texto_do_pdf
from src.links_das_fontes import link_da_fonte
from src.versao_do_codigo import versao_do_codigo

log = logging.getLogger("tickerlab.ratings")

FONTE_DOS_PDFS = "cvm-ipe-rating"
FONTE_DO_IPE = "cvm-hist-ipe"
URL_DO_IPE = eventos.URL_DO_IPE  # arquivo anual do IPE, como o arquivista guarda
CODIFICACAO_DA_CVM = "cp1252"
TIPO_DO_RELATORIO = "relatorio de agencia de rating"
# assunto (sem acento, minúsculas) que fala de rating; agência pelo nome ou pela palavra
ASSUNTO_COM_RATING = re.compile(
    r"\brating|classificacao de risco|agencia de (?:classificacao|risco)|nota de risco"
    r"|moody|fitch|standard ?(?:&(?:amp;?)?|and) ?poor|\bs ?&(?:amp;?)? ?p\b|austin rating"
    r"|liberum|\bsr rating|\blf rating|am best"
)
# "nota de crédito" fica de fora de propósito: no IPE quase sempre é a Nota de Crédito à Exportação
COLUNAS = (
    "cnpj",
    "empresa",
    "codigo_cvm",
    "evidencia",
    "categoria",
    "tipo",
    "assunto",
    "referencia",
    "publico_em",
    "protocolo",
    "versao",
    "link",
)


def _simples(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore"
    )
    return sem_acento.decode().lower().strip()


def ler_ipe_bruto(conteudo_do_zip: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next(n for n in arquivo.namelist() if "ipe_cia_aberta" in n)
        with arquivo.open(nome) as csv:
            return pd.read_csv(
                csv,
                sep=";",
                encoding=CODIFICACAO_DA_CVM,
                encoding_errors="replace",
                dtype=str,
            ).fillna("")


def evidencias(bruto: pd.DataFrame) -> pd.Series:
    """Por que cada documento entra: `relatorio_de_agencia` (o tipo próprio do IPE), `assunto` (o
    assunto fala de rating) ou vazio (não entra). Vetorizado: o IPE inteiro tem ~750 mil linhas e a
    coleta relê a lista a cada rodada."""
    relatorio = bruto["Tipo"].map(_simples).eq(TIPO_DO_RELATORIO)
    no_assunto = bruto["Assunto"].map(_simples).str.contains(ASSUNTO_COM_RATING)
    escolha = pd.Series(None, index=bruto.index, dtype=object)
    escolha[no_assunto] = "assunto"
    escolha[relatorio] = "relatorio_de_agencia"
    return escolha


def documentos_com_rating(bruto: pd.DataFrame) -> pd.DataFrame:
    """Os documentos do IPE que trazem rating, um por versão entregue, com a data pública."""
    escolha = evidencias(bruto)
    return tabela_do_ipe(
        bruto[escolha.notna()], COLUNAS, evidencia=escolha[escolha.notna()]
    )


def tabela_do_ipe(
    linhas: pd.DataFrame, colunas: Sequence[str], **extras: pd.Series
) -> pd.DataFrame:
    """Linhas escolhidas do IPE cru → uma linha por versão entregue, com a data pública. `extras`
    são colunas a mais, alinhadas a `linhas`; `colunas` dá a ordem final."""
    tabela = pd.DataFrame(
        {
            "cnpj": linhas["CNPJ_Companhia"].str.strip(),
            "empresa": linhas["Nome_Companhia"].str.strip(),
            "codigo_cvm": linhas["Codigo_CVM"].str.strip(),
            **extras,
            "categoria": linhas["Categoria"].str.strip(),
            "tipo": linhas["Tipo"].str.strip(),
            "assunto": linhas["Assunto"].str.strip(),
            "referencia": pd.to_datetime(
                linhas["Data_Referencia"], errors="coerce"
            ).dt.date,
            "publico_em": pd.to_datetime(
                linhas["Data_Entrega"], errors="coerce"
            ).dt.date,
            # de 2003 a 2014 o protocolo vem vazio: o link identifica o documento
            "protocolo": linhas["Protocolo_Entrega"]
            .str.strip()
            .where(
                linhas["Protocolo_Entrega"].str.strip() != "", linhas["Link_Download"]
            ),
            "versao": pd.to_numeric(linhas["Versao"], errors="coerce").astype("Int64"),
            "link": linhas["Link_Download"].map(link_da_fonte),
        },
        columns=list(colunas),
    )
    tabela = tabela.dropna(subset=["publico_em", "link"])
    tabela = tabela.drop_duplicates("link")
    return tabela.sort_values(["publico_em", "protocolo", "versao"]).reset_index(
        drop=True
    )


def ler_documentos_do_ipe(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os documentos com rating de um arquivo anual do IPE."""
    return documentos_com_rating(ler_ipe_bruto(conteudo_do_zip))


# --- extração do rating do texto -----------------------------------------------------------------
# v1: o rating principal de cada documento (a primeira nota da escala nacional; sem ela, a primeira
# da escala global) e as outras notas citadas. Notas por emissão, uma a uma, ficam para depois.

AGENCIAS = (
    ("fitch", re.compile(r"fitch", re.IGNORECASE)),
    ("moodys", re.compile(r"moody", re.IGNORECASE)),
    (
        "sp",
        re.compile(
            r"standard ?(?:&(?:amp;?)?|and) ?poor|s ?&(?:amp;?)? ?p\b|spglobal",
            re.IGNORECASE,
        ),
    ),
    ("austin", re.compile(r"austin rating", re.IGNORECASE)),
    ("liberum", re.compile(r"liberum", re.IGNORECASE)),
    ("sr_rating", re.compile(r"\bsr rating", re.IGNORECASE)),
    ("lf_rating", re.compile(r"\blf rating", re.IGNORECASE)),
    ("am_best", re.compile(r"am best", re.IGNORECASE)),
)
# escala de letras (Fitch, S&P, Austin...) e a da Moody's, do melhor ao pior: a posição é o `nivel`
ESCALA_LETRAS = [
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
    "B-",
    "CCC+",
    "CCC",
    "CCC-",
    "CC",
    "C",
    "RD",
    "SD",
    "D",
]
ESCALA_MOODYS = [
    "Aaa",
    "Aa1",
    "Aa2",
    "Aa3",
    "A1",
    "A2",
    "A3",
    "Baa1",
    "Baa2",
    "Baa3",
    "Ba1",
    "Ba2",
    "Ba3",
    "B1",
    "B2",
    "B3",
    "Caa1",
    "Caa2",
    "Caa3",
    "Ca",
    "C",
]
_LETRA = r"(?:AAA|AA|A|BBB|BB|B|CCC|CC|C)[+-]?|RD|SD|D"
_MOODYS = r"Aaa|Aa[1-3]|A[1-3]|Baa[1-3]|Ba[1-3]|B[1-3]|Caa[1-3]|Ca|C"
ASPAS = "'‘’\"“”"
# escala nacional: Fitch 'AA(bra)', 'AAAsf(bra)', 'AA(EXP)(bra)'; S&P e Austin brAA+;
# Moody's Aa1.br e, desde 2022, a Moody's Local AA.br; Liberum A-(fe); outras AA(br). Nota curta
# da S&P (brA-1+) não entra.
NACIONAL = re.compile(
    rf"(?<![A-Za-z])(?P<f>{_LETRA})(?i:sf)?(?i:\(exp\))?\s?\((?i:bra?|fe)\)"
    rf"|\bbr(?P<s>{_LETRA})(?![-+]?\d)(?![A-Za-z])(?:\s?\(?sf\)?)?"
    rf"|\b(?P<m>{_MOODYS})\.br\b"
    rf"|(?<![A-Za-z])(?P<l>{_LETRA})\.br\b"
)
GRUPOS_DA_MOODYS = ("m", "l")
PRELIMINAR = re.compile(
    r"\s?\(p\)", re.IGNORECASE
)  # Austin brA-(sf)(p): indicação, não rating
VARIAS_SERIES = re.compile(
    r"(?:realiza|takes)\s+a[cç][oõ]es\s+de\s+rating|rating\s+actions\s+on"
    r"|a[cç][oõ]es\s+de\s+rating\s+em",
    re.IGNORECASE,
)
# escala global: só entre aspas ('BB-'), para não confundir com siglas; Moody's pelo nome da nota,
# menos "B1" a "B3" soltos (B3 é a bolsa)
GLOBAL = re.compile(
    rf"[{ASPAS}](?P<f>{_LETRA})[{ASPAS}]"
    r"|\b(?P<m>Aaa|Aa[1-3]|A[1-3]|Baa[1-3]|Ba[1-3]|Caa[1-3])\b"
)
PERSPECTIVAS = (
    (re.compile(r"observa[cç][aã]o negativa|watch negative|creditwatch\W+(?:\w+\W+){0,4}negati"
                r"|revis[aã]o para (?:poss[ií]vel )?rebaixamento|review for downgrade", re.IGNORECASE),
     "em_observacao_negativa"),
    (re.compile(r"observa[cç][aã]o positiva|watch positive|creditwatch\W+(?:\w+\W+){0,4}positi"
                r"|revis[aã]o para (?:poss[ií]vel )?eleva[cç][aã]o|review for upgrade", re.IGNORECASE),
     "em_observacao_positiva"),
)  # fmt: skip
PERSPECTIVA_ALTERADA = re.compile(
    r"perspectiva[^.;]{0,80}?alterada de \w+ para (est[aá]vel|positiva|negativa)",
    re.IGNORECASE,
)
PERSPECTIVA = re.compile(
    r"perspectiva\W+(?:\w+\W+){0,3}?(est[aá]vel|positiva|negativa|em desenvolvimento)"
    r"|outlook\W+(?:\w+\W+){0,2}?(stable|positive|negative|developing)",
    re.IGNORECASE,
)
NOME_DA_PERSPECTIVA = {
    "estavel": "estavel", "stable": "estavel", "positiva": "positiva", "positive": "positiva",
    "negativa": "negativa", "negative": "negativa", "em desenvolvimento": "em_desenvolvimento",
    "developing": "em_desenvolvimento",
}  # fmt: skip
# ação, pelo título e pelo começo do texto; a primeira da lista que casar vale
ACOES = (
    ("retirada", re.compile(r"\bretir(?:a|ou|ad)|withdr[ae]w", re.IGNORECASE)),
    ("rebaixamento", re.compile(r"rebaix|downgrad|\blower(?:s|ed)\b", re.IGNORECASE)),
    (
        "elevacao",
        # "elevadas margens" é adjetivo: só o verbo e "elevado para/de"
        re.compile(
            r"\belev(?:a|ou|a[cç][aã]o)\b|\belevad[oa]s? (?:para|de)\b"
            r"|upgrad|\brais(?:es|ed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "atribuicao",
        re.compile(r"\batribu[ií]|\bassign|\brates\b|rating inicial", re.IGNORECASE),
    ),
    ("afirmacao", re.compile(r"afirm|\bmant(?:[eé]m|eve)\b|maintain", re.IGNORECASE)),
)
INICIO_DO_TEXTO = 700  # caracteres: título e primeira frase, onde ficam a ação e a data
MESES = {
    "jan": 1, "janeiro": 1, "january": 1, "fev": 2, "feb": 2, "fevereiro": 2, "february": 2,
    "mar": 3, "marco": 3, "march": 3, "abr": 4, "apr": 4, "abril": 4, "april": 4, "mai": 5,
    "may": 5, "maio": 5, "jun": 6, "junho": 6, "june": 6, "jul": 7, "julho": 7, "july": 7,
    "ago": 8, "aug": 8, "agosto": 8, "august": 8, "set": 9, "sep": 9, "sept": 9, "setembro": 9,
    "september": 9, "out": 10, "oct": 10, "outubro": 10, "october": 10, "nov": 11,
    "novembro": 11, "november": 11, "dez": 12, "dec": 12, "dezembro": 12, "december": 12,
}  # fmt: skip
_MES = r"(?P<mes>[a-z]{3,9})"
DATAS = (
    re.compile(
        rf"\b(?P<d>\d{{1,2}}) de {_MES} de (?P<a>\d{{4}})"
    ),  # 7 de julho de 2023
    re.compile(rf"\b(?P<d>\d{{1,2}}) {_MES}\.?,? (?P<a>\d{{4}})"),  # 07 Jul 2023
    re.compile(rf"\b{_MES}\.? (?P<d>\d{{1,2}}),? (?P<a>\d{{4}})"),  # October 11, 2017
    re.compile(
        rf"\b(?P<d>\d{{1,2}}), {_MES}, (?P<a>\d{{4}})"
    ),  # 26, jun, 2018 (Liberum)
    re.compile(r"\b(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<a>\d{4})\b"),  # 15/08/2019
)


@dataclass(frozen=True)
class Rating:
    agencia: str | None
    escala: str  # "nacional" ou "global"
    nota: str  # sem sufixos: AA, RD, Aa1
    nivel: int | None  # posição na escala (1 = AAA ou Aaa): compara agências
    nota_original: str
    perspectiva: str | None
    acao: str | None
    data_acao: date | None
    outras_notas: tuple[str, ...]


def nivel(nota: str) -> int | None:
    """A posição da nota na escala (1 = a melhor); Moody's e letras na mesma régua."""
    for escala in (ESCALA_LETRAS, ESCALA_MOODYS):
        if nota in escala:
            return escala.index(nota) + 1
    return None


def _nota_do_achado(achado: re.Match[str]) -> str:
    nome = next(g for g in ("f", "s", "m", "l") if achado.groupdict().get(g))
    texto = achado.group(nome)
    return texto if nome == "m" else texto.upper()


def _da_moodys(achado: re.Match[str]) -> bool:
    return any(achado.groupdict().get(g) for g in GRUPOS_DA_MOODYS)


def _agencia(texto: str, de_moodys: bool) -> str | None:
    contagem = {nome: len(p.findall(texto)) for nome, p in AGENCIAS}
    contagem = {nome: n for nome, n in contagem.items() if n}
    if de_moodys and "moodys" in contagem:
        return "moodys"
    if not contagem:
        return None
    return max(contagem, key=lambda nome: contagem[nome])


OBSERVACAO_REMOVIDA = re.compile(
    r"(?:remov|retir|exclu)\w*\W+(?:\w+\W+){0,2}$", re.IGNORECASE
)


def _perspectiva(texto: str) -> str | None:
    """A perspectiva citada primeiro (a do título); a legenda fixa do fim dos relatórios da Fitch
    ("OUTLOOK WATCH POSITIVE NEGATIVE...") vem depois e não ganha. No empate, "alterada de X para
    Y" vale mais que a menção simples."""
    achados: list[tuple[int, int, str]] = []
    for padrao, nome in PERSPECTIVAS:
        for achado in padrao.finditer(texto):
            # "Fitch Remove Observação Negativa": a observação acabou, não começou
            antes = texto[max(0, achado.start() - 30) : achado.start()]
            if not OBSERVACAO_REMOVIDA.search(antes):
                achados.append((achado.start(), 0, nome))
                break
    if alterada := PERSPECTIVA_ALTERADA.search(texto):
        nome = NOME_DA_PERSPECTIVA[_simples(alterada.group(1))]
        achados.append((alterada.start(), 1, nome))
    if achado := PERSPECTIVA.search(texto):
        nome = NOME_DA_PERSPECTIVA[_simples(achado.group(1) or achado.group(2))]
        achados.append((achado.start(), 2, nome))
    return min(achados)[2] if achados else None


# perspectiva colada na nota, nas tabelas: "AA.br Negativa" (Moody's Local), "brAA/Positiva/--" (S&P)
PERSPECTIVA_AO_LADO = re.compile(
    r"^\W{0,3}(est[aá]vel|positiva|negativa|stable|positive|negative|developing)\b",
    re.IGNORECASE,
)


def _perspectiva_ao_lado(texto: str, nota: re.Match[str]) -> str | None:
    achado = PERSPECTIVA_AO_LADO.match(texto[nota.end() : nota.end() + 20])
    return NOME_DA_PERSPECTIVA[_simples(achado.group(1))] if achado else None


def _acao(inicio: str) -> str | None:
    return next((nome for nome, padrao in ACOES if padrao.search(inicio)), None)


def _data_do_achado(achado: re.Match[str]) -> date | None:
    partes = achado.groupdict()
    mes = int(partes["m"]) if partes.get("m") else MESES.get(partes.get("mes") or "")
    dia, ano = int(partes["d"]), int(partes["a"])
    if not mes:
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _data(inicio: str) -> date | None:
    """A primeira data do começo do texto (a da ação da agência ou a do comunicado)."""
    simples = _simples(inicio)
    achados = [
        (a.start(), quando)
        for padrao in DATAS
        for a in padrao.finditer(simples)
        if (quando := _data_do_achado(a))
    ]
    return min(achados)[1] if achados else None


ANTES_DA_NOTA_ANTIGA = re.compile(r"\bde\W{0,3}$", re.IGNORECASE)
ENTRE_ANTIGA_E_NOVA = re.compile(r"^\W{0,3}para\W{0,3}$", re.IGNORECASE)


# palavras comuns em nomes de companhia: não servem para achar a companhia no texto
PALAVRAS_COMUNS = frozenset(
    [
        "companhia",
        "participacoes",
        "securitizadora",
        "securitizacao",
        "brasil",
        "brasileira",
        "brasileiro",
        "energia",
        "holding",
        "empreendimentos",
        "investimentos",
        "industria",
        "comercio",
        "servicos",
        "distribuidora",
        "geracao",
        "transmissao",
        "concessionaria",
        "rodovia",
        "rodovias",
        "saneamento",
        "estado",
        "paulo",
        "basico",
        "eletrica",
        "credito",
        "creditos",
        "direitos",
        "creditorios",
        "agronegocio",
        "financeira",
        "banco",
        "imobiliarios",
        "recebiveis",
    ]
)
# caracteres depois do nome da companhia onde procurar a nota dela
PERTO_DA_EMPRESA = 600
TAMANHO_DO_NOME = 80  # caracteres até o "S.A." do próprio nome da companhia
# fim do nome de uma companhia: marca onde começa o trecho da próxima
FIM_DO_TRECHO = re.compile(r"\bS\.?\s?A\.?(?=\W)|\bS/A\b|\bLtda\b")


def _escala(achado: re.Match[str]) -> str:
    return "nacional" if achado.re is NACIONAL else "global"


def _nomes_da_empresa(empresa: str) -> list[str]:
    """As palavras próprias do nome (GRUPO MATEUS → mateus; SUZANO PAPEL E CELULOSE → suzano,
    papel, celulose), para achar a companhia num documento que fala de várias."""
    palavras = [p for p in _simples(empresa).replace(".", " ").split() if len(p) >= 5]
    return [p for p in palavras if p not in PALAVRAS_COMUNS]


def _mesmo_tamanho(texto: str) -> str:
    """O texto em minúsculas e sem acento com UMA letra por letra do original: o que sumiria (•,
    aspas curvas) vira espaço, e a posição de um nome é a mesma no texto original."""
    letras = (unicodedata.normalize("NFKD", c)[:1] for c in texto)
    return "".join(c.lower() if c.isascii() else " " for c in letras)


def _nomes_no_texto(texto: str, empresa: str) -> list[str]:
    simples = _mesmo_tamanho(texto)
    return [nome for nome in _nomes_da_empresa(empresa) if nome in simples]


def _mais_perto_da_empresa(
    texto: str, achados: list[re.Match[str]], empresa: str
) -> re.Match[str] | None:
    """Num documento sobre várias companhias, a nota que vem logo depois de alguma menção à que
    entregou (a lista de nomes do topo não atrapalha: vale a menção mais próxima)."""
    simples = _mesmo_tamanho(texto)
    mencoes = sorted(
        m.start()
        for nome in _nomes_no_texto(texto, empresa)
        for m in re.finditer(re.escape(nome), simples)
    )
    trechos = []
    for mencao in mencoes:
        # o trecho da companhia vai do nome dela até o nome da próxima ("Neoenergia S.A."): uma
        # lista de nomes no topo dá trechos sem nota
        proprio = FIM_DO_TRECHO.search(texto, mencao, mencao + TAMANHO_DO_NOME)
        proxima = FIM_DO_TRECHO.search(texto, proprio.end() if proprio else mencao)
        fim = min(proxima.start() if proxima else len(texto), mencao + PERTO_DA_EMPRESA)
        if notas := [a for a in achados if mencao <= a.start() < fim]:
            trechos.append((notas[0].start() - mencao, mencao, notas))
    if not trechos:
        return None
    notas = min(trechos, key=lambda t: (t[0], t[1]))[2]
    # no trecho, a escala nacional ganha da global, como no resto do documento
    escolhida = next((a for a in notas if _escala(a) == "nacional"), notas[0])
    return _para_da_tabela(texto, notas, escolhida)


ANTES_DA_TABELA = re.compile(r"\bDe\s+Para\b")
ENTRE_DE_E_PARA = (
    40  # caracteres entre a nota da coluna "De" e a da "Para" (brA/Estável/-- )
)


def _para_da_tabela(
    texto: str, achados: list[re.Match[str]], nota: re.Match[str]
) -> re.Match[str]:
    """Nas tabelas "De / Para" da S&P (brA/Estável/-- brA+/Estável/--), vale a coluna "Para"."""
    seguinte = next((a for a in achados if a.start() > nota.start()), None)
    cabecalho = texto[max(0, nota.start() - 120) : nota.start()]
    if (
        seguinte is not None
        and seguinte.start() - nota.end() <= ENTRE_DE_E_PARA
        and ANTES_DA_TABELA.search(cabecalho)
    ):
        return seguinte
    return nota


def _fala_de_varias(texto: str, empresa: str | None) -> bool:
    """O documento é sobre várias companhias? Quando é sobre uma só, o nome dela está no título ou
    no começo do texto; nos comunicados de várias (a Moody's sobre o setor, a lista da S&P), não."""
    # o nome que não aparece em lugar nenhum é o de hoje num documento antigo (o IPE guarda o
    # nome atual: Voiter era Indusval, Brava era 3R): aí o documento é de uma companhia só
    nomes = _nomes_no_texto(texto, empresa) if empresa else []
    inicio = _mesmo_tamanho(texto[:INICIO_DO_TEXTO])
    return bool(nomes) and not any(nome in inicio for nome in nomes)


def _principal(texto: str, achados: list[re.Match[str]]) -> re.Match[str]:
    """A primeira nota citada; se ela é a antiga de um "de brAA+ para brAAA", vale a nova."""
    primeira = achados[0]
    if len(achados) > 1:
        antes = texto[max(0, primeira.start() - 6) : primeira.start()]
        entre = texto[primeira.end() : achados[1].start()]
        if ANTES_DA_NOTA_ANTIGA.search(antes) and ENTRE_ANTIGA_E_NOVA.match(entre):
            return achados[1]
    return primeira


def extrair_rating(texto: str, empresa: str | None = None) -> Rating | None:
    """O rating principal do documento (o da `empresa` que o entregou, quando ele fala de várias),
    ou None se o texto não traz nota (PDF escaneado, fonte embaralhada): nunca inventa nota."""
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if VARIAS_SERIES.search(texto[:INICIO_DO_TEXTO]):
        return None  # uma ação por série: sem a série certa, não há "o" rating do documento
    nacionais = [
        a for a in NACIONAL.finditer(texto) if not PRELIMINAR.match(texto, a.end())
    ]
    globais = list(GLOBAL.finditer(texto))
    perto = None
    if empresa and _fala_de_varias(texto, empresa):
        perto = _mais_perto_da_empresa(texto, nacionais + globais, empresa)
        if perto is None:
            return (
                None  # a nota de quem entregou não está no texto: a primeira é de outra
            )
    nacional = perto in nacionais if perto else bool(nacionais)
    achados = nacionais if nacional else globais
    if not achados:
        return None
    principal = perto or _principal(texto, achados)
    de_moodys = _da_moodys(principal)
    agencia = _agencia(texto, de_moodys)
    # sem agência no texto, ou "A1" solto sem a Moody's: não é rating (texto embaralhado, siglas)
    if agencia is None or (de_moodys and agencia != "moodys"):
        return None
    notas = list(dict.fromkeys(_nota_do_achado(a) for a in [principal, *achados]))
    inicio = texto[:INICIO_DO_TEXTO]
    return Rating(
        agencia=agencia,
        escala="nacional" if nacional else "global",
        nota=notas[0],
        nivel=nivel(notas[0]),
        nota_original=principal.group(0).strip(ASPAS + " "),
        perspectiva=_perspectiva_ao_lado(texto, principal) or _perspectiva(texto),
        acao=_acao(inicio),
        data_acao=_data(inicio),
        outras_notas=tuple(notas[1:]),
    )


# --- a tabela `ratings` da base ------------------------------------------------------------------
# Uma linha por documento baixado e lido; o mesmo evento contado por dois documentos (o relatório da
# agência e o comunicado da companhia) vira uma linha só, com a primeira data de entrega.

EXTRAIDO, NAO_EXTRAIDO, NAO_E_PDF = "extraido", "nao_extraido", "nao_e_pdf"
SITUACOES = (EXTRAIDO, NAO_EXTRAIDO, NAO_E_PDF)
COLUNAS_DO_RATING = (
    "agencia",
    "escala",
    "nota",
    "nivel",
    "nota_original",
    "perspectiva",
    "acao",
    "data_acao",
    "outras_notas",
)
COLUNAS_DA_TABELA = (
    "cnpj",
    "empresa",
    "codigo_cvm",
    *COLUNAS_DO_RATING,
    "publico_em",
    "protocolo",
    "versao",
    "link",
    "evidencia",
    "situacao_extracao",
    "documentos",
)
# o mesmo evento: mesma companhia, agência, escala, nota e data da ação
MESMO_EVENTO = ["cnpj", "agencia", "escala", "nota", "data_acao"]
ORDEM = ["publico_em", "protocolo", "versao"]
SEPARADOR = "; "
PASTA_DA_TABELA = "ratings"
# a linhagem que vem de cada documento (o PDF de onde saiu a linha), quando os documentos a trazem
LINHAGEM_DO_DOCUMENTO = ("origem_sha256", "origem_coletada_em")


def ler_texto(conteudo: bytes) -> str | None:
    """O texto do documento, ou None se ele não abre como PDF (Word, ZIP, PDF quebrado). Tenta mesmo
    sem o "%PDF" no começo: há documentos da CVM com lixo antes do cabeçalho que abrem assim mesmo."""
    if not conteudo:
        return None
    try:
        return texto_do_pdf(conteudo)
    except Exception:  # noqa: BLE001 - o leitor de PDF tem erros próprios; todos querem dizer "não é PDF"
        return None


def _linha_do_rating(documento: pd.Series, texto: str | None) -> dict[str, object]:
    if texto is None:
        return {"situacao_extracao": NAO_E_PDF}
    rating = extrair_rating(texto, empresa=documento["empresa"] or None)
    if rating is None:
        return {"situacao_extracao": NAO_EXTRAIDO}
    data_acao = rating.data_acao
    if data_acao is not None and data_acao > documento["publico_em"]:
        data_acao = None  # depois da entrega: erro de leitura ou de digitação; nunca olha o futuro
    return {
        "agencia": rating.agencia,
        "escala": rating.escala,
        "nota": rating.nota,
        "nivel": rating.nivel,
        "nota_original": rating.nota_original,
        "perspectiva": rating.perspectiva,
        "acao": rating.acao,
        "data_acao": data_acao,
        "outras_notas": SEPARADOR.join(rating.outras_notas) or None,
        "situacao_extracao": EXTRAIDO,
    }


def _juntar_eventos(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por evento: a do primeiro documento entregue (a tabela vem em `ORDEM`), com os
    protocolos de todos em `documentos`. Sem a data da ação não dá para saber se é o mesmo evento."""
    tabela = tabela.assign(documentos=tabela["protocolo"])
    juntaveis = (tabela["situacao_extracao"] == EXTRAIDO) & tabela["data_acao"].notna()
    do_evento = tabela[juntaveis]
    if do_evento.empty:
        return tabela
    protocolos = do_evento.groupby(MESMO_EVENTO, sort=False)["protocolo"].transform(
        lambda p: SEPARADOR.join(dict.fromkeys(p))
    )
    primeiros = do_evento.assign(documentos=protocolos).drop_duplicates(MESMO_EVENTO)
    return pd.concat([tabela[~juntaveis], primeiros])


def montar_ratings(
    documentos: pd.DataFrame,
    textos: Mapping[str, str | None],
    ate: date | None = None,
) -> pd.DataFrame:
    """A tabela `ratings`: os `documentos` com rating (`documentos_com_rating`) já baixados.

    `textos`: o texto de cada documento pelo link (None = não abriu como PDF); documento que não
    está aqui ainda não foi baixado e fica de fora. `ate`: a base como era nesse dia (nada entregue
    depois, nem na lista dos documentos de um evento). Passa o nome da companhia para a extração
    (documento sobre várias companhias: a nota é a de quem entregou).
    """
    if ate is not None:
        documentos = documentos[documentos["publico_em"] <= ate]
    baixados = documentos[documentos["link"].isin(list(textos.keys()))]
    baixados = baixados.sort_values(ORDEM, kind="stable").reset_index(drop=True)
    extraidos = pd.DataFrame(
        [_linha_do_rating(d, textos[d["link"]]) for _, d in baixados.iterrows()],
        index=baixados.index,
        columns=[*COLUNAS_DO_RATING, "situacao_extracao"],
        dtype=object,  # coluna toda vazia continua texto, não vira número
    )
    tabela = _juntar_eventos(pd.concat([baixados, extraidos], axis=1))
    linhagem = [c for c in LINHAGEM_DO_DOCUMENTO if c in tabela.columns]
    return (
        tabela.astype({"nivel": "Int64", "versao": "Int64"})
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
        .loc[:, [*COLUNAS_DA_TABELA, *linhagem]]
    )


# --- montagem pelo acervo (servidor de casa) -----------------------------------------------------
def documentos_guardados(conexao: sa.Connection) -> tuple[pd.DataFrame, list[sa.Row]]:
    """Os documentos com rating de todos os arquivos anuais do IPE guardados, e esses arquivos."""
    anuais = [
        original
        for original in originais_mais_recentes(conexao, FONTE_DO_IPE)
        if "ipe_cia_aberta_" in original.url
    ]
    tabelas = [
        ler_documentos_do_ipe(conteudo)
        for o in anuais
        if (conteudo := acervo.ler_original(o.caminho_do_original))
    ]
    if not tabelas:
        return pd.DataFrame(columns=list(COLUNAS)), anuais
    documentos = pd.concat(tabelas, ignore_index=True).drop_duplicates("link")
    return documentos.reset_index(drop=True), anuais


class _TextosDoAcervo(Mapping[str, str | None]):
    """O texto de cada PDF guardado, lido só quando pedido: um documento por vez na memória."""

    def __init__(self, originais: Mapping[str, sa.Row]) -> None:
        self._originais = originais

    def __getitem__(self, link: str) -> str | None:
        conteudo = acervo.ler_original(self._originais[link].caminho_do_original)
        if conteudo is None:
            log.warning("original de %s registrado, mas fora do acervo", link)
        return ler_texto(conteudo or b"")

    def __iter__(self) -> Iterator[str]:
        return iter(self._originais)

    def __len__(self) -> int:
        return len(self._originais)


def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> dict[str, int]:
    """`<pasta>/ratings/ratings.parquet` com os documentos já baixados; devolve quantos documentos
    há em cada situação. Remontada inteira a cada rodada (`gravar_se_mudou` só regrava o que mudou;
    o passado que muda vira `.vN`)."""
    documentos, anuais = documentos_guardados(conexao)
    links = set(documentos["link"])
    pdfs = {
        o.url: o
        for o in originais_mais_recentes(conexao, FONTE_DOS_PDFS)
        if o.url in links
    }
    documentos = documentos.assign(
        origem_sha256=documentos["link"].map(
            lambda u: pdfs[u].sha256 if u in pdfs else None
        ),
        origem_coletada_em=documentos["link"].map(
            lambda u: (
                pd.Timestamp(pdfs[u].baixado_em).isoformat() if u in pdfs else None
            )
        ),
    )
    tabela = montar_ratings(documentos, _TextosDoAcervo(pdfs))
    contagem = tabela["situacao_extracao"].value_counts()
    origens = [{"url": o.url, "sha256": o.sha256} for o in [*anuais, *pdfs.values()]]
    gravar_se_mudou(
        tabela.assign(
            montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
        ),
        pasta / PASTA_DA_TABELA / PASTA_DA_TABELA,
        origens,
        ORDEM,
        carimbos=LINHAGEM,
    )
    return {s: int(contagem.get(s, 0)) for s in SITUACOES}
