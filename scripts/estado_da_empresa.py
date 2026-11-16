"""Quadro do estado da empresa, gerado dos PRs abertos e das cópias do repositório.

O estado da operação era escrito à mão (quadro de sessões, fila), e texto escrito à mão envelhece:
em 16/11/2026 havia 8 PRs com os testes verdes parados há mais de um dia, nenhum com merge
automático, e nenhum aviso dizia isso. Este script pergunta ao GitHub e ao Git o que é verdade
agora e escreve um quadro com três alertas:

- PR verde, pronto e sem merge automático há mais de 2 horas (ninguém vai mesclar sozinho);
- PR sem atividade há mais de 7 dias (regra do AGENTS.md: vira linha da fila ou fecha);
- cópia do repositório cujo ramo é de um PR já mesclado (tarefa fechada = cópia apagada).

Só lê: não mescla, não fecha, não apaga e não muda regra nenhuma. O quadro é para ser gerado de
novo, nunca editado; por isso começa dizendo que é gerado e a que horas.

Uso: `python -m scripts.estado_da_empresa` imprime o quadro; com `--destino ARQUIVO`, grava nele
(o arquivo fica fora do repositório). Precisa do `gh` autenticado e roda de dentro de uma cópia
do repositório. Só usa a biblioteca padrão.

Roda: manual (`python -m scripts.estado_da_empresa --destino ARQUIVO`); sem agenda em 16/11/2026.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.portao_do_agente import e_ramo_do_agente

AVISO_DE_ARQUIVO_GERADO = "gerado, não editar"
DESCRICAO_DO_COMANDO = (
    "Quadro do estado da empresa, gerado dos PRs abertos e das cópias."
)

HORAS_DE_VERDE_PARADO = 2
DIAS_SEM_ATIVIDADE = 7
SEGUNDOS_POR_MINUTO = 60
MINUTOS_POR_HORA = 60
MINUTOS_POR_DIA = 24 * MINUTOS_POR_HORA
# Até aqui o tempo parado se lê melhor em horas ("há 30 h"); depois, em dias.
HORAS_ATE_CONTAR_EM_DIAS = 48

TESTES_VERDES = "verde"
TESTES_VERMELHOS = "vermelho"
TESTES_RODANDO = "rodando"
SEM_TESTES = "sem testes"

ALERTA_VERDE_SEM_MERGE_AUTOMATICO = "verde_sem_merge_automatico"
ALERTA_SEM_ATIVIDADE = "sem_atividade"
ALERTA_COPIA_DE_PR_MESCLADO = "copia_de_pr_mesclado"
TITULOS_DOS_ALERTAS = {
    ALERTA_VERDE_SEM_MERGE_AUTOMATICO: (
        f"Verde, pronto e sem merge automático há mais de {HORAS_DE_VERDE_PARADO} horas"
    ),
    ALERTA_SEM_ATIVIDADE: f"Sem atividade há mais de {DIAS_SEM_ATIVIDADE} dias",
    ALERTA_COPIA_DE_PR_MESCLADO: "Cópia do repositório de PR já mesclado",
}

# Como o GitHub descreve cada verificação: `CheckRun` traz `status` e `conclusion`;
# `StatusContext` traz só `state`.
CONCLUSOES_QUE_FALHAM = {
    "FAILURE",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
}
ESTADOS_QUE_FALHAM = {"FAILURE", "ERROR"}
ESTADOS_PENDENTES = {"PENDING", "EXPECTED"}
STATUS_TERMINADO = "COMPLETED"

CAMPOS_DO_PR = (
    "number,title,headRefName,updatedAt,isDraft,autoMergeRequest,"
    "mergeStateStatus,statusCheckRollup"
)
LIMITE_DE_ABERTOS = 200
# Os mesclados só servem para reconhecer cópias antigas: os 2.000 mais recentes cobrem o projeto
# inteiro em 16/11/2026 (cerca de 1.100 PRs) com folga.
LIMITE_DE_MESCLADOS = 2000
PREFIXO_DE_RAMO = "refs/heads/"

Estado = dict[str, Any]
Copia = dict[str, str | None]


def _falhou(check: dict[str, Any]) -> bool:
    return (
        check.get("conclusion") in CONCLUSOES_QUE_FALHAM
        or check.get("state") in ESTADOS_QUE_FALHAM
    )


def _ainda_roda(check: dict[str, Any]) -> bool:
    if "status" in check:
        return check["status"] != STATUS_TERMINADO
    return check.get("state") in ESTADOS_PENDENTES


def classificar_testes(checks: list[dict[str, Any]]) -> str:
    """Resume as verificações de um PR numa palavra; uma falha já basta para o vermelho."""
    if not checks:
        return SEM_TESTES
    if any(_falhou(check) for check in checks):
        return TESTES_VERMELHOS
    if any(_ainda_roda(check) for check in checks):
        return TESTES_RODANDO
    return TESTES_VERDES


def ler_copias(saida_do_git: str) -> list[Copia]:
    """Saída de `git worktree list --porcelain` em pasta e ramo (None quando a cópia está solta)."""
    copias: list[Copia] = []
    for linha in saida_do_git.splitlines():
        if linha.startswith("worktree "):
            copias.append({"pasta": linha.removeprefix("worktree "), "ramo": None})
        elif linha.startswith("branch ") and copias:
            ramo = linha.removeprefix("branch ").removeprefix(PREFIXO_DE_RAMO)
            copias[-1]["ramo"] = ramo
    return copias


def _minutos_parado(mexido_em: str, agora: datetime) -> int:
    """Minutos inteiros desde a hora do GitHub (`2026-11-16T11:33:21Z`)."""
    mexido = datetime.fromisoformat(mexido_em.replace("Z", "+00:00"))
    return int((agora - mexido).total_seconds() // SEGUNDOS_POR_MINUTO)


def _resumir_pr(pr: dict[str, Any], agora: datetime) -> dict[str, Any]:
    ramo = pr["headRefName"]
    return {
        "numero": pr["number"],
        "titulo": pr["title"],
        "ramo": ramo,
        "testes": classificar_testes(pr.get("statusCheckRollup") or []),
        "rascunho": bool(pr.get("isDraft")),
        "merge_automatico": pr.get("autoMergeRequest") is not None,
        "estado_de_merge": pr.get("mergeStateStatus") or "",
        "do_agente": e_ramo_do_agente(ramo),
        "minutos_parado": _minutos_parado(pr["updatedAt"], agora),
    }


def _ha_quanto(minutos: int) -> str:
    if minutos < MINUTOS_POR_HORA:
        return f"há {minutos} min"
    horas = minutos // MINUTOS_POR_HORA
    if horas < HORAS_ATE_CONTAR_EM_DIAS:
        return f"há {horas} h"
    return f"há {minutos // MINUTOS_POR_DIA} dias"


def _alerta_do_pr(tipo: str, pr: dict[str, Any]) -> dict[str, Any]:
    quanto = _ha_quanto(pr["minutos_parado"])
    return {
        "tipo": tipo,
        "numero": pr["numero"],
        "texto": f"#{pr['numero']} {pr['titulo']} · parado {quanto} · `{pr['ramo']}`",
    }


def _verde_esperando_alguem(pr: dict[str, Any]) -> bool:
    return (
        pr["testes"] == TESTES_VERDES
        and not pr["rascunho"]
        and not pr["merge_automatico"]
        and pr["minutos_parado"] > HORAS_DE_VERDE_PARADO * MINUTOS_POR_HORA
    )


def _alertas_dos_prs(prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    verdes = [
        _alerta_do_pr(ALERTA_VERDE_SEM_MERGE_AUTOMATICO, pr)
        for pr in prs
        if _verde_esperando_alguem(pr)
    ]
    esquecidos = [
        _alerta_do_pr(ALERTA_SEM_ATIVIDADE, pr)
        for pr in prs
        if pr["minutos_parado"] > DIAS_SEM_ATIVIDADE * MINUTOS_POR_DIA
    ]
    return verdes + esquecidos


def _alertas_das_copias(
    copias: list[Copia], ramos_abertos: set[str], ramos_mesclados: set[str]
) -> list[dict[str, Any]]:
    """Cópia cujo ramo já entrou na `main` e não tem outro PR aberto (o ramo pode ter sido reusado)."""
    return [
        {
            "tipo": ALERTA_COPIA_DE_PR_MESCLADO,
            "pasta": copia["pasta"],
            "ramo": copia["ramo"],
            "texto": f"`{copia['pasta']}` · ramo `{copia['ramo']}`",
        }
        for copia in copias
        if copia["ramo"] in ramos_mesclados and copia["ramo"] not in ramos_abertos
    ]


def _resumo(prs: list[dict[str, Any]], copias: list[Copia]) -> dict[str, int]:
    por_teste = Counter(pr["testes"] for pr in prs)
    return {
        "abertos": len(prs),
        "verdes": por_teste[TESTES_VERDES],
        "vermelhos": por_teste[TESTES_VERMELHOS],
        "rodando": por_teste[TESTES_RODANDO],
        "sem_testes": por_teste[SEM_TESTES],
        "do_agente": sum(pr["do_agente"] for pr in prs),
        "copias": len(copias),
    }


def montar_estado(
    prs: list[dict[str, Any]],
    copias: list[Copia],
    ramos_mesclados: set[str],
    agora: datetime,
) -> Estado:
    """O estado em tipos simples: os PRs resumidos, as contagens e os alertas.

    `prs` vem do `gh pr list --json` (campos de `CAMPOS_DO_PR`), `copias` de `ler_copias`,
    `ramos_mesclados` são os ramos dos PRs já mesclados e `agora` tem fuso.
    """
    resumidos = [_resumir_pr(pr, agora) for pr in prs]
    ramos_abertos = {pr["ramo"] for pr in resumidos}
    return {
        "gerado_em": agora.isoformat(timespec="minutes"),
        "resumo": _resumo(resumidos, copias),
        "alertas": _alertas_dos_prs(resumidos)
        + _alertas_das_copias(copias, ramos_abertos, ramos_mesclados),
        "prs": resumidos,
    }


def _linhas_dos_alertas(alertas: list[dict[str, Any]]) -> list[str]:
    if not alertas:
        return [
            "## Alertas",
            "",
            "Nenhum alerta: nada parado pelos três critérios.",
            "",
        ]
    linhas = [f"## Alertas ({len(alertas)})", ""]
    for tipo, titulo in TITULOS_DOS_ALERTAS.items():
        do_tipo = [alerta for alerta in alertas if alerta["tipo"] == tipo]
        if do_tipo:
            linhas += [f"### {titulo} ({len(do_tipo)})", ""]
            linhas += [f"- {alerta['texto']}" for alerta in do_tipo]
            linhas.append("")
    return linhas


def _linha_do_pr(pr: dict[str, Any]) -> str:
    testes = pr["testes"] + (" (rascunho)" if pr["rascunho"] else "")
    merge = "ligado" if pr["merge_automatico"] else "não"
    titulo = pr["titulo"].replace("|", "\\|")
    quanto = _ha_quanto(pr["minutos_parado"])
    return f"| #{pr['numero']} | {testes} | {quanto} | {merge} | `{pr['ramo']}` | {titulo} |"


def _linha_do_resumo(resumo: dict[str, int]) -> str:
    partes = [
        f"PRs abertos: {resumo['abertos']}",
        f"verdes: {resumo['verdes']}",
        f"vermelhos: {resumo['vermelhos']}",
        f"rodando: {resumo['rodando']}",
        f"sem testes: {resumo['sem_testes']}",
        f"do agente da nuvem: {resumo['do_agente']}",
        f"cópias do repositório: {resumo['copias']}",
    ]
    return " · ".join(partes)


def texto_do_quadro(estado: Estado) -> str:
    """O quadro em Markdown; a primeira linha diz que é gerado e a que horas."""
    hora = datetime.fromisoformat(estado["gerado_em"]).strftime("%d/%m/%Y %H:%M")
    linhas = [
        f"{AVISO_DE_ARQUIVO_GERADO} · {hora} · python -m scripts.estado_da_empresa",
        "",
        "# Estado da empresa",
        "",
        _linha_do_resumo(estado["resumo"]),
        "",
        *_linhas_dos_alertas(estado["alertas"]),
        "## PRs abertos",
        "",
        "| PR | Testes | Parado | Merge automático | Ramo | Título |",
        "|---|---|---|---|---|---|",
        *[_linha_do_pr(pr) for pr in estado["prs"]],
    ]
    return "\n".join(linhas) + "\n"


def escrever_quadro(estado: Estado, destino: Path) -> None:
    """Grava o quadro em `destino`, criando a pasta se faltar."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto_do_quadro(estado), encoding="utf-8", newline="\n")


