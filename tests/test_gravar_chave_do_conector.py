"""O script que grava a chave do servidor do conector no VPS (linha 570): sem eco, sem log, 600."""

import os
import stat
import sys

import pytest

from conector_remoto.selo import ler_chave
from scripts.gravar_chave_do_conector import (
    VARIAVEL,
    conferir_chave,
    nova_chave,
    principal,
)


def _chave_gravada(arquivo) -> str:
    linhas = [
        linha
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha.startswith(f"{VARIAVEL}=")
    ]
    assert len(linhas) == 1
    return linhas[0].split("=", 1)[1]


def test_cria_a_chave_sem_mostrar_e_o_conector_le(tmp_path, capsys):
    arquivo = tmp_path / ".env.mcp"
    assert principal(["--arquivo", str(arquivo)]) == 0
    chave = _chave_gravada(arquivo)
    assert len(ler_chave(chave)) == 32
    saida = capsys.readouterr()
    assert chave not in saida.out and chave not in saida.err
    assert "gravada" in saida.out


@pytest.mark.skipif(
    sys.platform == "win32", reason="permissão de arquivo do Linux (o VPS)"
)
def test_arquivo_fica_com_permissao_600(tmp_path):
    arquivo = tmp_path / ".env.mcp"
    arquivo.write_text("OUTRA=1\n", encoding="utf-8")
    os.chmod(arquivo, 0o644)
    assert principal(["--arquivo", str(arquivo)]) == 0
    assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600


def test_nao_troca_a_chave_sem_pedir_e_troca_com_trocar(tmp_path, capsys):
    arquivo = tmp_path / ".env.mcp"
    arquivo.write_text(f"OUTRA=1\n{VARIAVEL}=velha\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo)]) == 1
    assert "velha" in arquivo.read_text(encoding="utf-8")
    assert "--trocar" in capsys.readouterr().err
    assert principal(["--arquivo", str(arquivo), "--trocar"]) == 0
    texto = arquivo.read_text(encoding="utf-8")
    assert "velha" not in texto and "OUTRA=1" in texto
    assert not list(tmp_path.glob(".*.novo"))  # o temporário não fica para trás


def test_colar_pede_sem_eco_e_recusa_chave_ruim_sem_mostrar(tmp_path, capsys):
    arquivo = tmp_path / ".env.mcp"
    boa = nova_chave()
    assert (
        principal(
            ["--arquivo", str(arquivo), "--colar"], perguntar=lambda _p: f" {boa}\n"
        )
        == 0
    )
    assert _chave_gravada(arquivo) == boa
    ruim = "Q" * 20
    assert (
        principal(
            ["--arquivo", str(arquivo), "--colar", "--trocar"],
            perguntar=lambda _p: ruim,
        )
        == 1
    )
    assert _chave_gravada(arquivo) == boa
    saida = capsys.readouterr()
    assert ruim not in saida.err and boa not in saida.out + saida.err


def test_conferir_chave_aceita_so_32_bytes_em_base64url():
    assert conferir_chave(nova_chave())
    for ruim in ("", "nao-e-base64!", "QUFB"):
        with pytest.raises(ValueError):
            conferir_chave(ruim)
