"""As fontes de cada consulta do chat (linha 903), tiradas pelo código do que a ferramenta devolveu.

A tela "Perguntar" mostra, ao lado da resposta, as fontes que as consultas usaram e a data mais nova de cada
uma. Quem monta essa lista é o código, lendo o JSON da resposta da API (a lista `sources` e o
`published_at` de cada valor), e não o modelo: assim a lista não depende do que o modelo escreveu.

Só tipos simples na saída (dicionários prontos para virar JSON). Uma resposta que não é JSON não tem fonte;
nada aqui derruba a conversa.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass

# nomes dos campos como a API externa os publica (src/api_externa/nomes.py)
CAMPO_DAS_FONTES = "sources"
CAMPO_DA_FONTE = "source"
CAMPO_DA_ATRIBUICAO = "attribution"
CAMPO_DA_LICENCA = "license"
CAMPO_DA_DATA = "published_at"
# uma resposta grande tem centenas de valores: a tela só precisa das fontes, uma vez cada
MAXIMO_DE_FONTES = 20
CARACTERES_DO_TEXTO = 200
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class FonteUsada:
    """Uma fonte que a consulta usou: a chave (`rfb-cnpj`), a frase de atribuição, a licença e a data."""

    fonte: str
    atribuicao: str | None = None
    licenca: str | None = None
    publicado_em: str | None = (
        None  # AAAA-MM-DD, a mais nova entre os valores da resposta
    )

    def para_a_tela(self) -> dict[str, str | None]:
        return {
            "fonte": self.fonte,
            "atribuicao": self.atribuicao,
            "licenca": self.licenca,
            "publicado_em": self.publicado_em,
        }


def _texto(valor: object) -> str | None:
    if not isinstance(valor, str) or not valor.strip():
        return None
    return valor.strip()[:CARACTERES_DO_TEXTO]


def _dicionarios(valor: object) -> Iterator[dict[object, object]]:
    """Todos os objetos do JSON, em qualquer profundidade (sem recursão: a resposta pode ser funda)."""
    pilha = [valor]
    while pilha:
        atual = pilha.pop()
        if isinstance(atual, dict):
            yield atual
            pilha.extend(atual.values())
        elif isinstance(atual, list):
            pilha.extend(atual)


def _juntar(fontes: dict[str, FonteUsada], nova: FonteUsada) -> None:
    antiga = fontes.get(nova.fonte)
    if antiga is None:
        if len(fontes) < MAXIMO_DE_FONTES:
            fontes[nova.fonte] = nova
        return
    datas = [d for d in (antiga.publicado_em, nova.publicado_em) if d]
    fontes[nova.fonte] = FonteUsada(
        fonte=antiga.fonte,
        atribuicao=antiga.atribuicao or nova.atribuicao,
        licenca=antiga.licenca or nova.licenca,
        publicado_em=max(datas) if datas else None,
    )


def _da_lista(objeto: dict[object, object]) -> Iterator[FonteUsada]:
    lista = objeto.get(CAMPO_DAS_FONTES)
    if not isinstance(lista, list):
        return
    for item in lista:
        if isinstance(item, dict) and (nome := _texto(item.get(CAMPO_DA_FONTE))):
            yield FonteUsada(
                fonte=nome,
                atribuicao=_texto(item.get(CAMPO_DA_ATRIBUICAO)),
                licenca=_texto(item.get(CAMPO_DA_LICENCA)),
            )


def _do_valor(objeto: dict[object, object]) -> FonteUsada | None:
    nome = _texto(objeto.get(CAMPO_DA_FONTE))
    data = objeto.get(CAMPO_DA_DATA)
    if nome is None or not isinstance(data, str) or not _DATA.match(data):
        return None
    return FonteUsada(fonte=nome, publicado_em=data[:10])


def fontes_do_resultado(texto: str) -> tuple[FonteUsada, ...]:
    """As fontes de uma resposta da API, uma vez cada e em ordem alfabética; () se não é JSON."""
    try:
        corpo = json.loads(texto)
    # RecursionError: JSON fundo demais para o leitor
    except (ValueError, RecursionError):
        return ()
    fontes: dict[str, FonteUsada] = {}
    for objeto in _dicionarios(corpo):
        for fonte in _da_lista(objeto):
            _juntar(fontes, fonte)
        if (fonte := _do_valor(objeto)) is not None:
            _juntar(fontes, fonte)
    return tuple(fontes[nome] for nome in sorted(fontes))
