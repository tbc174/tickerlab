"""O portão do CI deixa o agente da fila mesclar sozinho só teste e doc (ADR 0105)."""

import pytest

from scripts.portao_do_agente import (
    ROTULO_DE_REVISAO,
    Alteracao,
    Veredito,
    e_ramo_do_agente,
    julgar,
    ler_alteracoes,
    ler_linhas_adicionadas,
)


def _mudou(*caminhos: str) -> list[Alteracao]:
    return [Alteracao("M", caminho) for caminho in caminhos]


@pytest.mark.parametrize(
    ("ramo", "esperado"),
    [
        ("claude/agente-relogio-da-b3", True),
        ("feat/molde-d", False),
        (
            "claude/priceless-pasteur-8e7b61",
            False,
        ),  # cópia de uma conversa, não o agente
        ("", False),
    ],
)
def test_so_ramos_claude_agente_sao_do_agente(ramo, esperado):
    assert e_ramo_do_agente(ramo) is esperado


def test_so_teste_e_doc_passa_sem_rotulo():
    veredito = julgar(
        _mudou("tests/test_copia_b3.py", "docs/dicionario-da-base.md"), [], [], "opened"
    )
    assert veredito == Veredito(passa=True, motivo=veredito.motivo)
    assert "sozinho" in veredito.motivo


def test_codigo_do_app_espera_o_rotulo_de_revisao():
    veredito = julgar(
        _mudou("scripts/reconciliar_b3_vps.py", "tests/test_copia_b3.py"),
        [],
        [],
        "opened",
    )
    assert not veredito.passa
    assert ROTULO_DE_REVISAO in veredito.motivo
    assert "scripts/reconciliar_b3_vps.py" in veredito.motivo


def test_codigo_do_app_com_rotulo_passa():
    veredito = julgar(_mudou("src/logs.py"), [], [ROTULO_DE_REVISAO], "labeled")
    assert veredito.passa


def test_push_depois_do_rotulo_volta_a_pedir_revisao():
    """A revisão vale para o código que a pessoa viu: commit novo pede o rótulo de novo."""
    veredito = julgar(_mudou("src/logs.py"), [], [ROTULO_DE_REVISAO], "synchronize")
    assert not veredito.passa
    assert "depois da revisão" in veredito.motivo


@pytest.mark.parametrize(
    "caminho",
    [
        ".github/workflows/testes.yml",
        "migracoes/versions/0042_x.py",
        "src/planos.py",
        "src/cobranca.py",
        "src/autenticacao.py",
        "src/banco/usuarios.py",
        "telas/conta/entrar.py",
        "trader/rodar_modelo.py",
        "conteudo/privacidade.md",
        "web/src/app/Formulario.tsx",
        "site/index.html",
        "requirements.txt",
        "Dockerfile",
        "README.md",
        "CLAUDE.md",
        "trader/CLAUDE.md",
        "AGENTS.md",
        "trader/AGENTS.md",
        "docs/pre-registro-m2-v0.4.md",
        "scripts/portao_do_agente.py",  # o agente não mexe no próprio portão
        "tests/test_portao_do_agente.py",
    ],
)
def test_area_proibida_falha_mesmo_com_rotulo(caminho):
    veredito = julgar(_mudou(caminho), [], [ROTULO_DE_REVISAO], "labeled")
    assert not veredito.passa
    assert caminho in veredito.motivo


@pytest.mark.parametrize(
    "caminho",
    [
        "tests/conftest.py",
        "tests/ajudantes_da_conta.py",
        "tests/arquivos/analise/cpfl/gabarito.json",
    ],
)
def test_base_compartilhada_dos_testes_e_gabaritos_pedem_revisao(caminho):
    """Mudar o conftest, um ajudante ou um gabarito pode fazer muitos testes passarem sem testar."""
    veredito = julgar(_mudou(caminho), [], [], "opened")
    assert not veredito.passa
    assert ROTULO_DE_REVISAO in veredito.motivo


def test_apagar_teste_pede_revisao():
    veredito = julgar([Alteracao("D", "tests/test_logs.py")], [], [], "opened")
    assert not veredito.passa
    assert "apaga" in veredito.motivo


@pytest.mark.parametrize(
    "linha",
    [
        "@pytest.mark.skip(reason='instável')",
        "    pytest.skip('sem rede')",
        "@pytest.mark.xfail",
        "pd = pytest.importorskip('pandas')",
    ],
)
def test_pular_teste_pede_revisao(linha):
    veredito = julgar(_mudou("tests/test_logs.py"), [linha], [], "opened")
    assert not veredito.passa
    assert "pula" in veredito.motivo


def test_lista_vazia_nao_passa_sozinha():
    assert not julgar([], [], [], "opened").passa


def test_le_as_alteracoes_do_git_diff_name_status():
    saida = "M\ttests/test_a.py\nD\ttests/test_b.py\nA\tdocs/novo.md\n\n"
    assert ler_alteracoes(saida) == [
        Alteracao("M", "tests/test_a.py"),
        Alteracao("D", "tests/test_b.py"),
        Alteracao("A", "docs/novo.md"),
    ]


def test_le_so_as_linhas_adicionadas_do_diff():
    diff = (
        "diff --git a/tests/test_a.py b/tests/test_a.py\n"
        "--- a/tests/test_a.py\n"
        "+++ b/tests/test_a.py\n"
        "@@ -1 +1 @@\n"
        "-@pytest.mark.skip\n"
        "+def test_novo():\n"
    )
    assert ler_linhas_adicionadas(diff) == ["def test_novo():"]
