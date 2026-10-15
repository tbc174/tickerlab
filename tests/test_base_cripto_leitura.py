"""Leitura do nó do Bitcoin, retomável e com reorganização (base de cripto, série 1, PR 2).

O nó é falso, em memória: uma cadeia de blocos sintéticos (só a coinbase de 50 BTC, um bloco por
intervalo fixo), com hashes encadeados. Dá para simular a cadeia crescendo, uma queda no meio da
leitura e uma reorganização (o fim da cadeia trocado por outro).
"""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from base.ancoragem import parquets_sem_manifesto
from base.cripto import leitura
from base.cripto.blocos import para_satoshis
from base.cripto.leitura import (
    CadeiaInconsistente,
    conferir_com_o_no,
    ler_ate_o_topo,
    ler_blocos,
    ler_parado,
    ler_reorganizacoes,
)

UM_DIA = 86_400
MEIO_DIA = UM_DIA // 2
UMA_HORA = 3_600
INICIO = 1_577_836_800  # 01/01/2020 00:00 UTC
AGORA = datetime(2026, 10, 13, 12, tzinfo=UTC)


def _bloco(altura: int, letra: str, anterior: str | None) -> dict:
    hora = INICIO + altura * UM_DIA + MEIO_DIA  # um bloco por dia, ao meio-dia
    bloco = {
        "hash": f"{letra}{altura:063x}",
        "height": altura,
        "time": hora,
        "mediantime": hora - UMA_HORA,
        "difficulty": 1.0,
        "tx": [
            {
                "txid": f"c{altura:063x}",
                "vin": [{"coinbase": "00"}],
                "vout": [{"value": 50.0, "scriptPubKey": {"type": "pubkey"}}],
                "vsize": 100,
            }
        ],
    }
    if anterior is not None:
        bloco["previousblockhash"] = anterior
    return bloco


def _cadeia(n: int, letra: str = "a", base: list[dict] | None = None) -> list[dict]:
    """Os blocos `base` e mais blocos novos (com a `letra` no hash) até ter `n`."""
    blocos = list(base or [])
    while len(blocos) < n:
        anterior = blocos[-1]["hash"] if blocos else None
        blocos.append(_bloco(len(blocos), letra, anterior))
    return blocos


class NoFalso:
    """O mesmo contrato do `ClienteRPC`, sobre uma lista de blocos."""

    def __init__(self, blocos: list[dict]):
        self.blocos = blocos
        self.liberados: list[int] = []
        self.ajuste_do_total = 0
        self.tamanho = 0  # bytes dos arquivos de blocos no disco
        self.rede: list[bool] = []  # cada vez que a leitura ligou ou desligou a rede

    def altura_do_topo(self) -> int:
        return len(self.blocos) - 1

    def hash_na_altura(self, altura: int) -> str:
        return self.blocos[altura]["hash"]

    def bloco(self, hash_do_bloco: str) -> dict:
        return next(b for b in self.blocos if b["hash"] == hash_do_bloco)

    def liberar_ate(self, altura: int) -> None:
        self.liberados.append(altura)

    def total_nao_gasto(self, altura: int) -> int:
        # só coinbases de 50 BTC, e a do bloco 0 nunca entra
        return altura * para_satoshis(50) + self.ajuste_do_total

    def tamanho_dos_blocos(self) -> int:
        return self.tamanho

    def ligar_rede(self, ligada: bool) -> None:
        self.rede.append(ligada)


def _sem_coleta(tabela):
    return tabela.drop(columns="coletado_em").reset_index(drop=True)


def test_bloco_sem_6_confirmacoes_nao_entra(tmp_path):
    # topo na altura 9: só até a 4 há 6 confirmações (4, 5, 6, 7, 8, 9)
    lidos = ler_ate_o_topo(NoFalso(_cadeia(10)), tmp_path, AGORA)

    assert lidos == 5
    assert ler_blocos(tmp_path)["altura"].tolist() == [0, 1, 2, 3, 4]


def test_linha_do_bloco_tem_metricas_e_data_da_coleta(tmp_path):
    ler_ate_o_topo(NoFalso(_cadeia(10)), tmp_path, AGORA)

    linha = ler_blocos(tmp_path).iloc[2]
    assert linha["hash"] == f"a{2:063x}"
    assert linha["emissao"] == para_satoshis(50)
    assert linha["hora"] == datetime(2020, 1, 3, 12, tzinfo=UTC)
    assert linha["coletado_em"] == AGORA


def test_leitura_recomeca_do_ultimo_ponto_e_da_o_mesmo_resultado(tmp_path):
    em_duas_vezes, de_uma_vez = tmp_path / "duas", tmp_path / "uma"
    no = NoFalso(_cadeia(10))
    ler_ate_o_topo(no, em_duas_vezes, AGORA, blocos_por_ponto=3)
    no.blocos = _cadeia(30, base=no.blocos)

    lidos = ler_ate_o_topo(no, em_duas_vezes, AGORA, blocos_por_ponto=3)
    ler_ate_o_topo(NoFalso(_cadeia(30)), de_uma_vez, AGORA, blocos_por_ponto=3)

    assert lidos == 20
    assert _sem_coleta(ler_blocos(em_duas_vezes)).equals(
        _sem_coleta(ler_blocos(de_uma_vez))
    )
    assert _sem_coleta(ler_parado(em_duas_vezes)).equals(
        _sem_coleta(ler_parado(de_uma_vez))
    )


