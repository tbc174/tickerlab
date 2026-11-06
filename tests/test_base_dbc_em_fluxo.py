"""Leitura do DBC em fluxo (base/dbc.py): o mesmo resultado da leitura inteira, com memória limitada.

O SIA PA de SP passa de 2 GB descomprimido por parte: a saída sai em pedaços e só a janela de 4.096 bytes
(a maior distância do PKWare DCL) fica na memória. Os fluxos de teste são fabricados aqui: o compressor
guloso abaixo usa repetições de verdade (comprimento e distância), para que a cópia atravesse a
fronteira entre dois pedaços. Nada vai à internet e nenhum dado real entra.
"""

import random
import struct

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from base import dbc
from tests.test_base_dbc import (
    VETOR_DO_BLAST,
    _bits_do_codigo,
    comprimir_so_com_literais,
    montar_dbc,
)

_DICIONARIO = 6  # 6 bits baixos na distância: alcance de 4.096 bytes
_MENOR_REPETICAO = 3
_MAIOR_REPETICAO = 518  # 519 é o marcador de fim
_CANDIDATAS = (
    16  # quantas posições anteriores do mesmo trigrama o compressor de teste tenta
)


def _numero(valor: int, quantos: int) -> list[int]:
    """Os `quantos` bits de `valor`, do menor para o maior (como o `_Bits.ler` lê)."""
    return [(valor >> i) & 1 for i in range(quantos)]


def _bits_do_comprimento(comprimento: int) -> list[int]:
    for simbolo in range(len(dbc._BASE_DO_COMPRIMENTO) - 1, -1, -1):
        base = dbc._BASE_DO_COMPRIMENTO[simbolo]
        extras = dbc._BITS_EXTRAS[simbolo]
        if base <= comprimento < base + (1 << extras):
            return _bits_do_codigo(dbc._CODIGO_COMPRIMENTO, simbolo) + _numero(
                comprimento - base, extras
            )
    raise AssertionError(f"comprimento sem símbolo: {comprimento}")


def _bits_da_distancia(distancia: int) -> list[int]:
    alta, baixa = divmod(distancia - 1, 1 << _DICIONARIO)
    return _bits_do_codigo(dbc._CODIGO_DISTANCIA, alta) + _numero(baixa, _DICIONARIO)


def _maior_repeticao(
    dados: bytes, posicao: int, candidatas: list[int] | None = None
) -> tuple[int, int]:
    """(comprimento, distância) da maior repetição que começa em `posicao` (sobreposição vale)."""
    melhor = (0, 0)
    if candidatas is None:
        candidatas = list(range(max(0, posicao - dbc._JANELA), posicao))
    for anterior in reversed(candidatas):
        distancia = posicao - anterior
        if distancia > dbc._JANELA:
            break
        comprimento = 0
        while (
            posicao + comprimento < len(dados)
            and comprimento < _MAIOR_REPETICAO
            and dados[posicao + comprimento] == dados[posicao + comprimento - distancia]
        ):
            comprimento += 1
        if comprimento > melhor[0]:
            melhor = (comprimento, distancia)
    return melhor


def comprimir_com_repeticoes(dados: bytes) -> bytes:
    """Fluxo PKWare válido, guloso: repetição de 3 ou mais bytes vira (comprimento, distância)."""
    bits: list[int] = []
    vistas: dict[
        bytes, list[int]
    ] = {}  # trigrama -> posições onde começou (busca rápida)

    guardadas = 0

    def guardar(ate: int) -> None:
        nonlocal guardadas
        for inicio in range(guardadas, ate):
            vistas.setdefault(dados[inicio : inicio + 3], []).append(inicio)
        guardadas = ate

    posicao = 0
    while posicao < len(dados):
        candidatas = vistas.get(dados[posicao : posicao + 3], [])[-_CANDIDATAS:]
        comprimento, distancia = _maior_repeticao(dados, posicao, candidatas)
        if comprimento >= _MENOR_REPETICAO:
            bits += (
                [1] + _bits_do_comprimento(comprimento) + _bits_da_distancia(distancia)
            )
            posicao += comprimento
        else:
            bits += [0] + _numero(dados[posicao], 8)
            posicao += 1
        guardar(posicao)
    bits += [1] + _bits_do_codigo(dbc._CODIGO_COMPRIMENTO, 15) + [1] * 8
    bits += [0] * (-len(bits) % 8)
    corpo = bytes(
        sum(bits[i + j] << j for j in range(8)) for i in range(0, len(bits), 8)
    )
    return bytes([0, _DICIONARIO]) + corpo


def _juntar(dados: bytes, tamanho_do_pedaco: int) -> bytes:
    return b"".join(dbc.descomprimir_em_pedacos(dados, tamanho_do_pedaco))


class TestCompressorDeTeste:
    def test_repeticoes_viram_copias(self):
        dados = b"abcabcabcabc" * 50
        comprimido = comprimir_com_repeticoes(dados)
        assert len(comprimido) < len(dados) // 4
        assert dbc.descomprimir_pkware(comprimido) == dados

    def test_distancia_maxima_da_janela(self):
        bloco = random.Random(36).randbytes(
            dbc._JANELA
        )  # sem período: só a cópia de 4.096 casa
        dados = bloco + bloco[:100]
        assert _maior_repeticao(dados, dbc._JANELA)[1] == dbc._JANELA
        assert dbc.descomprimir_pkware(comprimir_com_repeticoes(dados)) == dados


