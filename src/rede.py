"""Downloads das coletas que tentam de novo quando a fonte falha por um instante.

Um 502, uma conexão que cai ou um timeout costumam sumir em segundos (visto no Banco Central em
13/10/2026). `obter` faz o mesmo que `requests.get` e, nesses casos, espera um pouco e tenta de novo;
um 404 ou outro erro do pedido volta na hora, porque repetir não muda a resposta. Esgotadas as
tentativas, devolve a última resposta (ou levanta o último erro): quem chama continua usando
`raise_for_status()` como antes.

Só GET: repetir um POST (o e-mail da newsletter, por exemplo) poderia fazer a ação duas vezes.
O Banco Central (`src/bcb.py`) tem tentativas próprias, que também tratam a página de erro com
status 200, e não passa por aqui (senão as tentativas se multiplicariam).
"""

from __future__ import annotations

import logging
import time

import requests
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential_jitter,
)

from base.arquivo.agente import AGENTE

TENTATIVAS = 4  # a primeira e mais 3
ESPERA_INICIAL = (
    2  # segundos; dobra a cada tentativa (2, 4, 8), com um sorteio de até 1 s
)
ESPERA_MAXIMA = (
    60  # segundos: nem um Retry-After exagerado segura a coleta mais que isso
)
TEMPO_LIMITE = (
    60  # segundos, quando quem chama não diz (sem ele o requests espera para sempre)
)
STATUS_PASSAGEIROS = frozenset({429, 500, 502, 503, 504})
ERROS_PASSAGEIROS = (requests.ConnectionError, requests.Timeout)
esperar = time.sleep  # os testes trocam

log = logging.getLogger(__name__)

_exponencial = wait_exponential_jitter(
    multiplier=ESPERA_INICIAL, max=ESPERA_MAXIMA, jitter=1
)


def _passageira(resposta: requests.Response) -> bool:
    return getattr(resposta, "status_code", None) in STATUS_PASSAGEIROS


def _pedida_pela_fonte(resposta: requests.Response) -> float | None:
    """O Retry-After em segundos (o 429 e o 503 às vezes dizem quanto esperar); data é ignorada."""
    valor = resposta.headers.get("Retry-After", "").strip()
    return float(valor) if valor.isdigit() else None


def _espera(estado: RetryCallState) -> float:
    espera = _exponencial(estado)
    resultado = estado.outcome
    if resultado is not None and not resultado.failed:
        pedida = _pedida_pela_fonte(resultado.result())
        if pedida is not None:
            espera = max(espera, pedida)
    return min(espera, ESPERA_MAXIMA)


def _antes_de_esperar(estado: RetryCallState) -> None:
    resultado = estado.outcome
    if resultado is None:
        return
    if resultado.failed:
        motivo = repr(resultado.exception())
    else:
        resposta = resultado.result()
        motivo = f"HTTP {resposta.status_code}"
        resposta.close()  # com stream=True, a conexão ficaria presa
    url = estado.args[0] if estado.args else "?"
    espera = estado.next_action.sleep if estado.next_action else 0
    log.warning(
        "%s: %s (tentativa %s de %s); nova tentativa em %.0f s",
        url, motivo, estado.attempt_number, TENTATIVAS, espera,
    )  # fmt: skip


def _ultimo_resultado(estado: RetryCallState) -> requests.Response:
    """Esgotou: a última resposta volta como veio, e o último erro sobe como veio."""
    assert estado.outcome is not None
    return estado.outcome.result()


def _com_agente(kwargs: dict[str, object]) -> None:
    """Põe o `User-Agent` do TickerLab nos cabeçalhos, a menos que quem chama já tenha posto o seu
    (a SEC, por exemplo, pede o contato de quem baixa). ADR 0102: o coletor se identifica."""
    cabecalhos = dict(kwargs.get("headers") or {})  # type: ignore[call-overload]
    if not any(nome.lower() == "user-agent" for nome in cabecalhos):
        cabecalhos["User-Agent"] = AGENTE
    kwargs["headers"] = cabecalhos


def get_com_agente(url: str, *args: object, **kwargs: object) -> requests.Response:
    """Como `requests.get(url, ...)`, mas já com o `User-Agent` do TickerLab, para os leitores
    que recebem o `buscar` por parâmetro (e os testes trocam por um dublê)."""
    _com_agente(kwargs)
    return requests.get(url, *args, **kwargs)  # type: ignore[arg-type]


def obter(url: str, *args: object, **kwargs: object) -> requests.Response:
    """Como `requests.get(url, ...)`, com novas tentativas nas falhas passageiras."""
    kwargs.setdefault("timeout", TEMPO_LIMITE)
    _com_agente(kwargs)
    tentativas = Retrying(
        stop=stop_after_attempt(TENTATIVAS),
        wait=_espera,
        retry=retry_if_exception_type(ERROS_PASSAGEIROS) | retry_if_result(_passageira),
        sleep=lambda segundos: esperar(segundos),
        before_sleep=_antes_de_esperar,
        retry_error_callback=_ultimo_resultado,
    )
    return tentativas(requests.get, url, *args, **kwargs)
