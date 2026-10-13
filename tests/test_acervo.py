"""Acervo do arquivo original (Radar, PR 2): guardado como veio, pelo SHA-256, sem duplicar."""

import hashlib
import logging
from datetime import UTC, datetime

import pytest

from src import acervo
from src.banco import coletas
from src.banco.coletas import com_registro, ultimas

QUANDO = datetime(2026, 10, 13, 7, tzinfo=UTC)
URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/ipe_cia_aberta_2026.zip"


def test_original_fica_com_o_sha256_como_nome(tmp_path):
    relativo = acervo.guardar_original("cvm-eventos", URL, b"zip", QUANDO)
    sha256 = hashlib.sha256(b"zip").hexdigest()
    assert relativo == f"bruto/cvm-eventos/2026/{sha256}.zip"
    assert (tmp_path / "acervo" / relativo).read_bytes() == b"zip"
    assert acervo.confere_com_o_registro(relativo, sha256)


def test_texto_fica_em_gzip_e_volta_igual(tmp_path):
    json_ = b'{"filings": "' + b"x" * 5000 + b'"}'
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    relativo = acervo.guardar_original("sec-eventos", url, json_, QUANDO)
    assert relativo.endswith(f"{hashlib.sha256(json_).hexdigest()}.json.gz")
    assert (tmp_path / "acervo" / relativo).stat().st_size < len(json_) / 10
    assert acervo.ler_original(relativo) == json_
    assert acervo.confere_com_o_registro(relativo, hashlib.sha256(json_).hexdigest())
    assert acervo.ler_original("bruto/nao/existe.json.gz") is None


def test_mesmo_arquivo_duas_vezes_e_um_arquivo_so(tmp_path):
    primeiro = acervo.guardar_original("cvm-eventos", URL, b"zip", QUANDO)
    segundo = acervo.guardar_original("cvm-eventos", URL, b"zip", QUANDO)
    assert primeiro == segundo
    assert len(list((tmp_path / "acervo").rglob("*.*"))) == 1  # nem sobra .parcial


def test_arquivo_alterado_no_disco_nao_confere(tmp_path):
    relativo = acervo.guardar_original("sec-13f", URL, b"original", QUANDO)
    (tmp_path / "acervo" / relativo).write_bytes(b"mexido")
    assert not acervo.confere_com_o_registro(
        relativo, hashlib.sha256(b"original").hexdigest()
    )
    assert not acervo.confere_com_o_registro("bruto/nao/existe.zip", "0" * 64)


@pytest.mark.parametrize(
    ("url", "extensao"),
    [
        (URL, ".zip"),
        ("https://www.sec.gov/Archives/edgar/data/1/x.XML", ".xml"),
        ("https://data.sec.gov/submissions/CIK0000320193.json?x=1", ".json"),
        ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany", ".bin"),
        ("https://exemplo/arquivo.exe", ".bin"),
    ],
)
def test_extensao_vem_do_endereco(url, extensao):
    assert acervo.extensao_da_url(url) == extensao


def test_desligado_nao_guarda_nada(tmp_path, monkeypatch):
    monkeypatch.setenv(acervo.VARIAVEL_DA_PASTA, "desligado")
    assert acervo.guardar_original("cvm-eventos", URL, b"zip", QUANDO) is None
    assert not (tmp_path / "acervo").exists()


def test_coleta_registra_onde_ficou_o_original(banco, tmp_path):
    com_registro("cvm-eventos", lambda url: b"zip")(URL)
    with banco.connect() as conexao:
        [linha] = ultimas(conexao)
    assert linha.caminho_do_original.startswith("bruto/cvm-eventos/")
    assert (tmp_path / "acervo" / linha.caminho_do_original).read_bytes() == b"zip"


def test_404_nao_guarda_original(banco, tmp_path):
    com_registro("sec-13f", lambda url: None)(URL)
    with banco.connect() as conexao:
        [linha] = ultimas(conexao)
    assert linha.caminho_do_original is None
    assert not (tmp_path / "acervo").exists()


def test_disco_com_problema_nao_derruba_a_coleta(banco, monkeypatch, caplog):
    def sem_disco(*_):
        raise OSError("disco cheio")

    monkeypatch.setattr(acervo, "guardar_original", sem_disco)
    with caplog.at_level(logging.ERROR, logger=coletas.__name__):
        assert com_registro("cvm-cda", lambda url: b"x")(URL) == b"x"
    assert "Falha ao guardar o original da coleta de cvm-cda" in caplog.text
    with banco.connect() as conexao:
        [linha] = ultimas(conexao)
    assert (linha.situacao, linha.caminho_do_original) == ("ok", None)


def test_extensao_informada_vale_mais_que_a_do_endereco(tmp_path):
    """O ENET entrega o XML por um endereço .aspx: quem guarda informa que é XML."""
    url = "https://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?Numero=1"
    xml = b"<?xml version='1.0'?><Doc>" + b"x" * 3000 + b"</Doc>"
    relativo = acervo.guardar_original("cvm-enet", url, xml, QUANDO, extensao=".xml")
    assert relativo.endswith(f"{hashlib.sha256(xml).hexdigest()}.xml.gz")
    assert acervo.ler_original(relativo) == xml
