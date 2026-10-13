"""Métricas de um bloco do Bitcoin (base de cripto, série 1, PR 1).

Os blocos são montados à mão no formato do `getblock <hash> 3` do Bitcoin Core (valores em BTC,
cada entrada gasta com o `prevout`: valor e altura de onde a moeda veio). As contas esperadas são
feitas no papel, no comentário de cada teste.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from base.cripto.blocos import (
    SATOSHIS_POR_BTC,
    atualizar_histograma,
    emissao,
    metricas_do_bloco,
    para_satoshis,
)

PASTA = Path(__file__).parent / "arquivos" / "cripto" / "blocos"
HORA_DO_BLOCO = 1_700_000_000  # segundos Unix (14/11/2023)
UM_DIA = 86_400


def _entrada(valor_btc: float, altura: int) -> dict:
    return {
        "txid": "aa" * 32,
        "vout": 0,
        "prevout": {"value": valor_btc, "height": altura},
    }


def _saida(valor_btc: float, tipo: str = "witness_v0_keyhash") -> dict:
    return {"value": valor_btc, "scriptPubKey": {"type": tipo}}


def _coinbase(*valores_btc: float) -> dict:
    return {
        "txid": "cb" * 32,
        "vin": [{"coinbase": "03a0bb0d"}],
        "vout": [_saida(v) for v in valores_btc],
        "vsize": 150,
    }


def _transacao(entradas: list[dict], saidas: list[dict], vsize: int) -> dict:
    return {"txid": "tx" * 32, "vin": entradas, "vout": saidas, "vsize": vsize}


def _bloco(altura: int, transacoes: list[dict], hora: int = HORA_DO_BLOCO) -> dict:
    return {
        "hash": "00" * 32,
        "height": altura,
        "time": hora,
        "mediantime": hora - 3_600,
        "difficulty": 1.5,
        "tx": transacoes,
    }


def _hora_fixa(horas: dict[int, int]):
    """`hora_por_altura` dos testes: a hora (segundos Unix) de cada altura de origem."""
    return lambda altura: horas[altura]


def test_para_satoshis_nao_perde_centavo_de_bitcoin():
    # 0,1 + 0,2 em float dá 0,30000000000000004; em satoshis tem de dar exatos 30 milhões
    assert para_satoshis(0.1) + para_satoshis(0.2) == 30_000_000
    assert para_satoshis(0.00000001) == 1
    assert para_satoshis(21_000_000) == 21_000_000 * SATOSHIS_POR_BTC


@pytest.mark.parametrize(
    ("altura", "esperado_btc"),
    [
        (0, 50),
        (209_999, 50),
        (210_000, 25),
        (420_000, 12.5),
        (630_000, 6.25),
        (840_000, 3.125),
        (64 * 210_000, 0),  # depois de 64 halvings a emissão acaba
    ],
)
def test_emissao_por_altura(altura, esperado_btc):
    assert emissao(altura) == para_satoshis(esperado_btc)


def test_taxas_do_bloco_somam_entradas_menos_saidas_sem_a_coinbase():
    # tx1: entra 1,5 e sai 1,4 → taxa 0,1 BTC; tx2: entra 2,0 e sai 1,99 → taxa 0,01 BTC
    bloco = _bloco(
        800_000,
        [
            _coinbase(6.36),
            _transacao(
                [_entrada(1.0, 700_000), _entrada(0.5, 700_000)], [_saida(1.4)], 200
            ),
            _transacao([_entrada(2.0, 790_000)], [_saida(1.0), _saida(0.99)], 100),
        ],
    )
    horas = {
        700_000: HORA_DO_BLOCO - 100 * UM_DIA,
        790_000: HORA_DO_BLOCO - 10 * UM_DIA,
    }

    metricas = metricas_do_bloco(bloco, _hora_fixa(horas))

    assert metricas.taxas_total == para_satoshis(0.11)
    assert metricas.n_transacoes == 3
    # taxas por byte virtual: 10.000.000 / 200 = 50.000 e 1.000.000 / 100 = 10.000 → mediana 30.000
    assert metricas.taxa_mediana_por_vbyte == pytest.approx(30_000)
    # valor movimentado = saídas das transações comuns: 1,4 + 1,0 + 0,99
    assert metricas.valor_movimentado == para_satoshis(3.39)
    assert metricas.emissao == para_satoshis(6.25)


def test_dias_moeda_destruidos():
    # 1,5 BTC parados 100 dias (150) + 2,0 BTC parados 10 dias (20) = 170 BTC-dias
    bloco = _bloco(
        800_000,
        [
            _coinbase(6.25),
            _transacao(
                [_entrada(1.0, 700_000), _entrada(0.5, 700_000)], [_saida(1.5)], 200
            ),
            _transacao([_entrada(2.0, 790_000)], [_saida(2.0)], 100),
        ],
    )
    horas = {
        700_000: HORA_DO_BLOCO - 100 * UM_DIA,
        790_000: HORA_DO_BLOCO - 10 * UM_DIA,
    }

    assert metricas_do_bloco(
        bloco, _hora_fixa(horas)
    ).dias_moeda_destruidos == pytest.approx(170)


def test_bloco_so_com_a_coinbase_tem_taxa_zero_e_sem_mediana():
    metricas = metricas_do_bloco(_bloco(100, [_coinbase(50)]), _hora_fixa({}))

    assert metricas.taxas_total == 0
    assert metricas.taxa_mediana_por_vbyte is None
    assert metricas.valor_movimentado == 0
    assert metricas.dias_moeda_destruidos == 0


def test_hora_do_bloco_em_utc():
    metricas = metricas_do_bloco(_bloco(100, [_coinbase(50)], hora=0), _hora_fixa({}))

    assert metricas.hora == datetime(1970, 1, 1, tzinfo=UTC)


def test_histograma_soma_as_saidas_e_tira_as_gastas_da_altura_de_origem():
    histograma = np.zeros(10, dtype=np.int64)
    histograma[3] = para_satoshis(2.0)
    bloco = _bloco(
        7,
        [
            _coinbase(50),
            _transacao([_entrada(2.0, 3)], [_saida(1.2), _saida(0.7)], 100),
        ],
    )

    histograma = atualizar_histograma(histograma, bloco)

    assert histograma[3] == 0
    assert histograma[7] == para_satoshis(50 + 1.2 + 0.7)


def test_histograma_aceita_moeda_criada_e_gasta_no_mesmo_bloco():
    # a tx2 gasta a saída de 1,0 BTC que a tx1 criou neste mesmo bloco (altura 7)
    histograma = np.zeros(10, dtype=np.int64)
    histograma[3] = para_satoshis(1.0)
    bloco = _bloco(
        7,
        [
            _coinbase(50),
            _transacao([_entrada(1.0, 3)], [_saida(1.0)], 100),
            _transacao([_entrada(1.0, 7)], [_saida(0.9)], 100),
        ],
    )

    histograma = atualizar_histograma(histograma, bloco)

    assert histograma[3] == 0
    assert histograma[7] == para_satoshis(50 + 0.9)


def test_histograma_ignora_saida_impossivel_de_gastar():
    # OP_RETURN ("nulldata") nunca entra no conjunto de moedas não gastas
    bloco = _bloco(5, [_coinbase(50), _transacao([], [_saida(0.1, "nulldata")], 100)])

    histograma = atualizar_histograma(np.zeros(10, dtype=np.int64), bloco)

    assert histograma[5] == para_satoshis(50)


def test_metricas_trazem_dificuldade_e_hora_mediana():
    metricas = metricas_do_bloco(
        _bloco(100, [_coinbase(50)], hora=7_200), _hora_fixa({})
    )

    assert metricas.dificuldade == 1.5
    assert metricas.hora_mediana == datetime(1970, 1, 1, 1, tzinfo=UTC)


def test_histograma_deixa_de_fora_a_coinbase_do_bloco_zero():
    # os 50 BTC do bloco 0 nunca entraram no conjunto de moedas não gastas do Bitcoin Core
    histograma = atualizar_histograma(
        np.zeros(10, dtype=np.int64), _bloco(0, [_coinbase(50)])
    )

    assert histograma.sum() == 0


@pytest.mark.parametrize(
    ("altura", "altura_apagada"), [(91_842, 91_812), (91_880, 91_722)]
)
def test_histograma_segue_a_bip30(altura, altura_apagada):
    # em 2010 duas coinbases repetiram a transação de uma anterior e a apagaram (BIP30)
    histograma = np.zeros(100_000, dtype=np.int64)
    histograma[altura_apagada] = para_satoshis(50)

    histograma = atualizar_histograma(histograma, _bloco(altura, [_coinbase(50)]))

    assert histograma[altura_apagada] == 0
    assert histograma[altura] == para_satoshis(50)


def test_histograma_cresce_quando_a_altura_passa_do_tamanho():
    histograma = atualizar_histograma(
        np.zeros(4, dtype=np.int64), _bloco(9, [_coinbase(50)])
    )

    assert len(histograma) > 9
    assert histograma[9] == para_satoshis(50)


def test_histograma_recusa_gastar_mais_do_que_existe_na_origem():
    # sinal de bloco lido fora de ordem ou histograma de outra cadeia: parar, não ficar negativo
    bloco = _bloco(
        7, [_coinbase(50), _transacao([_entrada(2.0, 3)], [_saida(2.0)], 100)]
    )

    with pytest.raises(ValueError, match="altura 3"):
        atualizar_histograma(np.zeros(10, dtype=np.int64), bloco)


def test_bloco_170_primeira_transacao_entre_pessoas():
    # Bloco 170 (12/01/2009): 50 BTC criados no bloco 9 vão 10 para Hal Finney e 40 de volta.
    # Montado no formato do getblock verbosity 3; conferir contra o nó no PR 6.
    bloco = json.loads((PASTA / "bloco_170.json").read_text(encoding="utf-8"))
    hora_do_bloco_9 = 1_231_473_279

    metricas = metricas_do_bloco(bloco, _hora_fixa({9: hora_do_bloco_9}))

    assert metricas.taxas_total == 0
    assert metricas.valor_movimentado == para_satoshis(50)
    parado_dias = (bloco["time"] - hora_do_bloco_9) / UM_DIA
    assert metricas.dias_moeda_destruidos == pytest.approx(50 * parado_dias)
