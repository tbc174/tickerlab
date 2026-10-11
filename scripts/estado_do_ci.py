"""Diz se os testes do GitHub Actions de um commit passaram, lendo a resposta da API do GitHub.

Uso (o script de deploy faz isto):
    curl -s .../commits/<sha>/check-runs | python3 scripts/estado_do_ci.py

Imprime uma palavra: `ok` (todos passaram), `aguardando` (ainda rodando ou ainda não começou),
`falhou` (algum falhou) ou `sem-dados` (resposta ilegível). Só stdlib, para rodar no servidor.
"""

import json
import sys

CONCLUSOES_QUE_PASSAM = {"success", "skipped", "neutral"}


def avaliar(resposta: object) -> str:
    if not isinstance(resposta, dict):
        return "sem-dados"
    execucoes = resposta.get("check_runs")
    if not isinstance(execucoes, list):
        return "sem-dados"
    if not execucoes:
        return "aguardando"  # o GitHub ainda não criou as execuções deste commit
    if any(e.get("status") != "completed" for e in execucoes):
        return "aguardando"
    if all(e.get("conclusion") in CONCLUSOES_QUE_PASSAM for e in execucoes):
        return "ok"
    return "falhou"


def main() -> int:
    try:
        resposta = json.load(sys.stdin)
    except ValueError:
        resposta = None
    print(avaliar(resposta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
