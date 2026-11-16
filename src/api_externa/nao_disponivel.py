"""Um jeito só de dizer "não disponível para a sua organização" na API externa (linhas 878 e 880 a 882).

Um pedido pode juntar partes (os tipos de evento, os tipos de vínculo, os sinais, os blocos) que o portão da
organização libera uma a uma. A parte que o portão não libera não pode sumir em silêncio: a lista vazia ou o
bloco que falta leria como "a empresa não tem". O padrão, em todo conjunto:

- a resposta traz a lista das partes pedidas que o portão não libera, com o nome de fora
  `unavailable_<o que>` (por dentro, `<o que>_nao_disponiveis`), vazia quando tudo foi servido;
- os limites (`limits`) só falam das partes servidas e, quando há parte de fora, trazem o aviso de `aviso`;
- a parte conta como de fora quando o portão não a libera ou quando a base não tem a tabela dela: nos dois
  casos ela não foi consultada;
- quando nenhuma parte pedida é liberada, a resposta é 404 `not_available`, como o resto do contrato.
"""

from collections.abc import Iterable, Mapping, Sequence

from src.api_externa.nomes import NOMES_DE_FORA


def nao_disponiveis(servidas: Mapping[str, Sequence[str]]) -> list[str]:
    """As partes pedidas sem nenhum campo liberado pelo portão, na ordem do pedido."""
    return [parte for parte, campos in servidas.items() if not campos]


def aviso(chave: str, o_que: str, resposta: str) -> str:
    """A frase dos limites que diz que as partes da lista `chave` (o nome de dentro) não foram consultadas.

    `o_que` é o nome das partes no plural ("tipos"); `resposta`, o que não diz nada sobre elas ("a lista de
    eventos"). A frase cita o nome de fora da lista, o mesmo que sai na resposta."""
    return (
        f"Os {o_que} em {NOMES_DE_FORA[chave]} não estão disponíveis para esta organização e não foram "
        f"consultados: {resposta} não diz nada sobre eles."
    )


def limites(
    gerais: Sequence[str],
    das_partes: Mapping[str, str | tuple[str, ...]],
    servidas: Iterable[str],
    nao_disponiveis: Sequence[str],
    aviso: str,
    *,
    antes: int = 1,
) -> list[str]:
    """Os limites da resposta: os `antes` primeiros gerais (o do `known_at` e o que descreve o pedido), as
    frases das partes servidas (na ordem de `das_partes`, sem repetir a frase que vale para mais de uma; uma
    parte pode ter mais de uma frase), o aviso quando alguma parte ficou de fora e o resto dos gerais. A frase
    de uma parte que não foi servida não entra: a resposta não afirma o que não consultou."""
    servidas_ = set(servidas)
    frases = dict.fromkeys(
        frase
        for parte, da_parte in das_partes.items()
        if parte in servidas_
        for frase in ((da_parte,) if isinstance(da_parte, str) else da_parte)
    )
    return [
        *gerais[:antes],
        *frases,
        *([aviso] if nao_disponiveis else []),
        *gerais[antes:],
    ]
