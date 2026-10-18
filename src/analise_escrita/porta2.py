"""A porta 2 (0093): um segundo modelo, diferente do que escreveu, confere o sentido de cada frase.

A porta 1 confere que cada número existe na ficha; a 2 confere o que a frase diz com ele ("subiu"
quando caiu, a comparação trocada, a contagem por extenso, o juízo de valor disfarçado). Ela é às
cegas: o pedido não diz quem escreveu nem leva o gabarito. Nunca aprova por falta: frase sem
veredito, veredito fora da lista ou resposta fora do formato reprovam a parte (que vira molde).
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from src.analise_escrita import pedido as pe
from src.analise_escrita import saida

SUSTENTADA = "sustentada"
FORA_DOS_DADOS = "nao_esta_nos_dados"
JUIZO_DE_VALOR = "juizo_de_valor"
VEREDITOS = (SUSTENTADA, FORA_DOS_DADOS, JUIZO_DE_VALOR)
# O veredito de ~150 frases e o raciocínio do modelo, que conta aqui.
MAX_TOKENS_DO_VEREDITO = 32_000
INSTRUCAO = "Confira cada frase desta análise contra a ficha."

SISTEMA = f"""Você confere, frase por frase, uma análise de uma companhia aberta brasileira escrita \
a partir de uma ficha de dados públicos. A ficha vem em JSON, com um `id` por linha; cada frase da \
análise vem com um rótulo entre colchetes, o tipo do parágrafo (fato ou leitura) e as notas (os `id` \
das linhas de onde ela diz ter saído).

Dê um veredito para cada frase, pelo rótulo:

- `{SUSTENTADA}`: as linhas citadas sustentam o que a frase diz, inclusive o sentido (subiu ou caiu, \
acima ou abaixo, a comparação certa, a contagem escrita por extenso). Uma leitura também é sustentada \
quando segue dos fatos logo acima e diz o que os dados não permitem concluir. Um título curto ou uma \
frase sem número que só anuncia o assunto é sustentada.
- `{FORA_DOS_DADOS}`: a frase afirma algo que as linhas citadas não dizem (um número, um sentido, \
uma causa, um nome, uma data), ou tira uma conclusão que os fatos não sustentam.
- `{JUIZO_DE_VALOR}`: a frase recomenda, prevê, elogia ou condena (forte, fraco, barato, \
oportunidade, vai subir), ou acusa alguém.

Em `motivo`, uma frase curta dizendo o que não está nos dados ou qual é o juízo (vazio quando \
sustentada). Julgue todas as frases; na dúvida, não marque como sustentada."""

_ITEM = {
    "type": "object",
    "properties": {
        "frase": {"type": "string", "description": "o rótulo da frase"},
        "veredito": {"type": "string", "enum": list(VEREDITOS)},
        "motivo": {"type": "string"},
    },
    "required": ["frase", "veredito", "motivo"],
    "additionalProperties": False,
}
ESQUEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"frases": {"type": "array", "items": _ITEM}},
    "required": ["frases"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Veredito:
    # (rótulo, veredito, motivo) de cada frase, para a linhagem
    frases: tuple[tuple[str, str, str], ...]
    reprovadas: frozenset[str]  # as partes que voltam ao molde
    motivo: str | None = None  # por que a resposta inteira não valeu


def conferente(escritor: str) -> str:
    """Sempre outro modelo: o Sonnet confere os outros; o Opus confere o Sonnet."""
    return pe.OPUS if escritor == pe.SONNET else pe.SONNET


def _rotulo(chave: str, paragrafo: int, frase: int) -> str:
    return f"{chave}.{paragrafo}.{frase}"


def frases_rotuladas(analise: saida.Analise) -> list[tuple[str, saida.Frase]]:
    """Cada frase com o rótulo `parte.parágrafo.frase` (contando do zero), na ordem do texto."""
    return [
        (_rotulo(parte.chave, i, j), frase)
        for parte in analise.partes
        for i, paragrafo in enumerate(parte.paragrafos)
        for j, frase in enumerate(paragrafo.frases)
    ]


def _linhas_da_analise(analise: saida.Analise) -> Iterator[str]:
    tipos = {
        _rotulo(p.chave, i, j): g.tipo
        for p in analise.partes
        for i, g in enumerate(p.paragrafos)
        for j in range(len(g.frases))
    }
    for rotulo, frase in frases_rotuladas(analise):
        notas = ", ".join(frase.notas) or "sem notas"
        yield f"[{rotulo}] ({tipos[rotulo]}) {frase.texto}  {{notas: {notas}}}"


def pedido(
    analise: saida.Analise, entrada: dict[str, Any], modelo: str
) -> dict[str, Any]:
    """Os parâmetros de `messages.create` para conferir a análise (sem dizer quem escreveu)."""
    pe.modelo_conhecido(modelo)
    ficha = json.dumps(entrada, ensure_ascii=False, separators=(",", ":"))
    texto = "\n".join(_linhas_da_analise(analise))
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DO_VEREDITO,
        "system": [
            {"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {"format": {"type": "json_schema", "schema": ESQUEMA}},
        "messages": [
            {
                "role": "user",
                "content": f"{INSTRUCAO}\n\n<ficha>\n{ficha}\n</ficha>\n\n"
                f"<analise>\n{texto}\n</analise>",
            }
        ],
    }


def _julgadas(dados: dict[str, Any]) -> dict[str, tuple[str, str]]:
    itens = dados.get("frases")
    if not isinstance(itens, list):
        raise saida.RespostaInvalidaError("o veredito não tem a lista de frases")
    return {
        str(item.get("frase")): (str(item.get("veredito")), str(item.get("motivo", "")))
        for item in itens
        if isinstance(item, dict)
    }


def ler_veredito(
    stop_reason: str | None, texto: str, analise: saida.Analise
) -> Veredito:
    """As partes reprovadas; resposta cortada ou fora do formato reprova todas."""
    try:
        julgadas = _julgadas(pe.ler_resposta(stop_reason, texto))
    except saida.RespostaInvalidaError as erro:
        return Veredito((), frozenset(p.chave for p in analise.partes), str(erro))
    frases, reprovadas = [], set()
    for rotulo, _ in frases_rotuladas(analise):
        veredito, motivo = julgadas.get(rotulo, ("sem veredito", ""))
        frases.append((rotulo, veredito, motivo))
        if veredito != SUSTENTADA:
            reprovadas.add(rotulo.split(".")[0])
    return Veredito(tuple(frases), frozenset(reprovadas))
