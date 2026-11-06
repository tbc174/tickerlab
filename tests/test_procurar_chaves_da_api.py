"""O passo do CI que procura chaves da API nos arquivos (linha 170 da fila; N7)."""

import re

import pytest

from scripts import procurar_chaves_da_api as proc
from src import chaves_da_api as ch


def test_acha_chave_gerada_por_gerar_chave():
    for _ in range(200):  # o segredo pode acabar em "-" ou "_": o padrão aguenta
        _, chave = ch.gerar_chave()
        assert proc.linhas_com_chave(f"ok\nTLD_KEY={chave}\n") == [2]
        assert proc.linhas_com_chave(f'"{chave}"') == [1]
        assert proc.linhas_com_chave(f"({chave}).") == [1]


@pytest.mark.parametrize(
    "texto",
    [
        "tld_ não é chave",
        "o prefixo tld_ e o segredo",
        "tld_abcdefgh_curto",
        "tld_ABCDEFGH_" + "a" * 43,  # prefixo é minúsculo
        "tld_abcdefg1_" + "a" * 43,  # "1" não existe em base32
        "tld_abcdefgh_" + "a" * 42,
        "xtld_abcdefgh_" + "a" * 43,  # parte de outra palavra
        "tld_abcdefgh_" + "a" * 44,  # segredo maior que o da chave
        "tld_abcdefgh_" + "a" * 43 + "_",
        "tld_<prefixo>_<segredo>",
        "tld_xxxxxxxx_" + "x" * 10,
    ],
)
def test_nao_pega_texto_comum(texto):
    assert proc.linhas_com_chave(texto) == []


def test_o_padrao_do_github_pega_o_mesmo_que_o_do_ci():
    partes = proc.PADRAO_DO_GITHUB
    no_github = re.compile(f"{partes['antes']}({partes['segredo']}){partes['depois']}")
    _, chave = ch.gerar_chave()
    assert no_github.search(f"chave={chave}\n").group(2) == chave
    assert no_github.search("tld_abcdefgh_curto") is None
    assert no_github.search("xtld_abcdefgh_" + "a" * 43) is None


def test_procurar_diz_o_arquivo_e_a_linha_sem_mostrar_a_chave(tmp_path, capsys):
    _, chave = ch.gerar_chave()
    sujo = tmp_path / "config.txt"
    sujo.write_text(f"a\nb\nchave={chave}\n", encoding="utf-8")
    limpo = tmp_path / "limpo.txt"
    limpo.write_text("nada aqui\n", encoding="utf-8")
    binario = tmp_path / "foto.png"
    binario.write_bytes(b"\xff\xfe\x00\x80")

    assert proc.main([str(limpo), str(binario)]) == 0
    assert proc.main([str(sujo), str(limpo)]) == 1
    saida = capsys.readouterr().out
    assert f"{sujo}:3" in saida
    assert chave not in saida


def test_o_repositorio_nao_tem_chave_da_api():
    assert proc.procurar(proc.arquivos_versionados()) == []
