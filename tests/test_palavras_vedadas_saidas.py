"""Teste único das palavras vedadas em todas as saídas (ADR 0103, item 7; linha 726 da fila).

A ADR 0103 manda que a lista `VEDADAS` valha para "tela, PDF, API e os textos do modelo". Os testes do
café, do dossiê e das contestações já conferem os textos que eles montam; este varre o que está
escrito no código e nos arquivos de conteúdo de cada canal, a documentação da API, e confere se a
porta do modelo barra cada palavra da lista.

Como lê: de cada arquivo `.py` entram só as **strings do código** (docstring não é saída: ninguém vê),
dos `.md` e `.json` entra o texto. Dado de fonte (CSV, nome de município, razão social) não é texto
nosso e fica de fora. O que a varredura acha e não é texto exibido (regex, log, a lista que proíbe)
entra em `NAO_E_SAIDA` com o motivo. O que é texto público já publicado entra em
`ACHADOS_EM_TEXTO_PUBLICO`: não se reescreve aqui (texto público é nível 1, passa pelas duas
revisões), fica anotado e na fila; a exceção some quando o texto for corrigido (há teste que cobra).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator, Mapping
from functools import cache
from pathlib import Path

import pytest

from base.palavras_vedadas import VEDADAS, palavras_vedadas_em

RAIZ = Path(__file__).resolve().parents[1]

# Cada arquivo pertence ao primeiro canal que o reivindica (a ordem importa).
CANAIS: dict[str, tuple[str, ...]] = {
    "pdf": (
        "src/*pdf*.py",
        "src/securitizacao/relatorio.py",
        "src/memorando_ma/*.py",
    ),
    "api": (
        "src/api.py",
        "src/api_v1/*.py",
        "src/api_externa/**/*.py",
        "base/dicionario.py",
    ),
    "modelo": (
        "src/analise_escrita/*.py",
        "src/analise_escrita/*.md",
        "src/rotulos_ia.py",
        "base/boletim/*.py",
        "conteudo/molde_do_pregao.json",
        "conteudo/pregao/*.json",
        "conteudo/relatorios_semanais/*.json",
    ),
    "tela": (
        "app.py",
        "telas/**/*.py",
        "src/**/*.py",
        "base/**/*.py",
        "conteudo/**/*.md",
    ),
}
ARQUIVOS_DE_FORA = frozenset({"base/palavras_vedadas.py"})  # a própria lista

LISTA_NA_PORTA = "regex da porta 1: é a lista que barra, não texto que se publica"
PROIBICAO_AO_MODELO = "instrução que diz ao modelo o que ele não pode escrever"
PALAVRAS_DOS_GUIAS = ("fraude", "corrupção", "cartel", "conluio", "suspeito")
PALAVRAS_DA_PORTA = (
    "corrupção",
    "cartel",
    "conluio",
    "laranja",
    "superfaturamento",
    "direcionamento",
)

# (arquivo, palavra) -> motivo. Aparece no código, mas não é texto que alguém lê como nosso.
NAO_E_SAIDA: dict[tuple[str, str], str] = {
    **{("src/analise_escrita/porta1.py", p): LISTA_NA_PORTA for p in PALAVRAS_DA_PORTA},
    **{
        (guia, p): PROIBICAO_AO_MODELO
        for guia in (
            "src/analise_escrita/guia_v1.md",
            "src/analise_escrita/guia_setor_v2.md",
        )
        for p in PALAVRAS_DOS_GUIAS
    },
    ("base/boletim/leitura_ia.py", "fraude"): PROIBICAO_AO_MODELO
    + " (boletim interno)",
    (
        "src/rotulos_ia.py",
        "fraude",
    ): "instrução de classificação interna; o modelo devolve um número",
    (
        "src/rotulos_ia.py",
        "seguro",
    ): "lista de palavras de nome de empresa que o rótulo ignora",
    (
        "base/cripto/qualidade.py",
        "quebrou",
    ): "mensagem de log, não aparece para o usuário",
    (
        "base/securitizacao.py",
        "quebrada",
    ): "mensagem de log, não aparece para o usuário",
    (
        "base/processos.py",
        "seguro",
    ): "regex que classifica o nome da parte; não é texto exibido",
    ("src/raio_x.py", "seguro"): "regex do setor 'Seguro' (nome de setor), não é juízo",
    **{
        (
            arquivo,
            "seguro",
        ): "id da fonte e do pacote da ANTT (seguro de responsabilidade civil): nome do produto, não juízo"
        for arquivo in (
            "base/antt_cadastros.py",
            "base/arquivo/destinos.py",
            "base/arquivo/lote_cadastros_bcb_antt.py",
        )
    },
}

# (arquivo, palavra) -> o que é. Texto que o usuário vê e contém a palavra: NÃO reescrever aqui
# (texto público é nível 1). Está na fila (linha "palavras vedadas em texto já publicado").
ACHADOS_EM_TEXTO_PUBLICO: dict[tuple[str, str], str] = {
    (
        "src/modulos.py",
        "seguro",
    ): "nome do módulo 'Compartilhamento seguro' (menu e site)",
    ("conteudo/termos.md", "seguro"): "'manter seguro o acesso' nos Termos",
    ("conteudo/privacidade.md", "seguro"): "'seguro' na Política de Privacidade",
    ("conteudo/glossario.md", "confiável"): "'ainda não é confiável' no glossário",
    (
        "base/dicionario.py",
        "confiável",
    ): "descrição de campo no dicionário (API e catálogo)",
    (
        "src/eventos_sec.py",
        "confiável",
    ): "rótulo 'Balanço anterior não confiável' (8-K 4.02)",
    (
        "src/eventos_sec.py",
        "não confiável",
    ): "rótulo 'Balanço anterior não confiável' (8-K 4.02)",
    (
        "src/securitizacao/relatorio.py",
        "fraude",
    ): "limite do modelo no PDF: 'não captura ... fraude'",
    (
        "src/commodities/cafe/bienalidade.py",
        "quebrou",
    ): "'1 = quebrou' na série da bienalidade",
}


# --- a varredura -----------------------------------------------------------------------------------


def _casam(padroes: tuple[str, ...], raiz: Path) -> set[Path]:
    achados = {c for padrao in padroes for c in raiz.glob(padrao) if c.is_file()}
    return {
        c for c in achados if c.relative_to(raiz).as_posix() not in ARQUIVOS_DE_FORA
    }


def arquivos_do_canal(
    canal: str, raiz: Path = RAIZ, canais: Mapping[str, tuple[str, ...]] = CANAIS
) -> list[Path]:
    """Os arquivos que o canal escreve (sem os que um canal anterior já reivindicou)."""
    nomes = list(canais)
    reivindicados: set[Path] = set()
    for anterior in nomes[: nomes.index(canal)]:
        reivindicados |= _casam(canais[anterior], raiz)
    return sorted(_casam(canais[canal], raiz) - reivindicados)


def _docstrings(arvore: ast.AST) -> set[int]:
    """Os `id` dos nós que são docstring (módulo, classe, função): não são saída."""
    ids: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(
            no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            primeiro = no.body[0] if no.body else None
            if isinstance(primeiro, ast.Expr) and isinstance(
                primeiro.value, ast.Constant
            ):
                ids.add(id(primeiro.value))
    return ids


def textos_de_codigo(fonte: str) -> Iterator[str]:
    """As strings de um módulo Python, sem as docstrings."""
    arvore = ast.parse(fonte)
    docstrings = _docstrings(arvore)
    for no in ast.walk(arvore):
        if (
            isinstance(no, ast.Constant)
            and isinstance(no.value, str)
            and id(no) not in docstrings
        ):
            yield no.value


def _textos_do_json(valor: object) -> Iterator[str]:
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for filho in valor.values():
            yield from _textos_do_json(filho)
    elif isinstance(valor, list):
        for filho in valor:
            yield from _textos_do_json(filho)


def textos_do_arquivo(caminho: Path) -> Iterator[str]:
    """O que um arquivo escreve: as strings do código, ou o texto inteiro de um `.md` ou `.json`."""
    texto = caminho.read_text(encoding="utf-8")
    if caminho.suffix == ".py":
        yield from textos_de_codigo(texto)
    elif caminho.suffix == ".json":
        yield from _textos_do_json(json.loads(texto))
    else:
        yield texto


def achados_do_canal(
    canal: str, raiz: Path = RAIZ, canais: Mapping[str, tuple[str, ...]] = CANAIS
) -> set[tuple[str, str]]:
    """(arquivo, palavra) de tudo o que o canal escreve com palavra vedada."""
    achados: set[tuple[str, str]] = set()
    for caminho in arquivos_do_canal(canal, raiz, canais):
        relativo = caminho.relative_to(raiz).as_posix()
        for texto in textos_do_arquivo(caminho):
            achados.update((relativo, p) for p in palavras_vedadas_em(texto))
    return achados


def palavras_novas(
    canal: str,
    raiz: Path = RAIZ,
    canais: Mapping[str, tuple[str, ...]] = CANAIS,
    conhecidos: frozenset[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    """As palavras vedadas do canal que nenhuma exceção explica."""
    if conhecidos is None:
        conhecidos = frozenset(NAO_E_SAIDA) | frozenset(ACHADOS_EM_TEXTO_PUBLICO)
    return sorted(achados_do_canal(canal, raiz, canais) - conhecidos)


@cache
def _achados_reais(canal: str) -> frozenset[tuple[str, str]]:
    """A varredura do repositório de verdade (lê centenas de arquivos: faz uma vez por canal)."""
    return frozenset(achados_do_canal(canal))


@pytest.mark.parametrize("canal", list(CANAIS))
def test_nenhum_canal_escreve_palavra_vedada_fora_das_excecoes(canal):
    novas = _achados_reais(canal) - set(NAO_E_SAIDA) - set(ACHADOS_EM_TEXTO_PUBLICO)
    assert not novas, f"palavra vedada em texto do canal {canal}: {sorted(novas)}"


def test_cada_excecao_ainda_acontece():
    """Texto corrigido ou arquivo apagado: a exceção sai da lista (ela não pode ficar velha)."""
    existentes = set().union(*(_achados_reais(canal) for canal in CANAIS))
    velhas = sorted((set(NAO_E_SAIDA) | set(ACHADOS_EM_TEXTO_PUBLICO)) - existentes)
    assert not velhas, f"exceção que não acontece mais: {velhas}"


def test_a_mesma_excecao_nao_esta_nas_duas_listas():
    assert not set(NAO_E_SAIDA) & set(ACHADOS_EM_TEXTO_PUBLICO)


def test_todo_canal_tem_arquivos_para_varrer():
    for canal in CANAIS:
        assert arquivos_do_canal(canal), canal


# --- a API: o que a documentação OpenAPI diz -------------------------------------------------------


def test_a_documentacao_openapi_nao_usa_palavra_vedada():
    from src.api import criar_app

    texto = json.dumps(criar_app().openapi(), ensure_ascii=False)
    assert palavras_vedadas_em(texto) == []


# --- o modelo: a porta 1 barra o que ele escreve? ----------------------------------------------------

# Hoje a porta 1 (`_PROIBIDAS`, em src/analise_escrita/porta1.py) não barra estas, e a ADR 0103 diz
# que "a porta de conferência barra" o que o modelo escreve. Corrigir a porta é de outra linha da
# fila; o `strict` faz este teste cobrar a saída da palavra desta lista no dia em que ela for barrada.
FORA_DA_PORTA_1 = frozenset(
    {
        "quebrou",
        "quebrada",
        "calote",
        "golpe",
        "não confiável",
        "evite",
        "seguro",
        "confiável",
    }
)


def _porta_1_barra(palavra: str) -> bool:
    from src.analise_escrita import porta1

    frase = f"No período a empresa registrou {palavra} segundo o relatório."
    return any(
        tipo == porta1.PALAVRA for tipo, _ in porta1._falhas_de_palavra(frase, True)
    )


def _caso_da_porta(palavra: str):
    if palavra not in FORA_DA_PORTA_1:
        return palavra
    return pytest.param(
        palavra,
        marks=pytest.mark.xfail(strict=True, reason="a porta 1 ainda não barra (fila)"),
    )


@pytest.mark.parametrize("palavra", [_caso_da_porta(p) for p in VEDADAS])
def test_a_porta_1_do_modelo_barra_cada_palavra_vedada(palavra):
    assert _porta_1_barra(palavra)


# --- a prova de que a varredura funciona: planta a palavra e vê falhar -------------------------------

CANAIS_FALSOS = {"tela": ("telas/*.py", "conteudo/*.md", "conteudo/*.json")}


@pytest.fixture
def raiz_falsa(tmp_path):
    (tmp_path / "telas").mkdir()
    (tmp_path / "conteudo").mkdir()
    return tmp_path


def _novas_na_raiz(raiz: Path, conhecidos: frozenset[tuple[str, str]] = frozenset()):
    return palavras_novas("tela", raiz, CANAIS_FALSOS, conhecidos)


@pytest.mark.parametrize("palavra", VEDADAS)
def test_palavra_plantada_em_codigo_texto_ou_json_falha_a_varredura(
    raiz_falsa, palavra
):
    (raiz_falsa / "telas" / "a.py").write_text(
        f"TITULO = 'Empresa {palavra.upper()}'\n", "utf-8"
    )
    (raiz_falsa / "conteudo" / "b.md").write_text(
        f"# Texto\n\nAqui há {palavra}.\n", "utf-8"
    )
    (raiz_falsa / "conteudo" / "c.json").write_text(
        json.dumps({"x": [{"y": palavra}]}), "utf-8"
    )
    arquivos = {
        arquivo for arquivo, achada in _novas_na_raiz(raiz_falsa) if achada == palavra
    }
    assert arquivos == {"conteudo/b.md", "conteudo/c.json", "telas/a.py"}


def test_docstring_nao_e_saida_mas_a_string_do_codigo_e(raiz_falsa):
    codigo = raiz_falsa / "telas" / "a.py"
    codigo.write_text(
        '"""Fala de fraude."""\n\n\ndef f():\n    """E de calote."""\n    return "sem nada"\n',
        "utf-8",
    )
    assert _novas_na_raiz(raiz_falsa) == []
    codigo.write_text("def f():\n    return 'um golpe'\n", "utf-8")
    assert _novas_na_raiz(raiz_falsa) == [("telas/a.py", "golpe")]


def test_excecao_conhecida_passa_e_so_ela(raiz_falsa):
    (raiz_falsa / "telas" / "a.py").write_text("X = 'um golpe'\n", "utf-8")
    (raiz_falsa / "telas" / "b.py").write_text("X = 'um golpe'\n", "utf-8")
    conhecidos = frozenset({("telas/a.py", "golpe")})
    assert _novas_na_raiz(raiz_falsa, conhecidos) == [("telas/b.py", "golpe")]
