"""A porta 2 dos gráficos (plano de 23/10/2026): outro modelo, às cegas, julga cada gráfico.

A porta 1 confere que a tabela existe e serve à forma; a 2 confere o sentido: se o gráfico mostra o
que o porquê diz, se ajuda a ler o parágrafo onde fica, se a forma não engana (anos que não se
comparam, um passo que não soma) e se o título ou o porquê não julgam nem preveem. Como na porta 2
do texto, o pedido não diz quem escolheu, e nunca aprova por falta: item sem veredito, veredito fora
da lista ou resposta fora do formato reprovam o item (que dá lugar à reserva).

O conferente vê os pontos de cada gráfico como a ficha os escreve, não a ficha inteira: é o que o
leitor vai ver desenhado. Para o destaque, vê as linhas da seção.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from src.analise_escrita import graficos as gr
from src.analise_escrita import pedido as pe
from src.analise_escrita import pedido_dos_graficos as pg
from src.analise_escrita import porta1_dos_graficos as p1g
from src.analise_escrita import porta2, saida

MOSTRA = "mostra"
NAO_MOSTRA = "nao_mostra"
ENGANA = "engana"
VEREDITOS = (MOSTRA, NAO_MOSTRA, ENGANA, porta2.JUIZO_DE_VALOR)
MAX_TOKENS_DO_VEREDITO = 16_000
INSTRUCAO = "Julgue cada gráfico e cada destaque escolhidos para este relatório."

SISTEMA = f"""Você confere os gráficos e os destaques escolhidos para o relatório de uma companhia \
aberta brasileira. O texto do relatório vem com o rótulo de cada parágrafo; cada item vem com um \
rótulo entre colchetes, a forma, a tabela, as colunas, o título, a frase do porquê com as notas (os \
`id` das linhas de onde ela diz ter saído), o parágrafo junto do qual o item fica e os pontos que o \
código vai desenhar, escritos como a ficha os escreve.

Dê um veredito para cada item, pelo rótulo:

- `{MOSTRA}`: o desenho mostra o que o porquê diz, o porquê está nos pontos ou nas linhas citadas, e o \
item ajuda a ler o parágrafo junto do qual fica.
- `{NAO_MOSTRA}`: o porquê afirma algo que os pontos não mostram (um sentido, uma causa, um número), \
ou o item não tem relação com o parágrafo, ou a coluna escolhida não mede nada que o texto discuta \
(um código, um número de norma).
- `{ENGANA}`: a forma distorce o que os dados dizem: períodos que não se comparam lado a lado (um ano \
incompleto entre anos inteiros), passos de uma cascata que não somam de um total ao outro, colunas que \
medem coisas diferentes no mesmo eixo.
- `{porta2.JUIZO_DE_VALOR}`: o título ou o porquê recomenda, prevê, elogia ou condena.

