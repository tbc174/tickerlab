"""O pedido ao modelo que escreve a análise: o guia (prompt de sistema, em cache), a ficha em JSON e a
saída estruturada no formato de `saida.ESQUEMA`.

O gabarito da CPFL nunca entra aqui: ele é a prova às cegas (plano, decisão 6).
"""

import json
from pathlib import Path
from typing import Any

from src import rotulos_ia as ri
from src.analise_escrita import saida

VERSAO_DO_GUIA = "v1"
GUIA = (Path(__file__).parent / f"guia_{VERSAO_DO_GUIA}.md").read_text(encoding="utf-8")
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
ESCRITORES = (
    HAIKU,
    SONNET,
    OPUS,
)  # D1: a prova com os três; fica o mais barato que passa
# Preços da 0087 (US$ por milhão de tokens). A saída estimada é por relatório, só para o
# `--estimar` (o real vem de `usage`): texto e notas dão uns 8 mil; o raciocínio do Opus, mais.
MODELOS = {
    HAIKU: ri.Modelo(0.10, 0.50, 0.1, 8_000),
    SONNET: ri.Modelo(2.00, 10.00, 0.1, 10_000),
    OPUS: ri.Modelo(4.00, 20.00, 0.05, 16_000),
}
MAX_TOKENS_DA_RESPOSTA = (
    32_000  # 8 partes com notas e contas, mais a folga do raciocínio
)
FIM_NORMAL = "end_turn"
INSTRUCAO = "Escreva a análise completa desta ficha, nas 8 partes, no formato pedido."


def modelo_conhecido(nome: str) -> ri.Modelo:
    """O preço do modelo; um nome fora da lista é erro (nunca o preço de outro)."""
    if nome not in MODELOS:
        raise ValueError(
            f"Modelo sem preço cadastrado: {nome} (conhecidos: {', '.join(MODELOS)})"
        )
    return MODELOS[nome]


def pedido(entrada: dict[str, Any], modelo: str) -> dict[str, Any]:
    """Os parâmetros de `messages.create` (os mesmos servem para o lote)."""
    modelo_conhecido(modelo)
    ficha = json.dumps(entrada, ensure_ascii=False, separators=(",", ":"))
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": GUIA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {"format": {"type": "json_schema", "schema": saida.ESQUEMA}},
        "messages": [
            {"role": "user", "content": f"{INSTRUCAO}\n\n<ficha>\n{ficha}\n</ficha>"}
        ],
    }


def ler_resposta(stop_reason: str | None, texto: str) -> dict[str, Any]:
    """O JSON da resposta; cortada, recusada ou fora do JSON é `RespostaInvalidaError` (vira molde)."""
    if stop_reason != FIM_NORMAL:
        raise saida.RespostaInvalidaError(
            f"a resposta parou antes do fim: {stop_reason}"
        )
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise saida.RespostaInvalidaError(f"a resposta não é JSON: {erro}") from erro
    if not isinstance(dados, dict):
        raise saida.RespostaInvalidaError("a resposta não é um objeto JSON")
    return dados


def custo_em_dolares(
    tokens_entrada: int, tokens_saida: int, modelo: str, lote: bool = False
) -> float:
    """O custo pelos preços do modelo; pela Batch API, a metade."""
    preco = modelo_conhecido(modelo)
    custo = (tokens_entrada * preco.entrada + tokens_saida * preco.saida) / 1_000_000
    return custo * (ri.DESCONTO_DO_LOTE if lote else 1.0)
