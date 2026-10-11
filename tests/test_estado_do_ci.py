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
    """O script só segue quando o estado é `ok`; os outros casos saem sem tocar no servidor."""
    texto = (RAIZ / "scripts" / "deploy-automatico.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in texto
    assert 'case "$estado" in' in texto
    assert texto.index("ok) ;;") < texto.index("git merge --ff-only")
    assert "git reset -q --hard" in texto  # reversão automática
    assert "flock -n 9" in texto  # uma execução por vez
    assert "--force" not in texto
