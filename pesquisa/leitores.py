"""Leitura de documentos para o bot: texto e tabelas, sempre com o lugar de onde saiu (página,
planilha e linha), porque fato sem lugar não se confere.

O núcleo lê com o que o app já usa (`beautifulsoup4`, `pypdf`, `openpyxl`, `csv`). O Docling (MIT)
é opcional: quando instalado, lê as tabelas dos PDFs e, se pedido, as planilhas. Texto de PDF
escaneado volta vazio no `pypdf`; o aviso diz isso em vez de fingir que não há nada.
"""

import csv
import io
import re
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from openpyxl.worksheet._read_only import ReadOnlyWorksheet

MAXIMO_DE_CARACTERES = 30_000  # por chamada: o agente lê, não despeja o arquivo inteiro
MAXIMO_DE_LINHAS = 200  # de tabela, por chamada
DELIMITADORES = ";,\t|"
CODIFICACOES = ("utf-8-sig", "cp1252")
ASSINATURA_PDF = b"%PDF"
ASSINATURA_ZIP = b"PK"
COMECO_DE_HTML = re.compile(
    rb"^\s*(<\?xml[^>]*>\s*)?(<!doctype html|<html)", re.IGNORECASE
)
ESPACOS = re.compile(r"\s+")
TIPOS_DE_DOCUMENTO = frozenset({"pdf", "xlsx", "csv", "zip"})
EXTENSOES_DE_TEXTO_EM_TABELA = frozenset({".csv", ".txt", ".tsv"})


@dataclass(frozen=True)
class Bloco:
    posicao: str  # "pagina 3", "html"
    texto: str


@dataclass(frozen=True)
class Tabela:
    posicao: str  # "Planilha1", "pagina 4 tabela 2", "tabela 1"
    linhas: list[list[str]]
    primeira_linha: int = 1  # número da 1ª linha devolvida, contando da 1ª da tabela
    numeros: list[int] | None = (
        None  # número de cada linha na planilha, se pulou as vazias
    )


@dataclass
class Extracao:
    """O que foi lido de um documento e como."""

    tipo: str
    motor: str
    blocos: list[Bloco] = field(default_factory=list)
    tabelas: list[Tabela] = field(default_factory=list)
    truncado: bool = False
    avisos: list[str] = field(default_factory=list)
    planilhas: list[str] = field(
        default_factory=list
    )  # nomes das abas, para pedir uma só

    def trechos(self) -> Iterator[tuple[str, str]]:
        """Cada pedaço pesquisável com o lugar: os blocos e cada linha de cada tabela."""
        for bloco in self.blocos:
            yield bloco.posicao, bloco.texto
        for tabela in self.tabelas:
            numeros = tabela.numeros or range(
                tabela.primeira_linha, tabela.primeira_linha + len(tabela.linhas)
            )
            for numero, linha in zip(numeros, tabela.linhas, strict=True):
                yield f"{tabela.posicao} linha {numero}", " | ".join(linha)


def limpar(texto: str) -> str:
    """Espaços repetidos e quebras viram um espaço; é com este texto que o trecho é conferido."""
    return ESPACOS.sub(" ", texto).strip()


def descobrir_tipo(caminho: Path, nome_original: str | None = None) -> str:
    """O tipo pelo conteúdo (o nome do arquivo mente): pdf, xlsx, zip, html, csv ou desconhecido.

    Texto puro não tem assinatura; aí vale a extensão do `nome_original` (o caminho da URL),
    porque o arquivo em `caminho` pode ser um temporário `.tmp`."""
    with caminho.open("rb") as arquivo:
        inicio = arquivo.read(2048)
    if inicio.startswith(ASSINATURA_PDF):
        return "pdf"
    if inicio.startswith(ASSINATURA_ZIP):
        return "xlsx" if _zip_e_planilha(caminho) else "zip"
    if COMECO_DE_HTML.match(inicio):
        return "html"
    sufixo = PurePosixPath(nome_original).suffix if nome_original else caminho.suffix
    if sufixo.lower() in EXTENSOES_DE_TEXTO_EM_TABELA:
        return "csv"
    return "desconhecido"


def _zip_e_planilha(caminho: Path) -> bool:
    try:
        with zipfile.ZipFile(caminho) as pacote:
            return "xl/workbook.xml" in pacote.namelist()
    except zipfile.BadZipFile:
        return False


