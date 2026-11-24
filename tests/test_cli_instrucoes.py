"""As instruções da CLI (`tickerlab instrucoes`) saem da ajuda de cada comando, num lugar só (frente 2, PR 3).

Antes, o texto de cada comando estava escrito três vezes dentro do pacote: na ajuda (`--help`), na tabela do
AGENTS.md e na lista do SKILL.md, e as cópias já divergiam (a análise e os ativos estavam velhos nas instruções).
"""

import inspect
from importlib import resources

import click
import pytest
from click.testing import CliRunner
from tickerlab import comandos, instrucoes_montadas
from tickerlab.instrucoes_montadas import MARCA, ORDEM, montar, uso

OPCOES_DE_TODOS = ("--json", "--planilha", "--help", "-h")


def _comando(nome: str) -> click.Command:
    comando = comandos.principal.commands[nome]
    assert isinstance(comando, click.Command)
    return comando


def _rodar(*argumentos: str) -> str:
    resultado = CliRunner().invoke(comandos.principal, list(argumentos))
    assert resultado.exit_code == 0, resultado.output
    return resultado.output


def test_a_ordem_cobre_todo_comando_de_dado():
    """Comando novo na CLI entra nas instruções (ou é um dos que não leem a base)."""
    nao_leem_a_base = {"login", "logout", "instrucoes"}
    assert set(ORDEM) == set(comandos.principal.commands) - nao_leem_a_base
    assert len(ORDEM) == len(set(ORDEM))


@pytest.mark.parametrize("nome", ORDEM)
def test_cada_comando_tem_resumo_de_uma_linha(nome):
    """O primeiro parágrafo da ajuda é uma frase só: é o que vai ao SKILL.md e ao topo do --help."""
    ajuda = inspect.cleandoc(_comando(nome).help or "")
    primeiro = ajuda.split("\n\n")[0]
    assert primeiro and "\n" not in primeiro, nome


@pytest.mark.parametrize("nome", ORDEM)
def test_o_uso_traz_cada_opcao_do_comando(nome):
    """A linha de uso sai das opções do click: opção nova aparece sem ninguém escrever."""
    comando = _comando(nome)
    linha = uso(comando)
    assert linha.startswith(f"tickerlab {nome}")
    for parametro in comando.params:
        if isinstance(parametro, click.Option):
            longa = max(parametro.opts, key=len)
            if longa not in OPCOES_DE_TODOS:
                assert longa in linha, (nome, longa)


def test_o_uso_mostra_faixas_escolhas_e_obrigatorias():
    assert uso(_comando("vinculos")) == (
        "tickerlab vinculos <cnpj> [--como-era AAAA-MM-DD] [--profundidade 1-3] "
        "[--tipo auditor|coligada|controlada|participada]"
    )
    assert uso(_comando("compradores")).startswith(
        "tickerlab compradores --cnae <5 ou 7 dígitos> [--uf UF] [--anos 1-10]"
    )
    assert uso(_comando("setor")).startswith("tickerlab setor [<chave>]")
    assert "[--so-cadastro]" in uso(_comando("empresa"))


@pytest.mark.parametrize("qual", ["agents", "skill"])
def test_o_modelo_tem_a_marca_uma_vez(qual):
    nome = instrucoes_montadas.ARQUIVOS[qual]
    texto = (resources.files("tickerlab") / "instrucoes" / nome).read_text(
        encoding="utf-8"
    )
    assert texto.count(MARCA) == 1


@pytest.mark.parametrize("qual", ["agents", "skill"])
def test_as_instrucoes_saem_da_ajuda(qual):
    texto = montar(qual, comandos.principal)
    assert MARCA not in texto
    for nome in ORDEM:
        resumo = inspect.cleandoc(_comando(nome).help or "").split("\n\n")[0]
        assert resumo in texto, (qual, nome)
        assert uso(_comando(nome)).split(" [")[0] in texto.replace("\\|", "|"), (
            qual,
            nome,
        )
    # na ordem combinada: a linha da tabela (agents) ou o item da lista (skill) de cada comando
    inicio = "| `" if qual == "agents" else "- `"
    linhas = texto.splitlines()
    posicoes = [
        next(
            i for i, x in enumerate(linhas) if x.startswith(f"{inicio}tickerlab {nome}")
        )
        for nome in ORDEM
    ]
    assert posicoes == sorted(posicoes)


def test_o_agents_leva_a_ajuda_inteira_numa_linha_da_tabela():
    texto = montar("agents", comandos.principal)
    linha = next(x for x in texto.splitlines() if x.startswith("| `tickerlab analise"))
    assert linha.count(" | ") == 1 and linha.endswith(" |")
    assert "`timed_out`" in linha  # parágrafo de detalhe, não só o resumo


def test_a_barra_da_escolha_nao_quebra_a_tabela():
    texto = montar("agents", comandos.principal)
    linha = next(x for x in texto.splitlines() if x.startswith("| `tickerlab vinculos"))
    assert "auditor\\|coligada" in linha


def test_o_comando_imprime_o_montado():
    assert _rodar("instrucoes") == montar("agents", comandos.principal)
    assert _rodar("instrucoes", "skill") == montar("skill", comandos.principal)


@pytest.mark.parametrize(
    ("nome", "trecho"),
    [
        # a análise lista os blocos de hoje (antes parava nos comparáveis)
        ("analise", "agências reguladoras"),
        ("analise", "Banco Central"),
        ("analise", "integridade"),
        # os ativos também trazem a mineração da ANM (antes: "hoje, contratos de E&P da ANP")
        ("ativos", "ANM"),
    ],
)
def test_os_textos_velhos_foram_postos_em_dia(nome, trecho):
    assert trecho in (_comando(nome).help or "")
