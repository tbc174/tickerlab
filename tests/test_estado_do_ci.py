"""O deploy automático só implanta commits cujos testes passaram: confere a leitura da API do GitHub."""

import importlib.util
import json
import subprocess
import sys
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
