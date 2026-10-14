"""A camada do modelo de linguagem do leitor v2 (ADR 0069), com um cliente de mentira (sem rede).

O que importa aqui são os limites da ADR: lista fechada de tópicos, trecho que tem de existir no
documento, nada quando o modelo recusa ou a API falha, e a camada desligada sem chave.
"""

import json
from types import SimpleNamespace

import anthropic
import httpx2

from src import topicos
from src import topicos_modelo as tm

TITULO = "Fato Relevante"
TEXTO = (
    "A Companhia comunica que celebrou com a Sompo Seguros um acordo de parceria para distribuir "
    "seguros aos seus clientes por dez anos. A parceria começa no próximo trimestre."
)


class ClienteDeMentira:
    """Imita `anthropic.Anthropic().messages.create`, guardando o pedido."""

    def __init__(self, resposta: dict | None = None, stop_reason="end_turn", erro=None):
        self.pedidos: list[dict] = []
        self._resposta, self._stop, self._erro = resposta, stop_reason, erro
        self.messages = SimpleNamespace(create=self._criar)

    def _criar(self, **pedido):
        self.pedidos.append(pedido)
        if self._erro:
            raise self._erro
        texto = json.dumps(self._resposta or {})
        return SimpleNamespace(
            stop_reason=self._stop, content=[SimpleNamespace(type="text", text=texto)]
        )


def _resposta(
    principal="JV", trecho="celebrou com a Sompo Seguros um acordo de parceria"
):
    return {"principal": principal, "secundarios": [], "trecho": trecho}


def test_resposta_valida_vira_leitura_do_modelo():
    leitura = tm.ler_com_modelo(ClienteDeMentira(_resposta()), TITULO, TEXTO)
    assert leitura is not None
    assert (leitura.principal, leitura.metodo) == ("JV", "modelo")
    assert leitura.trecho == "celebrou com a Sompo Seguros um acordo de parceria"
    assert leitura.modelo == f"{tm.MODELO} · prompt {tm.VERSAO_DO_PROMPT}"
    assert leitura.versao == topicos.VERSAO


def test_trecho_que_nao_esta_no_documento_e_descartado():
    inventado = _resposta(trecho="adquiriu 100% da Sompo Seguros por R$ 2 bilhões")
    assert tm.ler_com_modelo(ClienteDeMentira(inventado), TITULO, TEXTO) is None


def test_trecho_vale_com_espacos_e_quebras_diferentes():
    texto_com_quebra = TEXTO.replace("acordo de parceria", "acordo\n  de parceria")
    assert (
        tm.ler_com_modelo(ClienteDeMentira(_resposta()), TITULO, texto_com_quebra)
        is not None
    )


def test_topico_fora_da_lista_ou_outros_nao_vale():
    assert (
        tm.ler_com_modelo(
            ClienteDeMentira(_resposta(principal="FOFOCA")), TITULO, TEXTO
        )
        is None
    )
    assert (
        tm.ler_com_modelo(
            ClienteDeMentira(_resposta(principal="OUTROS")), TITULO, TEXTO
        )
        is None
    )


def test_secundarios_fora_da_lista_ou_repetidos_saem():
    resposta = {
        **_resposta(),
        "secundarios": ["JV", "FOFOCA", "DIVIDA", "OPA", "RECOMPRA"],
    }
    leitura = tm.ler_com_modelo(ClienteDeMentira(resposta), TITULO, TEXTO)
    assert leitura is not None and leitura.secundarios == ("DIVIDA", "OPA")


def test_recusa_ou_falha_da_api_deixa_a_regra():
    assert (
        tm.ler_com_modelo(
            ClienteDeMentira(_resposta(), stop_reason="refusal"), TITULO, TEXTO
        )
        is None
    )
    falha = anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com")
    )
    assert tm.ler_com_modelo(ClienteDeMentira(erro=falha), TITULO, TEXTO) is None


def test_pedido_lista_fechada_modelo_pequeno_e_texto_cortado():
    cliente = ClienteDeMentira(_resposta())
    tm.ler_com_modelo(cliente, TITULO, "palavra " * 20_000)
    pedido = cliente.pedidos[0]
    assert pedido["model"] == tm.MODELO == "claude-haiku-5-5"
    formato = pedido["output_config"]["format"]
    assert formato["type"] == "json_schema"
    assert formato["schema"]["properties"]["principal"]["enum"] == list(topicos.TOPICOS)
    assert pedido["output_config"]["effort"] == "low"
    # o prompt fixo fica em cache; o documento vai depois, cortado no começo (onde está o assunto)
    assert pedido["system"][0]["cache_control"] == {"type": "ephemeral"}
    documento = pedido["messages"][0]["content"]
    assert len(documento) <= tm.MAX_CARACTERES_DO_TEXTO + len(TITULO) + 100


def test_sem_chave_a_camada_fica_desligada(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert tm.cliente_da_chave() is None
