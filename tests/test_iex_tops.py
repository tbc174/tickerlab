"""Leitor do IEX HIST (TOPS 1.6) com pacotes montados byte a byte, sem internet."""

import io
import struct
import threading

import pandas as pd
import pytest

from src import iex_tops

NOVE_E_MEIA_NY_EM_NS = pd.Timestamp("2026-10-09 09:30:05", tz="America/New_York").value


def mensagem_de_negocio(
    simbolo: str,
    preco: float,
    quantidade: int = 100,
    indicadores: int = 0,
    id_do_negocio: int = 1,
    tipo: int = iex_tops.NEGOCIO,
    instante: int = NOVE_E_MEIA_NY_EM_NS,
) -> bytes:
    return iex_tops.FORMATO_DO_NEGOCIO.pack(
        tipo,
        indicadores,
        instante,
        simbolo.ljust(8).encode("ascii"),
        quantidade,
        round(preco * iex_tops.PRECO_POR_UNIDADE),
        id_do_negocio,
    )


def mensagem_de_cotacao(simbolo: str) -> bytes:
    # Quote Update: 42 bytes; o leitor precisa pulá-la sem decodificar
    return b"Q" + b"\x00" * 9 + simbolo.ljust(8).encode("ascii") + b"\x00" * 24


def pacote(mensagens: list[bytes]) -> bytes:
    ethernet = b"\x00" * 12 + b"\x08\x00"
    ipv4 = b"\x45" + b"\x00" * 19
    udp = b"\x00" * 8
    corpo = b"".join(struct.pack("<H", len(m)) + m for m in mensagens)
    cabecalho_iex = struct.pack(
        "<BBHIIHHqqq", 1, 0, 0x8003, 1, 1, len(corpo), len(mensagens), 0, 0, 0
    )
    return ethernet + ipv4 + udp + cabecalho_iex + corpo


def bloco(tipo: int, corpo: bytes) -> bytes:
    corpo += b"\x00" * (-len(corpo) % 4)
    total = len(corpo) + 12
    return struct.pack("<II", tipo, total) + corpo + struct.pack("<I", total)


def pcapng(pacotes: list[bytes]) -> bytes:
    cabecalho_da_secao = bloco(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1))
    interface = bloco(1, struct.pack("<HHI", 1, 0, 65535))
    pacotes_em_blocos = [
        bloco(6, struct.pack("<IIIII", 0, 0, 0, len(p), len(p)) + p) for p in pacotes
    ]
    return cabecalho_da_secao + interface + b"".join(pacotes_em_blocos)


def ler(arquivo: bytes, simbolos: set[str] | None = None) -> iex_tops.NegociosDoDia:
    return iex_tops.coletar_negocios(
        iex_tops.pacotes_do_pcapng(io.BytesIO(arquivo)), simbolos
    )


def test_le_negocio_e_pula_cotacao():
    arquivo = pcapng(
        [pacote([mensagem_de_cotacao("AAPL"), mensagem_de_negocio("AAPL", 227.5, 30)])]
    )
    dia = ler(arquivo)
    assert dia.simbolo == ["AAPL"]
    assert dia.preco == [227.5]
    assert dia.quantidade == [30]
    assert dia.instante_ns == [NOVE_E_MEIA_NY_EM_NS]


def test_filtra_pelos_simbolos_pedidos():
    arquivo = pcapng(
        [pacote([mensagem_de_negocio("AAPL", 1.0), mensagem_de_negocio("ONDS", 2.0)])]
    )
    assert ler(arquivo, {"ONDS"}).simbolo == ["ONDS"]


def test_negocio_fora_do_pregao_regular_fica_de_fora_mas_e_contado():
    fora = mensagem_de_negocio("AAPL", 1.0, indicadores=iex_tops.FORA_DO_PREGAO_REGULAR)
    dia = ler(pcapng([pacote([fora])]))
    assert dia.simbolo == []
    assert dia.negocios_vistos == 1


def test_lote_fracionario_entra_marcado():
    fracionario = mensagem_de_negocio(
        "AAPL", 1.0, 3, indicadores=iex_tops.LOTE_FRACIONARIO
    )
    assert ler(pcapng([pacote([fracionario])])).lote_fracionario == [True]


def test_negocio_cancelado_sai_da_tabela():
    arquivo = pcapng(
        [
            pacote([mensagem_de_negocio("AAPL", 1.0, id_do_negocio=7)]),
            pacote([mensagem_de_negocio("AAPL", 2.0, id_do_negocio=8)]),
            pacote(
                [
                    mensagem_de_negocio(
                        "AAPL", 1.0, id_do_negocio=7, tipo=iex_tops.CANCELAMENTO
                    )
                ]
            ),
        ]
    )
    tabela = iex_tops.tabela_de_negocios(ler(arquivo))
    assert tabela["preco"].tolist() == [2.0]


