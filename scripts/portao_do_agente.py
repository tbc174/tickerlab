"""Portão do CI para os PRs do agente da fila (ADR 0105, na pasta privada).

O agente da fila roda na nuvem a cada 3 horas e abre PRs em ramos `claude/agente-...`. No GitHub
todo PR sai da mesma conta, então o CI só reconhece o agente pelo ramo. Este passo decide:

- só testes e docs → passa, e o PR pode entrar sozinho pelo auto-merge;
- outro código → falha até alguém pôr o rótulo `revisado` (e de novo a cada commit novo);
- área proibida (login, cobrança, planos, migração, CI, Docker, trader, site, textos legais,
  regras da casa) → falha sempre: não é trabalho do agente.

Uso no CI (job "o que mudou", só em PR): `python3 scripts/portao_do_agente.py BASE`, com o ramo
em `RAMO`, o evento em `ACAO` e os rótulos (JSON) em `ROTULOS`. Ramo que não é do agente passa
sem olhar nada. Roda antes de instalar as dependências: só usa a biblioteca padrão.
"""

import json
import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatch

PREFIXO_DO_RAMO = "claude/agente-"
ROTULO_DE_REVISAO = "revisado"

# O que o agente nunca muda, nem com revisão (no fnmatch, "*" também atravessa "/").
PROIBIDOS = (
    ".github/*",
    "migracoes/*",
    "alembic.ini",
    "Dockerfile",
    "compose.yaml",
    "requirements*.txt",
    "ruff.toml",
    "pyrightconfig.json",
    "pytest.ini",
    ".coveragerc",
    "trader/*",
    "pesquisa_m2/*",
    "conteudo/*",
    "site/*",
    "web/*",
    "novo/*",
    "static/*",
    "README.md",
    "CLAUDE.md",
    "*/CLAUDE.md",
    "AGENTS.md",
    "SECURITY.md",
    "docs/pre-registro-*",
    "src/autenticacao.py",
    "src/codigo_de_entrada.py",
    "src/cobranca.py",
    "src/planos.py",
    "src/administracao.py",
    "src/conformidade.py",
    "src/configuracao.py",
    "src/api.py",
    "src/api_v1/acesso.py",
    "src/api_v1/conta.py",
    "src/api_v1/sessao.py",
    "src/banco/conexao.py",
    "src/banco/dados_do_usuario.py",
    "src/banco/modelo.py",
    "src/banco/mudar_plano.py",
    "src/banco/sessoes.py",
    "src/banco/usuarios.py",
    "telas/conta/*",
    "telas/dados_da_conta.py",
    "scripts/deploy-automatico.sh",
    "scripts/expurgar_login.py",
    "scripts/mudou_so_texto.py",
    "scripts/repartir_testes.py",
    "scripts/portao_do_agente.py",
    "tests/test_portao_do_agente.py",
)

# O que entra sozinho pelo auto-merge (escolha do Tiago em 20/10: teste e doc).
SEM_REVISAO = (
    "tests/test_*.py",
    "tests/*/test_*.py",
    "tests/duracoes.json",
    "docs/*.md",
)

# Dentro de tests/, mas mudar faz muitos testes passarem sem testar: pede revisão.
BASE_DOS_TESTES = ("tests/conftest.py", "tests/ajudantes_*", "tests/arquivos/*")

# Linha adicionada que pula um teste: pede revisão (o jeito mais fácil de "consertar" um CI).
SINAIS_DE_PULAR = ("pytest.mark.skip", "pytest.skip(", "xfail", "importorskip")

ACAO_DE_COMMIT_NOVO = "synchronize"


@dataclass(frozen=True)
class Alteracao:
    """Um arquivo do PR e o que aconteceu com ele (letra do `git diff --name-status`)."""

    situacao: str
    caminho: str


@dataclass(frozen=True)
class Veredito:
    """Se o passo do CI passa e a frase que explica por quê."""

    passa: bool
    motivo: str


def e_ramo_do_agente(ramo: str) -> bool:
    """Diz se o ramo do PR é do agente da fila."""
    return ramo.startswith(PREFIXO_DO_RAMO)


