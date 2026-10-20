"""A análise que vai para a tela: parte do modelo que passou nas portas, parte do molde que não.

O molde entra parte por parte, nunca frase por frase (um texto remendado no meio leria mal), e a
análise inteira vira molde quando não há resposta, quando ela sai do formato ou quando a ficha
mudou desde que o texto foi escrito: texto com número velho nunca vai para a tela (plano, item 7).
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any

from src.analise_escrita import entrada as en
from src.analise_escrita import pedido as pe
from src.analise_escrita import porta1, saida
from src.analise_escrita.molde import molde

SEM_RESPOSTA = "sem resposta do modelo"
FICHA_NOVA = "análise sendo reescrita com os números novos"
FORA_DO_FORMATO = "resposta fora do formato"


@dataclass(frozen=True)
class Montagem:
    analise: saida.Analise
    # a porta 1 na resposta (None: nem chegou a ela)
    conferencia: porta1.Conferencia | None
    # por que a análise inteira saiu do molde (vai para a linhagem)
    motivo: str | None = None


def _so_pro(entrada: dict[str, Any]) -> frozenset[str]:
    """Os ids do dossiê que quem não é Pro não vê (a lacuna obrigatória não conta: diz o que falta)."""
    obrigatorias = set(entrada.get("obrigatorias", []))
    return frozenset(
        linha["id"]
        for linha in entrada["linhas"]
        if linha.get("so_pro") and linha["id"] not in obrigatorias
    )


def _cita(parte: saida.Parte, ids: frozenset[str]) -> bool:
    return any(
        nota in ids
        for p in parte.paragrafos
        for frase in p.frases
        for nota in frase.notas
    )


def _partes_do_dossie(analise: saida.Analise, entrada: dict[str, Any]) -> set[str]:
    dossie = _so_pro(entrada)
    return {p.chave for p in analise.partes if _cita(p, dossie)}


def sem_o_dossie(analise: saida.Analise, entrada: dict[str, Any]) -> saida.Analise:
    """A análise de quem não é Pro (D4): a parte que cita o dossiê vira o molde sem o dossiê."""
    return _juntar(analise, molde(entrada, False), _partes_do_dossie(analise, entrada))


def _juntar(
    analise: saida.Analise, reserva: saida.Analise, fora: Collection[str]
) -> saida.Analise:
    chaves = {p.chave for p in analise.partes}
    return saida.Analise(
        tuple(
            analise.parte(c) if c in chaves and c not in fora else reserva.parte(c)
            for c in saida.PARTES
        )
    )


def _montar(
    ler: Callable[[], saida.Analise],
    entrada: dict[str, Any],
    hash_da_resposta: str | None,
    reprovadas: Collection[str],
    incluir_so_pro: bool,
) -> Montagem:
    reserva = molde(entrada, incluir_so_pro)
    if hash_da_resposta != en.hash_da_entrada(entrada):
        return Montagem(reserva, None, FICHA_NOVA)
    try:
        analise = ler()
    except saida.RespostaInvalidaError as erro:
        return Montagem(reserva, None, f"{FORA_DO_FORMATO}: {erro}")
    conferencia = porta1.conferir(analise, entrada)
    fora = set(conferencia.partes_reprovadas) | set(reprovadas)
    if not incluir_so_pro:
        fora |= _partes_do_dossie(analise, entrada)
    return Montagem(_juntar(analise, reserva, fora), conferencia)


def analise_final(
    resposta: dict[str, Any] | None,
    entrada: dict[str, Any],
    hash_da_resposta: str | None,
    reprovadas: Collection[str] = (),
    incluir_so_pro: bool = True,
) -> Montagem:
    """Monta as 8 partes com a `origem` de cada uma.

    `hash_da_resposta` é o hash da entrada que o modelo recebeu; `reprovadas`, as partes que a
    porta 2 ou a 3 recusaram; `incluir_so_pro=False` é quem não é Pro (D4): a parte que cita o
    dossiê sai do molde sem o dossiê.
    """
    if resposta is None:
        return Montagem(molde(entrada, incluir_so_pro), None, SEM_RESPOSTA)
    return _montar(
        lambda: saida.ler_analise(resposta),
        entrada,
        hash_da_resposta,
        reprovadas,
        incluir_so_pro,
    )


def da_resposta_bruta(
    stop_reason: str | None,
    texto: str,
    entrada: dict[str, Any],
    hash_da_resposta: str | None,
    reprovadas: Collection[str] = (),
    incluir_so_pro: bool = True,
) -> Montagem:
    """A mesma montagem a partir do texto que a API devolveu (cortado ou fora do JSON vira molde)."""
    return _montar(
        lambda: saida.ler_analise(pe.ler_resposta(stop_reason, texto)),
        entrada,
        hash_da_resposta,
        reprovadas,
        incluir_so_pro,
    )
