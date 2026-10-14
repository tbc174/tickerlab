"""Linha de comando do arquivista (scripts/arquivar_fontes.py)."""

from scripts import arquivar_fontes


def test_listar_mostra_as_fontes(capsys):
    assert arquivar_fontes.main(["--listar"]) == 0
    saida = capsys.readouterr().out
    assert "cvm-fiagro" in saida
    assert "rfb-cnpj" in saida


def test_fonte_desconhecida_sai_com_2(capsys):
    assert arquivar_fontes.main(["nao-existe"]) == 2


def test_escolhe_por_grupo_ou_por_id():
    mensais = {f.id for f in arquivar_fontes.escolher("mensal")}
    assert {"rfb-cnpj", "pgfn-divida", "cvm-hist-ipe"} <= mensais
    assert "cvm-fiagro" not in mensais
    assert [f.id for f in arquivar_fontes.escolher("cvm-fiagro")] == ["cvm-fiagro"]
    assert arquivar_fontes.escolher("nada") == []
