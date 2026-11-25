"""As instruções para o agente de IA (`tickerlab instrucoes`), montadas a partir da ajuda de cada comando.

O texto de um comando fica num lugar só: a ajuda dele (o docstring em `comandos.py`, que o `--help` mostra). O
primeiro parágrafo é o resumo de uma frase; os outros, o detalhe. Daqui saem a tabela "Comandos" do AGENTS.md (o
uso e a ajuda inteira) e a lista do SKILL.md (o uso e o resumo), no lugar da marca dos modelos em `instrucoes/`.
A linha de uso sai das opções do click: opção nova aparece sozinha, com a faixa e as escolhas certas.
"""

import inspect
from importlib import resources

import click

ARQUIVOS = {"agents": "AGENTS.md", "skill": "SKILL.md"}
MARCA = "<!-- comandos: montados pela CLI a partir da ajuda de cada comando -->"
# a ordem dos comandos nas instruções: do CNPJ para o setor, depois a chave (o click os lista em ordem alfabética)
ORDEM = (
    "empresa",
    "analise",
    "comparaveis",
    "compradores",
    "ativos",
    "credito",
    "dossie",
    "eventos",
    "vinculos",
    "demonstracoes",
    "fundo",
    "prospectar",
    "setor",
    "deck",
    "novidades",
    "catalogo",
    "consumo",
)
# as opções que todo comando de dado tem: as instruções as explicam uma vez, fora da tabela
_OPCOES_DE_TODOS = frozenset({"como_json", "destino"})
_DIA = "AAAA-MM-DD"
_CABECALHO_DA_TABELA = "| Comando | O que devolve |\n|---|---|"


def _valor(opcao: click.Option) -> str:
    """O que vem depois da opção na linha de uso: o metavar dado, a faixa, as escolhas ou o formato do dia."""
    tipo = opcao.type
    if opcao.metavar:
        return opcao.metavar
    if isinstance(tipo, click.Choice):
        return "|".join(str(escolha) for escolha in tipo.choices)
    if isinstance(tipo, click.IntRange):
        return f"{tipo.min}-{tipo.max}"
    if isinstance(tipo, click.DateTime):
        return _DIA
    return "VALOR"


def _parte_do_uso(parametro: click.Parameter) -> str | None:
    if parametro.name in _OPCOES_DE_TODOS:
        return None
    if isinstance(parametro, click.Argument):
        nome = f"<{parametro.name}>"
        return nome if parametro.required else f"[{nome}]"
    if not isinstance(parametro, click.Option):
        return None
    texto = max(parametro.opts, key=len)
    if not parametro.is_flag:
        texto = f"{texto} {_valor(parametro)}"
    return texto if parametro.required else f"[{texto}]"


def uso(comando: click.Command) -> str:
    """A linha de uso do comando, como `tickerlab vinculos <cnpj> [--profundidade 1-3] ...`."""
    partes = [f"tickerlab {comando.name}"]
    partes += [p for p in map(_parte_do_uso, comando.params) if p is not None]
    return " ".join(partes)


def paragrafos(comando: click.Command) -> list[str]:
    """Os parágrafos da ajuda do comando, cada um numa linha só."""
    texto = inspect.cleandoc(comando.help or "")
    return [" ".join(p.split()) for p in texto.split("\n\n") if p.strip()]


def _linha_da_tabela(comando: click.Command) -> str:
    # a barra das escolhas (`a|b`) separaria a coluna da tabela do Markdown
    uso_na_tabela = uso(comando).replace("|", "\\|")
    ajuda = " ".join(paragrafos(comando)).replace("|", "\\|")
    return f"| `{uso_na_tabela}` | {ajuda} |"


def _item_da_lista(comando: click.Command) -> str:
    return f"- `{uso(comando)}`: {paragrafos(comando)[0]}"


def comandos_em_ordem(grupo: click.Group) -> list[click.Command]:
    return [grupo.commands[nome] for nome in ORDEM]


def montar(qual: str, grupo: click.Group) -> str:
    """O AGENTS.md (`agents`) ou o SKILL.md (`skill`) com os comandos de `grupo` no lugar da marca."""
    modelo = (resources.files("tickerlab") / "instrucoes" / ARQUIVOS[qual]).read_text(
        encoding="utf-8"
    )
    if qual == "agents":
        linhas = [_CABECALHO_DA_TABELA]
        linhas += [_linha_da_tabela(c) for c in comandos_em_ordem(grupo)]
    else:
        linhas = [_item_da_lista(c) for c in comandos_em_ordem(grupo)]
    return modelo.replace(MARCA, "\n".join(linhas))
