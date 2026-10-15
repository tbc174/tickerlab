"""Recibo do OpenTimestamps para a âncora da base (`scripts/ancorar_base.py`, ADR 0078):
só um hash sai da máquina, o recibo é desta âncora, e a data vem do bloco do Bitcoin. Calendários e
exploradores do Bitcoin são dublês: o teste não usa a internet."""

import hashlib
import json

import pandas as pd
import pytest
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.timestamp import Timestamp

from base.parquet import gravar_tabela
from scripts import ancorar_base as ab
from src import versao_do_codigo as vc

ALTURA = 920_000
TEMPO_DO_BLOCO = 1_791_000_000  # 2026-10-03 UTC, só para o teste
CALENDARIO = "https://alice.btc.calendar.opentimestamps.org"  # da lista oficial


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7")
    for nome, valores in {"fca/emissores": [1, 2], "cda/fundos": [3]}.items():
        tabela = pd.DataFrame({"cnpj": [str(v) for v in valores], "valor": valores})
        gravar_tabela(tabela, tmp_path / "base" / nome, [], ["cnpj"])
    return tmp_path / "base"


@pytest.fixture
def ancora(base, tmp_path):
    destino = tmp_path / "ancoras" / "base-2026-10-15.json"
    ab.montar(destino, rotulo="2026-10-15", pasta=base, arquivos=[])
    return destino


class Calendarios:
    """Dublê dos calendários: guarda o que recebeu e devolve uma promessa (pendente)."""

    def __init__(self, falham=()):
        self.recebidos: list[tuple[str, bytes]] = []
        self.falham = set(falham)

    def enviar(self, url, digest):
        if url in self.falham:
            raise OSError("fora do ar")
        self.recebidos.append((url, digest))
        promessa = Timestamp(digest)
        promessa.attestations.add(PendingAttestation(CALENDARIO))
        return promessa

    def buscar(self, _uri, compromisso):
        # O calendário já pôs o compromisso num bloco: devolve o atestado do Bitcoin.
        pronto = Timestamp(compromisso)
        pronto.attestations.add(BitcoinBlockHeaderAttestation(ALTURA))
        return pronto


def _bloco_que_tem(compromisso):
    # O explorador mostra a raiz de Merkle do bloco com os bytes ao contrário (hábito do Bitcoin).
    return lambda altura: (
        (compromisso[::-1].hex(), TEMPO_DO_BLOCO) if altura == ALTURA else None
    )


def test_so_sai_um_hash_de_32_bytes_com_sal(ancora):
    calendarios = Calendarios()
    recibo = ab.carimbar(ancora, enviar=calendarios.enviar)
    assert recibo == ancora.with_name(ancora.name + ".ots")
    digest_da_ancora = hashlib.sha256(ancora.read_bytes()).digest()
    assert len(calendarios.recebidos) == len(ab.CALENDARIOS)
    for _url, enviado in calendarios.recebidos:
        assert len(enviado) == 32
        assert enviado != digest_da_ancora  # o sal (nonce) esconde até o hash da âncora
    assert ab.ler_recibo(recibo).file_digest == digest_da_ancora


def test_carimbar_exige_dois_calendarios(ancora):
    calendarios = Calendarios(falham=ab.CALENDARIOS[1:])
    with pytest.raises(RuntimeError, match="calendários"):
        ab.carimbar(ancora, enviar=calendarios.enviar)
    assert not ancora.with_name(ancora.name + ".ots").exists()


def test_pendente_ate_o_bloco_e_depois_confirmado_com_a_data(ancora, base):
    calendarios = Calendarios()
    recibo = ab.carimbar(ancora, enviar=calendarios.enviar)
    compromisso = calendarios.recebidos[0][1]

    antes = ab.conferir(
        ancora, recibo, pasta=base, arquivos=[], bloco=_bloco_que_tem(compromisso)
    )
    assert antes.diferencas == [] and antes.recibo_desta_ancora
    assert antes.confirmado_em is None and antes.pendente

    assert ab.atualizar(recibo, buscar=calendarios.buscar)
    depois = ab.conferir(
        ancora, recibo, pasta=base, arquivos=[], bloco=_bloco_que_tem(compromisso)
    )
    assert depois.altura == ALTURA
    assert depois.confirmado_em is not None
    assert depois.confirmado_em.timestamp() == TEMPO_DO_BLOCO
    assert depois.ok


