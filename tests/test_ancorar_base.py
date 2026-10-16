"""Recibo do OpenTimestamps para a âncora da base (`scripts/ancorar_base.py`, ADR 0078):
só um hash sai da máquina, o recibo é desta âncora, e a data vem do bloco do Bitcoin. Calendários e
exploradores do Bitcoin são dublês: o teste não usa a internet."""

import hashlib
import json
import os
from datetime import datetime, timedelta

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


def test_carimbar_nao_sobrescreve_recibo(ancora):
    recibo = ab.carimbar(ancora, enviar=Calendarios().enviar)
    antes = recibo.read_bytes()
    with pytest.raises(FileExistsError):
        ab.carimbar(ancora, enviar=Calendarios().enviar)
    assert recibo.read_bytes() == antes


def test_explorador_fora_do_ar_vira_aviso(ancora, base):
    calendarios = Calendarios()
    recibo = ab.carimbar(ancora, enviar=calendarios.enviar)
    ab.atualizar(recibo, buscar=calendarios.buscar)

    def fora_do_ar(_altura):
        raise RuntimeError("os exploradores não concordam")

    resultado = ab.conferir(ancora, recibo, pasta=base, arquivos=[], bloco=fora_do_ar)
    assert resultado.confirmado_em is None
    assert any("não concordam" in aviso for aviso in resultado.avisos)


# --- rotina noturna (`noite`) --------------------------------------------------------------------
AGORA = datetime(2026, 10, 16, 0, 15, tzinfo=ab.BRASILIA)


@pytest.fixture
def rotulos(tmp_path):
    pasta = tmp_path / "rotulos_ia" / "v1"
    pasta.mkdir(parents=True)
    (pasta / "rotulos.jsonl").write_text('{"evento_id": "1"}\n', encoding="utf-8")
    lotes = [
        {"id": "msgbatch_A", "estado": "gravado"},
        {"id": "msgbatch_B", "estado": "enviado"},
    ]
    (pasta / "manifesto.json").write_text(
        json.dumps({"lotes": lotes}), encoding="utf-8"
    )
    return pasta


def _noite(tmp_path, base, rotulos=None, agora=AGORA, calendarios=None):
    calendarios = calendarios or Calendarios()
    return ab.noite(
        tmp_path / "ancoras",
        pasta=base,
        rotulos=rotulos,
        agora=agora,
        enviar=calendarios.enviar,
        buscar=calendarios.buscar,
    )


def _nomes(pasta):
    return sorted(p.name for p in pasta.iterdir())


def test_noite_ancora_base_nova(tmp_path, base):
    feito = _noite(tmp_path, base)
    assert _nomes(tmp_path / "ancoras") == [
        "base-2026-10-16.json",
        "base-2026-10-16.json.ots",
    ]
    assert feito.carimbadas == ["base-2026-10-16.json"] and feito.problemas == []
    ancora = json.loads(
        (tmp_path / "ancoras" / "base-2026-10-16.json").read_text("utf-8")
    )
    assert ab.diferencas_de_hoje(ancora, base, []) == []


def test_noite_nao_ancora_base_igual(tmp_path, base):
    _noite(tmp_path, base)
    feito = _noite(tmp_path, base, agora=AGORA + timedelta(days=1))
    assert feito.carimbadas == []
    assert not (tmp_path / "ancoras" / "base-2026-10-17.json").exists()


def test_noite_ancora_base_que_mudou_no_dia_seguinte(tmp_path, base):
    _noite(tmp_path, base)
    gravar_tabela(
        pd.DataFrame({"cnpj": ["9"], "valor": [9]}),
        base / "cda" / "fundos",
        [],
        ["cnpj"],
    )
    feito = _noite(tmp_path, base, agora=AGORA + timedelta(days=1))
    assert feito.carimbadas == ["base-2026-10-17.json"]


def test_noite_nao_faz_duas_ancoras_no_mesmo_dia(tmp_path, base):
    _noite(tmp_path, base)
    antes = (tmp_path / "ancoras" / "base-2026-10-16.json").read_bytes()
    gravar_tabela(
        pd.DataFrame({"cnpj": ["9"], "valor": [9]}),
        base / "cda" / "fundos",
        [],
        ["cnpj"],
    )
    feito = _noite(tmp_path, base, agora=AGORA + timedelta(hours=3))
    assert feito.carimbadas == []
    assert (tmp_path / "ancoras" / "base-2026-10-16.json").read_bytes() == antes


