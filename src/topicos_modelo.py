"""A camada 3 do leitor v2: um modelo de linguagem só para o que as regras deixam em "Outros".

Os limites vêm da ADR 0069 (exceção à 0020, que manteve o Research sem IA de terceiros):

- o modelo **escolhe numa lista fechada** de tópicos (saída estruturada); nunca escreve texto que vá
  para a tela, nunca produz número nem resumo;
- devolve um **trecho que tem de existir literalmente** no título ou no texto (comparado sem diferença
  de espaços e quebras de linha); se não existir, a resposta é descartada e fica a regra;
- recusa, falha da API ou "Outros" também deixam a regra;
- **sem a chave** (`ANTHROPIC_API_KEY` no servidor), a camada fica desligada.

Só documentos públicos (fatos relevantes da CVM) vão para o modelo. Modelo pequeno e esforço baixo:
é uma classificação curta. O prompt fixo fica em cache; o documento vai cortado no começo, onde está o
assunto (o mesmo que a camada 2 lê).
"""

import json
import logging
import os

import anthropic

from src import topicos

log = logging.getLogger("tickerlab.topicos")

MODELO = "claude-haiku-5-5"
VERSAO_DO_PROMPT = "1"
METODO = "modelo"
MAX_CARACTERES_DO_TEXTO = 6_000  # ~1.500 tokens: o começo do documento
MAX_TOKENS_DA_RESPOSTA = 512
VARIAVEL_DA_CHAVE = "ANTHROPIC_API_KEY"

_DEFINICOES = "\n".join(
    f"- {codigo}: {nome}" for codigo, nome in topicos.TOPICOS.items()
)
SISTEMA = f"""Você classifica fatos relevantes de companhias abertas brasileiras (documentos públicos da \
CVM) pelo assunto principal.

Tópicos possíveis (use só os códigos):
{_DEFINICOES}

Regras:
1. "principal" é o assunto central do fato: o que a empresa está comunicando, não o histórico nem as \
ressalvas.
2. "secundarios" são até 2 outros assuntos tratados no mesmo fato (pode ser vazio).
3. "trecho" é uma frase ou parte de frase copiada **exatamente** do documento que mostra o assunto \
principal. Não resuma nem traduza.
4. Se o documento não deixa claro o assunto, responda "OUTROS" com o trecho vazio.
5. Fusão, incorporação de empresa e incorporação de ações são FUSAO_INCORPORACAO; OPA para \
cancelamento de registro é FECHAMENTO_CAPITAL; recompra de ações é RECOMPRA, não AQUISICAO."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "principal": {"type": "string", "enum": list(topicos.TOPICOS)},
        "secundarios": {
            "type": "array",
            "items": {"type": "string", "enum": list(topicos.TOPICOS)},
        },
        "trecho": {"type": "string"},
    },
    "required": ["principal", "secundarios", "trecho"],
    "additionalProperties": False,
}


def cliente_da_chave() -> anthropic.Anthropic | None:
    """O cliente da API, ou None sem a chave no ambiente (a camada fica desligada)."""
    if not os.environ.get(VARIAVEL_DA_CHAVE):
        return None
    return anthropic.Anthropic()


def pedido(titulo: str, texto: str) -> dict:
    """Os parâmetros de `messages.create` para um fato (os mesmos servem para o lote)."""
    return {
        "model": MODELO,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": ESQUEMA},
        },
        "messages": [
            {
                "role": "user",
                "content": f"Título: {titulo}\n\nTexto:\n{texto[:MAX_CARACTERES_DO_TEXTO]}",
            }
        ],
    }


def _junto(texto: str) -> str:
    return " ".join(texto.split())


def interpretar(
    resposta: str, titulo: str, texto: str
) -> topicos.LeituraDoTopico | None:
    """A resposta do modelo vira leitura só se respeitar os limites da ADR 0069."""
    try:
        dados = json.loads(resposta)
    except json.JSONDecodeError:
        return None
    principal, trecho = dados.get("principal"), _junto(str(dados.get("trecho", "")))
    if principal not in topicos.TOPICOS or principal == topicos.OUTROS or not trecho:
        return None
    documento = _junto(f"{titulo} {texto[:MAX_CARACTERES_DO_TEXTO]}")
    if trecho not in documento:
        log.info("Trecho do modelo não está no documento: resposta descartada.")
        return None
    secundarios = [
        s for s in dict.fromkeys(dados.get("secundarios") or [])
        if s in topicos.TOPICOS and s not in (principal, topicos.OUTROS)
    ]  # fmt: skip
    return topicos.LeituraDoTopico(
        principal,
        tuple(secundarios[: topicos.MAX_SECUNDARIOS]),
        trecho,
        METODO,
        topicos.VERSAO,
        f"{MODELO} · prompt {VERSAO_DO_PROMPT}",
    )


def ler_com_modelo(
    cliente: anthropic.Anthropic, titulo: str, texto: str
) -> topicos.LeituraDoTopico | None:
    """O assunto pelo modelo, ou None (recusa, falha, "Outros" ou trecho que não está no documento)."""
    try:
        resposta = cliente.messages.create(**pedido(titulo, texto))
    except anthropic.APIError as erro:
        log.warning("Modelo indisponível, fica a regra: %s", erro)
        return None
    if resposta.stop_reason != "end_turn":  # recusa ou resposta cortada
        return None
    texto_da_resposta = next((b.text for b in resposta.content if b.type == "text"), "")
    return interpretar(texto_da_resposta, titulo, texto)