def _casa(caminho: str, padroes: Iterable[str]) -> bool:
    return any(fnmatch(caminho, padrao) for padrao in padroes)


def _dispensa_revisao(caminho: str) -> bool:
    return _casa(caminho, SEM_REVISAO) and not _casa(caminho, BASE_DOS_TESTES)


def _o_que_pede_revisao(
    alteracoes: list[Alteracao], linhas_adicionadas: list[str]
) -> list[str]:
    motivos = [a.caminho for a in alteracoes if not _dispensa_revisao(a.caminho)]
    apagados = [
        a.caminho
        for a in alteracoes
        if a.situacao == "D" and a.caminho.startswith("tests/")
    ]
    if apagados:
        motivos.append("apaga teste: " + ", ".join(apagados))
    if any(sinal in linha for linha in linhas_adicionadas for sinal in SINAIS_DE_PULAR):
        motivos.append("pula teste (skip ou xfail)")
    return motivos


def julgar(
    alteracoes: list[Alteracao],
    linhas_adicionadas: list[str],
    rotulos: list[str],
    acao: str,
) -> Veredito:
    """Julga um PR do agente pelos arquivos, pelas linhas adicionadas, pelos rótulos e pelo evento."""
    if not alteracoes:
        return Veredito(False, "PR sem arquivos mudados: nada para mesclar.")
    proibidos = [a.caminho for a in alteracoes if _casa(a.caminho, PROIBIDOS)]
    if proibidos:
        return Veredito(
            False, "área proibida ao agente (ADR 0105): " + ", ".join(proibidos)
        )
    pede_revisao = _o_que_pede_revisao(alteracoes, linhas_adicionadas)
    if not pede_revisao:
        return Veredito(True, "só teste e doc: pode entrar sozinho pelo auto-merge.")
    lista = "; ".join(pede_revisao)
    if ROTULO_DE_REVISAO not in rotulos:
        return Veredito(
            False, f"espera o rótulo '{ROTULO_DE_REVISAO}' de uma pessoa: {lista}"
        )
    if acao == ACAO_DE_COMMIT_NOVO:
        return Veredito(
            False,
            f"commit novo depois da revisão: tire e ponha o rótulo '{ROTULO_DE_REVISAO}' de novo.",
        )
    return Veredito(True, f"revisado: {lista}")


def ler_alteracoes(saida_do_git: str) -> list[Alteracao]:
    """Lê a saída de `git diff --name-status --no-renames`."""
    alteracoes = []
    for linha in saida_do_git.splitlines():
        if linha.strip():
            situacao, caminho = linha.split("\t", 1)
            alteracoes.append(Alteracao(situacao.strip(), caminho.strip()))
    return alteracoes


def ler_linhas_adicionadas(diff: str) -> list[str]:
    """Devolve as linhas que o diff acrescenta, sem o "+" (sem o cabeçalho "+++")."""
    return [
        linha[1:]
        for linha in diff.splitlines()
        if linha.startswith("+") and not linha.startswith("+++")
    ]


def _git(*argumentos: str) -> str:
    return subprocess.run(
        ["git", *argumentos], capture_output=True, text=True, check=True
    ).stdout


def main(base: str) -> int:
    """Roda o portão no CI e devolve o código de saída (0 passa)."""
    ramo = os.environ.get("RAMO", "")
    if not e_ramo_do_agente(ramo):
        print(f"Ramo '{ramo}' não é do agente da fila: o portão não se aplica.")
        return 0
    alteracoes = ler_alteracoes(
        _git("diff", "--name-status", "--no-renames", base, "HEAD")
    )
    linhas = ler_linhas_adicionadas(
        _git("diff", "--no-renames", base, "HEAD", "--", "tests/")
    )
    rotulos = json.loads(os.environ.get("ROTULOS") or "[]")
    veredito = julgar(alteracoes, linhas, rotulos, os.environ.get("ACAO", ""))
    print(("Passa: " if veredito.passa else "Barrado: ") + veredito.motivo)
    return 0 if veredito.passa else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
