"""O script que grava a chave do chat no VPS (linha 903): sem eco, sem log, 600, sem ligar o chat."""

import os
import stat
import sys

import pytest

from scripts.gravar_chave_do_chat import (
    VARIAVEL,
    VARIAVEL_DE_LIGAR,
    ChaveRecusada,
    conferir_chave,
    principal,
)

# inventada: nenhuma chave de verdade em teste
CHAVE = "chave-inventada-do-chat-0123456789"


def _colar(texto: str):
    return lambda _: texto


def _linhas_da_chave(arquivo) -> list[str]:
    return [
        linha
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha.startswith(f"{VARIAVEL}=")
    ]


def test_grava_a_chave_sem_mostrar_e_mantem_as_outras_linhas(tmp_path, capsys):
    arquivo = tmp_path / ".env"
    arquivo.write_text("TICKERLAB_AMBIENTE=producao\nOUTRA=1\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo)], _colar(f"  {CHAVE}\n")) == 0
    assert _linhas_da_chave(arquivo) == [f"{VARIAVEL}={CHAVE}"]
    texto = arquivo.read_text(encoding="utf-8")
    assert "TICKERLAB_AMBIENTE=producao" in texto and "OUTRA=1" in texto
    saida = capsys.readouterr()
    assert CHAVE not in saida.out and CHAVE not in saida.err
    assert "gravada" in saida.out and "tickerlab-api" in saida.out


def test_nao_liga_o_chat(tmp_path):
    arquivo = tmp_path / ".env"
    arquivo.write_text("OUTRA=1\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo)], _colar(CHAVE)) == 0
    assert VARIAVEL_DE_LIGAR not in arquivo.read_text(encoding="utf-8")
    # e não mexe na chave de ligar quando ela já existe, desligada
    arquivo.write_text(f"{VARIAVEL_DE_LIGAR}=0\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo), "--trocar"], _colar(CHAVE)) == 0
    assert f"{VARIAVEL_DE_LIGAR}=0" in arquivo.read_text(encoding="utf-8")


def test_nao_grava_a_chave_geral(tmp_path):
    arquivo = tmp_path / ".env"
    arquivo.write_text("OUTRA=1\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo)], _colar(CHAVE)) == 0
    assert not any(
        linha.startswith("ANTHROPIC_API_KEY=")
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="permissão de arquivo do Linux (o VPS)"
)
def test_arquivo_fica_com_permissao_600(tmp_path):
    arquivo = tmp_path / ".env"
    arquivo.write_text("OUTRA=1\n", encoding="utf-8")
    os.chmod(arquivo, 0o644)
    assert principal(["--arquivo", str(arquivo)], _colar(CHAVE)) == 0
    assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600


def test_nao_troca_a_chave_sem_pedir_e_troca_com_trocar(tmp_path, capsys):
    arquivo = tmp_path / ".env"
    arquivo.write_text(f"OUTRA=1\n{VARIAVEL}=velha\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo)], _colar(CHAVE)) == 1
    assert _linhas_da_chave(arquivo) == [f"{VARIAVEL}=velha"]
    assert "--trocar" in capsys.readouterr().err
    assert principal(["--arquivo", str(arquivo), "--trocar"], _colar(CHAVE)) == 0
    assert _linhas_da_chave(arquivo) == [f"{VARIAVEL}={CHAVE}"]
    assert "OUTRA=1" in arquivo.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".*.novo"))  # o temporário não fica para trás


@pytest.mark.parametrize(
    "colado", ["", "   \n", "chave com espaco", "chave\tcom-tab", "metade\noutra"]
)
def test_formato_ruim_nao_grava_nada_e_nao_mostra_o_valor(tmp_path, capsys, colado):
    arquivo = tmp_path / ".env"
    arquivo.write_text("OUTRA=1\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo)], _colar(colado)) == 1
    assert arquivo.read_text(encoding="utf-8") == "OUTRA=1\n"
    erro = capsys.readouterr().err
    assert "Nada foi gravado" in erro
    for pedaco in ("espaco", "com-tab", "metade", "outra", "cifrao", "comentario"):
        assert pedaco not in erro


def test_conferir_chave_tira_so_as_pontas():
    assert conferir_chave(f"\n {CHAVE} \r\n") == CHAVE
    with pytest.raises(ChaveRecusada):
        conferir_chave("a b")


def test_pede_a_chave_sem_eco_por_padrao():
    import getpass

    from scripts import gravar_chave_do_chat

    assert principal.__defaults__ == (None, getpass.getpass)
    assert gravar_chave_do_chat.getpass is getpass


@pytest.mark.parametrize(
    "jeito",
    [f"  {VARIAVEL}=velha", f"export {VARIAVEL}=velha", f"{VARIAVEL} = velha"],
)
def test_reconhece_a_chave_escrita_de_outro_jeito_e_nao_a_deixa_para_tras(
    tmp_path, jeito
):
    arquivo = tmp_path / ".env"
    arquivo.write_text(f"OUTRA=1\n{jeito}\n", encoding="utf-8")
    assert principal(["--arquivo", str(arquivo)], _colar(CHAVE)) == 1
    assert principal(["--arquivo", str(arquivo), "--trocar"], _colar(CHAVE)) == 0
    texto = arquivo.read_text(encoding="utf-8")
    assert "velha" not in texto
    assert _linhas_da_chave(arquivo) == [f"{VARIAVEL}={CHAVE}"]


def test_sem_o_env_na_pasta_nao_cria_um_solto(tmp_path, capsys):
    arquivo = tmp_path / ".env"
    assert principal(["--arquivo", str(arquivo)], _colar(CHAVE)) == 1
    assert not arquivo.exists()
    erro = capsys.readouterr().err
    assert "não existe" in erro and CHAVE not in erro


@pytest.mark.skipif(sys.platform == "win32", reason="link simbólico do Linux (o VPS)")
def test_nao_troca_um_link_por_arquivo(tmp_path):
    destino = tmp_path / "env-de-verdade"
    destino.write_text("OUTRA=1\n", encoding="utf-8")
    arquivo = tmp_path / ".env"
    arquivo.symlink_to(destino)
    assert principal(["--arquivo", str(arquivo)], _colar(CHAVE)) == 1
    assert arquivo.is_symlink()
    assert destino.read_text(encoding="utf-8") == "OUTRA=1\n"
