"""A análise que vai para a tela: parte do modelo que passou nas portas, parte do molde que não.

O molde entra parte por parte, nunca frase por frase (um texto remendado no meio leria mal), e a
análise inteira vira molde quando não há resposta, quando ela sai do formato ou quando a ficha
mudou desde que o texto foi escrito: texto com número velho nunca vai para a tela (plano, item 7).
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from src.analise_escrita import entrada as en
from src.analise_escrita import porta1, saida
from src.analise_escrita.molde import molde

SEM_RESPOSTA = "sem resposta do modelo"
FICHA_NOVA = "análise sendo reescrita com os números novos"
FORA_DO_FORMATO = "resposta fora do formato"


@dataclass(frozen=True)
class Montagem:
    analise: saida.Analise
    conferencia: (
        porta1.Conferencia | None
    )  # a porta 1 na resposta (None: nem chegou a ela)
    motivo: str | None = (
        None  # por que a análise inteira saiu do molde (vai para a linhagem)
    )


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
    reserva = molde(entrada, incluir_so_pro)
    if resposta is None:
        return Montagem(reserva, None, SEM_RESPOSTA)
    if hash_da_resposta != en.hash_da_entrada(entrada):
        return Montagem(reserva, None, FICHA_NOVA)
    try:
        analise = saida.ler_analise(resposta)
    except saida.RespostaInvalidaError as erro:
        return Montagem(reserva, None, f"{FORA_DO_FORMATO}: {erro}")
    conferencia = porta1.conferir(analise, entrada)
    fora = set(conferencia.partes_reprovadas) | set(reprovadas)
    if not incluir_so_pro:
        dossie = _so_pro(entrada)
        fora |= {p.chave for p in analise.partes if _cita(p, dossie)}
    return Montagem(_juntar(analise, reserva, fora), conferencia)
