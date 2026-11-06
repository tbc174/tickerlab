"""O deploy automático só implanta commits cujos testes passaram: confere a leitura da API do GitHub."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "estado_do_ci.py"
_spec = importlib.util.spec_from_file_location("estado_do_ci", SCRIPT)
estado_do_ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(estado_do_ci)


def _execucoes(*pares):
    return {"check_runs": [{"status": s, "conclusion": c} for s, c in pares]}


def test_tudo_passou():
    assert (
        estado_do_ci.avaliar(
            _execucoes(("completed", "success"), ("completed", "success"))
        )
        == "ok"
    )


def test_pulado_e_neutro_nao_atrapalham():
    assert (
        estado_do_ci.avaliar(
            _execucoes(("completed", "success"), ("completed", "skipped"))
        )
        == "ok"
    )


@pytest.mark.parametrize("conclusao", ["failure", "cancelled", "timed_out", None])
def test_qualquer_falha_barra_o_deploy(conclusao):
    resposta = _execucoes(("completed", "success"), ("completed", conclusao))
    assert estado_do_ci.avaliar(resposta) == "falhou"


@pytest.mark.parametrize("status", ["in_progress", "queued", "waiting"])
def test_ainda_rodando_espera(status):
    resposta = _execucoes(("completed", "success"), (status, None))
    assert estado_do_ci.avaliar(resposta) == "aguardando"


def test_nada_ainda_espera_em_vez_de_implantar():
    assert estado_do_ci.avaliar({"check_runs": []}) == "aguardando"


@pytest.mark.parametrize("lixo", [None, [], "texto", {}, {"check_runs": "x"}, 3])
def test_resposta_estranha_nao_implanta(lixo):
    assert estado_do_ci.avaliar(lixo) == "sem-dados"


def _rodar(entrada: str) -> str:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=entrada,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_como_programa_le_o_json_da_entrada_padrao():
    assert _rodar(json.dumps(_execucoes(("completed", "success")))) == "ok"
    assert _rodar("isto não é json") == "sem-dados"
    assert _rodar("") == "sem-dados"


def test_script_de_deploy_nao_implanta_sem_o_ok_do_ci():
    """O script só implanta um commit com o teste verde; sem nenhum, sai sem tocar no servidor."""
    texto = (RAIZ / "scripts" / "deploy-automatico.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in texto
    assert 'case "$estado" in' in texto
    sem_alvo = texto.index('if [ "$alvo" = "-" ]; then')
    assert sem_alvo < texto.index('novo="$alvo"') < texto.index("git merge --ff-only")
    assert texto.index("exit 0", sem_alvo) < texto.index('novo="$alvo"')
    assert "git reset -q --hard" in texto  # reversão automática
    assert "flock -n 9" in texto  # uma execução por vez
    assert "--force" not in texto


def test_script_de_deploy_espera_as_tarefas_agendadas():
    """O deploy recria o contêiner onde as coletas rodam: só segue sem nenhuma tarefa rodando."""
    texto = (RAIZ / "scripts" / "deploy-automatico.sh").read_text(encoding="utf-8")
    assert "/tmp/tickerlab-tarefas.lock" in texto  # a mesma trava do ~/rodar-tarefa.sh
    assert (
        "flock -n 8" in texto
    )  # exclusiva e sem esperar: tenta de novo no próximo minuto
    assert texto.index("flock -n 8") < texto.index("git merge --ff-only")


def test_script_de_deploy_confere_a_saude_no_caminho_do_streamlit():
    """O Streamlit está em /classico no servidor (18/10/2026; src/classico.py): a saúde fica em
    /classico/_stcore/health, e o caminho vem do compose.yaml do commit implantado. Um deploy que
    conferisse a raiz reverteria toda versão com o Streamlit fora dela."""
    texto = (RAIZ / "scripts" / "deploy-automatico.sh").read_text(encoding="utf-8")
    assert "STREAMLIT_SERVER_BASE_URL_PATH" in texto
    assert "8501/_stcore/health" not in texto  # o caminho fixo na raiz
    assert "$(caminho_do_streamlit)/_stcore/health" in texto
    # o compose do repositório põe o Streamlit em /classico: é o que o script vai ler no servidor
    compose = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    assert "STREAMLIT_SERVER_BASE_URL_PATH: classico" in compose


def _bash_funciona() -> bool:
    try:
        return (
            subprocess.run(
                ["bash", "-c", "echo ok"], capture_output=True, timeout=20, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.parametrize(
    ("linha_do_compose", "caminho"),
    [
        ("      STREAMLIT_SERVER_BASE_URL_PATH: classico\n", "/classico"),
        (
            "      STREAMLIT_SERVER_BASE_URL_PATH: /classico/  # comentário\n",
            "/classico",
        ),
        ("", ""),
    ],
)
def test_a_funcao_do_caminho_le_o_compose(tmp_path, linha_do_compose, caminho):
    """A função do script, rodada no bash de verdade, sobre um compose de mentira."""
    if not _bash_funciona():
        pytest.skip("sem bash")
    script = (RAIZ / "scripts" / "deploy-automatico.sh").read_text(encoding="utf-8")
    funcao = script[script.index("caminho_do_streamlit() {") :]
    funcao = funcao[: funcao.index("\n}\n") + 3]
    (tmp_path / "compose.yaml").write_text(
        "services:\n  tickerlab:\n    environment:\n"
        + linha_do_compose
        + "      OUTRA: x\n",
        encoding="utf-8",
    )
    (tmp_path / "f.sh").write_text(
        funcao + "\ncaminho_do_streamlit\n", encoding="utf-8"
    )
    saida = subprocess.run(
        ["bash", "f.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout == caminho


# --- escolher o commit a implantar (13/10/2026: com várias sessões mesclando, o último commit da
# main quase nunca tinha o teste terminado, e o deploy ficava parado) --------------------------


def _execucoes_do_workflow(*trios):
    return {
        "workflow_runs": [
            {"head_sha": sha, "status": status, "conclusion": conclusao}
            for sha, status, conclusao in trios
        ]
    }


def test_implanta_o_mais_novo_com_teste_verde_quando_o_ultimo_ainda_roda():
    resposta = _execucoes_do_workflow(
        ("ccc", "in_progress", None),
        ("bbb", "completed", "success"),
        ("aaa", "completed", "success"),
    )
    assert estado_do_ci.escolher(resposta, ["ccc", "bbb", "aaa"]) == (
        "bbb",
        "aguardando",
    )


def test_o_ultimo_verde_e_o_escolhido():
    resposta = _execucoes_do_workflow(
        ("ccc", "completed", "success"), ("bbb", "completed", "success")
    )
    assert estado_do_ci.escolher(resposta, ["ccc", "bbb"]) == ("ccc", "ok")


def test_cancelado_ou_falho_no_meio_nao_impede_o_verde_mais_velho():
    resposta = _execucoes_do_workflow(
        ("ccc", "completed", "cancelled"),
        ("bbb", "completed", "failure"),
        ("aaa", "completed", "success"),
    )
    assert estado_do_ci.escolher(resposta, ["ccc", "bbb", "aaa"]) == ("aaa", "falhou")


def test_nenhum_verde_nao_implanta_e_diz_o_estado_do_mais_novo():
    rodando = _execucoes_do_workflow(("ccc", "queued", None))
    assert estado_do_ci.escolher(rodando, ["ccc"]) == (None, "aguardando")
    falhou = _execucoes_do_workflow(("ccc", "completed", "failure"))
    assert estado_do_ci.escolher(falhou, ["ccc"]) == (None, "falhou")


def test_commit_sem_execucao_ainda_espera():
    assert estado_do_ci.escolher(_execucoes_do_workflow(), ["ccc"]) == (
        None,
        "aguardando",
    )


def test_rodar_de_novo_um_teste_que_falhou_e_passou_vale_o_verde():
    resposta = _execucoes_do_workflow(
        ("ccc", "completed", "failure"), ("ccc", "completed", "success")
    )
    assert estado_do_ci.escolher(resposta, ["ccc"]) == ("ccc", "ok")


def test_commit_fora_dos_candidatos_nunca_e_escolhido():
    """Verde, mas mais velho que o que está no ar (não está entre os candidatos): não volta atrás."""
    resposta = _execucoes_do_workflow(
        ("velho", "completed", "success"), ("ccc", "in_progress", None)
    )
    assert estado_do_ci.escolher(resposta, ["ccc"]) == (None, "aguardando")


def test_resposta_ilegivel():
    assert estado_do_ci.escolher({"erro": 1}, ["ccc"]) == (None, "sem-dados")


def test_linha_de_comando_do_escolher():
    resposta = json.dumps(
        _execucoes_do_workflow(
            ("ccc", "in_progress", None), ("bbb", "completed", "success")
        )
    )
    saida = subprocess.run(
        [sys.executable, str(SCRIPT), "--escolher", "ccc", "bbb"],
        input=resposta,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert saida == "bbb aguardando"


# --- o script inteiro, no bash de verdade, sobre um repositório git de mentira (18/10/2026: o
# cron reverteu 8 commits porque o bash seguiu lendo a versão antiga do script; a cota da API do
# GitHub acabou esperando a trava das tarefas; um aviso apagou a marca "revertido") ------------

DEPLOY = RAIZ / "scripts" / "deploy-automatico.sh"
SCRIPT_QUE_DEIXA_UMA_MARCA = """#!/usr/bin/env bash
# versão nova do script, de mentira: só anota como foi chamada e se herdou as travas
travas="$( { : >&8 && : >&9; } 2>/dev/null && echo travas-herdadas || echo travas-perdidas)"
echo "nova $* $travas" > "$FALSO_MARCA"
"""
FALSOS = {
    "flock": '[ "${*: -1}" != "${FALSO_TRAVA_OCUPADA:-}" ]\n',
    "docker": 'echo "docker $*" >> "$FALSO_CHAMADAS"\n',
    "sleep": "exit 0\n",
    # a API do GitHub responde o combinado; a saúde só vem com o commit certo no ar
    "curl": (
        'echo "curl $*" >> "$FALSO_CHAMADAS"\n'
        'case "$*" in\n'
        "  *api.github.com*) printf '%s' \"$FALSO_RESPOSTA_DA_API\" ;;\n"
        '  *) [ "$(git rev-parse HEAD)" = "${FALSO_SAUDAVEL_EM:-}" ] ;;\n'
        "esac\n"
    ),
    "python3": f'exec "{Path(sys.executable).as_posix()}" "$@"\n',
}


def _git(pasta: Path, *argumentos: str) -> str:
    ambiente = {
        **os.environ,
        "GIT_AUTHOR_NAME": "teste",
        "GIT_AUTHOR_EMAIL": "teste@exemplo.com",
        "GIT_COMMITTER_NAME": "teste",
        "GIT_COMMITTER_EMAIL": "teste@exemplo.com",
    }
    return subprocess.run(
        ["git", *argumentos],
        cwd=pasta,
        env=ambiente,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _commit_do_script(pasta: Path, texto: str, mensagem: str) -> str:
    (pasta / "scripts").mkdir(exist_ok=True)
    (pasta / "scripts" / "deploy-automatico.sh").write_text(texto, encoding="utf-8")
    shutil.copy(SCRIPT, pasta / "scripts" / "estado_do_ci.py")  # o deploy o chama
    (pasta / "compose.yaml").write_text(
        "services:\n  tickerlab:\n    environment:\n"
        "      STREAMLIT_SERVER_BASE_URL_PATH: classico\n",
        encoding="utf-8",
    )
    _git(pasta, "add", "-A")
    _git(pasta, "commit", "-q", "-m", mensagem)
    return _git(pasta, "rev-parse", "HEAD")


@dataclass
class Cenario:
    """Um 'servidor' clonado de um 'GitHub' de mentira, com os comandos de fora dublados."""

    servidor: Path
    no_ar: str  # commit que o servidor tem
    novo: str  # commit a mais no remoto
    ambiente: dict[str, str]
    log: Path
    chamadas: Path  # o que o curl e o docker de mentira receberam

    def rodar(self, *argumentos: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", (self.servidor / "scripts" / "deploy-automatico.sh").as_posix()]
            + list(argumentos),
            cwd=self.servidor,
            env=self.ambiente,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def head(self) -> str:
        return _git(self.servidor, "rev-parse", "HEAD")

    def texto(self, arquivo: Path) -> str:
        return arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""


def _cenario(tmp_path: Path, script_novo: str | None = None) -> Cenario:
    """Remoto com dois commits (o segundo troca o script pelo `script_novo`, se houver) e o
    servidor clonado no primeiro; os comandos de fora (curl, docker, flock, sleep) são de mentira."""
    if not _bash_funciona():
        pytest.skip("sem bash")
    script_atual = DEPLOY.read_text(encoding="utf-8")
    remoto = tmp_path / "remoto"
    remoto.mkdir()
    _git(remoto, "init", "-q", "-b", "main")
    no_ar = _commit_do_script(remoto, script_atual, "primeiro")
    servidor = tmp_path / "servidor"
    _git(tmp_path, "clone", "-q", remoto.as_posix(), servidor.as_posix())
    novo = _commit_do_script(remoto, script_novo or script_atual + "\n", "segundo")
    falsos = tmp_path / "falsos"
    falsos.mkdir()
    for nome, corpo in FALSOS.items():
        (falsos / nome).write_text("#!/usr/bin/env bash\n" + corpo, encoding="utf-8")
        (falsos / nome).chmod(0o755)
    chamadas = tmp_path / "chamadas.txt"
    resposta_da_api = json.dumps(_execucoes_do_workflow((novo, "completed", "success")))
    ambiente = {
        **os.environ,
        "PATH": falsos.as_posix() + os.pathsep + os.environ.get("PATH", ""),
        "TICKERLAB_PASTA": servidor.as_posix(),
        "TICKERLAB_LOG_DO_DEPLOY": (tmp_path / "deploy.log").as_posix(),
        "TICKERLAB_ULTIMO_AVISO": (tmp_path / "ultimo-aviso").as_posix(),
        "TICKERLAB_REVERTIDOS": (tmp_path / "revertidos").as_posix(),
        "TICKERLAB_TRAVA_DO_DEPLOY": (tmp_path / "deploy.lock").as_posix(),
        "TICKERLAB_TRAVA_DAS_TAREFAS": (tmp_path / "tarefas.lock").as_posix(),
        "TICKERLAB_ESPERA_MAXIMA": "1",
        "FALSO_CHAMADAS": chamadas.as_posix(),
        "FALSO_MARCA": (tmp_path / "marca").as_posix(),
        "FALSO_RESPOSTA_DA_API": resposta_da_api,
        "FALSO_SAUDAVEL_EM": novo,
    }
    return Cenario(servidor, no_ar, novo, ambiente, tmp_path / "deploy.log", chamadas)


def test_script_de_deploy_mescla_e_passa_a_vez_a_versao_nova():
    """O cron precisa valer a partir do próprio commit que implanta: depois do merge, a parte que
    sobe e confere roda na versão recém-mesclada do script, com as travas herdadas."""
    texto = DEPLOY.read_text(encoding="utf-8")
    assert texto.index("git merge --ff-only") < texto.index(
        'exec bash "$SCRIPT" --implantar "$atual" "$novo"'
    )
    assert 'if [ "${1:-}" = "--implantar" ]; then' in texto


def test_depois_do_merge_quem_sobe_e_o_script_da_versao_nova(tmp_path):
    cenario = _cenario(tmp_path, SCRIPT_QUE_DEIXA_UMA_MARCA)
    saida = cenario.rodar()
    assert saida.returncode == 0, saida.stderr
    assert cenario.head() == cenario.novo
    marca = cenario.texto(tmp_path / "marca").strip()
    assert marca == f"nova --implantar {cenario.no_ar} {cenario.novo} travas-herdadas"
    assert "docker" not in cenario.texto(
        cenario.chamadas
    )  # a versão antiga não subiu nada


def test_script_novo_que_nao_passa_na_sintaxe_volta_sem_subir(tmp_path):
    cenario = _cenario(tmp_path, "#!/usr/bin/env bash\nif then (\n")
    saida = cenario.rodar()
    assert saida.returncode == 1
    assert cenario.head() == cenario.no_ar
    assert cenario.texto(tmp_path / "revertidos").split() == [cenario.novo]
    assert "docker" not in cenario.texto(cenario.chamadas)
    assert "conferência de sintaxe" in cenario.texto(cenario.log)


def test_modo_implantar_sobe_e_registra_quando_fica_saudavel(tmp_path):
    cenario = _cenario(tmp_path)
    _git(cenario.servidor, "fetch", "-q", "origin", "main")
    _git(cenario.servidor, "merge", "--ff-only", "-q", cenario.novo)
    saida = cenario.rodar("--implantar", cenario.no_ar, cenario.novo)
    assert saida.returncode == 0, saida.stderr
    assert cenario.head() == cenario.novo
    assert "docker compose up -d --build" in cenario.texto(cenario.chamadas)
    assert "implantado e saudável" in cenario.texto(cenario.log)
    assert not (tmp_path / "revertidos").exists()


def test_modo_implantar_volta_e_anota_o_commit_que_nao_ficou_saudavel(tmp_path):
    cenario = _cenario(tmp_path)
    cenario.ambiente["FALSO_SAUDAVEL_EM"] = (
        cenario.no_ar
    )  # só a versão anterior responde
    _git(cenario.servidor, "fetch", "-q", "origin", "main")
    _git(cenario.servidor, "merge", "--ff-only", "-q", cenario.novo)
    saida = cenario.rodar("--implantar", cenario.no_ar, cenario.novo)
    assert saida.returncode == 1
    assert cenario.head() == cenario.no_ar
    assert "versão anterior restaurada" in cenario.texto(cenario.log)
    assert cenario.texto(tmp_path / "revertidos").split() == [cenario.novo]
    assert not (tmp_path / "ultimo-aviso").exists()  # a marca não mora no último aviso


def test_commit_revertido_nao_e_tentado_de_novo_mesmo_depois_de_outro_aviso(tmp_path):
    """Em 18/10/2026 o aviso 'não consegui ler o estado' sobrescreveu '<commit>:revertido' e o
    cron reimplantou (e reverteu) o mesmo commit de novo."""
    cenario = _cenario(tmp_path)
    (tmp_path / "revertidos").write_text(cenario.novo + "\n", encoding="utf-8")
    (tmp_path / "ultimo-aviso").write_text(
        f"{cenario.novo}:não consegui ler o estado dos testes (GitHub fora do ar?)\n",
        encoding="utf-8",
    )
    saida = cenario.rodar()
    assert saida.returncode == 0, saida.stderr
    assert cenario.head() == cenario.no_ar
    assert cenario.texto(cenario.chamadas) == ""  # nem a API do GitHub, nem o docker


def test_sem_a_trava_das_tarefas_o_deploy_nem_consulta_o_github(tmp_path):
    """A API sem token dá 60 consultas por hora: esperar a trava sem gastar a cota, e avisar uma
    vez só por commit."""
    texto = DEPLOY.read_text(encoding="utf-8")
    assert texto.index("flock -n 8") < texto.index("api.github.com")
    cenario = _cenario(tmp_path)
    cenario.ambiente["FALSO_TRAVA_OCUPADA"] = "8"
    for _ in range(2):
        saida = cenario.rodar()
        assert saida.returncode == 0, saida.stderr
    assert cenario.head() == cenario.no_ar
    assert "api.github.com" not in cenario.texto(cenario.chamadas)
    assert cenario.texto(cenario.log).count("esperando as tarefas agendadas") == 1
