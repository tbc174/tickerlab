"""Diz se os testes do GitHub Actions passaram, lendo a resposta da API do GitHub.

Dois usos (o script de deploy faz o segundo):
    curl -s .../commits/<sha>/check-runs | python3 scripts/estado_do_ci.py
    curl -s .../actions/workflows/testes.yml/runs?... | python3 scripts/estado_do_ci.py --escolher <sha> ...

O primeiro imprime uma palavra sobre um commit: `ok` (todos passaram), `aguardando` (ainda rodando
ou ainda não começou), `falhou` (algum falhou) ou `sem-dados` (resposta ilegível).

O segundo recebe os commits candidatos, do mais novo para o mais velho (os que estão entre o que
está no ar e o último da main), e imprime "<commit a implantar ou -> <estado do mais novo>". Assim
o deploy implanta o mais novo que já passou, em vez de esperar o último: com várias sessões
mesclando, o último quase nunca tinha o teste terminado e nada ia para o ar (13/10/2026).

Só stdlib, para rodar no servidor.
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


def _estado_do_commit(execucoes: list, sha: str) -> str:
    """Um commit passou se alguma execução dele passou (rodar de novo vale); senão, espera
    enquanto alguma roda; senão, falhou (inclui cancelado)."""
    dele = [e for e in execucoes if e.get("head_sha") == sha]
    if any(
        e.get("status") == "completed" and e.get("conclusion") in CONCLUSOES_QUE_PASSAM
        for e in dele
    ):
        return "ok"
    if not dele or any(e.get("status") != "completed" for e in dele):
        return "aguardando"
    return "falhou"


def escolher(resposta: object, candidatos: list[str]) -> tuple[str | None, str]:
    """O commit mais novo dos `candidatos` com o teste verde (ou None) e o estado do mais novo."""
    if not isinstance(resposta, dict) or not isinstance(
        resposta.get("workflow_runs"), list
    ):
        return None, "sem-dados"
    execucoes = resposta["workflow_runs"]
    estado_do_mais_novo = (
        _estado_do_commit(execucoes, candidatos[0]) if candidatos else "ok"
    )
    for sha in candidatos:
        if _estado_do_commit(execucoes, sha) == "ok":
            return sha, estado_do_mais_novo
    return None, estado_do_mais_novo


def main() -> int:
    try:
        resposta = json.load(sys.stdin)
    except ValueError:
        resposta = None
    if len(sys.argv) > 1 and sys.argv[1] == "--escolher":
        alvo, estado = escolher(resposta, sys.argv[2:])
        print(f"{alvo or '-'} {estado}")
        return 0
    print(avaliar(resposta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
