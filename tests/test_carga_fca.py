"""Carga do FCA para a base (série 3 da base de ML, PR 3): lê cada ano (do acervo ou da CVM), grava
as tabelas do código da ação com manifesto e versão do código. Sem internet."""

import json
from pathlib import Path

import pandas as pd
import pytest

from base.parquet import conferir_tabela
from scripts import carga_fca
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro
from src.banco.conexao import migrar_para

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fca"
VERSAO = "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7"
TABELAS = ("valores_mobiliarios", "emissores", "tickers", "codigos_invalidos")


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    pedidos: list[str] = []

    def baixar_falso(endereco: str) -> bytes | None:
        pedidos.append(endereco)
        arquivo = PASTA / endereco.rsplit("/", 1)[-1]
        return arquivo.read_bytes() if arquivo.exists() else None  # os outros anos: 404

    # como a coleta real: o que é baixado vai para o acervo e o registro de coletas
    monkeypatch.setattr(
        carga_fca, "baixar", com_registro(carga_fca.FONTE, baixar_falso)
    )
    return tmp_path / "base" / "fca", pedidos


def test_grava_as_tabelas_com_manifesto(ambiente):
    pasta, _ = ambiente
    assert (
        carga_fca.main(["--pasta", str(pasta), "--desde", "2010", "--ate", "2026"]) == 0
    )
    for nome in TABELAS:
        arquivo = pasta / f"{nome}.parquet"
        assert conferir_tabela(arquivo), nome
        manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
        assert manifesto["versao_do_codigo"] == VERSAO
        # os 4 anos das amostras (os outros deram 404) e, nas tabelas que a usam, a tabela conferida
        conferida = nome in ("emissores", "tickers")
        assert len(manifesto["origens"]) == 4 + conferida, nome
        assert (
            any(
                o["url"] == carga_fca.URL_DOS_CODIGOS_CONFERIDOS
                for o in manifesto["origens"]
            )
            == conferida
        ), nome
    emissores = pd.read_parquet(pasta / "emissores.parquet")
    assert {"PETR", "ITUB", "VVAR", "VIIA", "BHIA"} <= set(emissores["emissor"])
    invalidos = pd.read_parquet(pasta / "codigos_invalidos.parquet")
    assert "4030" in set(invalidos["codigo_informado"])


def test_btg_entra_pela_tabela_conferida(ambiente):
    """Série 3, PR 8: o BTG informa "000000" nas units; sem a tabela conferida, ficava sem ticker."""
    pasta, _ = ambiente
    carga_fca.main(["--pasta", str(pasta), "--desde", "2026", "--ate", "2026"])
    emissores = pd.read_parquet(pasta / "emissores.parquet").set_index("emissor")
    assert emissores.loc["BPAC", ["cnpj", "origem"]].tolist() == [
        "30.306.294/0001-45",
        "códigos conferidos",
    ]
    assert emissores.loc["PETR", "origem"] == "fca"
    tickers = pd.read_parquet(pasta / "tickers.parquet")
    assert "BPAC11" in set(tickers["codigo"])


def test_segunda_carga_le_do_acervo_sem_baixar_de_novo(ambiente):
    pasta, pedidos = ambiente
    carga_fca.main(["--pasta", str(pasta), "--desde", "2018", "--ate", "2018"])
    antes = len(pedidos)
    carga_fca.main(["--pasta", str(pasta), "--desde", "2018", "--ate", "2018"])
    assert len(pedidos) == antes


def test_sem_a_versao_do_codigo_nao_grava(ambiente, monkeypatch):
    pasta, _ = ambiente
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        carga_fca.main(["--pasta", str(pasta)])
    assert not pasta.exists()


def test_linhagem_de_cada_tabela_e_completa(ambiente):
    """Exigência 13 da ADR 0055: de qualquer tabela do FCA, chegar aos originais, à data da coleta e
    à versão do código."""
    import sqlalchemy as sa

    from base.linhagem import linhagem_da_tabela
    from src.banco.conexao import criar_engine

    pasta, _ = ambiente
    carga_fca.main(["--pasta", str(pasta), "--desde", "2018", "--ate", "2021"])
    motor = criar_engine()
    try:
        with motor.connect() as c:
            for nome in TABELAS:
                assert linhagem_da_tabela(c, pasta / f"{nome}.parquet").completa, nome
            versoes = set(
                c.execute(sa.text("select versao_do_codigo from coletas")).scalars()
            )
        assert versoes == {VERSAO}  # o registro de cada arquivo também diz o commit
    finally:
        motor.dispose()
