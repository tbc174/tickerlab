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
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date

import pandas as pd

from src import eventos
from src.links_das_fontes import link_da_fonte

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


def _ler_ipe_bruto(conteudo_do_zip: bytes) -> pd.DataFrame:
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
    linhas = bruto[escolha.notna()]
    tabela = pd.DataFrame(
        {
            "cnpj": linhas["CNPJ_Companhia"].str.strip(),
            "empresa": linhas["Nome_Companhia"].str.strip(),
            "codigo_cvm": linhas["Codigo_CVM"].str.strip(),
            "evidencia": escolha[escolha.notna()],
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
        columns=list(COLUNAS),
    )
    tabela = tabela.dropna(subset=["publico_em", "link"])
    tabela = tabela.drop_duplicates("link")
    return tabela.sort_values(["publico_em", "protocolo", "versao"]).reset_index(
        drop=True
    )


def ler_documentos_do_ipe(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os documentos com rating de um arquivo anual do IPE."""
    return documentos_com_rating(_ler_ipe_bruto(conteudo_do_zip))


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


def _nome_da_empresa(empresa: str) -> str | None:
    """A primeira palavra própria do nome (SUZANO PAPEL E CELULOSE → suzano), para achar a
    companhia num documento que fala de várias."""
    palavras = [p for p in _simples(empresa).replace(".", " ").split() if len(p) >= 5]
    return next((p for p in palavras if p not in PALAVRAS_COMUNS), None)


def _mais_perto_da_empresa(
    texto: str, achados: list[re.Match[str]], empresa: str
) -> re.Match[str] | None:
    """Num documento sobre várias companhias, a nota que vem logo depois de alguma menção à que
    entregou (a lista de nomes do topo não atrapalha: vale a menção mais próxima)."""
    nome = _nome_da_empresa(empresa)
    if not nome:
        return None
    trechos = []
    for mencao in (m.start() for m in re.finditer(re.escape(nome), _simples(texto))):
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
    return next((a for a in notas if _escala(a) == "nacional"), notas[0])


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
    if empresa and len({_nota_do_achado(a) for a in nacionais + globais}) > 1:
        perto = _mais_perto_da_empresa(texto, nacionais + globais, empresa)
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
