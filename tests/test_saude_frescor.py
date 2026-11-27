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
    # Só os metadados importam: a rota não deve abrir o conteúdo.
    arquivo = tabela / "dados.parquet"
    arquivo.write_bytes(b"conteudo que nao deve ser lido")
    os.utime(arquivo, (DATA.timestamp(), DATA.timestamp()))
    os.utime(pasta, (0, 0))
    return pasta


@pytest.mark.parametrize("rota", ["/saude/frescor", "/api/saude/frescor"])
def test_frescor_publico_devolve_so_data_e_nome_da_marca(base, rota):
    resposta = TestClient(api.app).get(rota)
    assert resposta.status_code == 200
    assert resposta.json() == {
        "base_atualizada_em": DATA.isoformat(),
        "fonte": "mtime_parquet",
    }
    assert resposta.headers["cache-control"] == "no-store"


def test_frescor_rele_o_parquet_regravado_sem_mudar_a_pasta(base):
    cliente = TestClient(api.app)
    antiga = base.with_name("base.antiga")
    antiga.mkdir()
    (antiga / "mais_novo.parquet").write_bytes(b"fora da base atual")
    (base / "metadados.json").write_text("{}", encoding="utf-8")
    os.utime(base, (0, 0))
    assert (
        cliente.get("/saude/frescor").json()["base_atualizada_em"] == DATA.isoformat()
    )
    nova = DATA.replace(day=27)
    os.utime(base / "tabela" / "dados.parquet", (nova.timestamp(), nova.timestamp()))
    assert base.stat().st_mtime == 0
    assert (
        cliente.get("/saude/frescor").json()["base_atualizada_em"] == nova.isoformat()
    )


def test_frescor_escolhe_o_mais_recente_em_subpastas(base):
    outro = base / "outra_tabela"
    outro.mkdir()
    novo = outro / "novo.parquet"
    novo.write_bytes(b"mais recente")
    nova = DATA.replace(day=27)
    os.utime(novo, (nova.timestamp(), nova.timestamp()))
    os.utime(base, (0, 0))
    resposta = TestClient(api.app).get("/saude/frescor")
    assert resposta.json()["base_atualizada_em"] == nova.isoformat()


@pytest.mark.parametrize("estado", ["sem_base", "vazia", "arquivo"])
def test_sem_base_util_responde_503_sem_caminho(tmp_path, monkeypatch, estado):
    monkeypatch.setenv("TICKERLAB_ACERVO", str(tmp_path))
    if estado == "vazia":
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
        if pasta == base / "tabela" / "dados.parquet":
            raise PermissionError("detalhe privado")
        return original(pasta, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", negar)
    resposta = TestClient(api.app).get("/saude/frescor")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "frescor indisponível"}


def test_acervo_explicitamente_desligado_responde_503(monkeypatch):
    monkeypatch.setenv("TICKERLAB_ACERVO", "desligado")
    assert TestClient(api.app).get("/saude/frescor").status_code == 503