def test_queda_entre_gravar_as_linhas_e_o_ponto_nao_duplica_bloco(tmp_path):
    no = NoFalso(_cadeia(20))
    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)
    # a queda: as linhas já estavam gravadas, mas o último ponto não
    max((tmp_path / "pontos").iterdir()).unlink()

    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)

    alturas = ler_blocos(tmp_path)["altura"]
    assert alturas.is_unique
    assert alturas.tolist() == list(range(15))


def test_reorganizacao_guarda_a_versao_anterior(tmp_path):
    no = NoFalso(_cadeia(30))
    ler_ate_o_topo(
        no, tmp_path, AGORA, blocos_por_ponto=5
    )  # lê até 24; pontos em 4, 9 ... 24
    # a rede trocou os blocos da altura 22 em diante por outros (letra "b")
    no.blocos = _cadeia(35, letra="b", base=no.blocos[:22])

    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)

    blocos = ler_blocos(tmp_path).set_index("altura")
    assert blocos.index.tolist() == list(range(30))
    assert blocos.loc[21, "hash"].startswith("a")
    assert blocos.loc[22, "hash"].startswith("b")
    desfeitos = ler_reorganizacoes(tmp_path)
    # voltou ao ponto da altura 19 (o último que a cadeia nova ainda tem): 20 a 24 ficam guardados
    assert desfeitos["altura"].tolist() == [20, 21, 22, 23, 24]
    assert (desfeitos["desfeito_em"] == AGORA).all()
    assert desfeitos["motivo"].str.contains("reorganiza").all()


def test_reorganizacao_sem_ponto_valido_para_a_leitura(tmp_path):
    no = NoFalso(_cadeia(20))
    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)
    no.blocos = _cadeia(20, letra="b")

    with pytest.raises(CadeiaInconsistente, match="nenhum ponto"):
        ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)


def test_bloco_que_nao_encadeia_no_anterior_para_a_leitura(tmp_path):
    blocos = _cadeia(20)
    blocos[3]["previousblockhash"] = "f" * 64

    with pytest.raises(CadeiaInconsistente, match="altura 3"):
        ler_ate_o_topo(NoFalso(blocos), tmp_path, AGORA)


def test_libera_no_no_so_o_que_ja_gravou_e_os_pontos_guardados_nao_precisam(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(leitura, "PONTOS_GUARDADOS", 3)
    no = NoFalso(_cadeia(400))

    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=50)  # lê até 394

    # pontos guardados: 299, 349 e 394; o nó ainda precisa dos 288 últimos blocos (394 - 288 = 106)
    assert len(list((tmp_path / "pontos").iterdir())) == 3
    assert max(no.liberados) == 106


def test_fracao_parada_ha_mais_de_um_ano(tmp_path):
    # um bloco de 50 BTC por dia (o do dia 0 não conta): no fim do dia D, estão parados há mais de
    # um ano os blocos 1 a D - 365, de um total de D blocos
    ler_ate_o_topo(NoFalso(_cadeia(400)), tmp_path, AGORA, blocos_por_ponto=100)

    parado = ler_parado(tmp_path).set_index("dia")["fracao_parada_1_ano"]
    assert pd.isna(parado.loc[date(2020, 1, 1)])  # no dia 0 ainda não há moeda nenhuma
    assert parado.loc[date(2020, 10, 27)] == 0  # dia 300
    dia_393 = date(2021, 1, 28)
    assert parado.loc[dia_393] == pytest.approx((393 - 365) / 393)


def test_conferencia_com_o_no(tmp_path):
    no = NoFalso(_cadeia(20))
    ler_ate_o_topo(no, tmp_path, AGORA)

    assert conferir_com_o_no(tmp_path, no) == 0
    no.ajuste_do_total = para_satoshis(1)
    assert conferir_com_o_no(tmp_path, no) == -para_satoshis(1)


GIGABYTE = 1024**3


@pytest.mark.parametrize(
    ("tamanho_em_gb", "esperado"),
    [(200, [False]), (40, [True]), (100, [])],
)
def test_freio_de_disco_desliga_e_religa_a_rede_do_no(
    tmp_path, tamanho_em_gb, esperado
):
    # acima de 150 GB de blocos ainda não lidos, o nó para de baixar; abaixo de 50 GB, volta;
    # no meio, fica como está (para não ligar e desligar a cada ponto)
    no = NoFalso(_cadeia(10))
    no.tamanho = tamanho_em_gb * GIGABYTE

    ler_ate_o_topo(no, tmp_path, AGORA)

    assert no.rede == esperado


def test_toda_tabela_do_no_tem_manifesto_e_rodada_sem_novidade_nao_regrava(tmp_path):
    no = NoFalso(_cadeia(30))
    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)
    no.blocos = _cadeia(35, letra="b", base=no.blocos[:22])  # reorganização
    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)
    assert parquets_sem_manifesto(tmp_path) == []
    assert not list(
        tmp_path.rglob("*.v1.parquet")
    )  # na cripto a última vence: sem versão

    antes = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*.parquet")}
    ler_ate_o_topo(no, tmp_path, AGORA, blocos_por_ponto=5)  # nada novo no topo
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*.parquet")} == antes
