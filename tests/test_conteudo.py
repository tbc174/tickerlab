"""Testes de src/conteudo.py."""

import pandas as pd
import pytest

from src.conteudo import (
    CAMINHO_ESTRATEGIAS,
    CAMINHO_GLOSSARIO,
    carregar_estrategias,
    carregar_glossario,
    descrever_pior_drawdown,
    proteger_cifrao,
)
from src.indicadores import PiorDrawdown

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
    "Volatilidade móvel",
    "Recuperação de um drawdown",
    "Gráfico de velas (candlestick)",
    "Retorno mensal",
    "Sazonalidade",
    "Base 100",
    "Stop-loss",
    "Take-profit",
    "Stop móvel",
    "Stop por ATR",
    "Risco por operação",
    "Alvo de volatilidade",
    "Treino e teste",
    "Walk-forward",
    "Mapa de parâmetros",
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


# --- Descrição da pior queda ----------------------------------------------------

TOPO = pd.Timestamp("2026-01-10")
FUNDO = pd.Timestamp("2026-04-10")


def test_descricao_de_queda_recuperada():
    pior = PiorDrawdown(-0.253, TOPO, FUNDO, pd.Timestamp("2026-09-10"))
    texto = descrever_pior_drawdown(pior)
    assert "-25,3%" in texto
    assert "10/01/2026" in texto and "10/04/2026" in texto and "10/09/2026" in texto
    assert "153 dias depois" in texto


def test_descricao_de_queda_nao_recuperada():
    texto = descrever_pior_drawdown(PiorDrawdown(-0.4, TOPO, FUNDO, None))
    assert "não voltou" in texto


def test_descricao_de_preco_sempre_subindo():
    texto = descrever_pior_drawdown(PiorDrawdown(0.0, None, None, None))
    assert "nunca ficou abaixo" in texto


def test_descricao_sem_dados():
    texto = descrever_pior_drawdown(PiorDrawdown(float("nan"), None, None, None))
    assert "dados suficientes" in texto


# --- Cifrão: o Streamlit lê "$...$" como fórmula --------------------------------------


def test_proteger_cifrao_poe_barra_antes_de_cada_cifrao():
    assert (
        proteger_cifrao("R$ 1.000 viraram R$ 1.300") == r"R\$ 1.000 viraram R\$ 1.300"
    )


def test_proteger_cifrao_nao_mexe_no_que_nao_tem():
    assert proteger_cifrao("sem moeda") == "sem moeda"
    assert proteger_cifrao("") == ""
    assert proteger_cifrao(None) is None


def test_nenhum_verbete_real_deixa_cifrao_solto_depois_de_protegido():
    for texto in carregar_glossario(CAMINHO_GLOSSARIO).values():
        protegido = proteger_cifrao(texto)
        assert protegido.count("$") == protegido.count(r"\$")


# --- Explicações das estratégias ---------------------------------------------------------

SECOES_DE_UMA_ESTRATEGIA = [
    "**A ideia:**",
    "**A regra:**",
    "**Quando costuma funcionar:**",
    "**Quando costuma falhar:**",
    "**O que olhar nos resultados:**",
]


def test_toda_estrategia_do_registro_tem_explicacao_completa():
    # Se alguém registrar uma estratégia nova e esquecer de explicá-la, este teste avisa.
    from src.estrategias import ESTRATEGIAS

    explicacoes = carregar_estrategias(CAMINHO_ESTRATEGIAS)
    for nome in ESTRATEGIAS:
        assert nome in explicacoes, (
            f"Falta o verbete de {nome} em conteudo/estrategias.md"
        )
        for secao in SECOES_DE_UMA_ESTRATEGIA:
            assert secao in explicacoes[nome], f"{nome}: falta a seção {secao}"


def test_nao_ha_explicacao_sem_estrategia():
    from src.estrategias import ESTRATEGIAS

    assert set(carregar_estrategias(CAMINHO_ESTRATEGIAS)) <= set(ESTRATEGIAS)
