"""Placar da semana da operação: sempre os mesmos dez números, medidos no GitHub.

A operação precisa de poucos números que só se comparam com eles mesmos, semana a semana, para
saber se uma mudança de processo melhorou ou piorou. Este script mede no GitHub os cinco que um
programa consegue medir e deixa os outros cinco na tabela, dizendo de onde cada um vem:

- 1: PRs que entraram na semana;
- 2: tempo mediano entre abrir e entrar;
- 3: falha dos testes na `main` (execuções canceladas por um push mais novo não contam);
- 4: PRs verdes, prontos e sem merge automático parados há mais de 24 horas (retrato de agora);
- 9: PRs de reversão que entraram na semana (aproximação de "pronto que foi desfeito").

A semana vai de segunda a domingo, no fuso do computador que roda. Só lê: não mescla, não fecha
e não muda nada. O placar é para ser gerado de novo, nunca editado.

Uso: `python -m scripts.placar_da_semana` imprime o placar da última semana fechada; `--semana
2026-W46` escolhe outra e `--destino ARQUIVO` grava (o arquivo fica fora do repositório).
Precisa do `gh` autenticado. Só usa a biblioteca padrão.

Roda: manual (`python -m scripts.placar_da_semana --destino ARQUIVO`); sem agenda em 16/11/2026.
"""

import argparse
import json
import re
import statistics
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from scripts.estado_da_empresa import (
    AVISO_DE_ARQUIVO_GERADO,
    MINUTOS_POR_HORA,
    SEGUNDOS_POR_MINUTO,
    TESTES_VERDES,
    buscar_prs_abertos,
    montar_estado,
    rodar_comando,
)

DESCRICAO_DO_COMANDO = "Placar da semana da operação, medido no GitHub."
QUANTOS_NUMEROS = 10
DIAS_DA_SEMANA = 7
HORAS_DE_VERDE_ESQUECIDO = 24
NAO_MEDIDO = "não medido por este programa"
FORMATO_DA_SEMANA = re.compile(r"(\d{4})-W(\d{2})")

# Execução cancelada (trocada por um push mais novo) ou pulada não diz se o código passa.
CONCLUSOES_QUE_PASSAM = {"success"}
CONCLUSOES_QUE_FALHAM = {"failure", "timed_out", "startup_failure"}
PREFIXO_DE_REVERSAO = "revert"

ARQUIVO_DO_CI = "testes.yml"
CAMPOS_DO_MESCLADO = "number,title,createdAt,mergedAt"
CAMPOS_DA_EXECUCAO = "conclusion,status,createdAt"
# O GitHub devolve no máximo 1.000 resultados numa busca; a semana mais cheia até 16/11/2026 teve
# cerca de 330 PRs. Bater no limite seria número errado, então o comando para em vez de gravar.
LIMITE_DA_BUSCA = 1000
# As datas da busca do GitHub são em UTC: um dia de folga de cada lado, e a conta exata é feita aqui.
DIAS_DE_FOLGA_NA_BUSCA = 1

Placar = dict[str, Any]


def ler_semana(escrito: str) -> date:
    """A segunda-feira da semana escrita como `2026-W46` (semana do calendário ISO)."""
    achado = FORMATO_DA_SEMANA.fullmatch(escrito)
    try:
        if achado is None:
            raise ValueError
        return date.fromisocalendar(int(achado[1]), int(achado[2]), 1)
    except ValueError:
        raise ValueError(
            f"semana inválida: {escrito!r}; escreva AAAA-Www, como 2026-W46"
        ) from None


def semana_anterior(hoje: date) -> date:
    """A segunda-feira da última semana que já fechou."""
    return hoje - timedelta(days=hoje.weekday() + DIAS_DA_SEMANA)


def _ler_hora(hora_do_github: str) -> datetime:
    return datetime.fromisoformat(hora_do_github.replace("Z", "+00:00"))


def _dentro_da_semana(hora_do_github: str, segunda: date, agora: datetime) -> bool:
    inicio = datetime.combine(segunda, time.min, tzinfo=agora.tzinfo)
    return inicio <= _ler_hora(hora_do_github) < inicio + timedelta(days=DIAS_DA_SEMANA)


def _medido(numero: int, nome: str, valor: float | None, texto: str) -> dict[str, Any]:
    return {
        "numero": numero,
        "nome": nome,
        "valor": valor,
        "texto": texto,
        "medido": True,
    }