Em `motivo`, uma frase curta (vazio quando mostra). Julgue todos os itens; na dúvida, não marque \
como `{MOSTRA}`."""

_ITEM = {
    "type": "object",
    "properties": {
        "item": {"type": "string", "description": "o rótulo do item"},
        "veredito": {"type": "string", "enum": list(VEREDITOS)},
        "motivo": {"type": "string"},
    },
    "required": ["item", "veredito", "motivo"],
    "additionalProperties": False,
}
ESQUEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"itens": {"type": "array", "items": _ITEM}},
    "required": ["itens"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Veredito:
    itens: tuple[
        tuple[str, str, str], ...
    ]  # (rótulo, veredito, motivo), para a linhagem
    reprovados: frozenset[str]  # os rótulos que saem da escolha
    motivo: str | None = None  # por que a resposta inteira não valeu


def rotulos(escolha: gr.Escolha) -> list[str]:
    """Os rótulos de todos os itens, na ordem da escolha: `grafico.0`, ..., `destaque.0`, ..."""
    return [p1g.rotulo(p1g.GRAFICO, i) for i in range(len(escolha.graficos))] + [
        p1g.rotulo(p1g.DESTAQUE, i) for i in range(len(escolha.destaques))
    ]


def _paragrafo(analise: saida.Analise, parte: str, indice: int) -> str:
    for p in analise.partes:
        if p.chave == parte and indice < len(p.paragrafos):
            return " ".join(f.texto for f in p.paragrafos[indice].frases)
    return "(parágrafo inexistente)"


def _porque(frase: saida.Frase) -> str:
    return f'porquê: "{frase.texto}" {{notas: {", ".join(frase.notas) or "sem notas"}}}'


def _pontos(grafico: gr.Grafico, entrada: dict[str, Any]) -> str:
    linhas = gr.tabelas_da_entrada(entrada).get(grafico.tabela, [])
    return " | ".join(
        f"{linha.celulas.get(grafico.eixo)}: "
        + ", ".join(f"{c} {linha.celulas.get(c)}" for c in grafico.colunas)
        for linha in linhas
    )


def _linhas_dos_itens(
    escolha: gr.Escolha, entrada: dict[str, Any], analise: saida.Analise
) -> Iterator[str]:
    for i, g in enumerate(escolha.graficos):
        yield (
            f"[{p1g.rotulo(p1g.GRAFICO, i)}] {g.tipo} da tabela {g.tabela}, eixo {g.eixo}, "
            f'colunas {", ".join(g.colunas)}; título: "{g.titulo}"; {_porque(g.por_que)}; '
            f"junto de [{g.parte}.{g.paragrafo}]: {_paragrafo(analise, g.parte, g.paragrafo)}\n"
            f"  pontos: {_pontos(g, entrada)}"
        )
    for i, d in enumerate(escolha.destaques):
        prefixo = f"{d.secao}."
        da_secao = [li for li in entrada["linhas"] if li["id"].startswith(prefixo)]
        secao = json.dumps(da_secao, ensure_ascii=False, separators=(",", ":"))
        yield (
            f"[{p1g.rotulo(p1g.DESTAQUE, i)}] a seção {d.secao} junto da parte {d.parte}; "
            f"{_porque(d.por_que)}\n  linhas da seção: {secao}"
        )


def pedido(
    escolha: gr.Escolha, entrada: dict[str, Any], analise: saida.Analise, modelo: str
) -> dict[str, Any]:
    """Os parâmetros de `messages.create` para julgar a escolha (sem dizer quem escolheu)."""
    pe.modelo_conhecido(modelo)
    itens = "\n".join(_linhas_dos_itens(escolha, entrada, analise))
    conteudo = (
        f"{INSTRUCAO}\n\n<analise>\n{pg.texto_da_analise(analise)}\n</analise>\n\n"
        f"<itens>\n{itens}\n</itens>"
    )
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DO_VEREDITO,
        "system": [
            {"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {"format": {"type": "json_schema", "schema": ESQUEMA}},
        "messages": [{"role": "user", "content": conteudo}],
    }


def _julgados(dados: dict[str, Any]) -> dict[str, tuple[str, str]]:
    itens = dados.get("itens")
    if not isinstance(itens, list):
        raise saida.RespostaInvalidaError("o veredito não tem a lista de itens")
    return {
        str(item.get("item")): (str(item.get("veredito")), str(item.get("motivo", "")))
        for item in itens
        if isinstance(item, dict)
    }


def ler_veredito(stop_reason: str | None, texto: str, escolha: gr.Escolha) -> Veredito:
    """Os itens reprovados; resposta cortada ou fora do formato reprova todos."""
    todos = rotulos(escolha)
    try:
        julgados = _julgados(pe.ler_resposta(stop_reason, texto))
    except saida.RespostaInvalidaError as erro:
        return Veredito((), frozenset(todos), str(erro))
    itens = [(r, *julgados.get(r, ("sem veredito", ""))) for r in todos]
    reprovados = frozenset(r for r, veredito, _ in itens if veredito != MOSTRA)
    return Veredito(tuple(itens), reprovados)
