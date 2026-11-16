"""Leitor de arquivos DBC do DATASUS (CNES e outros): um DBF com os registros comprimidos.

O DBC guarda o cabeçalho do DBF sem compressão e, depois dele e de 4 bytes de CRC, os registros no
formato PKWare DCL ("implode"). A descompressão é uma tradução em Python do `blast` de Mark Adler
(licença zlib, permissiva): nenhuma biblioteca GPL ou AGPL entra no projeto.

A saída sai em pedaços (`descomprimir_em_pedacos`): só a janela dos últimos 4.096 bytes (a maior
distância que o formato permite) fica na memória, e `ler_dbc` entrega registro a registro. O SIA PA de SP
passa de 2 GB descomprimido por arquivo; o comprimido continua inteiro na memória (algumas centenas de MB).

Sem Streamlit, sem rede; só a biblioteca padrão.
"""

import struct
from collections.abc import Iterator

# Tabelas do blast: cada byte é (repetições - 1) << 4 | comprimento do código (0 = símbolo sem uso).
_LITERAIS = bytes([
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8, 9, 7, 6, 7, 8, 7, 6, 55, 8,
    23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5, 7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11,
    8, 11, 9, 12, 8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27, 44, 253, 253,
    253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45, 44, 173,
])  # fmt: skip
_COMPRIMENTOS = bytes([2, 35, 36, 53, 38, 23])
_DISTANCIAS = bytes([2, 20, 53, 230, 247, 151, 248])
_BASE_DO_COMPRIMENTO = (3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264)
_BITS_EXTRAS = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8)
_FIM_DO_FLUXO = 519
_MAXIMO_DE_BITS = 13
_CRC_DO_DBC = 4
_JANELA = (
    4096  # maior distância do PKWare DCL: dicionário de 6 bits, (63 << 6) + 63 + 1
)
TAMANHO_DO_PEDACO = 1 << 16  # bytes de saída entregues por vez


class DbcInvalido(ValueError):
    """O arquivo não é um DBC íntegro (cabeçalho, fluxo comprimido ou tamanho dos registros)."""


class _Codigo:
    """Código de Huffman canônico do blast: os bits chegam invertidos, do menor comprimento ao maior."""

    def __init__(self, repeticoes: bytes) -> None:
        comprimentos: list[int] = []
        for byte in repeticoes:
            comprimentos += [byte & 15] * ((byte >> 4) + 1)
        self.quantidade = [0] * (_MAXIMO_DE_BITS + 1)
        for comprimento in comprimentos:
            self.quantidade[comprimento] += 1
        usados = [s for s, comprimento in enumerate(comprimentos) if comprimento]
        self.simbolos = sorted(usados, key=lambda s: (comprimentos[s], s))
        self.comprimentos = comprimentos


class _Bits:
    """Leitor de bits do menor para o maior de cada byte, como o PKWare."""

    def __init__(self, dados: bytes) -> None:
        self.dados = dados
        self.posicao = 0
        self.buffer = 0
        self.quantos = 0

    def ler(self, quantos: int) -> int:
        while self.quantos < quantos:
            if self.posicao >= len(self.dados):
                raise DbcInvalido(
                    "DBC: o fluxo comprimido acabou antes do marcador de fim"
                )
            self.buffer |= self.dados[self.posicao] << self.quantos
            self.posicao += 1
            self.quantos += 8
        valor = self.buffer & ((1 << quantos) - 1)
        self.buffer >>= quantos
        self.quantos -= quantos
        return valor

    def decodificar(self, codigo: _Codigo) -> int:
        valor = primeiro = indice = 0
        for comprimento in range(1, _MAXIMO_DE_BITS + 1):
            valor |= self.ler(1) ^ 1
            quantidade = codigo.quantidade[comprimento]
            if valor - quantidade < primeiro:
                return codigo.simbolos[indice + (valor - primeiro)]
            indice += quantidade
            primeiro = (primeiro + quantidade) << 1
            valor <<= 1
        raise DbcInvalido("DBC: código de Huffman inválido no fluxo comprimido")


_CODIGO_LITERAL = _Codigo(_LITERAIS)
_CODIGO_COMPRIMENTO = _Codigo(_COMPRIMENTOS)
_CODIGO_DISTANCIA = _Codigo(_DISTANCIAS)


def descomprimir_em_pedacos(
    dados: bytes, tamanho_do_pedaco: int = TAMANHO_DO_PEDACO
) -> Iterator[bytes]:
    """Descomprime um fluxo PKWare DCL entregando a saída aos poucos, com memória limitada.

    Guarda só a janela de `_JANELA` bytes que uma cópia pode alcançar; cada pedaço entregue tem até
    `tamanho_do_pedaco + _JANELA` bytes. Juntos, os pedaços são exatamente a saída inteira.
    """
    if tamanho_do_pedaco < 1:
        raise ValueError("DBC: o pedaço precisa ter ao menos 1 byte")
    bits = _Bits(dados)
    literais_codificados = bits.ler(8)
    if literais_codificados not in (0, 1):
        raise DbcInvalido("DBC: tipo de literal desconhecido no fluxo comprimido")
    dicionario = bits.ler(8)
    if not 4 <= dicionario <= 6:
        raise DbcInvalido("DBC: tamanho de dicionário inválido no fluxo comprimido")
    saida = bytearray()
    limite = tamanho_do_pedaco + _JANELA
    while True:
        if len(saida) >= limite:
            yield bytes(saida[:-_JANELA])
            del saida[:-_JANELA]
        if not bits.ler(1):
            saida.append(
                bits.decodificar(_CODIGO_LITERAL)
                if literais_codificados
                else bits.ler(8)
            )
            continue
        simbolo = bits.decodificar(_CODIGO_COMPRIMENTO)
        comprimento = _BASE_DO_COMPRIMENTO[simbolo] + bits.ler(_BITS_EXTRAS[simbolo])
        if comprimento == _FIM_DO_FLUXO:
            if saida:
                yield bytes(saida)
            return
        bits_baixos = 2 if comprimento == 2 else dicionario
        distancia = (
            (bits.decodificar(_CODIGO_DISTANCIA) << bits_baixos)
            + bits.ler(bits_baixos)
            + 1
        )
        # depois do 1º pedaço a janela guarda sempre `_JANELA` bytes, o alcance máximo de uma cópia
        if distancia > len(saida):
            raise DbcInvalido("DBC: referência para antes do começo da saída")
        _copiar(saida, distancia, comprimento)