def _rodar(comando: list[str]) -> str:
    feito = subprocess.run(
        comando, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return feito.stdout


def _listar_prs(estado: str, limite: int, campos: str) -> list[dict[str, Any]]:
    comando = ["gh", "pr", "list", "--state", estado, "--limit", str(limite)]
    return json.loads(_rodar([*comando, "--json", campos]))


def buscar_prs_abertos() -> list[dict[str, Any]]:
    return _listar_prs("open", LIMITE_DE_ABERTOS, CAMPOS_DO_PR)


def buscar_ramos_mesclados() -> set[str]:
    mesclados = _listar_prs("merged", LIMITE_DE_MESCLADOS, "headRefName")
    return {pr["headRefName"] for pr in mesclados}


def buscar_copias() -> list[Copia]:
    return ler_copias(_rodar(["git", "worktree", "list", "--porcelain"]))


def main(argumentos: list[str] | None = None) -> int:
    leitor = argparse.ArgumentParser(description=DESCRICAO_DO_COMANDO)
    leitor.add_argument(
        "--destino", type=Path, help="arquivo onde gravar (sem ele, imprime)"
    )
    opcoes = leitor.parse_args(argumentos)
    estado = montar_estado(
        buscar_prs_abertos(),
        buscar_copias(),
        buscar_ramos_mesclados(),
        datetime.now().astimezone(),
    )
    if opcoes.destino is None:
        print(texto_do_quadro(estado), end="")
    else:
        escrever_quadro(estado, opcoes.destino)
        print(f"quadro gravado em {opcoes.destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
