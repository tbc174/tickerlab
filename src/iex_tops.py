"""Leitor dos negócios do IEX HIST (feed TOPS 1.6) para montar barras intradiárias.

A bolsa IEX publica de graça, no dia seguinte, a gravação dos pacotes do seu feed TOPS
(https://iextrading.com/trading/market-data/). Os termos permitem exibir os dados, inclusive em
produto pago, desde que com a frase de `ATRIBUICAO` (ADR 0019 do projeto).

O arquivo é um pcapng comprimido com gzip (~9 GB por dia). Dentro de cada pacote UDP vem um
cabeçalho IEX-TP e várias mensagens; aqui só interessam os negócios ("Trade Report", `T`) e os
cancelamentos de negócio ("Trade Break", `B`). As cotações (`Q`), que são a maior parte do arquivo,
são puladas sem ser decodificadas.

Limite que a tela precisa dizer: são só os negócios feitos **na IEX**, uma parte pequena do volume
dos EUA. O preço das ações líquidas acompanha o mercado; o volume não.
"""

import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

import pandas as pd

ATRIBUICAO = (
    "Data provided for free by IEX. By accessing or using IEX Historical Data, "
    "you agree to the IEX Historical Data Terms of Use."
)

# pcapng: blocos com tipo e tamanho total (https://www.ietf.org/archive/id/draft-ietf-opsawg-pcapng-02.html)
BLOCO_PACOTE_APRIMORADO = 6
CABECALHO_DO_BLOCO = 8
INICIO_DOS_DADOS_DO_PACOTE = 28
POSICAO_DO_TAMANHO_CAPTURADO = 20

# Ethernet (14 bytes) + IPv4 (tamanho no campo IHL, em palavras de 4 bytes) + UDP (8 bytes)
TAMANHO_ETHERNET = 14
TAMANHO_UDP = 8
TAMANHO_CABECALHO_IEX_TP = 40
POSICAO_QUANTIDADE_DE_MENSAGENS = 14

NEGOCIO = 0x54  # "T", Trade Report
CANCELAMENTO = 0x42  # "B", Trade Break
TIPOS_QUE_INTERESSAM = (NEGOCIO, CANCELAMENTO)
FORMATO_DO_NEGOCIO = struct.Struct("<BBq8sIqq")  # 38 bytes, igual para T e B

# Indicadores de condição de venda (sale condition flags) do TOPS 1.6
FORA_DO_PREGAO_REGULAR = 0x40  # pré-abertura ou pós-fechamento
LOTE_FRACIONARIO = 0x20

PRECO_POR_UNIDADE = 10_000  # o preço vem em inteiros de 1/10.000 de dólar

TAMANHO_DA_LEITURA = 16 * 1024 * 1024


@dataclass
class NegociosDoDia:
    """Negócios selecionados de um dia, em colunas (cabe na memória para ~500 ações)."""

    instante_ns: list[int] = field(default_factory=list)
    simbolo: list[str] = field(default_factory=list)
    preco: list[float] = field(default_factory=list)
    quantidade: list[int] = field(default_factory=list)
    lote_fracionario: list[bool] = field(default_factory=list)
    id_do_negocio: list[int] = field(default_factory=list)
    cancelados: set[int] = field(default_factory=set)
    pacotes_lidos: int = 0
    negocios_vistos: int = 0


def pacotes_do_pcapng(fluxo: BinaryIO) -> Iterator[memoryview]:
    """Os dados de cada pacote (Ethernet em diante) de um pcapng já descomprimido.

    Lê em pedaços grandes porque ler bloco a bloco de um gzip é muito mais lento.
    """
    sobra = b""
    while True:
        lido = fluxo.read(TAMANHO_DA_LEITURA)
        if not lido:
            return
        dados = sobra + lido
        visao = memoryview(dados)
        posicao = 0
        while posicao + CABECALHO_DO_BLOCO <= len(dados):
            tipo, total = struct.unpack_from("<II", dados, posicao)
            if posicao + total > len(dados):
                break
            if tipo == BLOCO_PACOTE_APRIMORADO:
                capturado = struct.unpack_from(
                    "<I", dados, posicao + POSICAO_DO_TAMANHO_CAPTURADO
                )[0]
                inicio = posicao + INICIO_DOS_DADOS_DO_PACOTE
                yield visao[inicio : inicio + capturado]
            posicao += total
        sobra = dados[posicao:]


