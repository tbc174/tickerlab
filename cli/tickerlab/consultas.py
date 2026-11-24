"""A cópia da lista única das portas que a CLI leva no pacote (`consultas.json`).

A lista fica no repositório, em `conector_remoto/consultas_das_portas.py`: dela saem as ferramentas do conector e
este arquivo, gravado por `python -m scripts.exportar_conteudo` (há teste que acusa quando ele fica velho). A CLI
é instalada à parte no PC do analista e não importa o repositório; por isso lê a cópia. Daqui saem os mapas do
português para a API e a faixa de cada opção, os mesmos do conector.
"""

import json
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


def faixa_inteira(comando: str, opcao: str) -> click.IntRange:
    """A faixa de uma opção inteira, a mesma do parâmetro da ferramenta do conector."""
    opcao_da_lista = _DADOS["opcoes"][comando][opcao]
    return click.IntRange(int(opcao_da_lista["minimo"]), int(opcao_da_lista["maximo"]))
