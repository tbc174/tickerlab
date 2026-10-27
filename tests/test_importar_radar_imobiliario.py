"""Instalação atômica: falha de validação preserva a versão anterior."""

import json

import pytest

from scripts import importar_radar_imobiliario as importador
from scripts.importar_radar_imobiliario import instalar
from tests import test_radar_imobiliario as exemplos

dados_radar = exemplos.dados_radar


def test_instala_pacote_valido(dados_radar, tmp_path):
    origem, destino = tmp_path / "origem.json", tmp_path / "dados/radar.json"
    origem.write_text(json.dumps(dados_radar), encoding="utf-8")
    instalar(origem, destino)
    assert destino.exists()
    assert (
        json.loads(destino.read_text(encoding="utf-8"))["mensais"]
        == dados_radar["mensais"]
    )


def test_pacote_invalido_nao_substitui_anterior(tmp_path):
    origem, destino = tmp_path / "origem.json", tmp_path / "radar.json"
    origem.write_text('{"versao": 99}', encoding="utf-8")
    destino.write_text("anterior", encoding="utf-8")
    with pytest.raises(ValueError):
        instalar(origem, destino)
    assert destino.read_text(encoding="utf-8") == "anterior"


def test_limite_preserva_destino(tmp_path, monkeypatch):
    origem, destino = tmp_path / "origem.json", tmp_path / "radar.json"
    origem.write_bytes(b"x" * 21)
    destino.write_text("anterior", encoding="utf-8")
    monkeypatch.setattr(importador, "MAX_BYTES", 20)
    with pytest.raises(ValueError, match="limite"):
        instalar(origem, destino)
    assert destino.read_text(encoding="utf-8") == "anterior"


def test_cli_instala_em_destino_explicito(dados_radar, tmp_path, monkeypatch):
    origem, destino = tmp_path / "origem.json", tmp_path / "instalado.json"
    origem.write_text(json.dumps(dados_radar), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["importar", str(origem), "--destino", str(destino)])
    importador.main()
    assert destino.is_file()
