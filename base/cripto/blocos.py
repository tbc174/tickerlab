"""Métricas de um bloco do Bitcoin (base de cripto, série 1, PR 1).

Recebe o bloco como o Bitcoin Core devolve em `getblock <hash> 3` (JSON, valores em BTC). Nesse
nível de detalhe, cada entrada traz o `prevout`: o valor e a altura do bloco onde a moeda gasta foi
criada. Com isso dá para calcular taxas e dias-moeda destruídos sem índice extra no nó.

Tudo é contado em **satoshis** (inteiros; 1 BTC = 100 milhões): somar floats em BTC erra no oitavo
decimal (0,1 + 0,2 = 0,30000000000000004).

O que cada métrica mede:
- **taxas_total:** o que as transações comuns pagaram ao minerador (entradas menos saídas). Não usa
  a coinbase, porque há mineradores que reclamaram menos do que podiam.
- **taxa_mediana_por_vbyte:** a taxa típica, em satoshis por byte virtual; mede o quanto o espaço
  no bloco estava disputado. Sem transação comum, não existe (None).
- **valor_movimentado:** soma das saídas das transações comuns. Inclui o troco que volta para o
  próprio dono, então mede "dinheiro que passou pela rede", não "dinheiro que trocou de mãos".
- **dias_moeda_destruidos:** cada moeda gasta vezes os dias que ela ficou parada (BTC-dias). Sobe
  quando moedas antigas se mexem.
- **emissao:** moedas novas que a regra do protocolo permite no bloco (metade a cada 210 mil blocos).

O **histograma de idade** guarda, para cada altura, quanto do que foi criado ali ainda não foi gasto.
Atualizado bloco a bloco, dá "quanto do Bitcoin está parado há mais de um ano" sem guardar o
conjunto inteiro de moedas não gastas.
"""

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np

SATOSHIS_POR_BTC = 100_000_000
EMISSAO_INICIAL = 50 * SATOSHIS_POR_BTC
BLOCOS_POR_HALVING = 210_000
# depois de 64 divisões por 2, a emissão em satoshis vira zero (o protocolo para aí)
ULTIMO_HALVING = 64
SEGUNDOS_POR_DIA = 86_400
# saídas que ninguém consegue gastar não entram nas moedas não gastas. O Bitcoin Core (IsUnspendable)
# usa o script, não o tipo: começa em OP_RETURN (0x6a), ou passa de 10.000 bytes. O tipo "nulldata"
# cobre só o OP_RETURN bem formado; um OP_RETURN com "push" quebrado vira "nonstandard" (bloco 360.603).
TIPOS_IMPOSSIVEIS_DE_GASTAR = frozenset({"nulldata"})
PREFIXO_DO_OP_RETURN = "6a"
TAMANHO_MAXIMO_DO_SCRIPT = 10_000
# Regras do conjunto de moedas não gastas do Bitcoin Core que o histograma segue, para a soma bater
# com o `gettxoutsetinfo` do nó: a coinbase do bloco 0 nunca entrou no conjunto, e em 2010 duas
# coinbases repetiram a transação de uma anterior ainda não gasta e a apagaram (BIP30).
ALTURA_DA_GENESE = 0
# altura da coinbase repetida: altura da que ela apagou
COINBASES_APAGADAS_PELA_BIP30 = {91_842: 91_812, 91_880: 91_722}
# o histograma cresce de 100 mil em 100 mil alturas (~2 anos de blocos), para não copiar a cada bloco
FOLGA_DO_HISTOGRAMA = 100_000

HoraPorAltura = Callable[[int], int]


@dataclass(frozen=True)
class MetricasDoBloco:
    """O resumo de um bloco que vai para o acervo (valores em satoshis, salvo dito o contrário)."""

    altura: int
    hash: str
    hora: datetime  # hora que o minerador escreveu no bloco, em UTC
    # mediana das horas dos 11 blocos anteriores: só cresce, ao contrário da `hora`
    hora_mediana: datetime
    n_transacoes: int
    taxas_total: int
    taxa_mediana_por_vbyte: float | None
    valor_movimentado: int
    dias_moeda_destruidos: float  # em BTC-dias
    emissao: int
    # quanto custa achar um bloco (1 = a dificuldade inicial de 2009)
    dificuldade: float


def para_satoshis(valor_btc: float | Decimal) -> int:
    """O valor em BTC (como vem do JSON do nó) convertido em satoshis, sem erro de arredondamento."""
    return int((Decimal(str(valor_btc)) * SATOSHIS_POR_BTC).to_integral_value())


def emissao(altura: int) -> int:
    """Moedas novas permitidas no bloco desta altura, em satoshis."""
    halvings = altura // BLOCOS_POR_HALVING
    if halvings >= ULTIMO_HALVING:
        return 0
    return EMISSAO_INICIAL >> halvings


