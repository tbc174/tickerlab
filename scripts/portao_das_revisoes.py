"""Portão das revisões: PR que toca área sensível só passa com as duas revisões escritas no corpo (AGENTS.md).

O `AGENTS.md` pede, antes do merge de área sensível ou de nível 1, a revisão de segurança sem achado bloqueante e a
revisão cruzada por outro modelo sem P0 nem P1. Até aqui isso era só texto (a proteção da `main` pede 0
aprovações). Este passo lê o corpo do PR e exige duas linhas de formato fixo:

    Revisão de segurança: sem achado bloqueante · commit 1a2b3c4
    Revisão cruzada (Claude Sonnet 5.5): sem P0 nem P1 · commit 1a2b3c4

O commit citado tem de ser do PR, e nada sensível pode ter mudado depois dele. O modelo da cruzada tem de ser de outra
família que o de `Feito por:`. As exceções da Emenda 2 têm linha própria e valem só para o caso delas. O passo prova
que a revisão foi escrita, não que foi feita.

Uso no CI (workflow "revisões", só em PR): `python3 -m scripts.portao_das_revisoes`, com o corpo em `CORPO`, o último
commit do PR em `CABECA` e a `main` em `BASE`. Só biblioteca padrão. Semana de medição desde 25/11/2026: no CI ele
avisa e não barra.

Roda: CI (revisoes.yml).
"""

import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fnmatch import fnmatch

from scripts.portao_do_agente import AREAS_SENSIVEIS, Veredito

# Além do que o agente da fila já não pode tocar: pessoa na tela, os outros compose e os próprios portões.
AREAS_SENSIVEIS_EXTRAS = (
    "src/banco/membros_da_organizacao.py",
    "compose*.yaml",
    "scripts/portao_das_revisoes.py",
    "scripts/portao_do_agente.py",
)
# Pastas geradas: não contam. O CI já confere que batem com a fonte (que conta), e regerar o site acontece em
# quase todo PR que mexe em src/paginas.py (71 de 100 PRs "sensíveis" de 11 a 25/11 eram só isso).
GERADAS = ("site/*", "novo/*", "web/conteudo/*")
# Texto público (nível 1). Dentro de web/, só as páginas públicas: o app com login (web/src/app), os testes e o
# estilo não são texto público, embora o agente da fila também não possa mexer neles.
TEXTO_PUBLICO = (
    "web/src/site/*",
    "web/src/paginas/*",
    "web/src/conteudo.ts",
    "conteudo/*",
    "README.md",
)
MIGRACOES = ("migracoes/*",)

_SHA = r"([0-9a-f]{7,40})"
_SEGURANCA = re.compile(
    rf"revis[aã]o de seguran[cç]a: sem achado bloqueante · commit {_SHA}", re.IGNORECASE
)
_CRUZADA = re.compile(
    rf"revis[aã]o cruzada \(([^)]+)\): sem P0 nem P1 · commit {_SHA}", re.IGNORECASE
)
_CRUZADA_DISPENSADA = re.compile(
    r"revis[aã]o cruzada: dispensada \(migra[cç][aã]o s[oó] acrescenta, Emenda 2\)",
    re.IGNORECASE,
)
_TODAS_DISPENSADAS = re.compile(
    r"revis[oõ]es: dispensadas \(digita[cç][aã]o, Emenda 2\)", re.IGNORECASE
)
_FEITO_POR = re.compile(r"feito por: (.+)", re.IGNORECASE)

# Ordem importa: "Codex (GPT-6)" é da família gpt.
FAMILIAS = ("opus", "sonnet", "haiku", "fable", "gpt", "codex", "gemini", "copilot")

FORMATO_SEGURANCA = "Revisão de segurança: sem achado bloqueante · commit <sha>"
FORMATO_CRUZADA = "Revisão cruzada (<modelo>): sem P0 nem P1 · commit <sha>"


@dataclass
class Revisoes:
    """O que o corpo do PR diz das revisões (a última linha de cada tipo vale)."""

    seguranca: str = ""
    cruzada: str = ""
    modelo_da_cruzada: str = ""
    cruzada_dispensada: bool = False
    todas_dispensadas: bool = False
    feito_por: str = ""


def _casa(caminho: str, padroes: Iterable[str]) -> bool:
    return any(fnmatch(caminho, padrao) for padrao in padroes)


def _e_sensivel(caminho: str) -> bool:
    if _casa(caminho, GERADAS):
        return False
    if caminho.startswith("web/"):
        return _casa(caminho, TEXTO_PUBLICO)
    return _casa(caminho, AREAS_SENSIVEIS + AREAS_SENSIVEIS_EXTRAS)


def arquivos_sensiveis(caminhos: Iterable[str]) -> list[str]:
    """Os arquivos do PR que são área sensível ou de nível 1."""
    return [caminho for caminho in caminhos if _e_sensivel(caminho)]


def _limpar(linha: str) -> str:
    """Tira o enfeite de Markdown em volta da linha (marcador de lista, citação, negrito)."""
    return linha.strip().lstrip("-*> ").strip().strip("*").strip()


def ler_revisoes(corpo: str) -> Revisoes:
    """Lê as linhas de formato fixo do corpo do PR."""
    revisoes = Revisoes()
    for linha in map(_limpar, corpo.splitlines()):
        if achado := _SEGURANCA.fullmatch(linha):
            revisoes.seguranca = achado.group(1).lower()
        elif achado := _CRUZADA.fullmatch(linha):
            revisoes.modelo_da_cruzada, revisoes.cruzada = (
                achado.group(1).strip(),
                achado.group(2).lower(),
            )
        elif _CRUZADA_DISPENSADA.fullmatch(linha):
            revisoes.cruzada_dispensada = True
        elif _TODAS_DISPENSADAS.fullmatch(linha):
            revisoes.todas_dispensadas = True
        elif achado := _FEITO_POR.fullmatch(linha):
            revisoes.feito_por = achado.group(1).strip()
    return revisoes