def mensagens_iex_tp(pacote: memoryview) -> Iterator[memoryview]:
    """As mensagens IEX-TP dentro de um pacote Ethernet/IPv4/UDP."""
    tamanho_ip = (pacote[TAMANHO_ETHERNET] & 0x0F) * 4
    inicio = TAMANHO_ETHERNET + tamanho_ip + TAMANHO_UDP
    if len(pacote) < inicio + TAMANHO_CABECALHO_IEX_TP:
        return
    quantidade = struct.unpack_from(
        "<H", pacote, inicio + POSICAO_QUANTIDADE_DE_MENSAGENS
    )[0]
    posicao = inicio + TAMANHO_CABECALHO_IEX_TP
    for _ in range(quantidade):
        tamanho = pacote[posicao] | (pacote[posicao + 1] << 8)
        yield pacote[posicao + 2 : posicao + 2 + tamanho]
        posicao += 2 + tamanho


def coletar_negocios(
    pacotes: Iterable[memoryview], simbolos: set[str] | None = None
) -> NegociosDoDia:
    """Os negócios e cancelamentos de um dia, só dos `simbolos` pedidos (None = todos).

    Os símbolos seguem a IEX: "BRK.B", não o "BRK-B" do Yahoo.
    """
    dia = NegociosDoDia()
    for pacote in pacotes:
        dia.pacotes_lidos += 1
        for mensagem in mensagens_iex_tp(pacote):
            tipo = mensagem[0]
            if tipo not in TIPOS_QUE_INTERESSAM:
                continue
            _anotar_negocio(dia, mensagem, simbolos)
    return dia


def _anotar_negocio(
    dia: NegociosDoDia, mensagem: memoryview, simbolos: set[str] | None
) -> None:
    tipo, indicadores, instante, simbolo_bruto, quantidade, preco, id_negocio = (
        FORMATO_DO_NEGOCIO.unpack(mensagem)
    )
    simbolo = bytes(simbolo_bruto).decode("ascii").rstrip()
    if simbolos is not None and simbolo not in simbolos:
        return
    if tipo == CANCELAMENTO:
        dia.cancelados.add(id_negocio)
        return
    dia.negocios_vistos += 1
    if indicadores & FORA_DO_PREGAO_REGULAR:
        return
    dia.instante_ns.append(instante)
    dia.simbolo.append(simbolo)
    dia.preco.append(preco / PRECO_POR_UNIDADE)
    dia.quantidade.append(quantidade)
    dia.lote_fracionario.append(bool(indicadores & LOTE_FRACIONARIO))
    dia.id_do_negocio.append(id_negocio)


def tabela_de_negocios(dia: NegociosDoDia) -> pd.DataFrame:
    """Os negócios do pregão regular em tabela, já sem os cancelados (Trade Break).

    Colunas: instante (UTC), simbolo, preco (US$), quantidade, lote_fracionario.
    """
    tabela = pd.DataFrame(
        {
            "instante": pd.to_datetime(dia.instante_ns, unit="ns", utc=True),
            "simbolo": dia.simbolo,
            "preco": dia.preco,
            "quantidade": dia.quantidade,
            "lote_fracionario": dia.lote_fracionario,
            "id_do_negocio": dia.id_do_negocio,
        }
    )
    valido = ~tabela["id_do_negocio"].isin(dia.cancelados)
    return tabela[valido].drop(columns="id_do_negocio").reset_index(drop=True)
