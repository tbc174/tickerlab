"""O aviso de piloto em cada bloco servido pela prontidão de piloto (ADR 0108, Emenda 2, D11.3).

O portão (`src/portao_externo.py`) libera pelo piloto só a organização com a marca, e a decisão volta
`Decisao.piloto`. Esta é a outra metade: a rota abre um registro (`anotar`) em volta da leitura, o `Permitido`
anota em `registrar` por que cada campo saiu (prontidão cheia ou piloto) e, antes de traduzir, `marcar` põe no
envelope de cada bloco de piloto a marca e a frase fixa (`base.prontidao.AVISO_DE_PILOTO`). Bloco de piloto
sem o aviso é defeito P1, então tudo falha fechado:

- liberação de piloto sem registro aberto vira negação (a rota que não marca não serve piloto);
- com algum campo de piloto na resposta, todo envelope leva a marca, sem exceção: o campo de piloto pode ter
  escolhido, filtrado ou ordenado blocos que não são dele;
- o topo da resposta leva a frase também.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from base.prontidao import AVISO_DE_PILOTO
from src.portao_externo import Decisao

MARCA = "piloto"
AVISO = "aviso_de_piloto"
_ENVELOPE = frozenset({"valor", "fonte", "publico_em"})


@dataclass
class Liberados:
    """O que saiu pelo piloto num pedido, por fonte e campo."""

    piloto: set[tuple[str, str]] = field(default_factory=set)


_DO_PEDIDO: ContextVar[Liberados | None] = ContextVar(
    "liberados_do_pedido", default=None
)


@contextmanager
def anotar() -> Generator[Liberados]:
    """O registro de um pedido (a rota abre em volta da leitura e marca o corpo com ele)."""
    liberados = Liberados()
    ficha = _DO_PEDIDO.set(liberados)
    try:
        yield liberados
    finally:
        _DO_PEDIDO.reset(ficha)


def registrar(fonte: str, campo: str, decisao: Decisao) -> bool:
    """Anota a decisão no registro do pedido e diz se o campo sai. Piloto sem registro aberto não sai."""
    liberados = _DO_PEDIDO.get()
    if decisao.piloto:
        if liberados is None:
            return False
        liberados.piloto.add((fonte, campo))
        return True
    return decisao.libera


def _e_envelope(dentro: dict) -> bool:
    return dentro.keys() >= _ENVELOPE


def _marcar(dentro: object) -> object:
    """Todo envelope, em qualquer profundidade (inclusive no `valor` de outro), com a marca e a frase."""
    if isinstance(dentro, dict):
        marcado = {chave: _marcar(valor) for chave, valor in dentro.items()}
        if _e_envelope(dentro):
            marcado |= {MARCA: True, AVISO: AVISO_DE_PILOTO}
        return marcado
    if isinstance(dentro, list | tuple):
        return [_marcar(item) for item in dentro]
    return dentro


def marcar(corpo: dict, liberados: Liberados) -> dict:
    """O corpo com a marca e a frase em todo bloco e no topo, se algo saiu pelo piloto; igual se nada saiu.

    Com dado de piloto na resposta, **todo** bloco leva a marca, inclusive o da prontidão cheia (D11.3, leitura
    mais estreita): o campo de piloto pode ter escolhido, filtrado ou ordenado blocos que não são dele (a data de
    entrada que escolhe quais compradores saem, a receita que ordena os comparáveis), e a resposta não diz
    quais."""
    if not liberados.piloto:
        return corpo
    marcado = _marcar(corpo)
    assert isinstance(marcado, dict)  # dicionário entra, dicionário sai
    return marcado | {AVISO: AVISO_DE_PILOTO}
