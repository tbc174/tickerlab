"""Portão das revisões: PR que toca área sensível só passa com as duas revisões escritas no corpo (AGENTS.md).

Semana de medição (Diretoria, 25/11/2026): no CI ele só avisa. O teste cobra o que ele decide.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import portao_das_revisoes, portao_do_agente
from scripts.portao_das_revisoes import (
    arquivos_mudados_depois,
    arquivos_sensiveis,
    familia,
    julgar,
    ler_revisoes,
)

SHA = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
SEGURANCA = f"Revisão de segurança: sem achado bloqueante · commit {SHA[:7]}"
CRUZADA = f"Revisão cruzada (Claude Sonnet 5.5): sem P0 nem P1 · commit {SHA[:7]}"
FEITO_POR = "Feito por: Claude Opus 5.5"
CORPO_BOM = f"## O que muda\n\nalgo\n\n{SEGURANCA}\n{CRUZADA}\n\n{FEITO_POR}\n"


def _nada_depois(_sha: str) -> list[str]:
    return []


def _julgar(caminhos, corpo=CORPO_BOM, depois=_nada_depois):
    return julgar(list(caminhos), corpo, depois)


# ---------- o que é área sensível ----------


@pytest.mark.parametrize(
    "caminho",
    [
        "src/autenticacao.py",
        "src/cobranca.py",
        "src/planos.py",
        "migracoes/versions/0099_algo.py",
        ".github/workflows/testes.yml",
        "telas/conta/entrar.py",
        "src/conformidade.py",
        "conteudo/termos-de-uso.md",
        "web/src/site/Inicio.tsx",
        "web/src/paginas/precos.tsx",
        "web/src/conteudo.ts",
        "README.md",
        "src/banco/membros_da_organizacao.py",
        "compose.conector.yaml",
        "scripts/portao_das_revisoes.py",
        "scripts/portao_do_agente.py",
        # fonte em Python ou JS do texto público e legal (revisão de segurança do #1299)
        "src/paginas.py",
        "base/vitrine.py",
        "src/envio_novidades.py",
        "scripts/gerar_site.py",
        "web/publico/origem.js",
        "web/src/rotas.tsx",
        "web/src/entry-server.tsx",
        # login e contas do lado do cliente
        "web/src/app/login.ts",
        "web/src/app/conta.tsx",
        "web/src/app/administracao.ts",
        "web/src/app/EntradaPorEmail.tsx",
    ],
)
def test_area_sensivel(caminho):
    assert arquivos_sensiveis([caminho]) == [caminho]


@pytest.mark.parametrize(
    "caminho",
    [
        "src/indicadores.py",
        "tests/test_planos.py",
        "docs/cli.md",
        "trader/modelo.py",
        "requirements.txt",
        # pastas geradas: o CI já confere que batem com a fonte, e a fonte é que conta
        "site/index.html",
        "novo/app.js",
        "web/conteudo/paginas.json",
        # dentro de web/, só as páginas públicas são texto público: o app com login e os testes, não
        "web/src/app/Carteira.tsx",
        "web/testes/site.test.tsx",
        "web/src/estilo.ts",
    ],
)
def test_fora_da_area_sensivel(caminho):
    assert arquivos_sensiveis([caminho]) == []


def test_pr_sem_area_sensivel_passa_sem_olhar_o_corpo():
    veredito = _julgar(["src/indicadores.py", "tests/test_indicadores.py"], corpo="")
    assert veredito.passa


# a lista do agente da fila é a mesma de antes: tirar dela a parte sensível não muda o que ele pode
PROIBIDOS_ANTES = {
    ".github/*", "migracoes/*", "alembic.ini", "Dockerfile", "compose.yaml", "requirements*.txt", "ruff.toml",
    "pyrightconfig.json", "pytest.ini", ".coveragerc", "trader/*", "pesquisa_m2/*", "conteudo/*", "site/*",
    "web/*", "novo/*", "static/*", "README.md", "CLAUDE.md", "*/CLAUDE.md", "AGENTS.md", "*/AGENTS.md",
    "SECURITY.md", "docs/pre-registro-*", "src/autenticacao.py", "src/codigo_de_entrada.py", "src/cobranca.py",
    "src/planos.py", "src/administracao.py", "src/conformidade.py", "src/configuracao.py", "src/api.py",
    "src/api_v1/acesso.py", "src/api_v1/conta.py", "src/api_v1/sessao.py", "src/banco/conexao.py",
    "src/banco/dados_do_usuario.py", "src/banco/modelo.py", "src/banco/mudar_plano.py", "src/banco/sessoes.py",
    "src/banco/usuarios.py", "telas/conta/*", "telas/dados_da_conta.py", "scripts/deploy-automatico.sh",
    "scripts/expurgar_login.py", "scripts/mudou_so_texto.py", "scripts/repartir_testes.py",
    "scripts/portao_do_agente.py", "tests/test_portao_do_agente.py",
}  # fmt: skip


def test_o_agente_da_fila_continua_proibido_do_mesmo_jeito():
    assert set(portao_do_agente.PROIBIDOS) == PROIBIDOS_ANTES
    assert len(portao_do_agente.PROIBIDOS) == len(PROIBIDOS_ANTES)
    assert set(portao_do_agente.AREAS_SENSIVEIS) <= PROIBIDOS_ANTES


# ---------- leitura do corpo ----------


def test_le_as_linhas_com_markdown_e_fim_de_linha_do_windows():
    corpo = f"- **{SEGURANCA}**\r\n> {CRUZADA}\r\n{FEITO_POR}\r\n"
    revisoes = ler_revisoes(corpo)
    assert revisoes.seguranca == SHA[:7]
    assert (revisoes.cruzada, revisoes.modelo_da_cruzada) == (
        SHA[:7],
        "Claude Sonnet 5.5",
    )
    assert revisoes.feito_por == "Claude Opus 5.5"


def test_vale_a_ultima_revisao_escrita():
    corpo = f"{SEGURANCA}\n{SEGURANCA.replace(SHA[:7], 'abcdef0')}\n"
    assert ler_revisoes(corpo).seguranca == "abcdef0"


@pytest.mark.parametrize(
    ("modelo", "esperado"),
    [
        ("Claude Opus 5.5", "opus"),
        ("Claude Sonnet 5.5", "sonnet"),
        ("Claude Haiku 5.5", "haiku"),
        ("Claude Fable 5.2", "fable"),
        ("Codex (GPT-6)", "gpt"),
        ("Gemini 3 Pro", "gemini"),
        ("GitHub Copilot", "copilot"),
        ("um modelo qualquer", None),
    ],
)
def test_familia_do_modelo(modelo, esperado):
    assert familia(modelo) == esperado


# ---------- o veredito ----------


def test_area_sensivel_com_as_duas_revisoes_passa():
    assert _julgar(["src/cobranca.py"]).passa


@pytest.mark.parametrize(
    ("corpo", "motivo"),
    [
        ("", "revisão de segurança"),
        (f"{SEGURANCA}\n{FEITO_POR}", "revisão cruzada"),
        (f"{CRUZADA}\n{FEITO_POR}", "revisão de segurança"),
        (f"{SEGURANCA}\n{CRUZADA}", "Feito por"),
        (
            f"{SEGURANCA}\n{CRUZADA.replace('Sonnet', 'Opus')}\n{FEITO_POR}",
            "mesmo modelo",
        ),
        (
            f"{SEGURANCA}\n{CRUZADA.replace('Claude Sonnet 5.5', 'alguém')}\n{FEITO_POR}",
            "modelo não reconhecido",
        ),
        (
            f"{SEGURANCA.replace('sem achado bloqueante', 'um P1 aberto')}\n{CRUZADA}\n{FEITO_POR}",
            "segurança",
        ),
        (
            f"{SEGURANCA}\n{CRUZADA.replace('sem P0 nem P1', '1 P1')}\n{FEITO_POR}",
            "revisão cruzada",
        ),
    ],
)
def test_area_sensivel_sem_revisao_completa_falha(corpo, motivo):
    veredito = _julgar(["src/planos.py"], corpo=corpo)
    assert not veredito.passa
    assert motivo in veredito.motivo


def test_mudanca_sensivel_depois_da_revisao_derruba():
    veredito = _julgar(["src/planos.py"], depois=lambda _sha: ["src/planos.py"])
    assert not veredito.passa
    assert "depois da revisão" in veredito.motivo


def test_mudanca_que_nao_e_sensivel_depois_da_revisao_nao_derruba():
    assert _julgar(
        ["src/planos.py"], depois=lambda _sha: ["tests/test_planos.py"]
    ).passa


def test_commit_citado_que_nao_e_do_pr_falha():
    veredito = _julgar(["src/planos.py"], depois=lambda _sha: None)
    assert not veredito.passa
    assert "não está no PR" in veredito.motivo


def test_cruzada_dispensada_vale_so_para_migracao():
    corpo = f"{SEGURANCA}\nRevisão cruzada: dispensada (migração só acrescenta, Emenda 2)\n{FEITO_POR}"
    assert _julgar(["migracoes/versions/0099_coluna.py"], corpo=corpo).passa
    veredito = _julgar(
        ["migracoes/versions/0099_coluna.py", "src/planos.py"], corpo=corpo
    )
    assert not veredito.passa
    assert "dispensa" in veredito.motivo


def test_revisoes_dispensadas_valem_so_para_texto_publico():
    corpo = "Revisões: dispensadas (digitação, Emenda 2)"
    assert _julgar(["web/src/site/Inicio.tsx", "README.md"], corpo=corpo).passa
    veredito = _julgar(["web/src/site/Inicio.tsx", "src/cobranca.py"], corpo=corpo)
    assert not veredito.passa
    assert "dispensa" in veredito.motivo


def test_motivo_nunca_comeca_linha_com_comando_do_actions():
    veredito = _julgar(["src/planos.py", "::warning::x.py"], corpo="")
    assert "\n" not in veredito.motivo
    assert not veredito.motivo.startswith("::")


# ---------- o que mudou depois do commit revisado (git de verdade) ----------


def _git(pasta: Path, *argumentos: str) -> str:
    return subprocess.run(
        ["git", "-C", str(pasta), *argumentos],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _commit(pasta: Path, arquivo: str, mensagem: str) -> str:
    caminho = pasta / arquivo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(mensagem, encoding="utf-8")
    _git(pasta, "add", arquivo)
    _git(pasta, "commit", "-q", "-m", mensagem)
    return _git(pasta, "rev-parse", "HEAD")


@pytest.mark.skipif(shutil.which("git") is None, reason="sem git")
def test_arquivos_mudados_depois_ignoram_o_que_veio_da_main(tmp_path, monkeypatch):
    for variavel in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(variavel, raising=False)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "teste@exemplo.invalid")
    _git(tmp_path, "config", "user.name", "teste")
    _commit(tmp_path, "README.md", "início")
    _git(tmp_path, "switch", "-q", "-c", "ramo")
    revisado = _commit(tmp_path, "src/planos.py", "mudança revisada")
    _git(tmp_path, "switch", "-q", "main")
    _commit(tmp_path, "src/cobranca.py", "outra coisa na main")
    _git(tmp_path, "switch", "-q", "ramo")
    _git(tmp_path, "merge", "-q", "--no-edit", "main")
    cabeca = _commit(tmp_path, "tests/test_planos.py", "teste depois da revisão")

    monkeypatch.chdir(tmp_path)
    assert arquivos_mudados_depois(revisado[:7], cabeca, "main") == [
        "tests/test_planos.py"
    ]
    assert arquivos_mudados_depois(cabeca, cabeca, "main") == []
    assert arquivos_mudados_depois("0000000", cabeca, "main") is None
    fora_do_pr = _git(tmp_path, "rev-parse", "main")
    assert arquivos_mudados_depois(fora_do_pr, cabeca, "main") is None


@pytest.mark.skipif(shutil.which("git") is None, reason="sem git")
def test_renomear_arquivo_sensivel_depois_da_revisao_aparece(tmp_path, monkeypatch):
    for variavel in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(variavel, raising=False)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "teste@exemplo.invalid")
    _git(tmp_path, "config", "user.name", "teste")
    _commit(tmp_path, "src/cobranca.py", "cobrança")
    _git(tmp_path, "switch", "-q", "-c", "ramo")
    revisado = _commit(tmp_path, "docs/x.md", "revisado")
    _git(tmp_path, "mv", "src/cobranca.py", "src/outra.py")
    _git(tmp_path, "commit", "-q", "-m", "renomeia")
    cabeca = _git(tmp_path, "rev-parse", "HEAD")

    monkeypatch.chdir(tmp_path)
    assert "src/cobranca.py" in (
        arquivos_mudados_depois(revisado, cabeca, "main") or []
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="sem git")
def test_pr_atras_da_main_nao_herda_o_que_a_main_mudou(tmp_path, monkeypatch, capsys):
    """No CI, HEAD é o commit que junta o PR à main; o PR só de doc não vira sensível pela main."""
    for variavel in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GITHUB_STEP_SUMMARY",
    ):
        monkeypatch.delenv(variavel, raising=False)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "teste@exemplo.invalid")
    _git(tmp_path, "config", "user.name", "teste")
    _commit(tmp_path, "README.md", "início")
    _git(tmp_path, "switch", "-q", "-c", "ramo")
    cabeca = _commit(tmp_path, "docs/x.md", "só doc")
    _git(tmp_path, "switch", "-q", "main")
    _commit(tmp_path, "src/cobranca.py", "PR sensível mesclado na main depois")
    _git(tmp_path, "switch", "-q", "--detach", "main")
    _git(
        tmp_path, "merge", "-q", "--no-edit", "ramo"
    )  # o commit de merge que o CI testa

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CORPO", "")
    monkeypatch.setenv("CABECA", cabeca)
    monkeypatch.setenv("BASE", "HEAD^1")
    assert portao_das_revisoes.main() == 0
    assert "não toca área sensível" in capsys.readouterr().out


@pytest.mark.parametrize(
    "linha",
    [
        f"**Revisão de segurança:** sem achado bloqueante · commit {SHA[:7]}",
        f"1. Revisão de segurança: sem achado bloqueante · commit `{SHA[:7]}`.",
        f"`Revisão de segurança: sem achado bloqueante · commit {SHA[:7]}`",
    ],
)
def test_le_a_linha_com_enfeite_de_markdown_no_meio(linha):
    assert ler_revisoes(linha).seguranca == SHA[:7]


@pytest.mark.skipif(shutil.which("git") is None, reason="sem git")
def test_conflito_resolvido_no_merge_depois_da_revisao_aparece(tmp_path, monkeypatch):
    for variavel in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(variavel, raising=False)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "teste@exemplo.invalid")
    _git(tmp_path, "config", "user.name", "teste")
    _commit(tmp_path, "src/autenticacao.py", "base")
    _git(tmp_path, "switch", "-q", "-c", "ramo")
    revisado = _commit(tmp_path, "src/autenticacao.py", "versão do ramo")
    _git(tmp_path, "switch", "-q", "main")
    _commit(tmp_path, "src/autenticacao.py", "versão da main")
    _git(tmp_path, "switch", "-q", "ramo")
    subprocess.run(
        ["git", "-C", str(tmp_path), "merge", "-q", "main"],
        capture_output=True,
        check=False,
    )
    (tmp_path / "src/autenticacao.py").write_text(
        "resolvido à mão, diferente dos dois", encoding="utf-8"
    )
    _git(tmp_path, "add", "src/autenticacao.py")
    _git(tmp_path, "commit", "-q", "--no-edit")
    cabeca = _git(tmp_path, "rev-parse", "HEAD")

    monkeypatch.chdir(tmp_path)
    assert "src/autenticacao.py" in (
        arquivos_mudados_depois(revisado, cabeca, "main") or []
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="sem git")
def test_nome_com_acento_sai_sem_aspas(tmp_path, monkeypatch):
    for variavel in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(variavel, raising=False)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "teste@exemplo.invalid")
    _git(tmp_path, "config", "user.name", "teste")
    _commit(tmp_path, "README.md", "início")
    _git(tmp_path, "switch", "-q", "-c", "ramo")
    revisado = _commit(tmp_path, "docs/x.md", "revisado")
    cabeca = _commit(tmp_path, "migracoes/versions/0099_ação.py", "migração com acento")

    monkeypatch.chdir(tmp_path)
    assert arquivos_mudados_depois(revisado, cabeca, "main") == [
        "migracoes/versions/0099_ação.py"
    ]
