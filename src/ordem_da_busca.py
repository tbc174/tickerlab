"""Ordem dos candidatos da busca pública por nome: a companhia com ação na bolsa vem primeiro.

Uma filial com debêntures negociadas tem código na B3 e nome parecido com o da holding, e a ordem
alfabética a punha na frente. Aqui a regra fica fora da rota e do banco, só com tipos simples.
"""

from collections.abc import Iterable
from dataclasses import dataclass

PAPEIS_DE_PARTICIPACAO = ("ação", "ações", "acao", "acoes", "unit", "bdr")


@dataclass(frozen=True)
class Candidata:
    cnpj: str
    empresa: str
    listada: bool  # tem ação, unit ou BDR na bolsa (e não só dívida)


def _e_participacao(valor_mobiliario: str) -> bool:
    """Sem tipo informado, o código de negociação conta como o da própria companhia."""
    papel = valor_mobiliario.strip().lower()
    return not papel or any(marca in papel for marca in PAPEIS_DE_PARTICIPACAO)


def ordenar(linhas: Iterable[tuple[str, str, str]]) -> list[Candidata]:
    """Junta as linhas (cnpj, empresa, valor mobiliário) por CNPJ e põe as listadas primeiro.

    Dentro de cada grupo, a ordem é a do nome e, no empate, a do CNPJ.
    """
    por_cnpj: dict[str, Candidata] = {}
    for cnpj, empresa, papel in linhas:
        atual = por_cnpj.get(cnpj)
        listada = _e_participacao(papel) or (atual is not None and atual.listada)
        por_cnpj[cnpj] = Candidata(cnpj, atual.empresa if atual else empresa, listada)
    return sorted(por_cnpj.values(), key=lambda c: (not c.listada, c.empresa, c.cnpj))