def test_noite_carimba_ancora_que_ficou_sem_recibo(tmp_path, base):
    sem_calendario = Calendarios(falham=ab.CALENDARIOS)
    feito = _noite(tmp_path, base, calendarios=sem_calendario)
    assert feito.carimbadas == []
    assert any("base-2026-10-16.json sem recibo" in p for p in feito.problemas)
    depois = _noite(tmp_path, base, agora=AGORA + timedelta(days=1))
    assert depois.carimbadas == ["base-2026-10-16.json"]
    assert (tmp_path / "ancoras" / "base-2026-10-16.json.ots").exists()


def test_noite_nao_sobrescreve_recibo(tmp_path, base):
    _noite(tmp_path, base)
    recibo = tmp_path / "ancoras" / "base-2026-10-16.json.ots"
    compromisso = ab.ler_recibo(recibo).file_digest
    _noite(tmp_path, base, agora=AGORA + timedelta(minutes=5))
    # o atualizar acrescenta o caminho até o bloco, mas o recibo continua sendo desta âncora
    assert ab.ler_recibo(recibo).file_digest == compromisso


def test_noite_recusa_tabela_de_pessoas_pequena(tmp_path, base):
    gravar_tabela(
        pd.DataFrame({"cnpj": ["1"], "valor": [1]}),
        base / "pessoas" / "socios",
        [],
        ["cnpj"],
    )
    feito = _noite(tmp_path, base)
    assert feito.carimbadas == []
    assert any("pessoas/socios" in p for p in feito.problemas)
    assert not (tmp_path / "ancoras").exists() or _nomes(tmp_path / "ancoras") == []


def test_noite_ancora_cada_lote_gravado_uma_vez(tmp_path, rotulos):
    feito = _noite(tmp_path, None, rotulos=rotulos)
    assert feito.carimbadas == ["rotulos-msgbatch_A.json"]
    ancora = json.loads(
        (tmp_path / "ancoras" / "rotulos-msgbatch_A.json").read_text("utf-8")
    )
    assert [f["nome"] for f in ancora["folhas"]] == [
        "arquivos/manifesto.json",
        "arquivos/rotulos.jsonl",
    ]
    assert ancora["rotulo"] == "lote msgbatch_A"
    assert (
        _noite(
            tmp_path, None, rotulos=rotulos, agora=AGORA + timedelta(days=1)
        ).carimbadas
        == []
    )


def test_noite_nao_ancora_lote_enviado(tmp_path, rotulos):
    _noite(tmp_path, None, rotulos=rotulos)
    assert not (tmp_path / "ancoras" / "rotulos-msgbatch_B.json").exists()


def test_noite_atualiza_os_pendentes(tmp_path, base):
    _noite(tmp_path, base)
    feito = _noite(tmp_path, base, agora=AGORA + timedelta(days=1))
    assert feito.no_bitcoin == ["base-2026-10-16.json.ots"]
    assert _noite(tmp_path, base, agora=AGORA + timedelta(days=2)).no_bitcoin == []


class SemBloco(Calendarios):
    def buscar(self, _uri, _compromisso):
        return None


def _envelhecer(arquivo, dias):
    antes = (AGORA - timedelta(days=dias)).timestamp()
    os.utime(arquivo, (antes, antes))


def test_noite_avisa_recibo_pendente_ha_mais_de_2_dias(tmp_path, base):
    _noite(tmp_path, base, calendarios=SemBloco())
    _envelhecer(tmp_path / "ancoras" / "base-2026-10-16.json", 3)
    feito = _noite(tmp_path, base, calendarios=SemBloco())
    assert feito.problemas == ["base-2026-10-16.json.ots pendente há 3 dias"]


def test_noite_nao_avisa_antes_de_2_dias(tmp_path, base):
    _noite(tmp_path, base, calendarios=SemBloco())
    _envelhecer(tmp_path / "ancoras" / "base-2026-10-16.json", 1)
    assert _noite(tmp_path, base, calendarios=SemBloco()).problemas == []


def test_main_noite_sai_1_com_linha_falhas(tmp_path, base, monkeypatch, capsys):
    monkeypatch.setattr(ab, "_enviar", Calendarios(falham=ab.CALENDARIOS).enviar)
    codigo = ab.main(
        ["noite", "--ancoras", str(tmp_path / "ancoras"), "--pasta", str(base)]
    )
    assert codigo == 1
    assert "FALHAS: base-" in capsys.readouterr().out


def test_noite_avisa_parquet_sem_manifesto(tmp_path, base):
    pd.DataFrame({"a": [1]}).to_parquet(base / "solto.parquet", index=False)
    feito = _noite(tmp_path, base)
    assert feito.carimbadas == ["base-2026-10-16.json"]
    assert feito.problemas == [
        "1 Parquet(s) sem manifesto, fora da âncora: solto.parquet"
    ]
