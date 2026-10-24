"""O pedido ao modelo que escolhe os gráficos (plano de 23/10/2026): um pedido à parte, depois do
texto aprovado, para não refazer nenhuma análise.

O guia (em cache) traz o cardápio gerado de `graficos.CARDAPIO`, para o modelo e a porta 1 lerem a
mesma lista. A mensagem leva a ficha, um resumo das tabelas (colunas e quantos pontos com número ou
data cada uma tem: o que a porta 1 vai conferir) e o texto aprovado com o rótulo de cada parágrafo.
"""

import json
from pathlib import Path
from typing import Any

from src.analise_escrita import graficos as gr
from src.analise_escrita import pedido as pe
from src.analise_escrita import saida

VERSAO_DO_GUIA = "graficos_v3"
_MARCA_DO_CARDAPIO = "{{CARDAPIO}}"
# A escolha tem uns 2 mil tokens; o resto é folga para o raciocínio, que conta aqui.
MAX_TOKENS_DA_ESCOLHA = 16_000
INSTRUCAO = "Escolha os gráficos e os destaques deste relatório, no formato pedido."


def _quantas_colunas(minimo: int, maximo: int) -> str:
    if maximo == 1:
        return "1 coluna"
    return f"{minimo} colunas" if minimo == maximo else f"{minimo} a {maximo} colunas"


def texto_do_cardapio() -> str:
    """O cardápio em Markdown, uma forma por item, do jeito que o guia mostra ao modelo."""
    return "\n".join(
        f"- `{tipo}`: eixo de {'datas' if forma.eixo == gr.TEMPO else 'nomes ou passos'}; "
        f"{_quantas_colunas(*forma.colunas)} de valor; ao menos {forma.pontos} ponto(s) com "
        f"número. Serve para {forma.quando_serve}."
        for tipo, forma in gr.CARDAPIO.items()
    )


GUIA = (
    (Path(__file__).parent / f"guia_{VERSAO_DO_GUIA}.md")
    .read_text(encoding="utf-8")
    .replace(_MARCA_DO_CARDAPIO, texto_do_cardapio())
)


def _resumo_da_coluna(coluna: str, linhas: list[gr.LinhaDaTabela]) -> str:
    celulas = [linha.celulas.get(coluna) for linha in linhas]
    com_numero = sum(gr.valor_da_celula(c) is not None for c in celulas)
    com_data = sum(gr.momento_da_celula(c) is not None for c in celulas)
    return f"{coluna} [número em {com_numero}, data em {com_data}]"


def resumo_das_tabelas(entrada: dict[str, Any]) -> str:
    """Uma linha por tabela: o id, quantas linhas e cada coluna com quantos pontos servem."""
    resumo = []
    for tabela, linhas in gr.tabelas_da_entrada(entrada).items():
        colunas = dict.fromkeys(c for linha in linhas for c in linha.celulas)
        partes = "; ".join(_resumo_da_coluna(c, linhas) for c in colunas)
        resumo.append(f"{tabela} ({len(linhas)} linhas): {partes}")
    return "\n".join(resumo)


def texto_da_analise(analise: saida.Analise) -> str:
    """Cada parágrafo com o rótulo `parte.parágrafo`, que é a âncora do gráfico."""
    return "\n".join(
        f"[{parte.chave}.{i}] ({paragrafo.tipo}) "
        + " ".join(frase.texto for frase in paragrafo.frases)
        for parte in analise.partes
        for i, paragrafo in enumerate(parte.paragrafos)
    )


def pedido(
    entrada: dict[str, Any], analise: saida.Analise, modelo: str
) -> dict[str, Any]:
    """Os parâmetros de `messages.create` para escolher os gráficos de um relatório já escrito."""
    pe.modelo_conhecido(modelo)
    ficha = json.dumps(entrada, ensure_ascii=False, separators=(",", ":"))
    conteudo = (
        f"{INSTRUCAO}\n\n<ficha>\n{ficha}\n</ficha>\n\n"
        f"<tabelas>\n{resumo_das_tabelas(entrada)}\n</tabelas>\n\n"
        f"<analise>\n{texto_da_analise(analise)}\n</analise>"
    )
    esquema = gr.esquema(saida.partes_de(entrada))
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_ESCOLHA,
        "system": [
            {"type": "text", "text": GUIA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {"format": {"type": "json_schema", "schema": esquema}},
        "messages": [{"role": "user", "content": conteudo}],
    }


def ler_resposta(stop_reason: str | None, texto: str) -> gr.Escolha:
    """A escolha da resposta; cortada ou fora do formato é `RespostaInvalidaError` (fica a reserva)."""
    return gr.ler_escolha(pe.ler_resposta(stop_reason, texto))
