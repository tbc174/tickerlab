"""Carga do CDA para a base (série 3 da base de ML, PR 4): um Parquet por ano com manifesto, o
"como era na data" de cada posição, ano repetido pulado e arquivo regravado pela CVM guardado como
versão, sem apagar a anterior. Sem internet."""

import json
from pathlib import Path

import pandas as pd
import pytest

from base.parquet import conferir_tabela
from scripts import carga_cda
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro
from src.banco.conexao import migrar_para

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "cda"
VERSAO = "3af11e4c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    arquivos = {p.name: p.read_bytes() for p in PASTA.glob("*.zip")}
    pedidos: list[str] = []

    def baixar_falso(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        return arquivos.get(endereco.rsplit("/", 1)[-1])  # o resto: 404

    monkeypatch.setattr(
        carga_cda, "baixar", com_registro(carga_cda.FONTE, baixar_falso)
    )
    return tmp_path / "base" / "cda", arquivos, pedidos


def test_ano_historico_e_ano_mensal_viram_parquet_com_manifesto(ambiente):
    pasta, _, _ = ambiente
    assert (
        carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"]) == 0
    )
    assert (
        carga_cda.main(["--pasta", str(pasta), "--desde", "2025", "--ate", "2025"]) == 0
    )
    for ano, competencias in (("2005", {"2005-01", "2005-02"}), ("2025", {"2025-09"})):
        arquivo = pasta / f"{ano}.parquet"
        assert conferir_tabela(arquivo)
        tabela = pd.read_parquet(arquivo)
        assert set(tabela["competencia"].dt.strftime("%Y-%m")) == competencias
        assert (
            tabela["disponivel_em"] >= tabela["competencia"] + pd.Timedelta(days=90)
        ).all()
        manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
        assert manifesto["versao_do_codigo"] == VERSAO and manifesto["origens"]


def test_ano_igual_ao_que_ja_tem_e_pulado(ambiente):
    pasta, _, pedidos = ambiente
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    antes = (pasta / "2005.json").read_text(encoding="utf-8")
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    assert (pasta / "2005.json").read_text(encoding="utf-8") == antes
    assert sum("cda_fi_2005" in p for p in pedidos) == 1  # a 2ª vez leu do acervo


def test_arquivo_regravado_vira_versao_nova_sem_apagar(ambiente, monkeypatch):
    """A CVM regrava anos antigos: o Parquet anterior fica como `2005.v1` e o novo entra no lugar."""
    pasta, arquivos, _ = ambiente
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    primeiro = pd.read_parquet(pasta / "2005.parquet")
    regravado = PASTA.joinpath(
        "cda_fi_2014.zip"
    ).read_bytes()  # outro conteúdo no mesmo endereço
    monkeypatch.setattr(
        carga_cda, "original_mais_recente", lambda conexao, url: None
    )  # a CVM mudou o arquivo
    arquivos["cda_fi_2005.zip"] = regravado
    carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    assert conferir_tabela(pasta / "2005.v1.parquet")
    pd.testing.assert_frame_equal(pd.read_parquet(pasta / "2005.v1.parquet"), primeiro)
    assert not pd.read_parquet(pasta / "2005.parquet").equals(primeiro)


def test_sem_a_versao_do_codigo_nao_grava(ambiente, monkeypatch):
    pasta, _, _ = ambiente
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        carga_cda.main(["--pasta", str(pasta), "--desde", "2005", "--ate", "2005"])
    assert not pasta.exists()


def test_linhagem_do_ano_e_completa(ambiente):
    """Exigência 13 da ADR 0055: do Parquet do ano ao arquivo do CDA, à coleta e à versão."""
    from base.linhagem import linhagem_da_tabela
    from src.banco.conexao import criar_engine

    pasta, _, _ = ambiente
    carga_cda.main(["--pasta", str(pasta), "--desde", "2025", "--ate", "2025"])
    motor = criar_engine()
    try:
        with motor.connect() as c:
            assert linhagem_da_tabela(c, pasta / "2025.parquet").completa
    finally:
        motor.dispose()
