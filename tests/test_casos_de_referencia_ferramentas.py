"""As calculadoras do site dão os números de referência, calculados à mão ou por fonte pública.

Diferente do golden (`test_golden_ferramentas.py`), que só guarda o que o Python devolveu, estes
casos vêm de fora do código: matemática financeira de livro-texto, a tabela regressiva do IR, as
regras do DARF. Cada caso diz a origem do número. O mesmo arquivo é lido pelo vitest
(`web/testes/ferramentas/casos_de_referencia.test.ts`), que confere as contas em TypeScript.
Caso novo: acrescente em `tests/arquivos/casos_de_referencia_ferramentas.json` com a origem.
Calculadora que errar um caso tem bug: corrija a conta (e a cópia em TS), não o número.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import gerar_golden_ferramentas as golden

ARQUIVO = Path(__file__).parent / "arquivos" / "casos_de_referencia_ferramentas.json"
CASOS = json.loads(ARQUIVO.read_text(encoding="utf-8"))


def _campo(valor: Any, caminho: str) -> Any:
    """Entra no resultado: "" é ele todo; "0.parcela" é o campo `parcela` do item 0."""
    for parte in filter(None, caminho.split(".")):
        valor = valor[int(parte)] if parte.isdigit() else valor[parte]
    return valor


@pytest.mark.parametrize(
    "caso", CASOS, ids=lambda c: f"{c['conta']}({c['argumentos']}){c['campo']}"
)
def test_caso_de_referencia(caso):
    resultado = golden._simples(golden.CONTAS[caso["conta"]](*caso["argumentos"]))
    obtido = _campo(json.loads(json.dumps(resultado)), caso["campo"])
    if isinstance(caso["esperado"], str):
        assert obtido == caso["esperado"], caso["origem"]
    else:
        assert obtido == pytest.approx(caso["esperado"], abs=caso["tolerancia"]), caso[
            "origem"
        ]


def test_todo_caso_diz_a_origem_do_numero():
    assert all(len(caso["origem"]) > 20 for caso in CASOS)


def test_as_contas_dos_casos_existem_no_golden():
    assert {caso["conta"] for caso in CASOS} <= set(golden.CONTAS)
