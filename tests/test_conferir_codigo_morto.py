"""O conferidor do código morto compara a saída do vulture com a lista esperada sem rodar o vulture."""

from collections.abc import Callable
from pathlib import Path

import pytest

from scripts import conferir_codigo_morto as conferir

ITEM_FUNCAO = "src/a.py: unused function 'foo' (60% confidence)"
ITEM_VARIAVEL = "base/b.py: unused variable 'BAR' (60% confidence)"
ITEM_INALCANCAVEL = "base/c.py: unreachable code after 'return' (100% confidence)"

SAIDA_DO_VULTURE = (
    "src/a.py:10: unused function 'foo' (60% confidence)\n"
    "base/b.py:5: unused variable 'BAR' (60% confidence)\n"
)
ESPERADO_IGUAL = [ITEM_VARIAVEL, ITEM_FUNCAO]


def _raiz_com_esperado(tmp_path: Path, linhas: list[str]) -> Path:
    esperado = tmp_path / conferir.ESPERADO
    esperado.parent.mkdir(parents=True)
    esperado.write_text("".join(f"{linha}\n" for linha in linhas), encoding="utf-8")
    return tmp_path


def _vulture_de_mentira(saida: str) -> Callable[[Path], str]:
    return lambda raiz: saida


def test_normalizar_tira_o_numero_da_linha_e_ordena():
    assert conferir.normalizar(SAIDA_DO_VULTURE) == ESPERADO_IGUAL


def test_caminho_do_windows_vira_o_mesmo_item_do_linux():
    windows = (
        "base\\arquivo\\obter.py:491: unreachable code after 'return' (100% confidence)"
    )
    linux = (
        "base/arquivo/obter.py:491: unreachable code after 'return' (100% confidence)"
    )
    assert conferir.normalizar_linha(windows) == conferir.normalizar_linha(linux)


def test_numero_de_linha_diferente_nao_e_diferenca():
    antes = conferir.normalizar("src/a.py:10: unused function 'foo' (60% confidence)\n")
    depois = conferir.normalizar(
        "src/a.py:42: unused function 'foo' (60% confidence)\n"
    )
    assert conferir.comparar(depois, antes).vazia


def test_linha_fora_do_formato_e_erro():
    with pytest.raises(ValueError, match="fora do formato"):
        conferir.normalizar_linha("Error: src could not be found.")


def test_duplicatas_contam_como_multiconjunto():
    diferenca = conferir.comparar(
        [ITEM_INALCANCAVEL, ITEM_INALCANCAVEL], [ITEM_INALCANCAVEL]
    )
    assert diferenca.novos == [ITEM_INALCANCAVEL]
    assert diferenca.sumidos == []


def test_tudo_igual_sai_zero_com_resumo(tmp_path, capsys):
    raiz = _raiz_com_esperado(tmp_path, ESPERADO_IGUAL)

    codigo = conferir.main([], raiz=raiz, rodar=_vulture_de_mentira(SAIDA_DO_VULTURE))

    assert codigo == 0
    saida = capsys.readouterr().out
    assert "2 itens" in saida
    assert "novo:" not in saida
    assert "saiu da lista" not in saida


def test_item_novo_sai_um_e_diz_o_que_fazer(tmp_path, capsys):
    raiz = _raiz_com_esperado(tmp_path, [ITEM_VARIAVEL])

    codigo = conferir.main([], raiz=raiz, rodar=_vulture_de_mentira(SAIDA_DO_VULTURE))

    assert codigo == conferir.SAIDA_LISTA_DIFERENTE
    saida = capsys.readouterr().out
    assert f"novo: {ITEM_FUNCAO}" in saida
    assert "--gravar" in saida
    assert "saiu da lista" not in saida


def test_item_que_sumiu_sai_um_e_pede_gravar(tmp_path, capsys):
    raiz = _raiz_com_esperado(tmp_path, [*ESPERADO_IGUAL, ITEM_INALCANCAVEL])

    codigo = conferir.main([], raiz=raiz, rodar=_vulture_de_mentira(SAIDA_DO_VULTURE))

    assert codigo == conferir.SAIDA_LISTA_DIFERENTE
    saida = capsys.readouterr().out
    assert f"saiu da lista: {ITEM_INALCANCAVEL} (rode --gravar)" in saida
    assert "novo:" not in saida


def test_gravar_reescreve_o_esperado_em_ordem_e_a_conferencia_passa(tmp_path, capsys):
    raiz = _raiz_com_esperado(tmp_path, ["lista velha: qualquer coisa"])
    rodar = _vulture_de_mentira(SAIDA_DO_VULTURE)

    assert conferir.main(["--gravar"], raiz=raiz, rodar=rodar) == 0
    assert (raiz / conferir.ESPERADO).read_bytes() == b"".join(
        f"{item}\n".encode() for item in ESPERADO_IGUAL
    )
    assert conferir.main([], raiz=raiz, rodar=rodar) == 0
    assert "Gravados 2 itens" in capsys.readouterr().out


def test_sem_lista_esperada_pede_gravar(tmp_path, capsys):
    codigo = conferir.main(
        [], raiz=tmp_path, rodar=_vulture_de_mentira(SAIDA_DO_VULTURE)
    )

    assert codigo == conferir.SAIDA_LISTA_DIFERENTE
    assert "rode --gravar" in capsys.readouterr().out


def test_vulture_que_falha_nao_passa_por_lista_diferente(tmp_path, capsys):
    raiz = _raiz_com_esperado(tmp_path, ESPERADO_IGUAL)

    def rodar_quebrado(raiz: Path) -> str:
        raise conferir.VultureFalhou("No module named vulture")

    codigo = conferir.main([], raiz=raiz, rodar=rodar_quebrado)

    assert codigo == conferir.SAIDA_FERRAMENTA_FALHOU
    assert "No module named vulture" in capsys.readouterr().out


def test_comando_do_vulture_leva_alvos_confianca_e_decoradores():
    comando = conferir.comando_do_vulture()

    assert comando[1:3] == ["-m", "vulture"]
    assert set(conferir.ALVOS) <= set(comando)
    assert comando[comando.index("--min-confidence") + 1] == str(
        conferir.CONFIANCA_MINIMA
    )
    decoradores = comando[comando.index("--ignore-decorators") + 1].split(",")
    assert "@*.fixture" in decoradores
    assert "@field_validator" in decoradores
