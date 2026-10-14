"""Qual versão do código está rodando (série 3 da base de ML, PR 1; ADR 0055, exigência 13).

A exigência 13 pede que de qualquer número da base se chegue ao original, à data da coleta e à
versão do código que o processou. No contêiner, o build grava o commit em `TICKERLAB_VERSAO`
(`Dockerfile`, `compose.yaml`, `scripts/deploy-automatico.sh`). Fora dele (PC), pergunta ao Git; com
mudanças não salvas num commit, a versão leva "-modificado", porque o número não se refaria daquele
commit. As cargas da base vendável recusam versão desconhecida ou modificada
(`exigir_versao_do_codigo`); o resto só registra o que souber.
"""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

VARIAVEL = "TICKERLAB_VERSAO"
DESCONHECIDA = "desconhecida"
MODIFICADO = "-modificado"
RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parent.parent
SEGUNDOS_PARA_O_GIT = 10

RespostaDoGit = tuple[str, bool] | None  # (commit, tem mudanças não salvas)


class VersaoDesconhecidaError(RuntimeError):
    """A carga da base não sabe de qual commit é o código: a linhagem ficaria sem a versão."""


def _git(*argumentos: str) -> str:
    return subprocess.run(
        ["git", *argumentos],
        cwd=RAIZ_DO_REPOSITORIO,
        capture_output=True,
        text=True,
        check=True,
        timeout=SEGUNDOS_PARA_O_GIT,
    ).stdout.strip()


def _perguntar_ao_git() -> RespostaDoGit:
    """O commit atual e se há mudanças não salvas; None se não há Git ou repositório."""
    try:
        commit = _git("rev-parse", "HEAD")
        modificado = bool(_git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.SubprocessError):
        return None
    return commit, modificado


def versao_do_codigo(git: Callable[[], RespostaDoGit] = _perguntar_ao_git) -> str:
    """O commit do código que está rodando: da imagem, do Git ou `DESCONHECIDA`."""
    gravada = os.environ.get(VARIAVEL, "").strip()
    if gravada:
        return gravada
    resposta = git()
    if resposta is None:
        return DESCONHECIDA
    commit, modificado = resposta
    return commit + MODIFICADO if modificado else commit


def exigir_versao_do_codigo(
    git: Callable[[], RespostaDoGit] = _perguntar_ao_git,
) -> str:
    """Como `versao_do_codigo`, mas recusa a versão desconhecida ou modificada (cargas da base)."""
    versao = versao_do_codigo(git)
    if versao == DESCONHECIDA:
        raise VersaoDesconhecidaError(
            f"Não sei a versão do código: rode na imagem (com {VARIAVEL}) ou numa cópia do Git."
        )
    if versao.endswith(MODIFICADO):
        raise VersaoDesconhecidaError(
            f"Código {versao}: salve as mudanças num commit antes de gravar a base."
        )
    return versao