def _nao_medido(numero: int, nome: str, de_onde_vem: str) -> dict[str, Any]:
    texto = f"{NAO_MEDIDO}: {de_onde_vem}"
    return {
        "numero": numero,
        "nome": nome,
        "valor": None,
        "texto": texto,
        "medido": False,
    }


def _duracao(minutos: int) -> str:
    if minutos < MINUTOS_POR_HORA:
        return f"{minutos} min"
    return f"{minutos // MINUTOS_POR_HORA} h {minutos % MINUTOS_POR_HORA} min"


def _minutos_ate_entrar(pr: dict[str, Any]) -> float:
    aberto_ha = _ler_hora(pr["mergedAt"]) - _ler_hora(pr["createdAt"])
    return aberto_ha.total_seconds() / SEGUNDOS_POR_MINUTO


def _tempo_mediano(entraram: list[dict[str, Any]]) -> dict[str, Any]:
    nome = "Tempo mediano entre abrir e entrar"
    if not entraram:
        return _medido(2, nome, None, "nenhum PR entrou na semana")
    mediana = round(statistics.median(_minutos_ate_entrar(pr) for pr in entraram))
    return _medido(2, nome, mediana, _duracao(mediana))


def _falha_na_main(execucoes: list[dict[str, Any]]) -> dict[str, Any]:
    nome = "Falha dos testes na versão principal"
    falharam = sum(e["conclusion"] in CONCLUSOES_QUE_FALHAM for e in execucoes)
    terminaram = falharam + sum(
        e["conclusion"] in CONCLUSOES_QUE_PASSAM for e in execucoes
    )
    if not terminaram:
        return _medido(3, nome, None, "nenhuma execução terminada na semana")
    taxa = round(100 * falharam / terminaram, 1)
    escrita = f"{taxa:.1f}%".replace(".", ",")
    return _medido(
        3, nome, taxa, f"{escrita} ({falharam} de {terminaram} execuções terminadas)"
    )


def _verdes_esquecidos(
    abertos: list[dict[str, Any]], agora: datetime
) -> dict[str, Any]:
    """Mesma régua do alerta do quadro do estado, com o limite de um dia."""
    nome = f"PRs verdes parados há mais de {HORAS_DE_VERDE_ESQUECIDO} horas"
    limite = HORAS_DE_VERDE_ESQUECIDO * MINUTOS_POR_HORA
    esquecidos = [
        f"#{pr['numero']}"
        for pr in montar_estado(abertos, [], set(), agora)["prs"]
        if pr["testes"] == TESTES_VERDES
        and not pr["rascunho"]
        and not pr["merge_automatico"]
        and pr["minutos_parado"] > limite
    ]
    retrato = f"retrato de {agora:%d/%m %H:%M}, não da semana"
    quais = f": {', '.join(esquecidos)}" if esquecidos else ""
    return _medido(4, nome, len(esquecidos), f"{len(esquecidos)}{quais} ({retrato})")


def _reversoes(entraram: list[dict[str, Any]]) -> dict[str, Any]:
    quantas = sum(
        pr["title"].lower().startswith(PREFIXO_DE_REVERSAO) for pr in entraram
    )
    texto = f"{quantas} (PRs com título de reversão; aproximação)"
    return _medido(9, '"Pronto" desfeito na semana', quantas, texto)


def montar_placar(
    mesclados: list[dict[str, Any]],
    execucoes: list[dict[str, Any]],
    abertos: list[dict[str, Any]],
    segunda: date,
    agora: datetime,
) -> Placar:
    """Os dez números da semana que começa em `segunda`, em tipos simples.

    `mesclados` e `execucoes` podem trazer itens de fora da semana (a busca do GitHub é folgada):
    o corte exato é feito aqui. `abertos` são os PRs abertos agora; `agora` tem fuso.
    """
    entraram = [
        pr for pr in mesclados if _dentro_da_semana(pr["mergedAt"], segunda, agora)
    ]
    da_semana = [
        e for e in execucoes if _dentro_da_semana(e["createdAt"], segunda, agora)
    ]
    ano, numero_da_semana, _ = segunda.isocalendar()
    return {
        "gerado_em": agora.isoformat(timespec="minutes"),
        "semana": {
            "rotulo": f"{ano}-W{numero_da_semana:02d}",
            "inicio": segunda.isoformat(),
            "fim": (segunda + timedelta(days=DIAS_DA_SEMANA - 1)).isoformat(),
        },
        "numeros": [
            _medido(1, "PRs que entraram na semana", len(entraram), str(len(entraram))),
            _tempo_mediano(entraram),
            _falha_na_main(da_semana),
            _verdes_esquecidos(abertos, agora),
            _nao_medido(
                5,
                "Diferenças entre o quadro e a realidade",
                "falta comparar o quadro escrito à mão com o gerado",
            ),
            _nao_medido(
                6, "As quatro contagens de memória", "vem da folha das contagens"
            ),
            _nao_medido(
                7, "Decisões esperando o dono", "vem da lista de pendências do dono"
            ),
            _nao_medido(
                8,
                '"Concordo" na amostra de decisões',
                "vem da amostra semanal do dono",
            ),
            _reversoes(entraram),
            _nao_medido(
                10, "Cota usada na semana", "vem do painel de uso da assinatura"
            ),
        ],
    }