def extrair(
    caminho: Path,
    *,
    motor: str = "auto",
    pagina_inicial: int = 1,
    pagina_final: int | None = None,
    linha_inicial: int = 1,
    planilha: str | None = None,
    contem: tuple[str, ...] = (),
    filtro_por_coluna: Mapping[str, Sequence[str]] | None = None,
    maximo_de_linhas: int = MAXIMO_DE_LINHAS,
    maximo_de_caracteres: int = MAXIMO_DE_CARACTERES,
) -> Extracao:
    """Lê o documento. `motor`: "auto" (núcleo; Docling para as tabelas de PDF, se houver) ou
    "docling" (força o Docling). Páginas e linhas contam a partir de 1; a conferência de fato
    passa limites enormes para procurar o trecho no documento inteiro. `contem` devolve só as
    linhas de tabela e as páginas (ou o texto da página HTML) em que todos os termos aparecem.
    `filtro_por_coluna` (número da coluna, a partir de 1 → termos) exige os termos na coluna
    certa das linhas de tabela, para um termo curto não casar em outra coluna; quem só usa
    `contem` não muda."""
    extracao = _extrair(
        caminho,
        motor,
        pagina_inicial,
        pagina_final,
        linha_inicial,
        planilha,
        _filtro(contem, filtro_por_coluna),
        maximo_de_linhas,
        maximo_de_caracteres,
    )
    extracao.avisos.extend(_avisos_do_filtro(filtro_por_coluna))
    return extracao


def _extrair(
    caminho: Path,
    motor: str,
    pagina_inicial: int,
    pagina_final: int | None,
    linha_inicial: int,
    planilha: str | None,
    termos: "Filtro",
    maximo_de_linhas: int,
    maximo_de_caracteres: int,
) -> Extracao:
    tipo = descobrir_tipo(caminho)
    if motor == "docling" or (
        motor == "auto" and tipo == "pdf" and docling_instalado()
    ):
        resultado = _com_docling(caminho, tipo)
        if resultado is not None:
            recortado = _recortar(
                resultado, pagina_inicial, pagina_final, maximo_de_caracteres
            )
            return _filtrar(recortado, termos)
    if tipo == "pdf":
        lido = _ler_pdf(caminho, pagina_inicial, pagina_final, maximo_de_caracteres)
        return _filtrar(lido, termos)
    if tipo == "xlsx":
        return _ler_xlsx(caminho, linha_inicial, maximo_de_linhas, planilha, termos)
    if tipo == "html":
        return _filtrar(ler_html(caminho.read_bytes(), maximo_de_caracteres), termos)
    if tipo == "csv":
        return _ler_csv(caminho, linha_inicial, maximo_de_linhas, termos)
    extracao = Extracao(tipo, "nenhum")
    extracao.avisos.append(
        "tipo não suportado" if tipo == "zip" else f"não sei ler este tipo ({tipo})"
    )
    return extracao


@dataclass(frozen=True)
class Filtro:
    """Os termos (em minúsculas) que um trecho precisa ter: em qualquer lugar da linha ou
    da página (`geral`) e na coluna certa das linhas de tabela (`por_coluna`, de 1 em diante)."""

    geral: tuple[str, ...] = ()
    por_coluna: Mapping[int, tuple[str, ...]] = field(default_factory=dict)

    def vazio(self) -> bool:
        return not self.geral and not self.por_coluna


def _filtro(
    contem: Sequence[str], filtro_por_coluna: Mapping[str, Sequence[str]] | None
) -> Filtro:
    por_coluna: dict[int, tuple[str, ...]] = {}
    for coluna, termos in (filtro_por_coluna or {}).items():
        numero = str(coluna).strip()
        limpos = tuple(t.casefold() for t in termos if t.strip())
        if numero.isdecimal() and int(numero) >= 1 and limpos:
            por_coluna[int(numero)] = limpos
    return Filtro(tuple(t.casefold() for t in contem if t.strip()), por_coluna)


def _avisos_do_filtro(
    filtro_por_coluna: Mapping[str, Sequence[str]] | None,
) -> list[str]:
    invalidas = [
        str(coluna)
        for coluna in (filtro_por_coluna or {})
        if not (str(coluna).strip().isdecimal() and int(str(coluna).strip()) >= 1)
    ]
    return [
        f"filtro_por_coluna: a coluna {coluna!r} foi ignorada (use o número da coluna, a partir de 1)"
        for coluna in invalidas
    ]


