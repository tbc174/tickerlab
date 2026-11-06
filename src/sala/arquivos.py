"""Que arquivos entram na sala de dados: tipos e tamanhos (decisões D5 e D6 do plano do B-20).

Entram PDF, XLSX, DOCX e CSV, e o tipo é decidido **pelo conteúdo** (assinatura e estrutura do
arquivo), nunca pela extensão nem pelo que o navegador diz; a extensão só precisa concordar com o
conteúdo (um `.pdf` que é um ZIP é recusado). Tudo aqui é Python puro sobre os bytes, sem abrir o
documento com biblioteca de leitura: quem lê o conteúdo é o subprocesso de `leitura.py`, que
confere de novo o que só a leitura vê (páginas, JavaScript e anexos pelo PDFium).

Cada recusa tem um código de uma lista fechada (`MOTIVOS_DE_RECUSA`): é ele que vai para a
auditoria e para a tela, nunca o nome do arquivo.
"""

import io
import re
import zipfile
import zlib
from pathlib import PurePosixPath, PureWindowsPath

MEGABYTE = 1024 * 1024
TAMANHO_MAXIMO_DO_ARQUIVO = 25 * MEGABYTE
PAGINAS_MAXIMAS = 300

# ZIP por dentro do XLSX e do DOCX (zip bomb): o que ele diz que tem descomprimido
DESCOMPRIMIDO_MAXIMO = 100 * MEGABYTE
RAZAO_MAXIMA_DE_COMPRESSAO = 100
ENTRADAS_MAXIMAS_NO_ZIP = 2000
TAMANHO_MAXIMO_DO_INDICE_DO_OOXML = MEGABYTE  # o [Content_Types].xml
TAMANHO_MAXIMO_DA_RELACAO = MEGABYTE  # cada arquivo `.rels`
BLOCO_DA_CONTAGEM = 64 * 1024  # quanto se descomprime por vez ao contar o tamanho real
CABECALHO_LOCAL_DO_ZIP = 30  # bytes fixos antes do nome da entrada
METODOS_DO_ZIP = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)  # o Office só usa estes

# PDF: quanto a conferência descomprime dos fluxos (FlateDecode) para procurar nomes escondidos
DESCOMPRIMIDO_MAXIMO_DO_PDF = 100 * MEGABYTE

TIPOS_ACEITOS = ("pdf", "xlsx", "docx", "csv")
EXTENSOES = {".pdf": "pdf", ".xlsx": "xlsx", ".docx": "docx", ".csv": "csv"}
EXTENSOES_COM_MACRO = frozenset({".xlsm", ".docm", ".xltm", ".dotm", ".xlam"})

# códigos de recusa (lista fechada: auditoria e tela usam estes, sem texto livre)
VAZIO = "vazio"
GRANDE_DEMAIS = "grande_demais"
TIPO_NAO_ACEITO = "tipo_nao_aceito"
EXTENSAO_NAO_BATE = "extensao_nao_bate"
COM_MACRO = "com_macro"
PDF_CIFRADO = "pdf_cifrado"
PDF_ATIVO = "pdf_ativo"  # JavaScript, ação de abrir programa ou arquivo anexado
PAGINAS_DEMAIS = "paginas_demais"
ZIP_CAMINHO_ESTRANHO = "zip_caminho_estranho"
ZIP_GRANDE_DEMAIS = "zip_grande_demais"
OBJETO_EMBUTIDO = "objeto_embutido"  # objeto OLE dentro do DOCX ou do XLSX
CSV_BINARIO = "csv_binario"
ARQUIVO_DANIFICADO = "arquivo_danificado"
MOTIVOS_DE_RECUSA = (
    VAZIO,
    GRANDE_DEMAIS,
    TIPO_NAO_ACEITO,
    EXTENSAO_NAO_BATE,
    COM_MACRO,
    PDF_CIFRADO,
    PDF_ATIVO,
    PAGINAS_DEMAIS,
    ZIP_CAMINHO_ESTRANHO,
    ZIP_GRANDE_DEMAIS,
    OBJETO_EMBUTIDO,
    CSV_BINARIO,
    ARQUIVO_DANIFICADO,
)

ASSINATURA_DO_PDF = b"%PDF-"
ASSINATURA_DO_ZIP = b"PK\x03\x04"
ASSINATURA_DO_OLE = (
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # .doc e .xls antigos, OOXML com senha
)