def metricas_do_bloco(bloco: dict, hora_por_altura: HoraPorAltura) -> MetricasDoBloco:
    """As métricas de um bloco (`getblock` verbosity 3).

    `hora_por_altura` devolve a hora (segundos Unix) do bloco de uma altura anterior; serve para
    saber há quanto tempo cada moeda gasta estava parada.
    """
    comuns = [tx for tx in bloco["tx"] if not _e_coinbase(tx)]
    taxas = [_taxa(tx) for tx in comuns]
    return MetricasDoBloco(
        altura=bloco["height"],
        hash=bloco["hash"],
        hora=datetime.fromtimestamp(bloco["time"], tz=UTC),
        hora_mediana=datetime.fromtimestamp(bloco["mediantime"], tz=UTC),
        n_transacoes=len(bloco["tx"]),
        taxas_total=sum(taxas),
        taxa_mediana_por_vbyte=_mediana_por_vbyte(comuns, taxas),
        valor_movimentado=sum(_soma_das_saidas(tx) for tx in comuns),
        dias_moeda_destruidos=_dias_moeda_destruidos(
            comuns, bloco["time"], hora_por_altura
        ),
        emissao=emissao(bloco["height"]),
        dificuldade=float(bloco["difficulty"]),
    )


def atualizar_histograma(histograma: np.ndarray, bloco: dict) -> np.ndarray:
    """Soma as saídas do bloco na altura dele e tira as moedas gastas da altura de onde vieram.

    Muda o array **no lugar** (copiar ~1 milhão de números a cada bloco deixaria a leitura da cadeia
    inteira lenta demais) e o devolve, ou devolve um maior, se a altura passou do tamanho.
    As transações são lidas na ordem do bloco, então uma moeda criada e gasta no mesmo bloco entra
    antes de sair. Gastar mais do que existe numa altura é sinal de bloco fora de ordem: para com
    ValueError, e o histograma fica pela metade (descarte-o e recomece do último mês gravado).
    """
    altura = bloco["height"]
    if altura >= len(histograma):
        histograma = np.concatenate(
            [
                histograma,
                np.zeros(altura - len(histograma) + FOLGA_DO_HISTOGRAMA, np.int64),
            ]
        )
    if altura == ALTURA_DA_GENESE:
        return histograma
    if altura in COINBASES_APAGADAS_PELA_BIP30:
        coinbase = next(tx for tx in bloco["tx"] if _e_coinbase(tx))
        histograma[COINBASES_APAGADAS_PELA_BIP30[altura]] -= _soma_das_saidas(coinbase)
    for tx in bloco["tx"]:
        histograma[altura] += sum(
            para_satoshis(saida["value"])
            for saida in tx["vout"]
            if _pode_ser_gasta(saida)
        )
        for entrada in _entradas_gastas(tx):
            _tirar_do_histograma(histograma, entrada["prevout"])
    return histograma


def _tirar_do_histograma(histograma: np.ndarray, prevout: dict) -> None:
    origem = prevout["height"]
    valor = para_satoshis(prevout["value"])
    if histograma[origem] < valor:
        raise ValueError(
            f"Moeda gasta maior do que o que resta na altura {origem}: "
            "bloco lido fora de ordem ou histograma de outra cadeia."
        )
    histograma[origem] -= valor


def _e_coinbase(tx: dict) -> bool:
    return any("coinbase" in entrada for entrada in tx["vin"])


def _entradas_gastas(tx: dict) -> list[dict]:
    return [entrada for entrada in tx["vin"] if "prevout" in entrada]


def _pode_ser_gasta(saida: dict) -> bool:
    script = saida["scriptPubKey"]
    if script.get("type") in TIPOS_IMPOSSIVEIS_DE_GASTAR:
        return False
    codigo = script.get("hex", "")
    return not (
        codigo.startswith(PREFIXO_DO_OP_RETURN)
        or len(codigo) // 2 > TAMANHO_MAXIMO_DO_SCRIPT
    )


def _soma_das_saidas(tx: dict) -> int:
    return sum(para_satoshis(saida["value"]) for saida in tx["vout"])


def _taxa(tx: dict) -> int:
    entradas = sum(para_satoshis(e["prevout"]["value"]) for e in _entradas_gastas(tx))
    return entradas - _soma_das_saidas(tx)


def _mediana_por_vbyte(comuns: list[dict], taxas: list[int]) -> float | None:
    if not comuns:
        return None
    return statistics.median(
        taxa / tx["vsize"] for tx, taxa in zip(comuns, taxas, strict=True)
    )


def _dias_moeda_destruidos(
    comuns: list[dict], hora_do_bloco: int, hora_por_altura: HoraPorAltura
) -> float:
    total = 0.0
    for tx in comuns:
        for entrada in _entradas_gastas(tx):
            prevout = entrada["prevout"]
            dias_parada = (
                hora_do_bloco - hora_por_altura(prevout["height"])
            ) / SEGUNDOS_POR_DIA
            total += para_satoshis(prevout["value"]) / SATOSHIS_POR_BTC * dias_parada
    return total