def _copiar(saida: bytearray, distancia: int, comprimento: int) -> None:
    """Copia `comprimento` bytes de `distancia` atrás; a origem pode se sobrepor ao destino."""
    inicio = len(saida) - distancia
    if distancia >= comprimento:
        saida += saida[inicio : inicio + comprimento]
        return
    for _ in range(
        comprimento
    ):  # sobreposição: cada byte copiado pode ser a origem do próximo
        saida.append(saida[-distancia])


def descomprimir_pkware(dados: bytes) -> bytes:
    """Descomprime um fluxo PKWare DCL inteiro (do byte do tipo de literal até o marcador de fim)."""
    return b"".join(descomprimir_em_pedacos(dados))


def campos_do_cabecalho(cabecalho: bytes) -> list[tuple[str, int]]:
    """`(nome, tamanho)` de cada campo, lidos dos descritores de 32 bytes do cabeçalho do DBF."""
    campos: list[tuple[str, int]] = []
    for inicio in range(32, len(cabecalho) - 31, 32):
        if cabecalho[inicio] == 0x0D:
            break
        nome = (
            cabecalho[inicio : inicio + 11].split(b"\x00")[0].decode("ascii", "replace")
        )
        campos.append((nome.upper(), cabecalho[inicio + 16]))
    return campos


def nomes_das_colunas(conteudo: bytes) -> list[str]:
    """Os nomes dos campos do DBC, lidos só do cabeçalho (sem descomprimir nada)."""
    if len(conteudo) < 32:
        raise DbcInvalido("DBC: arquivo menor que o cabeçalho")
    tamanho_do_cabecalho = struct.unpack_from("<H", conteudo, 8)[0]
    return [nome for nome, _ in campos_do_cabecalho(conteudo[:tamanho_do_cabecalho])]


def ler_dbc(
    conteudo: bytes,
    colunas: tuple[str, ...],
    tamanho_do_pedaco: int = TAMANHO_DO_PEDACO,
) -> Iterator[dict[str, str]]:
    """Os registros do DBC, só com as `colunas` pedidas (texto sem espaços nas pontas, em latin-1).

    Lê em fluxo: a memória não cresce com o tamanho do arquivo descomprimido. Coluna que não existe no
    arquivo é erro: o layout mudou e quem consome precisa saber. Registro apagado (marca `*`) é ignorado;
    a leitura para no número de registros do cabeçalho (o DBF termina com o byte 0x1A).
    """
    if len(conteudo) < 32:
        raise DbcInvalido("DBC: arquivo menor que o cabeçalho")
    registros, tamanho_do_cabecalho, tamanho_do_registro = struct.unpack_from(
        "<xxxxIHH", conteudo, 0
    )
    posicoes = _posicoes_das_colunas(
        conteudo[:tamanho_do_cabecalho], tamanho_do_registro, colunas
    )
    fluxo = descomprimir_em_pedacos(
        conteudo[tamanho_do_cabecalho + _CRC_DO_DBC :], tamanho_do_pedaco
    )
    lidos = 0
    sobra = bytearray()
    for pedaco in fluxo:
        sobra += pedaco
        completos = min(len(sobra) // tamanho_do_registro, registros - lidos)
        for numero in range(completos):
            inicio = numero * tamanho_do_registro
            registro = sobra[inicio : inicio + tamanho_do_registro]
            if registro[:1] != b"*":
                yield {
                    coluna: registro[comeco:final].decode("latin-1").strip()
                    for coluna, (comeco, final) in posicoes.items()
                }
        del sobra[: completos * tamanho_do_registro]
        lidos += completos
    if lidos < registros:
        raise DbcInvalido("DBC: menos registros do que o cabeçalho promete")


def _posicoes_das_colunas(
    cabecalho: bytes, tamanho_do_registro: int, colunas: tuple[str, ...]
) -> dict[str, tuple[int, int]]:
    """`(começo, fim)` de cada coluna pedida dentro do registro, conferindo o layout do cabeçalho."""
    todas: dict[str, tuple[int, int]] = {}
    deslocamento = 1  # o primeiro byte do registro é a marca de apagado
    for nome, tamanho in campos_do_cabecalho(cabecalho):
        todas[nome] = (deslocamento, deslocamento + tamanho)
        deslocamento += tamanho
    if deslocamento != tamanho_do_registro:
        raise DbcInvalido("DBC: os campos não somam o tamanho do registro do cabeçalho")
    faltando = [coluna for coluna in colunas if coluna not in todas]
    if faltando:
        raise DbcInvalido(f"DBC: colunas ausentes no arquivo: {', '.join(faltando)}")
    return {coluna: todas[coluna] for coluna in colunas}