def test_bloco_com_outra_raiz_nao_confirma(ancora, base):
    calendarios = Calendarios()
    recibo = ab.carimbar(ancora, enviar=calendarios.enviar)
    ab.atualizar(recibo, buscar=calendarios.buscar)
    resultado = ab.conferir(
        ancora, recibo, pasta=base, arquivos=[], bloco=_bloco_que_tem(b"x" * 32)
    )
    assert resultado.confirmado_em is None
    assert not resultado.ok


def test_ancora_mexida_nao_e_a_do_recibo(ancora, base):
    recibo = ab.carimbar(ancora, enviar=Calendarios().enviar)
    texto = json.loads(ancora.read_text(encoding="utf-8"))
    ancora.write_text(json.dumps({**texto, "rotulo": "outro"}), encoding="utf-8")
    resultado = ab.conferir(
        ancora, recibo, pasta=base, arquivos=[], bloco=lambda _a: None
    )
    assert not resultado.recibo_desta_ancora
    assert not resultado.ok


def test_base_mudada_aparece_na_conferencia(ancora, base):
    recibo = ab.carimbar(ancora, enviar=Calendarios().enviar)
    (base / "cda" / "fundos.json").unlink()
    resultado = ab.conferir(
        ancora, recibo, pasta=base, arquivos=[], bloco=lambda _a: None
    )
    assert resultado.diferencas == ["cda/fundos: sumiu"]


def test_arquivos_entram_na_ancora_pelo_nome(tmp_path):
    prereg = tmp_path / "pre-registro-m3-v1.md"
    prereg.write_text("critério", encoding="utf-8")
    destino = tmp_path / "pre-registro.json"
    ab.montar(destino, rotulo="m3-v1", pasta=None, arquivos=[prereg])
    ancora = json.loads(destino.read_text(encoding="utf-8"))
    assert [f["nome"] for f in ancora["folhas"]] == ["arquivos/pre-registro-m3-v1.md"]
    prereg.write_text("critério mudado depois", encoding="utf-8")
    assert ab.diferencas_de_hoje(ancora, pasta=None, arquivos=[prereg]) == [
        "arquivos/pre-registro-m3-v1.md: mudou"
    ]


def test_raiz_do_bloco_exige_exploradores_de_acordo():
    respostas = {
        "https://um/block-height/7": "abc",
        "https://um/block/abc": json.dumps({"merkle_root": "ff", "timestamp": 5}),
        "https://dois/block-height/7": "abc",
        "https://dois/block/abc": json.dumps({"merkle_root": "ff", "timestamp": 5}),
    }
    assert ab.raiz_do_bloco(
        7, respostas.__getitem__, ["https://um", "https://dois"]
    ) == ("ff", 5)
    respostas["https://dois/block/abc"] = json.dumps(
        {"merkle_root": "ee", "timestamp": 5}
    )
    with pytest.raises(RuntimeError, match="não concordam"):
        ab.raiz_do_bloco(7, respostas.__getitem__, ["https://um", "https://dois"])


def test_prova_de_uma_tabela_pela_linha_de_comando(ancora, base, tmp_path, capsys):
    prova = tmp_path / "prova.json"
    assert ab.main(["provar", str(ancora), "fca/emissores", "--saida", str(prova)]) == 0
    manifesto = base / "fca" / "emissores.json"
    assert ab.main(["conferir-prova", str(prova), str(manifesto)]) == 0
    assert "está na raiz" in capsys.readouterr().out
    assert (
        ab.main(["conferir-prova", str(prova), str(base / "cda" / "fundos.json")]) == 1
    )
