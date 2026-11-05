"""RAR5 "guardado" (sem compressão) para os testes: não há programa livre que crie RAR, então o arquivo
é montado pelo formato publicado pela RARLAB ("RAR 5.0 archive format"): assinatura, cabeçalho principal,
um cabeçalho de arquivo por membro (com o CRC32 dos dados) e o fim. O bsdtar (libarchive) lê como lê um
RAR da ARTESP; a descompressão de verdade é conferida no servidor, com os arquivos baixados."""

import struct
import zlib

ASSINATURA = b"Rar!\x1a\x07\x01\x00"
CABECALHO_PRINCIPAL, CABECALHO_DE_ARQUIVO, FIM = 1, 2, 5
TEM_DADOS = 0x02  # o cabeçalho é seguido pelos dados do membro
TEM_CRC = 0x04  # o cabeçalho do membro traz o CRC32 dos dados
ARQUIVO_COMUM = 0x20  # atributo do Windows
GUARDADO = 0  # método 0: sem compressão
WINDOWS = 0


def _vint(numero: int) -> bytes:
    """Inteiro de tamanho variável do RAR5: 7 bits por byte, o bit alto diz que tem mais."""
    saida = bytearray()
    while True:
        byte, numero = numero & 0x7F, numero >> 7
        saida.append(byte | (0x80 if numero else 0))
        if not numero:
            return bytes(saida)


def _bloco(corpo: bytes) -> bytes:
    tamanho = _vint(len(corpo))
    return struct.pack("<I", zlib.crc32(tamanho + corpo)) + tamanho + corpo


def rar5(membros: list[tuple[str, bytes]]) -> bytes:
    """Um RAR5 com os membros (nome, conteúdo), na ordem dada."""
    partes = [ASSINATURA, _bloco(_vint(CABECALHO_PRINCIPAL) + _vint(0) + _vint(0))]
    for nome, dados in membros:
        nome_em_bytes = nome.encode()
        corpo = (
            _vint(CABECALHO_DE_ARQUIVO) + _vint(TEM_DADOS) + _vint(len(dados))
            + _vint(TEM_CRC) + _vint(len(dados)) + _vint(ARQUIVO_COMUM)
            + struct.pack("<I", zlib.crc32(dados)) + _vint(GUARDADO) + _vint(WINDOWS)
            + _vint(len(nome_em_bytes)) + nome_em_bytes
        )  # fmt: skip
        partes += [_bloco(corpo), dados]
    partes.append(_bloco(_vint(FIM) + _vint(0) + _vint(0)))
    return b"".join(partes)
