"""A saúde pública expõe só o carimbo do recorte principal, sem ler seus dados."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import api

DATA = datetime(2026, 11, 26, 12, tzinfo=UTC)


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path))
    pasta = tmp_path / "base"
    pasta.mkdir()
    tabela = pasta / "tabela"
    tabela.mkdir()
    # Só a existência importa: a rota não deve abrir o conteúdo.
    (tabela / "dados.parquet").write_bytes(b"conteudo que nao deve ser lido")
    os.utime(pasta, (DATA.timestamp(), DATA.timestamp()))
    return pasta


@pytest.mark.parametrize("rota", ["/saude/frescor", "/api/saude/frescor"])
def test_frescor_publico_devolve_so_data_e_nome_da_marca(base, rota):
    resposta = TestClient(api.app).get(rota)
    assert resposta.status_code == 200
    assert resposta.json() == {
        "base_atualizada_em": DATA.isoformat(),
        "fonte": "mtime_base",
    }
    assert resposta.headers["cache-control"] == "no-store"


def test_frescor_rele_a_marca_e_ignora_as_outras_pastas(base):
    cliente = TestClient(api.app)
    antiga = base.with_name("base.antiga")
    antiga.mkdir()
    assert (
        cliente.get("/saude/frescor").json()["base_atualizada_em"] == DATA.isoformat()
    )
    nova = DATA.replace(day=27)
    os.utime(base, (nova.timestamp(), nova.timestamp()))
    assert (
        cliente.get("/saude/frescor").json()["base_atualizada_em"] == nova.isoformat()
    )


@pytest.mark.parametrize("estado", ["sem_acervo", "sem_base", "vazia", "arquivo"])
def test_sem_base_util_responde_503_sem_caminho(tmp_path, monkeypatch, estado):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path))
    if estado == "sem_acervo":
        monkeypatch.delenv("TICKERLAB_ACERVO")
    elif estado == "vazia":
        (tmp_path / "base").mkdir()
    elif estado == "arquivo":
        (tmp_path / "base").write_text("nao e pasta", encoding="utf-8")
    resposta = TestClient(api.app).get("/saude/frescor")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "frescor indisponível"}
    assert resposta.headers["cache-control"] == "no-store"


def test_falha_ao_ler_marca_nao_expoe_detalhe(base, monkeypatch):
    original = Path.stat

    def negar(pasta, *args, **kwargs):
        if pasta == base:
            raise PermissionError("detalhe privado")
        return original(pasta, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", negar)
    resposta = TestClient(api.app).get("/saude/frescor")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "frescor indisponível"}