def texto_do_placar(placar: Placar) -> str:
    """O placar em Markdown; a primeira linha diz que é gerado e a que horas."""
    hora = datetime.fromisoformat(placar["gerado_em"]).strftime("%d/%m/%Y %H:%M")
    semana = placar["semana"]
    inicio = date.fromisoformat(semana["inicio"])
    fim = date.fromisoformat(semana["fim"])
    comando = f"python -m scripts.placar_da_semana --semana {semana['rotulo']}"
    linhas = [
        f"{AVISO_DE_ARQUIVO_GERADO} · {hora} · {comando}",
        "",
        f"# Placar da semana {semana['rotulo']} ({inicio:%d/%m} a {fim:%d/%m/%Y})",
        "",
        "| # | Número | Valor |",
        "|---|---|---|",
        *[
            f"| {linha['numero']} | {linha['nome']} | {linha['texto']} |"
            for linha in placar["numeros"]
        ],
        "",
        "Estes números só se comparam com eles mesmos, semana a semana.",
    ]
    return "\n".join(linhas) + "\n"


def escrever_placar(placar: Placar, destino: Path) -> None:
    """Grava o placar em `destino`, criando a pasta se faltar."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto_do_placar(placar), encoding="utf-8", newline="\n")


def _buscar(comando: list[str], campos: str) -> list[dict[str, Any]]:
    """Roda uma listagem do `gh` e para se ela bateu no limite (o número sairia errado)."""
    limite = ["--limit", str(LIMITE_DA_BUSCA), "--json", campos]
    achados = json.loads(rodar_comando([*comando, *limite]))
    if len(achados) >= LIMITE_DA_BUSCA:
        raise SystemExit(
            f"a busca bateu no limite de {LIMITE_DA_BUSCA}: o placar sairia errado"
        )
    return achados


def buscar_prs_mesclados(de: date, ate: date) -> list[dict[str, Any]]:
    busca = f"merged:{de.isoformat()}..{ate.isoformat()}"
    comando = ["gh", "pr", "list", "--state", "merged", "--search", busca]
    return _buscar(comando, CAMPOS_DO_MESCLADO)


def buscar_execucoes_da_main(de: date, ate: date) -> list[dict[str, Any]]:
    """Execuções do CI disparadas por push na `main` (cada merge é um push)."""
    comando = ["gh", "run", "list", "--workflow", ARQUIVO_DO_CI, "--branch", "main"]
    criadas = f"{de.isoformat()}..{ate.isoformat()}"
    return _buscar(
        [*comando, "--event", "push", "--created", criadas], CAMPOS_DA_EXECUCAO
    )


def main(argumentos: list[str] | None = None) -> int:
    leitor = argparse.ArgumentParser(description=DESCRICAO_DO_COMANDO)
    leitor.add_argument(
        "--semana", type=ler_semana, help="AAAA-Www (sem ela, a última fechada)"
    )
    leitor.add_argument(
        "--destino", type=Path, help="arquivo onde gravar (sem ele, imprime)"
    )
    opcoes = leitor.parse_args(argumentos)
    agora = datetime.now().astimezone()
    segunda = opcoes.semana or semana_anterior(agora.date())
    de = segunda - timedelta(days=DIAS_DE_FOLGA_NA_BUSCA)
    ate = segunda + timedelta(days=DIAS_DA_SEMANA + DIAS_DE_FOLGA_NA_BUSCA)
    placar = montar_placar(
        buscar_prs_mesclados(de, ate),
        buscar_execucoes_da_main(de, ate),
        buscar_prs_abertos(),
        segunda,
        agora,
    )
    if opcoes.destino is None:
        print(texto_do_placar(placar), end="")
    else:
        escrever_placar(placar, opcoes.destino)
        print(f"placar gravado em {opcoes.destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