def _bate(texto: str, termos: tuple[str, ...]) -> bool:
    """Todos os termos (já em minúsculas) aparecem no texto, sem distinguir caixa."""
    minusculo = texto.casefold()
    return all(termo in minusculo for termo in termos)


def _linha_bate(celulas: Sequence[str], filtro: Filtro) -> bool:
    """A linha tem todos os termos gerais e, em cada coluna pedida, todos os termos dela."""
    if not _bate(" | ".join(celulas), filtro.geral):
        return False
    return all(
        coluna <= len(celulas) and _bate(celulas[coluna - 1], termos)
        for coluna, termos in filtro.por_coluna.items()
    )


def _filtrar(extracao: Extracao, filtro: Filtro) -> Extracao:
    """Fica só com o que contém todos os termos: páginas (blocos) e linhas de tabela. Com
    filtro por coluna, só as linhas de tabela são filtradas por ela; as páginas, só pelos termos gerais."""
    if filtro.vazio():
        return extracao
    extracao.blocos = [b for b in extracao.blocos if _bate(b.texto, filtro.geral)]
    filtradas: list[Tabela] = []
    for tabela in extracao.tabelas:
        numeros = tabela.numeros or list(
            range(tabela.primeira_linha, tabela.primeira_linha + len(tabela.linhas))
        )
        itens = [
            (n, linha)
            for n, linha in zip(numeros, tabela.linhas, strict=True)
            if _linha_bate(linha, filtro)
        ]
        filtradas.append(
            Tabela(
                tabela.posicao,
                [linha for _, linha in itens],
                tabela.primeira_linha,
                [n for n, _ in itens],
            )
        )
    extracao.tabelas = filtradas
    return extracao


def docling_instalado() -> bool:
    try:
        import docling  # noqa: F401
    except ImportError:
        return False
    return True


def _recortar(
    extracao: Extracao, inicial: int, final: int | None, maximo: int
) -> Extracao:
    """Fica só com as páginas pedidas, nos blocos e nas tabelas que dizem a página."""

    def dentro(posicao: str) -> bool:
        achado = re.match(r"pagina (\d+)", posicao)
        if achado is None:
            return True
        numero = int(achado.group(1))
        return numero >= inicial and (final is None or numero <= final)

    extracao.blocos = [b for b in extracao.blocos if dentro(b.posicao)]
    extracao.tabelas = [t for t in extracao.tabelas if dentro(t.posicao)]
    return _limitar(extracao, maximo)


def _limitar(extracao: Extracao, maximo: int) -> Extracao:
    """Corta o texto no máximo de caracteres, marcando que cortou."""
    gasto = 0
    mantidos: list[Bloco] = []
    for bloco in extracao.blocos:
        if gasto + len(bloco.texto) > maximo:
            extracao.truncado = True
            restante = maximo - gasto
            if restante > 0:
                mantidos.append(Bloco(bloco.posicao, bloco.texto[:restante]))
            break
        gasto += len(bloco.texto)
        mantidos.append(bloco)
    extracao.blocos = mantidos
    return extracao


def _ler_pdf(caminho: Path, inicial: int, final: int | None, maximo: int) -> Extracao:
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho))
    total = len(leitor.pages)
    ultima = min(final or total, total)
    extracao = Extracao("pdf", "pypdf")
    for numero in range(max(inicial, 1), ultima + 1):
        texto = limpar(leitor.pages[numero - 1].extract_text() or "")
        extracao.blocos.append(Bloco(f"pagina {numero}", texto))
    if ultima < total:
        extracao.avisos.append(
            f"o PDF tem {total} páginas; lidas de {inicial} a {ultima}"
        )
    if not any(bloco.texto for bloco in extracao.blocos):
        extracao.avisos.append(
            "sem texto nas páginas lidas: pode ser PDF escaneado (precisa de OCR)"
        )
    extracao.avisos.append("tabelas de PDF só com o Docling instalado")
    return _limitar(extracao, maximo)


def _ler_xlsx(
    caminho: Path,
    linha_inicial: int,
    maximo_de_linhas: int,
    so_a_planilha: str | None,
    termos: Filtro,
) -> Extracao:
    """Lê as abas (ou só `so_a_planilha`). Linhas vazias são puladas e as células vazias do fim
    cortadas, mas o número devolvido é o da linha na planilha, para o trecho ser achável."""
    from openpyxl import load_workbook

    pasta = load_workbook(caminho, read_only=True, data_only=True)
    extracao = Extracao("xlsx", "openpyxl", planilhas=list(pasta.sheetnames))
    try:
        if so_a_planilha is not None and so_a_planilha not in pasta.sheetnames:
            extracao.avisos.append(
                f"não há a planilha {so_a_planilha!r}; use um dos nomes de `planilhas`"
            )
            return extracao
        for planilha in pasta.worksheets:
            if so_a_planilha is not None and planilha.title != so_a_planilha:
                continue
            extracao.tabelas.append(
                _ler_planilha(
                    planilha, linha_inicial, maximo_de_linhas, extracao, termos
                )
            )
    finally:
        pasta.close()
    return extracao


