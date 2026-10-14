"""Base histórica (B1): tabelas por ano lidas dos originais que o arquivista guardou no acervo."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from base import historico
from src.banco.coletas import com_registro

PASTA_CVM = Path(__file__).parent / "arquivos" / "cvm"
URL_IPE = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_2024.zip"
)
URL_VLMO = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_2024.zip"
)
AGORA = datetime(2026, 10, 14, 6, tzinfo=UTC)


def _zip_do_ipe() -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(
            "ipe_cia_aberta_2024.csv", (PASTA_CVM / "ipe_amostra.csv").read_bytes()
        )
    return saida.getvalue()


def _guardar(fonte: str, url: str, conteudo: bytes) -> None:
    com_registro(fonte, lambda _url: conteudo)(url)


def test_eventos_do_ipe_saem_num_parquet_por_ano_com_a_origem(
    banco, tmp_path, monkeypatch
):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    conteudo = _zip_do_ipe()
    _guardar("cvm-hist-ipe", URL_IPE, conteudo)
    with banco.connect() as conexao:
        linhas = historico.montar("eventos", conexao, tmp_path / "base", AGORA)
    assert set(linhas) == {2024} and linhas[2024] > 0
    tabela = pd.read_parquet(tmp_path / "base" / "eventos" / "2024.parquet")
    assert len(tabela) == linhas[2024]
    assert {"protocolo", "cnpj", "publicado_em", "rotulo"} <= set(tabela.columns)
    assert set(tabela["origem_sha256"]) == {hashlib.sha256(conteudo).hexdigest()}
    assert set(tabela["ano_do_arquivo"]) == {2024}
    assert set(tabela["montado_em"]) == {AGORA.isoformat()}
    assert set(tabela["versao_do_codigo"]) == {"0123abc"}  # exigência 13 (ADR 0055)


def test_usa_a_copia_mais_recente_do_mesmo_arquivo(banco, tmp_path):
    _guardar("cvm-hist-ipe", URL_IPE, b"PK versao velha que nao abre")
    novo = _zip_do_ipe()
    _guardar("cvm-hist-ipe", URL_IPE, novo)
    with banco.connect() as conexao:
        historico.montar("eventos", conexao, tmp_path / "base", AGORA)
    tabela = pd.read_parquet(tmp_path / "base" / "eventos" / "2024.parquet")
    assert set(tabela["origem_sha256"]) == {hashlib.sha256(novo).hexdigest()}


def test_negociacoes_do_vlmo(banco, tmp_path):
    _guardar("cvm-hist-vlmo", URL_VLMO, (PASTA_CVM / "vlmo_amostra.zip").read_bytes())
    with banco.connect() as conexao:
        linhas = historico.montar("negociacoes", conexao, tmp_path / "base", AGORA)
    assert linhas[2024] > 0
    assert (tmp_path / "base" / "negociacoes" / "2024.parquet").exists()


def test_sem_original_guardado_nada_e_montado(banco, tmp_path):
    with banco.connect() as conexao:
        assert historico.montar("eventos", conexao, tmp_path / "base", AGORA) == {}


def test_arquivo_que_nao_abre_falha_e_nao_grava(banco, tmp_path):
    _guardar("cvm-hist-ipe", URL_IPE, b"PK nao e um zip de verdade")
    with banco.connect() as conexao, pytest.raises(historico.ArquivoIlegivel):
        historico.montar("eventos", conexao, tmp_path / "base", AGORA)
    assert not (tmp_path / "base" / "eventos" / "2024.parquet").exists()


def test_tabela_desconhecida(banco, tmp_path):
    with banco.connect() as conexao, pytest.raises(KeyError):
        historico.montar("nao-existe", conexao, tmp_path, AGORA)


def test_ano_vem_do_nome_do_arquivo():
    assert historico.ano_do_arquivo(URL_IPE) == 2024
    assert historico.ano_do_arquivo("https://x/cda_fi_202609.zip") is None


def test_comando_monta_as_tabelas_pedidas(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import montar_base_historica

    _guardar("cvm-hist-ipe", URL_IPE, _zip_do_ipe())
    saida = montar_base_historica.main(["eventos", "--pasta", str(tmp_path / "b")])
    assert saida == 0
    assert (tmp_path / "b" / "eventos" / "2024.parquet").exists()
    assert not (tmp_path / "b" / "negociacoes").exists()


def test_comando_recusa_codigo_modificado(banco, tmp_path, monkeypatch):
    """Como as outras cargas da base: sem saber o commit, nada é montado."""
    import pytest

    from scripts import montar_base_historica
    from src.versao_do_codigo import VersaoDesconhecidaError

    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc-modificado")
    _guardar("cvm-hist-ipe", URL_IPE, _zip_do_ipe())
    with pytest.raises(VersaoDesconhecidaError):
        montar_base_historica.main(["eventos", "--pasta", str(tmp_path / "b")])
    assert not (tmp_path / "b").exists()


def test_comando_sai_com_1_se_um_original_nao_abre(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    from scripts import montar_base_historica

    _guardar("cvm-hist-ipe", URL_IPE, b"PK quebrado")
    assert montar_base_historica.main(["--pasta", str(tmp_path / "b")]) == 1
