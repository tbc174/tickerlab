"""A rotulagem da fila das 21h por IA (ADR 0072), sem rede.

O que importa aqui são as proteções da ADR: o nome da empresa não chega ao modelo, a resposta só
vale dentro da lista fechada e com o trecho copiado do documento, e o custo é estimado antes.
"""

import json

import pytest

from src import rotulos_ia as ri
from src import topicos

FATO = {
    "id": "020702IPE030920240104553811-12",
    "empresa": "VIVER INCORPORADORA E CONSTRUTORA S.A",
    "setor": "Construção Civil, Mat. Constr. e Decoração",
    "entrega": "2024-09-03",
    "categoria": "Fato Relevante",
    "tipo": "",
    "especie": "",
    "assunto": "Aquisição de controle pela Viver Incorporadora",
}
AVISO = {**FATO, "categoria": "Aviso aos Acionistas", "assunto": "Bônus de Subscrição"}
TEXTO = (
    "A Viver Incorporadora e Construtora S.A. (VIVR3), inscrita no CNPJ 67.571.414/0001-41, "
    "comunica que concluiu a aquisição de 60% da Construtora Alfa por R$ 80 milhões."
)


def _resposta(**campos) -> str:
    base = {"nota": 4, "tema": "fusao", "assunto": "AQUISICAO", "confianca": "alta",
            "trecho": "concluiu a aquisição de 60% da Construtora Alfa"}  # fmt: skip
    return json.dumps({**base, **campos})


# --- anonimizar ---------------------------------------------------------------------------


def test_anonimiza_nome_codigo_e_cnpj():
    texto = ri.anonimizar(TEXTO, [FATO["empresa"]])
    assert "Viver" not in texto and "VIVER" not in texto
    assert "VIVR3" not in texto and "67.571.414/0001-41" not in texto
    assert texto.count(ri.EMPRESA) == 1
    assert ri.CODIGO in texto and ri.CNPJ in texto
    assert "Construtora Alfa" in texto  # outras empresas ficam


def test_anonimiza_sem_acento_e_em_qualquer_caixa():
    nome = "CIA DE SANEAMENTO BÁSICO DO ESTADO DE SÃO PAULO - SABESP"
    texto = "A cia de saneamento basico do estado de sao paulo - sabesp informa."
    assert ri.anonimizar(texto, [nome]) == f"A {ri.EMPRESA} informa."


def test_anonimiza_o_nome_sem_o_sufixo_da_sociedade():
    texto = "A Viver Incorporadora e Construtora informa que a Viver Incorporadora e Construtora S/A"
    assert "Viver" not in ri.anonimizar(texto, [FATO["empresa"]])


def test_codigos_de_negociacao_e_cnpj_sem_mascara():
    texto = "Ações PETR4 e PETR3 e units TAEE11; CNPJ 33000167000101."
    saida = ri.anonimizar(texto, [])
    assert (
        "PETR" not in saida and "TAEE11" not in saida and "33000167000101" not in saida
    )


def test_comeco_do_nome_tambem_e_trocado_mas_palavra_sozinha_nao():
    nome = "BANCO DO ESTADO DO RIO GRANDE DO SUL S.A."
    texto = "O Banco do Estado do Rio Grande informa. Outro banco também."
    assert (
        ri.anonimizar(texto, [nome]) == f"O {ri.EMPRESA} informa. Outro banco também."
    )


def test_nome_vazio_nao_apaga_o_texto():
    assert ri.anonimizar("Texto comum.", ["", "S.A."]) == "Texto comum."


# --- o pedido ---------------------------------------------------------------------------


def test_pedido_sem_nome_da_empresa():
    pedido = json.dumps(ri.pedido(FATO, TEXTO), ensure_ascii=False)
    assert "Viver" not in pedido and "VIVER" not in pedido and "VIVR3" not in pedido
    assert "Construção Civil" in pedido  # o setor vai


