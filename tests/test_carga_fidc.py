"""Carga do FIDC e do cadastro de fundos para a base (série 3 da base de ML, PR 6). Sem internet."""

import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base.parquet import conferir_tabela
from scripts import carga_fidc
from src import acervo
from src import versao_do_codigo as vc
from src.banco.coletas import com_registro
from src.banco.conexao import migrar_para
from tests.test_base_fidc import CADASTRO

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fidc"
VERSAO = "7b2d29a1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b2"


def _historico() -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(
            "cad_fi_hist_admin.csv",
            "CNPJ_FUNDO;DT_REG;CNPJ_ADMIN;ADMIN;DT_INI_ADMIN;DT_FIM_ADMIN\n"
            "11.111.111/0001-11;2010-01-01;22.222.222/0001-22;ADMIN A;2010-01-01;\n",
        )
        arquivo.writestr(
            "cad_fi_hist_diretor_resp.csv", "CNPJ_FUNDO;DIRETOR\n1;FULANO\n"
        )
    return conteudo.getvalue()


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'b.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, str(tmp_path / "acervo"))
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    migrar_para("head", url=url)
    arquivos = {p.name: p.read_bytes() for p in PASTA.glob("*.zip")}
    arquivos["cad_fi.csv"] = CADASTRO.encode("latin-1")
    arquivos["cad_fi_hist.zip"] = _historico()

    def baixar_falso(endereco: str) -> bytes | None:
        return arquivos.get(endereco.rsplit("/", 1)[-1])  # o resto: 404

    monkeypatch.setattr(
        carga_fidc, "baixar", com_registro(carga_fidc.FONTE, baixar_falso)
    )
    return tmp_path / "base" / "fidc"


def test_informe_vira_uma_tabela_por_quadro_e_ano(ambiente):
    pasta = ambiente
    assert (
        carga_fidc.main(["--pasta", str(pasta), "--desde", "2013", "--ate", "2013"])
        == 0
    )
    assert (
        carga_fidc.main(["--pasta", str(pasta), "--desde", "2026", "--ate", "2026"])
        == 0
    )
    for quadro in ("tab_I", "tab_IV", "tab_X_1"):
        for ano in (2013, 2026):
            arquivo = pasta / "informe" / quadro / f"{ano}.parquet"
            assert conferir_tabela(arquivo), arquivo
            tabela = pd.read_parquet(arquivo)
            assert (tabela["disponivel_em"] > tabela["competencia"]).all()


def test_cadastro_entra_sem_dado_pessoal(ambiente):
    pasta = ambiente
    carga_fidc.main(["--pasta", str(pasta), "--desde", "2013", "--ate", "2013"])
    cadastro = pd.read_parquet(pasta / "cadastro" / "cad_fi.parquet")
    assert "DIRETOR" not in cadastro.columns and cadastro["GESTOR"].isna().sum() == 1
    assert (pasta / "cadastro" / "hist_admin.parquet").exists()
    assert not (pasta / "cadastro" / "hist_diretor_resp.parquet").exists()


def test_sem_a_versao_do_codigo_nao_grava(ambiente, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        carga_fidc.main(["--pasta", str(ambiente)])
    assert not ambiente.exists()
