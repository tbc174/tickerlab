"""Leitor do IEX HIST (TOPS 1.6) com pacotes montados byte a byte, sem internet."""

import io
import struct

import pandas as pd

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