def test_bloco_partido_entre_duas_leituras_nao_se_perde(monkeypatch):
    # o arquivo real é lido em pedaços de 16 MB; um bloco sempre acaba cortado no meio
    monkeypatch.setattr(iex_tops, "TAMANHO_DA_LEITURA", 37)
    pacotes = [
        pacote([mensagem_de_negocio("AAPL", float(i), id_do_negocio=i)])
        for i in range(1, 6)
    ]
    dia = ler(pcapng(pacotes))
    assert dia.preco == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert dia.pacotes_lidos == 5


def test_atribuicao_tem_a_frase_exigida_pelos_termos_da_iex():
    assert iex_tops.ATRIBUICAO.startswith("Data provided for free by IEX.")


# --- arquivos malformados (A-03 e A-04 do Master v3): falham rápido, sem resultado parcial ---


def _com_limite(funcao, segundos=5):
    """Roda `funcao` numa thread: um laço infinito vira falha do teste, não um CI travado."""
    resultado = {}

    def alvo():
        try:
            resultado["valor"] = funcao()
        except Exception as erro:  # noqa: BLE001 - o teste confere o tipo logo abaixo
            resultado["erro"] = erro

    thread = threading.Thread(target=alvo, daemon=True)
    thread.start()
    thread.join(segundos)
    assert not thread.is_alive(), f"não terminou em {segundos} s (laço infinito)"
    return resultado


def _deve_recusar(arquivo: bytes):
    resultado = _com_limite(lambda: ler(arquivo))
    assert isinstance(resultado.get("erro"), iex_tops.ArquivoIexInvalidoError), (
        resultado
    )


def _pacote_cru(corpo_iex: bytes, quantidade: int) -> bytes:
    cabecalho = bytearray(14 + 20 + 8 + 40)
    cabecalho[14] = 0x45
    struct.pack_into("<H", cabecalho, 14 + 20 + 8 + 14, quantidade)
    return bytes(cabecalho) + corpo_iex


@pytest.mark.parametrize(
    "arquivo",
    [
        pytest.param(struct.pack("<II", 6, 0), id="bloco de pacote com tamanho 0"),
        pytest.param(struct.pack("<II", 0, 0), id="bloco de outro tipo com tamanho 0"),
        pytest.param(
            struct.pack("<II", 6, 0) + b"\0" * 32, id="tamanho 0 seguido de dados"
        ),
        pytest.param(
            struct.pack("<II", 6, 4) + b"x" * 8, id="tamanho menor que o cabeçalho"
        ),
        pytest.param(
            struct.pack("<II", 1, 14) + b"x" * 6, id="tamanho que não é múltiplo de 4"
        ),
        pytest.param(
            struct.pack("<II", 6, 1 << 30) + b"x" * 64, id="tamanho absurdo (1 GiB)"
        ),
    ],
)
def test_bloco_com_tamanho_impossivel_e_recusado(arquivo):
    _deve_recusar(arquivo)


def test_arquivo_que_acaba_no_meio_de_um_bloco_e_recusado():
    _deve_recusar(struct.pack("<II", 6, 64) + b"x" * 20)


def test_tamanho_capturado_maior_que_o_bloco_e_recusado():
    bloco_mentiroso = struct.pack("<II", 6, 32) + b"\0" * 12 + struct.pack("<I", 1000)
    bloco_mentiroso += b"\0" * 8
    _deve_recusar(bloco_mentiroso + bloco(1, b"ZZZZ"))


@pytest.mark.parametrize(
    ("corpo", "quantidade"),
    [
        pytest.param(b"", 3, id="mais mensagens do que cabem no pacote"),
        pytest.param(struct.pack("<H", 0), 1, id="mensagem de tamanho 0"),
        pytest.param(
            struct.pack("<H", 10) + b"T" + b"\0" * 9, 1, id="negócio com 10 bytes"
        ),
        pytest.param(
            struct.pack("<H", 50) + b"T" + b"\0" * 9,
            1,
            id="mensagem maior que o pacote",
        ),
    ],
)
def test_pacote_iex_malformado_e_recusado(corpo, quantidade):
    _deve_recusar(pcapng([_pacote_cru(corpo, quantidade)]))


def test_simbolo_que_nao_e_ascii_e_recusado():
    negocio = struct.pack(
        "<BBq8sIqq", iex_tops.NEGOCIO, 0, 1, b"\xff" * 8, 1, 10_000, 1
    )
    _deve_recusar(pcapng([pacote([negocio])]))


def test_arquivo_bom_continua_sendo_lido_igual():
    arquivo = pcapng([pacote([mensagem_de_negocio("AAPL", 227.5, 30)])])
    resultado = _com_limite(lambda: ler(arquivo))
    assert resultado["valor"].preco == [227.5]