class TestDescompressaoEmPedacos:
    def test_vetor_do_blast_em_pedacos_de_um_byte(self):
        assert _juntar(VETOR_DO_BLAST, 1) == b"AIAIAIAIAIAIA"

    def test_pedacos_respeitam_o_tamanho(self):
        dados = bytes(range(256)) * 40
        pedacos = list(
            dbc.descomprimir_em_pedacos(comprimir_com_repeticoes(dados), 1000)
        )
        assert b"".join(pedacos) == dados
        assert all(len(p) <= 1000 + dbc._JANELA for p in pedacos)
        assert len(pedacos) > 1

    def test_copia_atravessa_a_fronteira_dos_pedacos(self):
        bloco = bytes((i * 31) % 256 for i in range(3000))
        dados = bloco + bloco + bloco
        comprimido = comprimir_com_repeticoes(dados)
        for tamanho in (1, 7, 512, 4096, 10_000):
            assert _juntar(comprimido, tamanho) == dados

    def test_inteiro_igual_aos_pedacos(self):
        dados = bytes(range(256)) * 3
        comprimido = comprimir_so_com_literais(dados)
        assert dbc.descomprimir_pkware(comprimido) == _juntar(comprimido, 5) == dados

    def test_fluxo_cortado_e_erro_mesmo_em_pedacos(self):
        with pytest.raises(dbc.DbcInvalido):
            _juntar(VETOR_DO_BLAST[:-2], 1)

    def test_referencia_antes_do_comeco_e_erro(self):
        bits = [1] + _bits_do_comprimento(3) + _bits_da_distancia(5)
        bits += [0] * (-len(bits) % 8)
        corpo = bytes(
            sum(bits[i + j] << j for j in range(8)) for i in range(0, len(bits), 8)
        )
        with pytest.raises(dbc.DbcInvalido, match="antes do começo"):
            _juntar(bytes([0, _DICIONARIO]) + corpo, 1)

    def test_pedaco_sem_tamanho_e_erro(self):
        with pytest.raises(ValueError):
            _juntar(VETOR_DO_BLAST, 0)

    @settings(max_examples=40, deadline=None)
    @given(
        st.lists(
            st.sampled_from([b"ab", b"xyz", b"\x00", b"SUS", bytes(range(20))]),
            max_size=300,
        ),
        st.integers(min_value=1, max_value=600),
    )
    def test_propriedade_pedacos_nao_mudam_o_resultado(self, partes, tamanho):
        dados = b"".join(partes)
        comprimido = comprimir_com_repeticoes(dados)
        assert (
            _juntar(comprimido, tamanho) == dbc.descomprimir_pkware(comprimido) == dados
        )


CAMPOS = [("CNES", 7), ("VALOR", 5)]


class TestRegistrosEmFluxo:
    def test_ler_dbc_com_registros_em_pedacos_pequenos(self):
        registros = [[f"{i:07d}", str(i % 97)] for i in range(500)]
        conteudo = montar_dbc(CAMPOS, registros)
        lidos = list(dbc.ler_dbc(conteudo, ("CNES", "VALOR"), tamanho_do_pedaco=3))
        assert lidos == [{"CNES": c, "VALOR": v} for c, v in registros]

    def test_mesmo_resultado_em_qualquer_tamanho_de_pedaco(self):
        registros = [[f"{i:07d}", "1"] for i in range(40)]
        conteudo = montar_dbc(CAMPOS, registros)
        esperado = list(dbc.ler_dbc(conteudo, ("CNES",)))
        for tamanho in (1, 8, 13, 1 << 16):
            assert (
                list(dbc.ler_dbc(conteudo, ("CNES",), tamanho_do_pedaco=tamanho))
                == esperado
            )

    def test_registro_apagado_e_ignorado(self):
        conteudo = bytearray(montar_dbc(CAMPOS, [["1111111", "1"], ["2222222", "2"]]))
        tamanho_do_cabecalho = struct.unpack_from("<H", conteudo, 8)[0]
        corpo = dbc.descomprimir_pkware(bytes(conteudo[tamanho_do_cabecalho + 4 :]))
        corpo = b"*" + corpo[1:]
        novo = bytes(conteudo[: tamanho_do_cabecalho + 4]) + comprimir_so_com_literais(
            corpo
        )
        assert [r["CNES"] for r in dbc.ler_dbc(novo, ("CNES",))] == ["2222222"]

    def test_para_no_numero_de_registros_do_cabecalho(self):
        """O DBF termina com 0x1A depois do último registro: não vira um registro a mais."""
        conteudo = bytearray(montar_dbc(CAMPOS, [["1111111", "1"]]))
        tamanho_do_cabecalho = struct.unpack_from("<H", conteudo, 8)[0]
        corpo = (
            dbc.descomprimir_pkware(bytes(conteudo[tamanho_do_cabecalho + 4 :]))
            + b"\x1a"
        )
        novo = bytes(conteudo[: tamanho_do_cabecalho + 4]) + comprimir_so_com_literais(
            corpo
        )
        assert list(dbc.ler_dbc(novo, ("CNES",))) == [{"CNES": "1111111"}]

    def test_menos_registros_que_o_prometido_e_erro_em_fluxo(self):
        conteudo = bytearray(montar_dbc(CAMPOS, [["1111111", "1"]]))
        struct.pack_into("<I", conteudo, 4, 3)
        with pytest.raises(dbc.DbcInvalido, match="menos registros"):
            list(dbc.ler_dbc(bytes(conteudo), ("CNES",), tamanho_do_pedaco=2))