def test_pedido_usa_o_guia_v2_e_o_modelo_combinado():
    pedido = ri.pedido(FATO, TEXTO)
    assert pedido["model"] == "claude-sonnet-5-5"
    sistema = pedido["system"][0]["text"]
    assert "Na dúvida entre duas notas, fique com a menor" in sistema
    assert "Muda a tese" in sistema
    assert pedido["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_assunto_so_em_fato_relevante():
    com = ri.pedido(FATO, TEXTO)["output_config"]["format"]["schema"]
    sem = ri.pedido(AVISO, TEXTO)["output_config"]["format"]["schema"]
    assert com["properties"]["assunto"]["enum"] == list(topicos.TOPICOS)
    assert "assunto" not in sem["properties"]
    assert com["additionalProperties"] is False and sem["additionalProperties"] is False


def test_pedido_corta_o_texto_no_comeco():
    longo = "palavra " * 5_000
    conteudo = ri.pedido(AVISO, longo)["messages"][0]["content"]
    assert len(conteudo) < ri.MAX_CARACTERES_DO_TEXTO + 1_000


def test_pedido_sem_texto_avisa_o_modelo():
    conteudo = ri.pedido(AVISO, "")["messages"][0]["content"]
    assert ri.SEM_TEXTO in conteudo


# --- a resposta ---------------------------------------------------------------------------


def test_resposta_valida_vira_rotulo():
    rotulo = ri.interpretar(_resposta(), FATO, TEXTO)
    assert isinstance(rotulo, ri.RotuloDaIA)
    assert (rotulo.nota, rotulo.tema, rotulo.assunto) == (4, "fusao", "AQUISICAO")
    guardado = rotulo.para_guardar()
    assert guardado["por"] == "ia" and guardado["modelo"] == ri.MODELO
    assert (
        guardado["versao_do_prompt"] == ri.VERSAO_DO_PROMPT
        and guardado["guia"] == ri.GUIA
    )


def test_fora_do_fato_relevante_o_assunto_fica_nulo():
    resposta = json.dumps({"nota": 2, "tema": "governanca", "confianca": "media",
                           "trecho": "Bônus de Subscrição"})  # fmt: skip
    rotulo = ri.interpretar(resposta, AVISO, "")
    assert isinstance(rotulo, ri.RotuloDaIA) and rotulo.assunto is None


@pytest.mark.parametrize(
    "resposta",
    [
        "não é json",
        _resposta(nota=6),
        _resposta(nota="4"),
        _resposta(tema="outro"),
        _resposta(assunto="INVENTADO"),
        _resposta(confianca="total"),
        json.dumps({"nota": 4}),
    ],
)
def test_resposta_invalida_vira_erro(resposta):
    assert isinstance(ri.interpretar(resposta, FATO, TEXTO), ri.ErroDeRotulo)


def test_trecho_tem_de_existir_no_texto():
    erro = ri.interpretar(_resposta(trecho="comprou a empresa toda"), FATO, TEXTO)
    assert isinstance(erro, ri.ErroDeRotulo) and "trecho" in erro.motivo


def test_trecho_pode_vir_do_assunto_e_ignora_espacos():
    resposta = _resposta(trecho="Aquisição  de controle")
    assert isinstance(ri.interpretar(resposta, FATO, ""), ri.RotuloDaIA)


def test_trecho_anonimizado_tambem_vale():
    resposta = _resposta(trecho=f"A {ri.EMPRESA} ({ri.CODIGO})")
    assert isinstance(ri.interpretar(resposta, FATO, TEXTO), ri.RotuloDaIA)


def test_recusa_vira_erro():
    erro = ri.de_mensagem(
        stop_reason="refusal", texto="", evento=FATO, texto_do_documento=TEXTO
    )
    assert isinstance(erro, ri.ErroDeRotulo) and "refusal" in erro.motivo


def test_mensagem_completa_vira_rotulo():
    rotulo = ri.de_mensagem("end_turn", _resposta(), FATO, TEXTO)
    assert isinstance(rotulo, ri.RotuloDaIA)


# --- custo ---------------------------------------------------------------------------


def test_custo_em_lote_e_metade():
    normal = ri.custo_em_dolares(1_000_000, 100_000, lote=False)
    assert normal == pytest.approx(2.0 + 1.0)  # Sonnet 5.5: US$ 2 e US$ 10 por milhão
    assert ri.custo_em_dolares(1_000_000, 100_000, lote=True) == pytest.approx(
        normal / 2
    )


def test_estimativa_da_fila_inteira_fica_perto_do_plano():
    # 3.196 eventos x 4.500 tokens de entrada x 500 de saída, pela Batch: ~US$ 22 (plano de 14/10)
    estimativa = ri.custo_em_dolares(
        3_196 * 4_500, 3_196 * ri.SAIDA_ESTIMADA_POR_EVENTO
    )
    assert 15 < estimativa < 30


# --- identificação ---------------------------------------------------------------------------


def test_identificacao_le_o_mesmo_documento_anonimizado():
    pedido = ri.pedido_de_identificacao(FATO, TEXTO)
    assert pedido["messages"][0]["content"] == ri.documento(FATO, TEXTO)
    assert "Viver" not in json.dumps(pedido, ensure_ascii=False)


@pytest.mark.parametrize(
    ("parada", "resposta", "esperado"),
    [
        ("end_turn", '{"empresa": "Viver"}', "Viver"),
        ("end_turn", '{"empresa": ""}', ri.NAO_SEI),
        ("end_turn", "não é json", ri.NAO_SEI),
        ("refusal", '{"empresa": "Viver"}', ri.NAO_SEI),
    ],
)
def test_palpite_da_identificacao(parada, resposta, esperado):
    assert ri.palpite_da_identificacao(parada, resposta) == esperado


def test_cliente_manda_o_workspace_quando_configurado(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste-sem-valor")
    monkeypatch.setenv(ri.VARIAVEL_DO_WORKSPACE, " wrkspc_teste ")
    assert ri.cliente().default_headers["anthropic-workspace-id"] == "wrkspc_teste"
    monkeypatch.delenv(ri.VARIAVEL_DO_WORKSPACE)
    assert "anthropic-workspace-id" not in ri.cliente().default_headers
