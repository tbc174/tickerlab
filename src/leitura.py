"""Leitura dos documentos (Research R5) com algoritmo próprio, sem inteligência artificial.

Decisão 0020: nada de IA de terceiros. Tudo aqui é determinístico e explicável:

- **Fato relevante (B3):** resumo **extrativo** (as frases do próprio documento, nunca reescritas):
  cada frase recebe uma nota pela importância das palavras que usa (frequência no documento, sem
  as palavras vazias), com bônus para números e penalidade para o texto jurídico-padrão
  ("em atendimento ao disposto na Resolução..."). Ficam as melhores, na ordem original. Também
  saem os números citados (R$, %, quantidades) e o assunto, por regras de palavras-chave.
- **10-K (EUA):** a seção de fatores de risco ("Item 1A") comparada com a do ano anterior:
  semelhança entre os textos (cosseno das frequências de palavras, a medida do estudo "Lazy
  Prices", de Cohen, Malloy e Nguyen, 2020), frases novas e palavras que mais cresceram.

A versão do algoritmo (`VERSAO`) vai junto de cada resultado: se a regra mudar, os resultados
antigos podem ser refeitos.
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from itertools import pairwise

VERSAO = "1"
FRASES_DO_RESUMO = 3
MAX_PALAVRAS_POR_FRASE = 90  # frases maiores são cortadas no resumo (com "...")
MIN_PALAVRAS_POR_FRASE = 6
MAX_NUMEROS = 6
FRASES_NOVAS = 5
PALAVRAS_EM_ALTA = 8
MIN_OCORRENCIAS = 4  # uma palavra só "cresce" se aparece pelo menos isto no ano novo
SEMELHANCA_DE_FRASE = (
    0.5  # abaixo disto, a frase do ano novo não existia no ano anterior
)


def _palavras_do_texto(texto: str) -> frozenset[str]:
    """Uma lista de palavras escrita como texto corrido (mais fácil de ler e editar)."""
    return frozenset(texto.split())


PALAVRAS_VAZIAS_PT = _palavras_do_texto(
    """
    a ao aos as à às com como da das de do dos e em entre era essa esse esta este eu foi há
    isso já lhe mais mas me mesmo na nas nem no nos o os ou para pela pelas pelo pelos por
    qual quando que se sem ser seu seus sua suas são também te tem um uma umas uns até sobre
    sob após está estão foram será serão sendo pode podem poderá deverá nesta neste nessa
    nesse desta deste dessa desse cada todo toda todos todas outro outra outros outras
    qualquer quaisquer companhia sociedade presente data termos acordo forma bem assim ainda
    conforme
    """
)
PALAVRAS_VAZIAS_EN = _palavras_do_texto(
    """
    a about above after again against all also an and any are as at be because been being but
    by can could did do does doing for from further had has have having if in into is it its
    itself may might more most must no nor not of off on once only or other our ours out over
    own same shall should so some such than that the their them then there these they this
    those through to under until up upon very was we were what when where which while who
    whom why will with would company companys including include includes
    """
)
# texto jurídico-padrão: frases com estes trechos perdem nota (dizem o que a lei manda, não o fato)
JURIDIQUES = (
    "em atendimento ao disposto", "nos termos da", "nos termos do", "resolução cvm",
    "resolução da cvm", "lei nº", "instrução cvm", "público em geral", "manterá o mercado",
    "manter seus acionistas", "informados", "relações com investidores",
)  # fmt: skip
ASSUNTOS = {
    "Recompra de ações": ("recompra", "ações em tesouraria"),
    "Dividendos e JCP": ("dividendo", "juros sobre capital próprio", "jcp", "proventos"),
    "Aquisição, venda ou fusão": ("aquisição", "alienação", "incorporação", "fusão", "m&a",
                                  "venda da participação", "compra de participação"),
    "Dívida e captação": ("debêntures", "notas promissórias", "emissão de notas", "captação",
                          "financiamento", "bonds"),
    "Oferta de ações": ("oferta pública", "follow-on", "oferta restrita", "aumento de capital"),
    "Reestruturação e recuperação": ("recuperação judicial", "recuperação extrajudicial",
                                     "reestruturação", "falência"),
    "Mudança na administração": ("renúncia", "eleição", "diretor presidente", "ceo", "conselheiro",
                                 "nomeação"),
    "Projeções e resultados": ("projeção", "projeções", "guidance", "resultado", "lucro",
                               "receita", "ebitda"),
    "Processos e investigações": ("processo", "arbitragem", "ação judicial", "investigação",
                                  "auto de infração", "acordo de leniência"),
}  # fmt: skip
ABREVIACOES = ("S.A.", "S/A", "nº", "Nº", "Sr.", "Sra.", "Dr.", "Dra.", "art.", "arts.", "Ltda.",
               "Cia.", "Inc.", "Co.", "Corp.", "Ltd.", "U.S.", "e.g.", "i.e.", "etc.")  # fmt: skip
NUMERO = re.compile(
    r"(?:R\$|US\$|USD)\s?\d[\d.,]*(?:\s(?:mil|milhão|milhões|bilhão|bilhões|million|billion))?"
    r"|\d[\d.,]*\s?%"
    r"|\d{1,3}(?:\.\d{3})+(?:,\d+)?\s(?:ações|units|debêntures)",
    re.IGNORECASE,
)


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()


_NORMALIZADAS = {
    lista: frozenset(_sem_acento(p) for p in lista)
    for lista in (PALAVRAS_VAZIAS_PT, PALAVRAS_VAZIAS_EN)
}


def _palavras(texto: str, vazias: frozenset[str]) -> list[str]:
    """As palavras com conteúdo (sem acento, minúsculas, sem as vazias e as de 1 ou 2 letras)."""
    normalizadas = _NORMALIZADAS[vazias]
    return [
        p
        for p in re.findall(r"[a-z]+", _sem_acento(texto))
        if len(p) > 2 and p not in normalizadas
    ]


def dividir_em_frases(texto: str) -> list[str]:
    """Frases do texto, sem quebrar nas abreviações comuns (S.A., nº, Inc.)."""
    protegido = texto
    for i, abreviacao in enumerate(ABREVIACOES):
        protegido = protegido.replace(abreviacao, f"\x00{i}\x00")
    partes = re.split(r"(?<=[.!?;])\s+(?=[A-ZÀ-Ü“\"(])", " ".join(protegido.split()))
    frases = []
    for parte in partes:
        for i, abreviacao in enumerate(ABREVIACOES):
            parte = parte.replace(f"\x00{i}\x00", abreviacao)
        if len(parte.split()) >= MIN_PALAVRAS_POR_FRASE:
            frases.append(parte.strip())
    return frases


# --- fato relevante ------------------------------------------------------------------------------
@dataclass(frozen=True)
class ResumoDoDocumento:
    frases: tuple[str, ...]
    numeros: tuple[str, ...]
    assuntos: tuple[str, ...]
    palavras: int
    versao: str = VERSAO

    def para_guardar(self) -> dict:
        return asdict(self)


def _sem_cabecalho_e_assinatura(texto: str) -> str:
    """Tira o cabeçalho (até o título "Fato Relevante") e a assinatura do fim."""
    texto = " ".join(texto.split())
    titulo = re.search(r"(?i)fato\s+relevante", texto)
    if titulo and titulo.start() < len(texto) // 3:
        texto = texto[titulo.end() :]
    fim = re.search(r"(?i)\b(atenciosamente|diretor[a]? (financeir[oa] )?e de relações com investidores)", texto)  # fmt: skip
    if fim and fim.start() > len(texto) // 2:
        texto = texto[: fim.start()]
    return texto


def _nota_da_frase(frase: str, pesos: Counter, posicao: int) -> float:
    palavras = _palavras(frase, PALAVRAS_VAZIAS_PT)
    if not palavras:
        return 0.0
    nota = sum(pesos[p] for p in set(palavras)) / math.sqrt(len(palavras))
    nota *= 1 + 0.3 * min(len(NUMERO.findall(frase)), 3)  # números concretos ajudam
    if any(trecho in frase.lower() for trecho in JURIDIQUES):
        nota *= 0.3
    return nota * (1.2 if posicao < 2 else 1.0)  # o fato costuma vir logo no começo


def _cortar(frase: str) -> str:
    palavras = frase.split()
    if len(palavras) <= MAX_PALAVRAS_POR_FRASE:
        return frase
    return " ".join(palavras[:MAX_PALAVRAS_POR_FRASE]) + " (...)"


def resumir_fato_relevante(texto: str) -> ResumoDoDocumento:
    """O resumo extrativo, os números e os assuntos de um fato relevante (ou comunicado)."""
    corpo = _sem_cabecalho_e_assinatura(texto)
    frases = dividir_em_frases(corpo)
    pesos = Counter(_palavras(corpo, PALAVRAS_VAZIAS_PT))
    notas = sorted(
        ((_nota_da_frase(f, pesos, i), i) for i, f in enumerate(frases)), reverse=True
    )
    escolhidas = sorted(i for _, i in notas[:FRASES_DO_RESUMO])
    numeros = tuple(dict.fromkeys(m.strip() for m in NUMERO.findall(corpo)))[
        :MAX_NUMEROS
    ]
    minusculo = _sem_acento(corpo)
    contagem = {
        assunto: sum(minusculo.count(_sem_acento(chave)) for chave in chaves)
        for assunto, chaves in ASSUNTOS.items()
    }
    assuntos = tuple(
        a for a, n in sorted(contagem.items(), key=lambda x: -x[1]) if n > 0
    )[:3]
    return ResumoDoDocumento(
        tuple(_cortar(frases[i]) for i in escolhidas),
        numeros,
        assuntos,
        len(corpo.split()),
    )


# --- 10-K: fatores de risco ----------------------------------------------------------------------
class _Texto(HTMLParser):
    """HTML → texto, com quebra de linha nos blocos e sem script/style."""

    BLOCOS = ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "td", "table")

    def __init__(self) -> None:
        super().__init__()
        self.partes: list[str] = []
        self.ignorando = 0

    def handle_starttag(self, tag: str, atributos: list) -> None:
        if tag in ("script", "style"):
            self.ignorando += 1
        if tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.ignorando = max(0, self.ignorando - 1)

    def handle_data(self, dados: str) -> None:
        if not self.ignorando:
            self.partes.append(dados)


def texto_do_html(html: str) -> str:
    html = re.sub(r"(?is)<ix:header>.*?</ix:header>", "", html)  # dados XBRL ocultos
    leitor = _Texto()
    leitor.feed(html)
    return re.sub(r"[ \t\xa0]+", " ", "".join(leitor.partes))


def fatores_de_risco(html: str) -> str | None:
    """O texto do "Item 1A. Risk Factors" de um 10-K (o maior trecho entre o título e o item
    seguinte; o sumário também tem o título, mas é curto). None se não achar."""
    texto = texto_do_html(html)
    inicios = [
        m.start()
        for m in re.finditer(r"(?i)item\s*1a\.?\s*\n?\s*risk\s+factors", texto)
    ]
    fins = [m.start() for m in re.finditer(r"(?i)item\s*1b\.?|item\s*1c\.?|item\s*2\.?\s*\n?\s*properties", texto)]  # fmt: skip
    trechos = []
    for inicio in inicios:
        depois = [f for f in fins if f > inicio]
        if depois:
            trechos.append(texto[inicio : min(depois)])
    if not trechos:
        return None
    maior = max(trechos, key=len)
    return " ".join(maior.split()) if len(maior.split()) > 200 else None


@dataclass(frozen=True)
class MudancaNosRiscos:
    semelhanca: float  # 0 a 1 (1 = texto igual)
    palavras_antes: int
    palavras_agora: int
    frases_novas: tuple[str, ...]
    novas_no_total: int
    palavras_em_alta: tuple[tuple[str, int, int], ...]  # (palavra, antes, agora)
    versao: str = VERSAO

    def para_guardar(self) -> dict:
        dados = asdict(self)
        dados["palavras_em_alta"] = [list(p) for p in self.palavras_em_alta]
        return dados


def _cosseno(a: Counter, b: Counter) -> float:
    comuns = set(a) & set(b)
    numerador = sum(a[p] * b[p] for p in comuns)
    norma = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(
        sum(v * v for v in b.values())
    )
    return numerador / norma if norma else 0.0


def _pares(frase: str) -> set[tuple[str, str]]:
    palavras = _palavras(frase, PALAVRAS_VAZIAS_EN)
    return set(pairwise(palavras))


def comparar_riscos(antes: str, agora: str) -> MudancaNosRiscos:
    """O que mudou entre os fatores de risco de dois anos."""
    contagem_antes = Counter(_palavras(antes, PALAVRAS_VAZIAS_EN))
    contagem_agora = Counter(_palavras(agora, PALAVRAS_VAZIAS_EN))
    pares_antes = [_pares(f) for f in dividir_em_frases(antes)]
    indice: dict[tuple[str, str], list[int]] = {}
    for i, pares in enumerate(pares_antes):
        for par in pares:
            indice.setdefault(par, []).append(i)
    novas = []
    for frase in dividir_em_frases(agora):
        pares = _pares(frase)
        if len(pares) < MIN_PALAVRAS_POR_FRASE:
            continue
        candidatas = Counter(i for par in pares for i in indice.get(par, ()))
        melhor = max(
            (
                len(pares & pares_antes[i]) / len(pares | pares_antes[i])
                for i in candidatas
            ),
            default=0.0,
        )
        if melhor < SEMELHANCA_DE_FRASE:
            novas.append((sum(contagem_agora[p] == 0 or 1 for p in pares), frase))
    total_antes, total_agora = (
        sum(contagem_antes.values()) or 1,
        sum(contagem_agora.values()) or 1,
    )
    crescimento = [
        (contagem_agora[p] / total_agora - contagem_antes[p] / total_antes, p)
        for p in contagem_agora
        if contagem_agora[p] >= MIN_OCORRENCIAS
    ]
    em_alta = tuple(
        (p, contagem_antes[p], contagem_agora[p])
        for d, p in sorted(crescimento, reverse=True)[:PALAVRAS_EM_ALTA]
        if d > 0
    )
    destaque = sorted(novas, key=lambda x: -len(x[1]))[:FRASES_NOVAS]
    return MudancaNosRiscos(
        round(_cosseno(contagem_antes, contagem_agora), 4),
        len(antes.split()),
        len(agora.split()),
        tuple(_cortar(f) for _, f in destaque),
        len(novas),
        em_alta,
    )


# --- PDF ----------------------------------------------------------------------------------------
def e_pdf(conteudo: bytes) -> bool:
    """O conteúdo é um PDF completo? (a CVM às vezes devolve uma página de aviso no lugar)."""
    return conteudo[:5] == b"%PDF-" and b"%%EOF" in conteudo[-2048:]


def texto_do_pdf(conteudo: bytes) -> str:
    """O texto de todas as páginas (vazio se o PDF for só imagem, como um documento escaneado)."""
    import pypdfium2 as pdfium  # só a coleta precisa (a imagem do app já tem)

    documento = pdfium.PdfDocument(conteudo)
    try:
        return " ".join(
            documento[i].get_textpage().get_text_range() for i in range(len(documento))
        )
    finally:
        documento.close()
