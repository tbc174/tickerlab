"""Medida de uso do conector (linha 901): uma linha de JSON por chamada de ferramenta.

Para saber, desde o primeiro dia do piloto, o que a casa de M&A usa e o que falha. A linha leva só o nome da
ferramenta (um dos nomes registrados; nome desconhecido vira `desconhecida`), o resultado, a duração e o id
público da chave (`tld_...`), que já é o que a auditoria da API guarda. Nunca os argumentos, o texto do
pedido, a resposta ou a mensagem de erro: um argumento pode ser um nome digitado pelo analista, e a mensagem
de validação do pedido repete o que veio nele.

O conector não chama `src.logs.configurar_logs` (não importa `src/`), e a raiz do logging fica em WARNING:
por isso este registro tem saída própria, ligada pelo `python -m conector_remoto`. Contagem por ferramenta
no VPS: `docker logs tickerlab-mcp 2>&1 | grep ferramenta_chamada`.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from enum import StrEnum
from typing import TextIO

from conector_remoto.ferramentas import CONJUNTOS_DA_FERRAMENTA

registro_de_uso = logging.getLogger("conector_remoto.uso")
EVENTO = "ferramenta_chamada"
FERRAMENTA_DESCONHECIDA = "desconhecida"
MILISSEGUNDOS_POR_SEGUNDO = 1000


class Resultado(StrEnum):
    """Como a chamada terminou."""

    OK = "ok"
    ERRO = "erro"  # a ferramenta rodou e devolveu erro (API, parâmetro, pessoa recusada...)
    RECUSADA = "recusada"  # a chave não pode usar a ferramenta, ou ela não existe


def linha_de_uso(
    ferramenta: str, resultado: Resultado, duracao_s: float, chave: str | None
) -> dict[str, object]:
    """Os campos da linha, e só eles."""
    return {
        "evento": EVENTO,
        "hora": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "ferramenta": ferramenta
        if ferramenta in CONJUNTOS_DA_FERRAMENTA
        else FERRAMENTA_DESCONHECIDA,
        "resultado": resultado.value,
        "duracao_ms": round(duracao_s * MILISSEGUNDOS_POR_SEGUNDO),
        "chave": chave,
    }


def registrar_chamada(
    ferramenta: str, resultado: Resultado, duracao_s: float, chave: str | None
) -> None:
    """Grava a linha de uso de uma chamada."""
    registro_de_uso.info(
        json.dumps(
            linha_de_uso(ferramenta, resultado, duracao_s, chave), ensure_ascii=False
        )
    )


def ligar_registro_de_uso(saida: TextIO | None = None) -> logging.Handler:
    """Põe a saída do registro de uso no `saida` (stderr por padrão), uma linha por chamada.

    Pode ser chamada de novo: troca a saída anterior em vez de duplicar as linhas.
    """
    for antiga in list(registro_de_uso.handlers):
        registro_de_uso.removeHandler(antiga)
    handler = logging.StreamHandler(saida or sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    registro_de_uso.addHandler(handler)
    registro_de_uso.setLevel(logging.INFO)
    registro_de_uso.propagate = False
    return handler
