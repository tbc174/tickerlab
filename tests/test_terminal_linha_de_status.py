"""A linha de status do Claude Code com a cara do TickerLab (scripts/terminal/statusline.js) roda no Node:
aqui conferimos as funções puras (CI, PR, nome da conversa, fila) e uma saída ponta a ponta com um JSON de
amostra. Pula quando o Node não está instalado."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
LINHA_DE_STATUS = RAIZ / "scripts" / "terminal" / "statusline.js"
EXEMPLO_DA_FILA = RAIZ / "scripts" / "terminal" / "testes" / "exemplos" / "fila.md"
NODE = shutil.which("node")
SEGUNDOS_DE_LIMITE = 60
CODIGO_ANSI = re.compile(r"\x1b\[[0-9;]*m")
VERMELHO, VERDE, AMARELO = "\x1b[31m", "\x1b[32m", "\x1b[33m"
LARGURA_DO_NOME = 48

pytestmark = pytest.mark.skipif(
    NODE is None, reason="Node.js (node) não está instalado"
)


def rodar_node(
    *argumentos: str, entrada: str = "", ambiente: dict[str, str] | None = None
) -> str:
    assert NODE is not None
    resultado = subprocess.run(
        [NODE, *argumentos],
        input=entrada,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=SEGUNDOS_DE_LIMITE,
        check=False,
        env=ambiente,
    )
    assert resultado.returncode == 0, resultado.stderr
    return resultado.stdout


def chamar(funcao: str, *argumentos: object) -> object:
    """Chama uma função exportada pelo statusline.js, com os argumentos em JSON, e devolve o resultado."""
    codigo = (
        f"const linha = require({json.dumps(LINHA_DE_STATUS.as_posix())});"
        "const argumentos = JSON.parse(process.argv[1]);"
        f"process.stdout.write(JSON.stringify(linha[{json.dumps(funcao)}](...argumentos)));"
    )
    return json.loads(rodar_node("-e", codigo, "--", json.dumps(list(argumentos))))


def sem_cores(texto: object) -> str:
    return CODIGO_ANSI.sub("", str(texto))


@pytest.mark.parametrize(
    ("verificacoes", "esperado"),
    [
        ([], "…"),
        ([{"conclusion": "SUCCESS"}, {"conclusion": "SUCCESS"}], "✓"),
        ([{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}], "✗"),
        ([{"conclusion": "SUCCESS"}, {"conclusion": None, "state": "PENDING"}], "…"),
        ([{"conclusion": "SUCCESS"}, {"status": "IN_PROGRESS"}], "…"),
        ([{"conclusion": "CANCELLED"}, {"status": "IN_PROGRESS"}], "✗"),
    ],
)
def test_resumo_do_ci_como_no_painel_tl(verificacoes, esperado):
    assert chamar("resumoDoCI", verificacoes) == esperado


def test_texto_do_pr_mostra_estado_ci_rascunho_e_conflito():
    aberto = {
        "number": 912,
        "state": "OPEN",
        "isDraft": False,
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "mergeStateStatus": "CLEAN",
    }
    assert sem_cores(chamar("textoDoPR", aberto)) == "PR #912 ✓"
    rascunho = {
        **aberto,
        "isDraft": True,
        "statusCheckRollup": [{"status": "IN_PROGRESS"}],
    }
    assert sem_cores(chamar("textoDoPR", rascunho)) == "PR #912 rascunho …"
    conflito = {
        **aberto,
        "statusCheckRollup": [{"conclusion": "FAILURE"}],
        "mergeStateStatus": "DIRTY",
    }
    assert sem_cores(chamar("textoDoPR", conflito)) == "PR #912 ✗ conflito"
    assert (
        sem_cores(chamar("textoDoPR", {**aberto, "state": "MERGED"}))
        == "PR #912 mesclado"
    )
    assert (
        sem_cores(chamar("textoDoPR", {**aberto, "state": "CLOSED"}))
        == "PR #912 fechado"
    )
    assert chamar("textoDoPR", None) == ""


@pytest.mark.parametrize(
    ("pasta", "esperado"),
    [
        ("analise-acoes-plataforma-terminal", "Plataforma · terminal"),
        ("analise-acoes-dados-sidra-392", "Dados · sidra 392"),
        ("analise-acoes-satelites-pead-680", "Satélites · pead 680"),
        ("analise-acoes-dados", "Dados"),
        ("analise-acoes-virada-fase1-pr2", "virada fase1 pr2"),
        ("analise-acoes", ""),
        ("outro-projeto", ""),
    ],
)
def test_nome_pela_pasta_da_copia(pasta, esperado):
    assert chamar("nomePelaPasta", pasta) == esperado


def test_nome_da_conversa_prefere_o_nome_da_sessao():
    nome = "Plataforma · painel do Claude no terminal"
    assert (
        chamar(
            "nomeDaConversa",
            {"session_name": nome, "cwd": "C:/x/analise-acoes-dados-sidra-392"},
        )
        == nome
    )
    assert (
        chamar("nomeDaConversa", {"cwd": "C:/x/analise-acoes-dados-sidra-392"})
        == "Dados · sidra 392"
    )
    pelo_workspace = {
        "workspace": {"current_dir": "/home/x/analise-acoes-produto-ficha"}
    }
    assert chamar("nomeDaConversa", pelo_workspace) == "Produto · ficha"
    assert chamar("nomeDaConversa", {}) == ""


def test_nome_longo_e_encurtado_com_reticencias():
    nome = chamar("nomeDaConversa", {"session_name": "Dados · " + "palavra " * 20})
    assert isinstance(nome, str)
    assert nome.endswith("…")
    assert len(nome) <= LARGURA_DO_NOME


def test_linhas_da_tabela_do_trabalhando_agora():
    texto = EXEMPLO_DA_FILA.read_text(encoding="utf-8")
    linhas = chamar("linhasDaTabela", texto, "Trabalhando agora")
    assert isinstance(linhas, list)
    assert len(linhas) == 2
    assert "TCE-CE" in linhas[0]
    assert chamar("linhasDaTabela", texto, "Seção que não existe") == []


def test_titulo_da_secao_com_complemento_ainda_conta():
    # A fila de verdade escreve "## Trabalhando agora (máximo 15, até 5 por mesa)".
    texto = EXEMPLO_DA_FILA.read_text(encoding="utf-8").replace(
        "## Trabalhando agora", "## Trabalhando agora (máximo 15, até 5 por mesa)"
    )
    assert len(chamar("linhasDaTabela", texto, "Trabalhando agora")) == 2
    assert (
        chamar("linhasDaTabela", texto, "Fil") == []
    )  # pedaço de palavra não é título


def test_vagas_da_fila_pelo_exemplo():
    assert sem_cores(chamar("vagasDaFila", str(EXEMPLO_DA_FILA))) == "fila 2/15"
    assert chamar("vagasDaFila", str(EXEMPLO_DA_FILA.with_name("nao-existe.md"))) == ""
    assert chamar("vagasDaFila", "") == ""


def fila_com(quantas: int, pasta: Path) -> Path:
    linhas = [
        "## Trabalhando agora",
        "",
        "| Conversa | Mesa | Item | Desde |",
        "|---|---|---|---|",
    ]
    linhas += [
        f"| Conversa {numero} | Dados | {numero}: item | 05/11 |"
        for numero in range(quantas)
    ]
    linhas += ["", "## Fila", "", "| Item |", "|---|", "| 1 |"]
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "fila.md"
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return arquivo


def test_fila_cheia_fica_vermelha_e_quase_cheia_amarela(tmp_path):
    cheia = str(chamar("vagasDaFila", str(fila_com(15, tmp_path / "cheia"))))
    assert sem_cores(cheia) == "fila 15/15 cheia"
    assert VERMELHO in cheia
    quase = str(chamar("vagasDaFila", str(fila_com(13, tmp_path / "quase"))))
    assert sem_cores(quase) == "fila 13/15"
    assert AMARELO in quase
    folgada = str(chamar("vagasDaFila", str(fila_com(2, tmp_path / "folgada"))))
    assert VERDE in folgada


def test_saida_ponta_a_ponta_com_json_de_amostra(tmp_path):
    pasta_privada = tmp_path / "privada"
    (pasta_privada / "projeto-acoes").mkdir(parents=True)
    shutil.copyfile(EXEMPLO_DA_FILA, pasta_privada / "projeto-acoes" / "fila.md")
    copia = (
        tmp_path / "analise-acoes-dados-sidra-392"
    )  # sem git: sem ramo, sem PR e sem processo filho
    copia.mkdir()
    dados = {
        "cwd": str(copia),
        "model": {"id": "claude-fable-5-1", "display_name": "Fable 5.1"},
        "effort": {"level": "high"},
        "context_window": {
            "context_window_size": 1_000_000,
            "used_percentage": 42,
            "current_usage": {
                "input_tokens": 400_000,
                "cache_creation_input_tokens": 10_000,
                "cache_read_input_tokens": 10_000,
            },
        },
        "rate_limits": {
            "five_hour": {"used_percentage": 30, "resets_at": 1_800_000_000},
            "seven_day": {"used_percentage": 70, "resets_at": 1_800_100_000},
        },
        "prompt_cache": {"hit_ratio": 0.9, "warm": True},
        "cost": {"total_cost_usd": 1.5},
    }
    ambiente = {**os.environ, "TICKERLAB_PASTA_PRIVADA": str(pasta_privada)}
    saida = rodar_node(
        str(LINHA_DE_STATUS), entrada=json.dumps(dados), ambiente=ambiente
    )
    linhas = sem_cores(saida).splitlines()
    assert len(linhas) == 2
    assert linhas[0].startswith(
        "Dados · sidra 392 · Fable 5.1 high · analise-acoes-dados-sidra-392"
    )
    assert "PR" not in linhas[0]
    assert "▓" in linhas[1]
    assert "42%" in linhas[1]
    assert "5h 30%" in linhas[1]
    assert "semana 70%" in linhas[1]
    assert "cache 90%" in linhas[1]
    assert "≈US$ 1,50" in linhas[1]
    assert linhas[1].endswith("fila 2/15")


def test_sem_pasta_privada_a_linha_so_nao_mostra_a_fila(tmp_path):
    ambiente = {
        chave: valor
        for chave, valor in os.environ.items()
        if chave != "TICKERLAB_PASTA_PRIVADA"
    }
    saida = rodar_node(
        str(LINHA_DE_STATUS),
        entrada=json.dumps({"cwd": str(tmp_path)}),
        ambiente=ambiente,
    )
    assert "fila" not in sem_cores(saida)
    assert "contexto" in sem_cores(saida)


def test_json_invalido_nao_derruba_a_linha():
    assert (
        rodar_node(str(LINHA_DE_STATUS), entrada="isto não é JSON").strip()
        == "linha de status: JSON inválido"
    )