# nomes do PDF que fazem o arquivo agir sozinho (rodar código, abrir programa, carregar anexo)
NOMES_ATIVOS_DO_PDF = frozenset(
    {b"JavaScript", b"JS", b"Launch", b"EmbeddedFile", b"EmbeddedFiles"}
)
_NOME_DO_PDF = re.compile(rb"/([^\s/<>\[\]()%{}]+)")
_ESCAPE_NO_NOME = re.compile(rb"#([0-9A-Fa-f]{2})")
_INICIO_DO_FLUXO = re.compile(rb"stream\r?\n")
_FIM_DO_FLUXO = b"endstream"
_PAGINA_DO_PDF = re.compile(rb"/Type\s*/Page(?![A-Za-z])")

# caracteres de controle que não aparecem em texto (tab, fim de linha e quebra de página podem)
_CONTROLE_FORA_DE_TEXTO = re.compile(rb"[\x00-\x08\x0b\x0e-\x1f\x7f]")


class ArquivoRecusado(ValueError):
    """O arquivo não entra na sala; `motivo` é um dos `MOTIVOS_DE_RECUSA`."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def conferir(conteudo: bytes, nome: str) -> str:
    """O tipo do arquivo (`pdf`, `xlsx`, `docx` ou `csv`), conferido pelo conteúdo.

    Levanta `ArquivoRecusado` com o código do motivo quando o arquivo não pode entrar.
    """
    if not conteudo:
        raise ArquivoRecusado(VAZIO)
    if len(conteudo) > TAMANHO_MAXIMO_DO_ARQUIVO:
        raise ArquivoRecusado(GRANDE_DEMAIS)
    extensao = _extensao(nome)
    if extensao in EXTENSOES_COM_MACRO:
        raise ArquivoRecusado(COM_MACRO)
    tipo = _tipo_pelo_conteudo(conteudo, extensao)
    if EXTENSOES.get(extensao) != tipo:
        raise ArquivoRecusado(EXTENSAO_NAO_BATE)
    return tipo


def _extensao(nome: str) -> str:
    # o nome vem do navegador: pode ter pasta de Windows ou de Linux na frente
    return PurePosixPath(PureWindowsPath(nome).name).suffix.lower()


def _tipo_pelo_conteudo(conteudo: bytes, extensao: str) -> str:
    if conteudo.startswith(ASSINATURA_DO_PDF):
        conferir_pdf(conteudo)
        return "pdf"
    if conteudo.startswith(ASSINATURA_DO_ZIP):
        return conferir_ooxml(conteudo)
    if conteudo.startswith(ASSINATURA_DO_OLE):
        raise ArquivoRecusado(TIPO_NAO_ACEITO)
    if extensao == ".csv":
        conferir_csv(conteudo)
        return "csv"
    raise ArquivoRecusado(TIPO_NAO_ACEITO)


# --- PDF ----------------------------------------------------------------------------------


def _fluxos_descomprimidos(conteudo: bytes) -> list[bytes]:
    """O conteúdo dos fluxos FlateDecode do PDF, até `DESCOMPRIMIDO_MAXIMO_DO_PDF` no total.

    É ali que um PDF esconde objetos (fluxos de objetos, `/ObjStm`): sem descomprimir, um
    `/JavaScript` dentro deles passaria. Fluxo que não é zlib é ignorado (imagem, fonte).
    """
    restante = DESCOMPRIMIDO_MAXIMO_DO_PDF
    fluxos = []
    for inicio in _INICIO_DO_FLUXO.finditer(conteudo):
        fim = conteudo.find(_FIM_DO_FLUXO, inicio.end())
        if fim < 0 or restante <= 0:
            break
        try:
            texto = zlib.decompressobj().decompress(
                conteudo[inicio.end() : fim], restante
            )
        except zlib.error:
            continue
        restante -= len(texto)
        fluxos.append(texto)
    return fluxos


def _nomes_do_pdf(trecho: bytes) -> set[bytes]:
    # /J#61vaScript é o mesmo nome que /JavaScript (escape hexadecimal da especificação)
    return {
        _ESCAPE_NO_NOME.sub(lambda m: bytes([int(m.group(1), 16)]), nome)
        for nome in _NOME_DO_PDF.findall(trecho)
    }


def conferir_pdf(conteudo: bytes) -> None:
    """Recusa PDF cifrado, com JavaScript, ação de abrir programa, anexo ou páginas demais."""
    trechos = [conteudo, *_fluxos_descomprimidos(conteudo)]
    nomes = set().union(*(_nomes_do_pdf(trecho) for trecho in trechos))
    if b"Encrypt" in nomes:
        raise ArquivoRecusado(PDF_CIFRADO)
    if nomes & NOMES_ATIVOS_DO_PDF:
        raise ArquivoRecusado(PDF_ATIVO)
    paginas = sum(len(_PAGINA_DO_PDF.findall(trecho)) for trecho in trechos)
    if paginas > PAGINAS_MAXIMAS:
        raise ArquivoRecusado(PAGINAS_DEMAIS)


# --- XLSX e DOCX (OOXML: um ZIP de XMLs) -------------------------------------------------


def _caminho_estranho(nome: str) -> bool:
    partes = nome.replace("\\", "/").split("/")
    return (
        nome.startswith(("/", "\\"))
        or ":" in nome  # C:\ ou fluxo alternativo do NTFS
        or ".." in partes
        or "\x00" in nome
    )


def _bytes_comprimidos(conteudo: bytes, entrada: zipfile.ZipInfo) -> memoryview:
    """Os bytes da entrada como estão no arquivo, achados pelo cabeçalho local."""
    inicio = entrada.header_offset
    cabecalho = conteudo[inicio : inicio + CABECALHO_LOCAL_DO_ZIP]
    if len(cabecalho) < CABECALHO_LOCAL_DO_ZIP or cabecalho[:4] != ASSINATURA_DO_ZIP:
        raise ArquivoRecusado(ARQUIVO_DANIFICADO)
    tamanho_do_nome = int.from_bytes(cabecalho[26:28], "little")
    tamanho_do_extra = int.from_bytes(cabecalho[28:30], "little")
    dados = inicio + CABECALHO_LOCAL_DO_ZIP + tamanho_do_nome + tamanho_do_extra
    return memoryview(conteudo)[dados : dados + entrada.compress_size]


def _saida_maxima(limite: int, total: int) -> int:
    # nunca 0 (no zlib, 0 é "sem limite") e nunca mais que um bloco grande por chamada
    return min(limite + 1 - total, MEGABYTE)


def _tamanho_real(conteudo: bytes, entrada: zipfile.ZipInfo, limite: int) -> int:
    """Quantos bytes a entrada tem descomprimida **de verdade** (não o que o ZIP declara), contados
    até `limite` + 1: o declarado pode mentir para baixo e passar pelas contas de
    `_conferir_entradas`. Descomprime aos poucos, sem guardar nada na memória."""
    comprimido = _bytes_comprimidos(conteudo, entrada)
    if entrada.compress_type == zipfile.ZIP_STORED:
        return len(comprimido)
    if entrada.compress_type != zipfile.ZIP_DEFLATED:
        raise ArquivoRecusado(ARQUIVO_DANIFICADO)
    descompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    total = 0
    posicao = 0
    while posicao < len(comprimido) and total <= limite:
        pedaco = comprimido[posicao : posicao + BLOCO_DA_CONTAGEM]
        posicao += len(pedaco)
        total += len(descompressor.decompress(pedaco, _saida_maxima(limite, total)))
        while descompressor.unconsumed_tail and total <= limite:
            total += len(
                descompressor.decompress(
                    descompressor.unconsumed_tail, _saida_maxima(limite, total)
                )
            )
    return total


def _conferir_tamanhos_reais(conteudo: bytes, entradas: list[zipfile.ZipInfo]) -> None:
    """Recusa o ZIP cujo tamanho descomprimido de verdade passa do declarado ou do limite."""
    restante = DESCOMPRIMIDO_MAXIMO
    for entrada in entradas:
        if entrada.compress_type not in METODOS_DO_ZIP:
            raise ArquivoRecusado(ARQUIVO_DANIFICADO)
        real = _tamanho_real(conteudo, entrada, restante)
        if real > restante or real > entrada.file_size:
            raise ArquivoRecusado(ZIP_GRANDE_DEMAIS)
        if real < entrada.file_size:  # diz ter mais do que tem: dado faltando
            raise ArquivoRecusado(ARQUIVO_DANIFICADO)
        restante -= real


def _lido_ate_o_limite(arquivo: zipfile.ZipFile, nome: str, limite: int) -> bytes:
    with arquivo.open(nome) as aberto:
        texto = aberto.read(limite + 1)
    if len(texto) > limite:
        raise ArquivoRecusado(ZIP_GRANDE_DEMAIS)
    return texto


def _conferir_sem_objeto_ole(arquivo: zipfile.ZipFile, indice: str) -> None:
    """Recusa objeto OLE (binário de outro programa, embutido ou ligado de fora).

    O Office liga cada objeto por uma relação do tipo `.../relationships/oleObject`; o gráfico
    com a planilha embutida usa `.../package` e segue aceito.
    """
    if "oleobject" in indice:  # o tipo de conteúdo de `embeddings/*.bin`
        raise ArquivoRecusado(OBJETO_EMBUTIDO)
    for entrada in arquivo.infolist():
        if entrada.filename.lower().endswith(".rels"):
            texto = _lido_ate_o_limite(
                arquivo, entrada.filename, TAMANHO_MAXIMO_DA_RELACAO
            )
            if b"oleobject" in texto.lower():
                raise ArquivoRecusado(OBJETO_EMBUTIDO)


def _conferir_entradas(arquivo: zipfile.ZipFile, tamanho_comprimido: int) -> None:
    entradas = arquivo.infolist()
    if len(entradas) > ENTRADAS_MAXIMAS_NO_ZIP:
        raise ArquivoRecusado(ZIP_GRANDE_DEMAIS)
    descomprimido = sum(entrada.file_size for entrada in entradas)
    if (
        descomprimido > DESCOMPRIMIDO_MAXIMO
        or descomprimido > RAZAO_MAXIMA_DE_COMPRESSAO * tamanho_comprimido
    ):
        raise ArquivoRecusado(ZIP_GRANDE_DEMAIS)
    for entrada in entradas:
        if _caminho_estranho(entrada.filename):
            raise ArquivoRecusado(ZIP_CAMINHO_ESTRANHO)
        if entrada.flag_bits & 0x1:  # entrada com senha: não há como conferir
            raise ArquivoRecusado(ARQUIVO_DANIFICADO)
        nome = entrada.filename.lower()
        if nome.endswith("vbaproject.bin") or "/activex/" in f"/{nome}":
            raise ArquivoRecusado(COM_MACRO)


def _indice_do_ooxml(arquivo: zipfile.ZipFile) -> str:
    try:
        with arquivo.open("[Content_Types].xml") as indice:
            # lê no máximo o limite + 1 byte: o tamanho que o ZIP declara pode mentir
            texto = indice.read(TAMANHO_MAXIMO_DO_INDICE_DO_OOXML + 1)
    except KeyError:
        raise ArquivoRecusado(TIPO_NAO_ACEITO) from None
    if len(texto) > TAMANHO_MAXIMO_DO_INDICE_DO_OOXML:
        raise ArquivoRecusado(ZIP_GRANDE_DEMAIS)
    return texto.decode("utf-8", errors="replace").lower()


def conferir_ooxml(conteudo: bytes) -> str:
    """`xlsx` ou `docx`; recusa macro, ZIP bomba, caminho estranho e ZIP que não é Office."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
            _conferir_entradas(arquivo, len(conteudo))
            _conferir_tamanhos_reais(conteudo, arquivo.infolist())
            indice = _indice_do_ooxml(arquivo)
            _conferir_sem_objeto_ole(arquivo, indice)
            nomes = set(arquivo.namelist())
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError):
        raise ArquivoRecusado(ARQUIVO_DANIFICADO) from None
    if "macroenabled" in indice or "vbaproject" in indice:
        raise ArquivoRecusado(COM_MACRO)
    if "word/document.xml" in nomes:
        return "docx"
    if "xl/workbook.xml" in nomes:
        return "xlsx"
    raise ArquivoRecusado(TIPO_NAO_ACEITO)


# --- CSV ----------------------------------------------------------------------------------


def conferir_csv(conteudo: bytes) -> None:
    """Recusa CSV com byte nulo ou outro caractere de controle (arquivo binário renomeado)."""
    if _CONTROLE_FORA_DE_TEXTO.search(conteudo):
        raise ArquivoRecusado(CSV_BINARIO)
    try:
        conteudo.decode("utf-8")
    except UnicodeDecodeError:
        try:
            conteudo.decode("cp1252")  # o Excel em português salva CSV assim
        except UnicodeDecodeError:
            raise ArquivoRecusado(CSV_BINARIO) from None
