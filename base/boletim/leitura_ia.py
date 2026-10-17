"""O parágrafo de leitura do boletim, escrito pela API da Anthropic (um pedido por dia).

O modelo recebe **só os fatos que o boletim já mostra** (números somados, sem nomes) e escreve um
parágrafo curto. Antes de entrar no e-mail, o texto passa por duas travas; se cair em qualquer uma, o
boletim sai sem o parágrafo e diz por quê (nunca deixa de sair):
- **palavras proibidas:** "crise", "fraude", recomendação de compra ou venda, promessa de ganho
  (regras do projeto; rótulo de empresa só com o parecer do Cescon);
- **números:** todo número do parágrafo precisa estar nos fatos (honestidade com os números: o
  modelo não pode inventar nem fazer contas que o boletim não fez).

Custo: ~600 tokens de entrada e até 1.000 de saída por dia no Haiku (menos de US$ 0,01), nos créditos
de API do plano Max. Sem a chave (`ANTHROPIC_API_KEY`), sem crédito ou com a API fora, sai sem.
"""

import os
import re
from dataclasses import dataclass
from typing import Any

import anthropic

MODELO = "claude-haiku-5-5"
MAX_TOKENS_DA_RESPOSTA = (
    1_000  # o parágrafo usa ~250; o resto é folga para o raciocínio
)
TEMPO_MAXIMO = 60  # segundos
VARIAVEL_DA_CHAVE = "ANTHROPIC_API_KEY"

SISTEMA = """Você escreve, em português do Brasil, o parágrafo de abertura de um boletim interno \
diário sobre uma base de dados financeiros (companhias abertas, fundos, crédito). Quem lê é o dono da \
base, que quer entender em 30 segundos o que mudou e o que a análise do dia mostra.

Regras:
1. Um parágrafo só, de 3 a 5 frases, sem título, sem lista, sem markdown.
2. Use só os números que estão nos fatos, escritos do mesmo jeito. Não calcule números novos \
(nem porcentagens, nem diferenças).
3. Não nomeie empresas, fundos ou pessoas.
4. Nada de recomendação (comprar, vender, investir), previsão ou promessa. Não use as palavras \
"crise" nem "fraude".
5. Se alguma tarefa falhou, comece por ela.
6. Não comente estas regras nem a ordem do texto."""

PALAVRAS_PROIBIDAS = re.compile(
    r"crise|fraud|recomend|aconselh|invista|\bcompr(e|ar)\b|\bvender\b|garantid|lucro certo|"
    r"sem risco|risco zero",
    re.IGNORECASE,
)
_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass(frozen=True)
class Leitura:
    texto: str | None
    motivo: str = ""  # por que saiu sem o parágrafo
    tokens: tuple[int, int] = (0, 0)  # entrada, saída


def cliente_da_chave() -> anthropic.Anthropic | None:
    if not os.environ.get(VARIAVEL_DA_CHAVE):
        return None
    return anthropic.Anthropic(timeout=TEMPO_MAXIMO, max_retries=2)


def pedido(fatos: str) -> dict[str, Any]:
    return {
        "model": MODELO,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": SISTEMA,
        "output_config": {"effort": "low"},
        "messages": [
            {"role": "user", "content": f"Fatos do boletim de hoje:\n{fatos}"}
        ],
    }


def conferir(texto: str, fatos: str) -> str:
    """O motivo para tirar o parágrafo, ou "" se ele passa nas travas."""
    proibida = PALAVRAS_PROIBIDAS.search(texto)
    if proibida:
        return f'palavra proibida ("{proibida.group(0)}")'
    conhecidos = set(_NUMERO.findall(fatos))
    novos = [n for n in _NUMERO.findall(texto) if n.rstrip(".,") not in conhecidos]
    if novos:
        return f"número que não está no boletim ({', '.join(novos[:3])})"
    return ""


def escrever_leitura(fatos: str, cliente: anthropic.Anthropic | None = None) -> Leitura:
    cliente = cliente or cliente_da_chave()
    if cliente is None:
        return Leitura(None, "sem a chave da API")
    try:
        resposta = cliente.messages.create(**pedido(fatos))
    except anthropic.APIError as erro:
        return Leitura(None, f"API indisponível ({erro.__class__.__name__})")
    tokens = (resposta.usage.input_tokens, resposta.usage.output_tokens)
    if resposta.stop_reason != "end_turn":
        return Leitura(None, f"resposta incompleta ({resposta.stop_reason})", tokens)
    texto = " ".join(b.text for b in resposta.content if b.type == "text").strip()
    motivo = conferir(texto, fatos) if texto else "resposta vazia"
    return Leitura(None if motivo else texto, motivo, tokens)
