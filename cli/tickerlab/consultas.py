"""A cópia da lista única das portas que a CLI leva no pacote (`consultas.json`).

A lista fica no repositório, em `conector_remoto/consultas_das_portas.py`: dela saem as ferramentas do conector e
este arquivo, gravado por `python -m scripts.exportar_conteudo` (há teste que acusa quando ele fica velho). A CLI
é instalada à parte no PC do analista e não importa o repositório; por isso lê a cópia. Daqui saem os mapas do
português para a API e a faixa de cada opção, os mesmos do conector.
"""

import json
import math
import re
from importlib import resources

import click

_ARQUIVO = "consultas.json"
_DADOS: dict = json.loads(
    resources.files("tickerlab").joinpath(_ARQUIVO).read_text(encoding="utf-8")
)


def traducao(nome: str) -> dict[str, str]:
    """Um mapa da escolha em português (a que o analista escreve) para o valor da API, na ordem da lista."""
    return dict(_DADOS["traducoes"][nome])


def valores(comando: str, opcao: str) -> tuple[str, ...]:
    """As escolhas fechadas de uma opção, na ordem da lista."""
    return tuple(_DADOS["opcoes"][comando][opcao]["valores"])


def maximo(comando: str, opcao: str) -> int:
    """O maior valor aceito por uma opção inteira."""
    return int(_DADOS["opcoes"][comando][opcao]["maximo"])


class _FaixaReal(click.FloatRange):
    """A faixa com casas decimais que recusa `nan` e o infinito, como o conector (o `FloatRange` deixa o `nan`
    passar, porque toda comparação com ele dá falso)."""

    def convert(
        self, value: object, param: click.Parameter | None, ctx: click.Context | None
    ) -> float:
        numero = super().convert(value, param, ctx)
        if not math.isfinite(numero):
            self.fail(f"{value} não é um número.", param, ctx)
        return numero


def faixa_real(comando: str, opcao: str) -> click.FloatRange:
    """A faixa de uma opção com casas decimais, a mesma do parâmetro da ferramenta do conector."""
    opcao_da_lista = _DADOS["opcoes"][comando][opcao]
    return _FaixaReal(
        float(opcao_da_lista["minimo"]),
        float(opcao_da_lista["maximo"]),
        min_open=bool(opcao_da_lista["minimo_aberto"]),
    )


def formato(nome: str) -> str:
    """Um formato da lista (a expressão regular), como `chave_do_setor`."""
    return str(_DADOS["formatos"][nome])


def compilado(nome: str) -> re.Pattern[str]:
    """O formato `nome` pronto para conferir um valor inteiro (`fullmatch`)."""
    return re.compile(formato(nome))


def faixa_inteira(comando: str, opcao: str) -> click.IntRange:
    """A faixa de uma opção inteira, a mesma do parâmetro da ferramenta do conector."""
    opcao_da_lista = _DADOS["opcoes"][comando][opcao]
    return click.IntRange(int(opcao_da_lista["minimo"]), int(opcao_da_lista["maximo"]))
