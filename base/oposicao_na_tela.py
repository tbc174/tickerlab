"""Oposição do titular na tela da equipe (LGPD, art. 18, § 2º; linha 829; ADR 0128, Emenda 1).

A política de privacidade promete que quem se opôs sai também da tela da organização em 15 dias. A oposição
(`base/pessoas/oposicoes.py`) guarda só o `id_pessoa`: o HMAC do meio do CPF e do primeiro e do último nome.
A montagem do `acervo_pessoa` calcula esse mesmo id de cada sócio (do CPF mascarado do `Socios*.zip`) e de
cada titular de empresário individual (do CPF no fim da razão social), **só na memória**: o CPF nunca é
gravado nem sai daqui. Quem tem id com oposição, atendida ou não, fica fora do acervo.

Falha fechada: sem a pasta restrita ou sem a chave, nada é montado (`SemOposicoesError`, `ErroSemChave`).
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from base.pessoas import chave as chaves
from base.pessoas import oposicoes


class SemOposicoesError(RuntimeError):
    """A pasta restrita, onde estão as oposições, não existe neste servidor."""


@dataclass(frozen=True)
class Opostos:
    """Os ids com oposição registrada e a chave para calcular o id de quem entra no acervo."""

    ids: frozenset[str]
    chave: bytes = field(repr=False)  # nunca no log nem no texto de erro

    def _oposto(self, documento: str, nome: str) -> bool:
        try:
            primeiro, ultimo = chaves.primeiro_e_ultimo(nome)
            return chaves.id_pessoa(documento, primeiro, ultimo, self.chave) in self.ids
        except ValueError:  # CPF malformado ou nome vazio não casa com id nenhum
            return False

    def marcar(self, documentos: pd.Series, nomes: pd.Series) -> pd.Series:
        """Verdadeiro para quem tem oposição (documento e nome da mesma linha)."""
        if not self.ids:
            return pd.Series(False, index=documentos.index)
        marcas = [self._oposto(d, n) for d, n in zip(documentos, nomes, strict=True)]
        return pd.Series(marcas, index=documentos.index)


def carregar(restrita: Path) -> Opostos:
    """As oposições da pasta restrita e a chave do pseudônimo; recusa pasta ou chave ausentes."""
    if not restrita.is_dir():
        raise SemOposicoesError("pasta restrita de pessoas ausente")
    return Opostos(frozenset(oposicoes.ids_opostos(restrita)), chaves.ler_chave())
