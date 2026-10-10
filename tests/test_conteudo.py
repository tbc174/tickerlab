"""Testes de src/conteudo.py."""

import pytest

from src.conteudo import CAMINHO_GLOSSARIO, carregar_glossario

EXEMPLO = """# Glossário de teste
Texto de introdução, que não é um termo.

---

## Volatilidade
**O que é:** o quanto oscila.

**Cuidado:** não é perda.

## Drawdown
**O que é:** queda desde o topo.
"""


@pytest.fixture
def arquivo_exemplo(tmp_path):
    caminho = tmp_path / "glossario.md"
    caminho.write_text(EXEMPLO, encoding="utf-8")
    return caminho


def test_separa_um_item_por_termo(arquivo_exemplo):
    glossario = carregar_glossario(arquivo_exemplo)
    assert list(glossario) == ["Volatilidade", "Drawdown"]  # na ordem do arquivo


def test_texto_do_termo_vai_ate_o_proximo_termo(arquivo_exemplo):
    glossario = carregar_glossario(arquivo_exemplo)
    assert glossario["Volatilidade"] == (
        "**O que é:** o quanto oscila.\n\n**Cuidado:** não é perda."
    )


def test_ultimo_termo_tambem_e_lido(arquivo_exemplo):
    glossario = carregar_glossario(arquivo_exemplo)
    assert glossario["Drawdown"] == "**O que é:** queda desde o topo."


def test_ignora_o_que_vem_antes_do_primeiro_termo(arquivo_exemplo):
    glossario = carregar_glossario(arquivo_exemplo)
    assert all("introdução" not in texto for texto in glossario.values())


def test_arquivo_vazio_devolve_dicionario_vazio(tmp_path):
    caminho = tmp_path / "vazio.md"
    caminho.write_text("", encoding="utf-8")
    assert carregar_glossario(caminho) == {}


def test_arquivo_inexistente_levanta_erro(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_glossario(tmp_path / "nao-existe.md")


# --- O glossário de verdade ---------------------------------------------------

TERMOS_DO_PAINEL = [
    "Retorno acumulado",
    "Retorno anualizado",
    "Volatilidade",
    "Drawdown",
    "Melhor e pior dia",
    "Índice de Sharpe",
    "Dias de alta",
    "Perda de um dia ruim (VaR)",
]


@pytest.mark.parametrize("termo", TERMOS_DO_PAINEL)
def test_glossario_real_explica_cada_numero_do_painel(termo):
    glossario = carregar_glossario(CAMINHO_GLOSSARIO)
    assert termo in glossario
    assert "**O que é:**" in glossario[termo]


def test_glossario_real_nao_tem_verbete_vazio():
    glossario = carregar_glossario(CAMINHO_GLOSSARIO)
    assert glossario  # tem alguma coisa
    assert all(texto for texto in glossario.values())
