"""O pedido ao modelo que escreve: guia em cache, a ficha em JSON, a saída estruturada."""

import json
import re

import pytest

from src.analise_escrita import pedido, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

ENTRADA = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
NOMES_DA_CPFL = (
    "CPFL",
    "CEEE",
    "PwC",
    "KPMG",
    "Deloitte",
    "Enercan",
    "Piratininga",
    "ALESTA",
)
NUMEROS_DO_GUIA = {str(n) for n in range(1, len(saida.PARTES) + 1)} | {"100"}


def _ficha_do_pedido(parametros: dict) -> dict:
    conteudo = parametros["messages"][0]["content"]
    achado = re.search(r"<ficha>\n(.*)\n</ficha>", conteudo, re.DOTALL)
    assert achado is not None
    return json.loads(achado.group(1))


def test_pedido_tem_guia_em_cache_ficha_em_json_e_saida_estruturada():
    parametros = pedido.pedido(ENTRADA, pedido.SONNET)
    (sistema,) = parametros["system"]
    assert sistema["text"] == pedido.GUIA
    assert sistema["cache_control"] == {"type": "ephemeral"}
    formato = parametros["output_config"]["format"]
    assert formato == {"type": "json_schema", "schema": saida.ESQUEMA}
    assert _ficha_do_pedido(parametros) == ENTRADA
    assert parametros["model"] == pedido.SONNET


def test_os_tres_escritores_tem_preco():
    for modelo in pedido.ESCRITORES:
        assert pedido.pedido(ENTRADA, modelo)["model"] == modelo


def test_modelo_sem_preco_e_erro():
    with pytest.raises(ValueError, match="sem preço"):
        pedido.pedido(ENTRADA, "claude-outro")


def test_guia_nao_tem_numero_nem_nome_da_cpfl():
    """O gabarito é a prova às cegas: nada dele pode ensinar o modelo (plano, decisão 6)."""
    assert set(re.findall(r"\d+(?:[.,]\d+)*", pedido.GUIA)) <= NUMEROS_DO_GUIA
    assert [nome for nome in NOMES_DA_CPFL if nome in pedido.GUIA] == []


def test_guia_cita_partes_fato_e_leitura_contas_lacunas_e_proibicoes():
    guia = pedido.GUIA
    assert all(f"`{chave}`" in guia for chave in saida.PARTES)
    assert all(f"`{operacao}`" in guia for operacao in saida.OPERACOES)
    for trecho in (
        "**fato**",
        "**leitura**",
        "`obrigatorias`",
        "conta nossa",
        "`corte`",
    ):
        assert trecho in guia
    for proibida in ("preço-alvo", "vai", "forte", "fraude", "Nome de pessoa"):
        assert proibida in guia


def test_resposta_cortada_ou_fora_do_json_e_invalida():
    with pytest.raises(saida.RespostaInvalidaError, match="max_tokens"):
        pedido.ler_resposta("max_tokens", '{"partes": []}')
    with pytest.raises(saida.RespostaInvalidaError, match="JSON"):
        pedido.ler_resposta("end_turn", "partes: nenhuma")
    assert pedido.ler_resposta("end_turn", '{"partes": []}') == {"partes": []}


def test_custo_pelos_precos_do_modelo():
    milhao = 1_000_000
    assert pedido.custo_em_dolares(milhao, milhao, pedido.SONNET) == pytest.approx(12.0)
    no_lote = pedido.custo_em_dolares(milhao, milhao, pedido.OPUS, lote=True)
    assert no_lote == pytest.approx(12.0)
