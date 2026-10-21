"""Onde os arquivos cifrados da sala ficam no disco (B-20, PR 2): caminho só dos ids, gravação
inteira ou nada, pasta e arquivo só do dono, e o envio para com o disco quase cheio."""

import os
import shutil
import sys
import uuid
from collections import namedtuple

import pytest

from src.sala import guarda

OPERACAO = uuid.uuid4()
DOCUMENTO = uuid.uuid4()
SO_NO_LINUX = pytest.mark.skipif(sys.platform == "win32", reason="permissões do POSIX")


def test_o_caminho_nasce_so_dos_ids(tmp_path):
    original = guarda.caminho_do_documento(tmp_path, OPERACAO, DOCUMENTO, "original")
    texto = guarda.caminho_do_documento(tmp_path, OPERACAO, DOCUMENTO, "texto")
    assert original == tmp_path / str(OPERACAO) / f"{DOCUMENTO}.bin"
    assert texto == tmp_path / str(OPERACAO) / f"{DOCUMENTO}.txt.bin"


@pytest.mark.parametrize("estranho", ["../../etc", "a/../../b", "..", "C:\\x", ""])
def test_texto_que_nao_e_uuid_nao_vira_caminho(tmp_path, estranho):
    with pytest.raises(ValueError):
        guarda.pasta_da_operacao(tmp_path, estranho)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        guarda.caminho_do_documento(tmp_path, OPERACAO, estranho, "original")  # type: ignore[arg-type]


def test_parte_desconhecida_nao_vira_caminho(tmp_path):
    with pytest.raises(KeyError):
        guarda.caminho_do_documento(tmp_path, OPERACAO, DOCUMENTO, "../segredo")


def test_grava_e_le_sem_deixar_temporario(tmp_path):
    caminho = guarda.caminho_do_documento(tmp_path, OPERACAO, DOCUMENTO, "original")
    guarda.gravar(caminho, b"cifrado")
    guarda.gravar(caminho, b"cifrado de novo")  # a segunda gravação troca a primeira
    assert guarda.ler(caminho) == b"cifrado de novo"
    assert [p.name for p in caminho.parent.iterdir()] == [caminho.name]


def test_gravacao_que_falha_nao_deixa_arquivo_pela_metade(tmp_path, monkeypatch):
    caminho = guarda.caminho_do_documento(tmp_path, OPERACAO, DOCUMENTO, "original")

    def falha(*_):
        raise OSError("disco cheio")

    monkeypatch.setattr(guarda.os, "replace", falha)
    with pytest.raises(OSError, match="disco cheio"):
        guarda.gravar(caminho, b"x" * 1000)
    assert list(caminho.parent.iterdir()) == []


@SO_NO_LINUX
def test_pasta_e_arquivo_so_do_dono(tmp_path):
    raiz = tmp_path / "sala"
    caminho = guarda.caminho_do_documento(raiz, OPERACAO, DOCUMENTO, "original")
    guarda.gravar(caminho, b"x")
    assert caminho.stat().st_mode & 0o777 == guarda.PERMISSAO_DO_ARQUIVO
    assert caminho.parent.stat().st_mode & 0o777 == guarda.PERMISSAO_DA_PASTA


def test_apagar_documento_leva_original_e_texto_e_nao_falha_se_ja_foi(tmp_path):
    for parte in ("original", "texto"):
        guarda.gravar(
            guarda.caminho_do_documento(tmp_path, OPERACAO, DOCUMENTO, parte), b"x"
        )
    outro = guarda.caminho_do_documento(tmp_path, OPERACAO, uuid.uuid4(), "original")
    guarda.gravar(outro, b"y")
    guarda.apagar_documento(tmp_path, OPERACAO, DOCUMENTO)
    guarda.apagar_documento(tmp_path, OPERACAO, DOCUMENTO)
    assert [p.name for p in outro.parent.iterdir()] == [outro.name]


def test_apagar_operacao_leva_a_pasta_inteira_e_so_ela(tmp_path):
    outra = uuid.uuid4()
    guarda.gravar(
        guarda.caminho_do_documento(tmp_path, OPERACAO, DOCUMENTO, "original"), b"x"
    )
    guarda.gravar(
        guarda.caminho_do_documento(tmp_path, outra, DOCUMENTO, "original"), b"x"
    )
    guarda.apagar_operacao(tmp_path, OPERACAO)
    guarda.apagar_operacao(tmp_path, OPERACAO)  # de novo: nada a fazer
    assert [p.name for p in tmp_path.iterdir()] == [str(outra)]


def test_apagar_operacao_nao_segue_atalho_para_fora_da_sala(tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "importante.txt").write_text("nao apague")
    raiz = tmp_path / "sala"
    raiz.mkdir()
    try:
        os.symlink(
            fora, guarda.pasta_da_operacao(raiz, OPERACAO), target_is_directory=True
        )
    except OSError:
        pytest.skip("sem permissão para criar atalho neste sistema")
    guarda.apagar_operacao(raiz, OPERACAO)
    assert (fora / "importante.txt").read_text() == "nao apague"
    assert list(raiz.iterdir()) == []


Uso = namedtuple("Uso", "total used free")


@pytest.mark.parametrize(("livre", "para"), [(19, True), (20, False), (60, False)])
def test_o_envio_para_com_menos_de_20_por_cento_livre(
    tmp_path, monkeypatch, livre, para
):
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Uso(100, 100 - livre, livre))
    if para:
        with pytest.raises(guarda.SalaSemEspacoError):
            guarda.conferir_espaco_livre(tmp_path)
    else:
        guarda.conferir_espaco_livre(tmp_path)


def test_a_pasta_vem_da_variavel_ou_do_padrao(monkeypatch, tmp_path):
    monkeypatch.delenv(guarda.VARIAVEL_DA_PASTA, raising=False)
    assert guarda.pasta_da_sala() == guarda.PASTA_PADRAO
    monkeypatch.setenv(guarda.VARIAVEL_DA_PASTA, str(tmp_path))
    assert guarda.pasta_da_sala() == tmp_path