def _ler_planilha(
    planilha: "ReadOnlyWorksheet",
    linha_inicial: int,
    maximo_de_linhas: int,
    extracao: Extracao,
    termos: "Filtro",
) -> Tabela:
    linhas: list[list[str]] = []
    numeros: list[int] = []
    for numero, linha in enumerate(planilha.iter_rows(values_only=True), 1):
        if numero < linha_inicial:
            continue
        celulas = ["" if c is None else str(c) for c in linha]
        while celulas and not celulas[-1]:
            celulas.pop()
        if not celulas or not _linha_bate(celulas, termos):
            continue
        if len(linhas) >= maximo_de_linhas:
            extracao.truncado = True
            break
        linhas.append(celulas)
        numeros.append(numero)
    return Tabela(planilha.title, linhas, linha_inicial, numeros)


def _ler_csv(
    caminho: Path,
    linha_inicial: int,
    maximo_de_linhas: int,
    termos: Filtro,
) -> Extracao:
    texto = _decodificar(caminho.read_bytes())
    try:
        delimitador = (
            csv.Sniffer().sniff(texto[:4096], delimiters=DELIMITADORES).delimiter
        )
    except csv.Error:
        delimitador = ";"
    extracao = Extracao("csv", "csv")
    linhas: list[list[str]] = []
    numeros: list[int] = []
    leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)
    for numero, linha in enumerate(leitor, 1):
        if numero < linha_inicial or not _linha_bate(linha, termos):
            continue
        if len(linhas) >= maximo_de_linhas:
            extracao.truncado = True
            break
        linhas.append(linha)
        numeros.append(numero)
    extracao.tabelas.append(Tabela("csv", linhas, linha_inicial, numeros))
    return extracao


def _decodificar(conteudo: bytes) -> str:
    for codificacao in CODIFICACOES:
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1")


def ler_html(conteudo: bytes, maximo: int = MAXIMO_DE_CARACTERES) -> Extracao:
    sopa = BeautifulSoup(conteudo, "lxml")
    for lixo in sopa(["script", "style", "noscript"]):
        lixo.decompose()
    extracao = Extracao("html", "beautifulsoup")
    for numero, tabela in enumerate(sopa.find_all("table"), 1):
        linhas = [
            [limpar(celula.get_text(" ")) for celula in tr.find_all(["td", "th"])]
            for tr in tabela.find_all("tr")
        ]
        linhas = [linha for linha in linhas if any(linha)]
        if linhas:
            extracao.tabelas.append(
                Tabela(f"tabela {numero}", linhas[:MAXIMO_DE_LINHAS])
            )
    extracao.blocos.append(Bloco("html", limpar(sopa.get_text(" "))))
    return _limitar(extracao, maximo)


def _com_docling(caminho: Path, tipo: str) -> Extracao | None:
    """Lê com o Docling (MIT); None se não está instalado ou falhou (cai no núcleo, com aviso)."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return None
    documento = DocumentConverter().convert(str(caminho)).document
    extracao = Extracao(tipo, "docling")
    paginas: dict[int, list[str]] = {}
    for item in documento.texts:
        pagina = item.prov[0].page_no if item.prov else 0
        paginas.setdefault(pagina, []).append(item.text)
    for pagina, textos in sorted(paginas.items()):
        extracao.blocos.append(Bloco(f"pagina {pagina}", limpar(" ".join(textos))))
    for numero, tabela in enumerate(documento.tables, 1):
        pagina = tabela.prov[0].page_no if tabela.prov else 0
        quadro = tabela.export_to_dataframe(documento)
        linhas = [list(map(str, quadro.columns))] + [
            [str(valor) for valor in linha] for linha in quadro.values.tolist()
        ]
        extracao.tabelas.append(
            Tabela(f"pagina {pagina} tabela {numero}", linhas[:MAXIMO_DE_LINHAS])
        )
    return extracao
