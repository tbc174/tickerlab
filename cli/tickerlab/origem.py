"""De onde vem um conjunto ou um campo (`tickerlab de-onde-vem`), tirado do catálogo que a chave já lê.

É a mesma explicação da ferramenta `de_onde_vem` do conector (`conector_remoto/ferramentas_do_analista.py`),
repetida aqui porque a CLI é um pacote à parte e não importa o conector; `tests/test_conector_de_onde_vem.py`
trava as duas na mesma resposta. Não pede dado de empresa: só o `/catalog`.
"""

import re
from collections.abc import Mapping

PERGUNTA_VALIDA = re.compile(r"[a-z0-9_]{1,80}")
MAXIMO_DE_ACHADOS = 50
LIMITE_DO_CATALOGO = (
    "O catálogo da chave traz o conjunto, o campo, a fonte, a licença e a marca de piloto; não traz o "
    "significado de cada campo nem o dia do retrato (o dia de cada valor vem em `published_at`, na resposta "
    "do dado)."
)


class NomeInvalido(ValueError):
    """O nome pedido não é nome de conjunto nem de campo (antes de qualquer pedido à API)."""


class NadaComEsseNome(LookupError):
    """A chave não vê conjunto nem campo com o nome pedido."""


def pergunta(texto: str) -> str:
    """O nome pedido, em minúsculas e sem espaço nas pontas; `NomeInvalido` se não é nome de conjunto ou campo."""
    limpo = texto.strip().lower()
    if not PERGUNTA_VALIDA.fullmatch(limpo):
        raise NomeInvalido(
            "diga o nome de um conjunto ou de um campo, só com letras, números e `_`, como `credit` ou "
            "`legal_name`. A lista do que a sua chave vê está em `tickerlab catalogo`."
        )
    return limpo


def _campos_do_conjunto(conjunto: Mapping) -> list[Mapping]:
    campos = conjunto.get("fields")
    return (
        [c for c in campos if isinstance(c, Mapping)]
        if isinstance(campos, list)
        else []
    )


def _campo_enxuto(campo: Mapping) -> dict[str, object]:
    enxuto: dict[str, object] = {
        "field": campo.get("field"),
        "source": campo.get("source"),
    }
    if campo.get("pilot") is True:
        enxuto["pilot"] = True
    return enxuto


def _achados(corpo: Mapping, nome: str) -> tuple[str, list[dict[str, object]]]:
    """Os conjuntos de nome `nome` ou, se não há, os campos de nome `nome`, cada um com o conjunto."""
    lista = corpo.get("datasets")
    conjuntos = (
        [c for c in lista if isinstance(c, Mapping)] if isinstance(lista, list) else []
    )
    de_conjunto: list[dict[str, object]] = [
        {
            "dataset": c.get("dataset"),
            "purpose": c.get("purpose"),
            "fields": [_campo_enxuto(f) for f in _campos_do_conjunto(c)],
        }
        for c in conjuntos
        if str(c.get("dataset", "")).lower() == nome
    ]
    if de_conjunto:
        return "dataset", de_conjunto
    de_campo: list[dict[str, object]] = [
        {"dataset": c.get("dataset"), "purpose": c.get("purpose")} | _campo_enxuto(f)
        for c in conjuntos
        for f in _campos_do_conjunto(c)
        if str(f.get("field", "")).lower() == nome
    ]
    return "field", de_campo


def campos_do_achado(achado: Mapping) -> list[Mapping]:
    """Os campos de um achado: os do conjunto, ou o próprio achado quando é um campo."""
    campos = achado.get("fields")
    return campos if isinstance(campos, list) else [achado]


def _fontes_do_achado(corpo: Mapping, achados: list[dict[str, object]]) -> list[object]:
    """A licença e a atribuição das fontes que aparecem nos achados, uma vez cada, em ordem alfabética."""
    usadas = {
        campo.get("source")
        for achado in achados
        for campo in campos_do_achado(achado)
        if isinstance(campo.get("source"), str)
    }
    lista = corpo.get("sources")
    por_nome = {
        f["source"]: f
        for f in (lista if isinstance(lista, list) else [])
        if isinstance(f, Mapping) and isinstance(f.get("source"), str)
    }
    return [por_nome.get(nome, {"source": nome}) for nome in sorted(usadas, key=str)]


def _campos_de_piloto(achados: list[dict[str, object]]) -> list[str]:
    return sorted(
        {
            f"{achado.get('dataset')}.{campo.get('field')}"
            for achado in achados
            for campo in campos_do_achado(achado)
            if campo.get("pilot") is True
        }
    )


def explicacao(corpo: Mapping, nome: str) -> dict[str, object]:
    """A explicação de `nome` (já passado por `pergunta`), com o aviso de piloto uma vez só; `NadaComEsseNome`
    se a chave não vê nada assim."""
    tipo, achados = _achados(corpo, nome)
    if not achados:
        raise NadaComEsseNome(
            "a sua chave não vê um conjunto nem um campo com esse nome. A lista do que ela vê está em "
            "`tickerlab catalogo`."
        )
    cortado = len(achados) > MAXIMO_DE_ACHADOS
    achados = achados[:MAXIMO_DE_ACHADOS]
    saida: dict[str, object] = {
        "asked": nome,
        "kind": tipo,
        "matches": achados,
        "sources": _fontes_do_achado(corpo, achados),
        "limits": [LIMITE_DO_CATALOGO],
    }
    if cortado:
        saida["truncated"] = True
    de_piloto = _campos_de_piloto(achados)
    aviso = corpo.get("pilot_notice")
    if de_piloto and isinstance(aviso, str):
        saida["pilot_fields"] = de_piloto
        saida["pilot_notice"] = aviso
    return saida
