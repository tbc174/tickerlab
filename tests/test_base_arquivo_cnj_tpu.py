"""A coleta das classes da TPU do CNJ (`base/arquivo/cnj_tpu.py`). Os usuários são inventados."""

import json
from pathlib import Path

import pytest

from base.arquivo import cnj_tpu
from base.arquivo.coleta import Alvo


class Gateway:
    """O download das classes em memória."""

    def __init__(self, conteudo: bytes):
        self.conteudo = conteudo
        self.baixados: list[str] = []

    def baixar(self, url: str, destino: Path):
        self.baixados.append(url)
        destino.write_bytes(self.conteudo)
        return {"Content-Type": "application/json"}


def _classe(codigo: int, pai: int | None, nome: str) -> dict:
    return {
        "cod_item": codigo,
        "cod_item_pai": pai,
        "nome": nome,
        "situacao": "A",
        "usuario_inclusao": "fulano.inventado",
        "usuario_alteracao": "beltrano.inventado",
    }


def test_guarda_as_classes_sem_o_usuario_do_cnj(tmp_path: Path):
    classes = [_classe(2, None, "PROCESSO CÍVEL"), _classe(7, 2, "Procedimento Comum")]
    cliente = Gateway(json.dumps(classes).encode())
    destino = tmp_path / "classes.json"

    cnj_tpu.obter_classes(cnj_tpu.CLASSES)(cliente, destino)  # type: ignore[arg-type]

    guardado = json.loads(destino.read_text(encoding="utf-8"))
    assert cliente.baixados == [cnj_tpu.CLASSES]
    assert [c["cod_item"] for c in guardado] == [2, 7]
    assert "inventado" not in destino.read_text(encoding="utf-8")
    assert guardado[1]["nome"] == "Procedimento Comum"
    assert not list(tmp_path.glob("*.bruto"))


def test_resposta_que_nao_e_lista_de_classes_falha(tmp_path: Path):
    cliente = Gateway(json.dumps({"status": 404}).encode())
    with pytest.raises(ValueError, match="TPU"):
        cnj_tpu.obter_classes(cnj_tpu.CLASSES)(cliente, tmp_path / "x.json")  # type: ignore[arg-type]


def test_a_fonte_e_mensal_e_tem_um_alvo():
    fonte = cnj_tpu.fonte()
    alvos = fonte.descobrir(None, None)  # type: ignore[arg-type]
    assert (fonte.id, fonte.grupo, fonte.tipo) == ("cnj-tpu", "mensal", "json")
    assert [a.url for a in alvos] == [cnj_tpu.CLASSES]
    assert isinstance(alvos[0], Alvo)
