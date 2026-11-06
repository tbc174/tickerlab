"""O pedido ao modelo que escreve a análise: o guia (prompt de sistema, em cache), a ficha em JSON e a
saída estruturada no formato de `saida.ESQUEMA`.

A entrada de um setor (molde D) tem o próprio guia, a própria instrução e o esquema das 7 partes do
setor. Os gabaritos (o da CPFL e o do setor elétrico) nunca entram aqui: são a prova às cegas (plano,
decisão 6).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src import rotulos_ia as ri
from src.analise_escrita import saida

VERSAO_DO_GUIA = "v1"
VERSAO_DO_GUIA_DO_SETOR = "setor_v2"
GUIA = (Path(__file__).parent / f"guia_{VERSAO_DO_GUIA}.md").read_text(encoding="utf-8")
GUIA_DO_SETOR = (
    Path(__file__).parent / f"guia_{VERSAO_DO_GUIA_DO_SETOR}.md"
).read_text(encoding="utf-8")
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
# O raciocínio do modelo conta aqui e não aparece no texto: na 1ª prova da CPFL ele comeu de 20 mil
# (Opus) a 32 mil (Haiku, que não chegou a escrever) dos 32 mil; as 8 partes ocupam ~9 mil.
MAX_TOKENS_DA_RESPOSTA = 64_000
CORTADA = "max_tokens"
FIM_NORMAL = "end_turn"
INSTRUCAO = "Escreva a análise completa desta ficha, nas 8 partes, no formato pedido."
INSTRUCAO_DO_SETOR = "Escreva a análise completa deste relatório do setor, nas 7 partes, no formato pedido."


@dataclass(frozen=True)
class Guia:
    """O que muda no pedido entre a análise de uma empresa e a de um setor."""

    versao: str
    texto: str
    instrucao: str
    esquema: dict[str, Any]


DA_EMPRESA = Guia(VERSAO_DO_GUIA, GUIA, INSTRUCAO, saida.ESQUEMA)
DO_SETOR = Guia(
    VERSAO_DO_GUIA_DO_SETOR,
    GUIA_DO_SETOR,
    INSTRUCAO_DO_SETOR,
    saida.esquema(saida.PARTES_DO_SETOR),
)


def guia_de(entrada: dict[str, Any]) -> Guia:
    return DO_SETOR if entrada.get("tipo") == saida.TIPO_SETOR else DA_EMPRESA


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
    guia = guia_de(entrada)
    ficha = json.dumps(entrada, ensure_ascii=False, separators=(",", ":"))
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": guia.texto, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {"format": {"type": "json_schema", "schema": guia.esquema}},
        "messages": [
            {
                "role": "user",
                "content": f"{guia.instrucao}\n\n<ficha>\n{ficha}\n</ficha>",
            }
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
