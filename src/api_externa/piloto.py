"""O aviso de piloto em cada bloco servido pela prontidão de piloto (ADR 0108, Emenda 2, D11.3).

O portão (`src/portao_externo.py`) libera pelo piloto só a organização com a marca, e a decisão volta
`Decisao.piloto`. Esta é a outra metade: a rota abre um registro (`anotar`) em volta da leitura, o `Permitido`
anota em `registrar` por que cada campo saiu (prontidão cheia ou piloto) e, antes de traduzir, `marcar` põe no
envelope de cada bloco de piloto a marca e a frase fixa (`base.prontidao.AVISO_DE_PILOTO`). Bloco de piloto
sem o aviso é defeito P1, então tudo falha fechado:

- liberação de piloto sem registro aberto vira negação (a rota que não marca não serve piloto);
- com algum campo de piloto na resposta, todo envelope leva a marca, menos o que tem a fonte e o nome de um
  campo liberado pela prontidão cheia (o nome do envelope nem sempre é o do campo: na dúvida, marca);
- se um campo de piloto não aparece como bloco próprio (serviu só de filtro ou condição), todo envelope leva
  a marca, sem exceção;
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
    """O que saiu num pedido, por fonte e campo: pela prontidão cheia ou pelo piloto."""

    cheio: set[tuple[str, str]] = field(default_factory=set)
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
    if decisao.libera and liberados is not None:
        liberados.cheio.add((fonte, campo))
    return decisao.libera


def _e_envelope(dentro: dict) -> bool:
    return dentro.keys() >= _ENVELOPE


def _marcado(envelope: dict, nome: str | None, liberados: Liberados) -> dict:
    pronto = (envelope.get("fonte"), nome) in liberados.cheio
    pelo_piloto = (envelope.get("fonte"), nome) in liberados.piloto
    marcado = dict(envelope)
    marcado["valor"] = _marcar(envelope["valor"], None, liberados)
    if pelo_piloto or not pronto:
        marcado |= {MARCA: True, AVISO: AVISO_DE_PILOTO}
    return marcado


def _marcar(dentro: object, nome: str | None, liberados: Liberados) -> object:
    if isinstance(dentro, dict):
        if _e_envelope(dentro):
            return _marcado(dentro, nome, liberados)
        return {
            chave: _marcar(valor, str(chave), liberados)
            for chave, valor in dentro.items()
        }
    if isinstance(dentro, list | tuple):
        return [_marcar(item, nome, liberados) for item in dentro]
    return dentro


def _blocos(dentro: object, nome: str | None) -> Generator[tuple[str, str | None]]:
    """(fonte, nome) de cada envelope do corpo, no mesmo caminho que `_marcar` percorre."""
    if isinstance(dentro, dict):
        if _e_envelope(dentro):
            yield dentro.get("fonte"), nome
            yield from _blocos(dentro["valor"], None)
            return
        for chave, valor in dentro.items():
            yield from _blocos(valor, str(chave))
    elif isinstance(dentro, list | tuple):
        for item in dentro:
            yield from _blocos(item, nome)


def marcar(corpo: dict, liberados: Liberados) -> dict:
    """O corpo com a marca e a frase em todo bloco de piloto e no topo; igual se nada saiu pelo piloto.

    Campo de piloto que não virou bloco próprio na resposta serviu de filtro ou de condição (ex.: a data de
    entrada que escolhe quais compradores saem): não se sabe quais blocos ele tocou, então todos levam a marca,
    inclusive os da prontidão cheia (D11.3, leitura mais estreita)."""
    if not liberados.piloto:
        return corpo
    if liberados.piloto - set(_blocos(corpo, None)):
        liberados = Liberados(
            piloto=liberados.piloto
        )  # sem o `cheio`: nenhum bloco escapa da marca
    marcado = _marcar(corpo, None, liberados)
    assert isinstance(marcado, dict)  # dicionário entra, dicionário sai
    return marcado | {AVISO: AVISO_DE_PILOTO}