def familia(modelo: str) -> str | None:
    """A família do modelo (opus, sonnet, gpt...), ou None se não for conhecida."""
    minusculo = modelo.lower()
    return next((nome for nome in FAMILIAS if nome in minusculo), None)


def _problemas_do_commit(
    nome: str, sha: str, depois: Callable[[str], list[str] | None]
) -> list[str]:
    mudados = depois(sha)
    if mudados is None:
        return [f"o commit {sha} da {nome} não está no PR"]
    sensiveis = arquivos_sensiveis(mudados)
    if sensiveis:
        return [
            f"mudança sensível depois da {nome} ({', '.join(sensiveis)}): revisar de novo o último commit"
        ]
    return []


def _problemas_da_seguranca(
    revisoes: Revisoes, depois: Callable[[str], list[str] | None]
) -> list[str]:
    if not revisoes.seguranca:
        return [f"falta a linha da revisão de segurança ({FORMATO_SEGURANCA})"]
    return _problemas_do_commit("revisão de segurança", revisoes.seguranca, depois)


def _problemas_da_cruzada(
    revisoes: Revisoes, sensiveis: list[str], depois: Callable[[str], list[str] | None]
) -> list[str]:
    if revisoes.cruzada_dispensada and not revisoes.cruzada:
        fora = [caminho for caminho in sensiveis if not _casa(caminho, MIGRACOES)]
        if fora:
            return [
                f"a dispensa da revisão cruzada vale só para migração, e o PR muda {', '.join(fora)}"
            ]
        return []
    if not revisoes.cruzada:
        return [f"falta a linha da revisão cruzada ({FORMATO_CRUZADA})"]
    problemas = _problemas_do_commit("revisão cruzada", revisoes.cruzada, depois)
    if not revisoes.feito_por:
        return [
            *problemas,
            "falta a linha 'Feito por:' para comparar o modelo da revisão cruzada",
        ]
    da_cruzada, do_autor = (
        familia(revisoes.modelo_da_cruzada),
        familia(revisoes.feito_por),
    )
    if da_cruzada is None or do_autor is None:
        problemas.append("modelo não reconhecido na revisão cruzada ou no 'Feito por:'")
    elif da_cruzada == do_autor:
        problemas.append(f"revisão cruzada pelo mesmo modelo do autor ({da_cruzada})")
    return problemas


def julgar(
    caminhos: list[str], corpo: str, depois: Callable[[str], list[str] | None]
) -> Veredito:
    """Julga o PR pelos arquivos e pelo corpo; `depois(sha)` diz o que o PR mudou depois daquele commit."""
    sensiveis = arquivos_sensiveis(caminhos)
    if not sensiveis:
        return Veredito(True, "o PR não toca área sensível.")
    lista = ", ".join(sensiveis).replace("\n", " ").replace("\r", " ")
    revisoes = ler_revisoes(corpo)
    if revisoes.todas_dispensadas:
        fora = [caminho for caminho in sensiveis if not _casa(caminho, TEXTO_PUBLICO)]
        if fora:
            return Veredito(
                False,
                f"área sensível ({lista}): a dispensa da Emenda 2 vale só para texto público",
            )
        return Veredito(
            True,
            f"área sensível ({lista}): revisões dispensadas (digitação, Emenda 2).",
        )
    problemas = _problemas_da_seguranca(revisoes, depois) + _problemas_da_cruzada(
        revisoes, sensiveis, depois
    )
    if problemas:
        return Veredito(False, f"área sensível ({lista}): " + "; ".join(problemas))
    return Veredito(
        True,
        f"área sensível ({lista}): as duas revisões estão escritas e valem para o último commit.",
    )


def _git(*argumentos: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argumentos], capture_output=True, text=True, check=False
    )


def arquivos_mudados_depois(sha: str, cabeca: str, base: str) -> list[str] | None:
    """Os arquivos que os commits do próprio PR mudaram depois de `sha` (os que vieram da `main` não contam).

    None quando `sha` não é um commit do PR: não existe, não leva ao último commit ou já está na `main`.
    """
    resolvido = _git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    if resolvido.returncode != 0:
        return None
    completo = resolvido.stdout.strip()
    if _git("merge-base", "--is-ancestor", completo, cabeca).returncode != 0:
        return None
    if completo != _git("rev-parse", cabeca).stdout.strip() and (
        _git("merge-base", "--is-ancestor", completo, base).returncode == 0
    ):
        return None
    saida = _git(
        "log",
        "--no-merges",
        "--format=",
        "--name-only",
        cabeca,
        f"^{completo}",
        f"^{base}",
    ).stdout
    return sorted({linha.strip() for linha in saida.splitlines() if linha.strip()})


def main() -> int:
    """Roda o portão no CI e devolve o código de saída (0 passa)."""
    cabeca = os.environ.get("CABECA") or "HEAD"
    base = os.environ.get("BASE") or "HEAD^1"
    caminhos = _git(
        "diff", "--name-only", "--no-renames", base, cabeca
    ).stdout.splitlines()
    veredito = julgar(
        caminhos,
        os.environ.get("CORPO", ""),
        lambda sha: arquivos_mudados_depois(sha, cabeca, base),
    )
    texto = ("Passa: " if veredito.passa else "Barrado: ") + veredito.motivo
    print(texto)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"### Revisões de área sensível\n\n{texto}\n")
    return 0 if veredito.passa else 1


if __name__ == "__main__":
    sys.exit(main())
