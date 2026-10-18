"""A porta 3: a nota de revisão no Obsidian, o veredito do Tiago e o critério de saída da 0100."""

import json

import pytest

from src.analise_escrita import porta3, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

ENTRADA = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
ANALISE = saida.ler_analise(
    json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))["analise"]
)
LINHAGEM = {"modelo": "claude-sonnet-5-5", "hash_da_entrada": "a" * 64}


def _nota() -> str:
    return porta3.nota(ANALISE, ENTRADA, LINHAGEM)


def _com_veredito(veredito: str, motivo: str = "") -> str:
    nota = _nota().replace("veredito: \n", f"veredito: {veredito}\n", 1)
    return nota.replace("motivo: \n", f"motivo: {motivo}\n", 1)


def test_nota_tem_as_propriedades_do_painel():
    propriedades = porta3.propriedades(_nota())
    assert propriedades["tipo"] == "revisao"
    assert propriedades["situacao"] == porta3.ESPERANDO
    assert propriedades["cnpj"] == ENTRADA["cnpj"]
    assert propriedades["hash_da_entrada"] == LINHAGEM["hash_da_entrada"]
    assert propriedades["veredito"] == ""


def test_nota_abre_a_fonte_ao_lado_de_cada_frase():
    nota = _nota()
    for titulo in saida.TITULOS.values():
        assert titulo in nota
    assert (
        "`retorno.roe` ROE (retorno sobre o patrimônio): 26,4% (" in nota
    )  # nome e valor
    assert "*Leitura.*" in nota
    assert "conta nossa:" in nota  # a conta declarada, para conferir à mão


def test_sem_veredito_ainda_espera():
    assert porta3.ler_revisao(_nota()) is None


@pytest.mark.parametrize("veredito", porta3.VEREDITOS)
def test_le_o_veredito(veredito):
    revisao = porta3.ler_revisao(_com_veredito(veredito, "o ROE está certo"))
    assert revisao == porta3.Revisao(
        ENTRADA["cnpj"], LINHAGEM["hash_da_entrada"], veredito, "o ROE está certo"
    )


def test_veredito_fora_da_lista_e_erro():
    with pytest.raises(ValueError, match="veredito"):
        porta3.ler_revisao(_com_veredito("quase"))


def test_criterio_de_saida_pede_200_seguidos_sem_numero_errado():
    aprovados = [porta3.APROVADO] * 200
    assert porta3.criterio_de_saida(aprovados).atingido
    com_erro = [*aprovados[:150], porta3.NUMERO_ERRADO, *aprovados[:199]]
    saida_ = porta3.criterio_de_saida(com_erro)
    assert saida_.seguidos == 199 and not saida_.atingido


def test_criterio_de_saida_aceita_ate_2_por_cento_por_tom():
    quatro = [porta3.TOM] * 4 + [porta3.APROVADO] * 196
    assert porta3.criterio_de_saida(quatro).atingido
    cinco = [porta3.TOM] * 5 + [porta3.APROVADO] * 195
    saida_ = porta3.criterio_de_saida(cinco)
    assert saida_.por_tom == 5 and not saida_.atingido
