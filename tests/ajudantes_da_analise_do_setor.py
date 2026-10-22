"""O par dados → texto do setor elétrico: o relatório do setor de 21/10/2026 e a análise à mão.

O relatório (`relatorio.json`) saiu da base de verdade: a noite de 21/10/2026 (a seção `setor` da
ficha) e o banco do app (membros pela CVM, DFP e ITR do lado a lado), com
`relatorio_setor.montar_relatorio_do_setor(..., plano="pro", hoje=21/10/2026)`. Ele fica guardado
como saiu, porque o banco muda todo dia; a entrada é uma função dele, com os mesmos ids da análise
de uma empresa (`{seção}.{chave}`, `{seção}.{tabela}.{i}`, `{seção}.paragrafos.{i}`).

Rodar como módulo regrava a entrada a partir do relatório guardado:
`python -m tests.ajudantes_da_analise_do_setor`.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.analise_escrita import entrada as en
from src.analise_escrita import saida

PAR_DO_SETOR = Path(__file__).parent / "arquivos" / "analise" / "setor_eletrico"
CORTE = date(2026, 10, 21)  # o dia da noite e do banco de onde o relatório saiu
VERSAO = "setor-1"
# O roteiro do setor (as partes da análise de uma empresa não servem: não há controlador nem caixa)
PARTES_DO_SETOR = (
    "em_meia_pagina",
    "quem_esta",
    "tamanho_e_concentracao",
    "participacao",
    "lado_a_lado",
    "o_que_mudaria",
    "limites",
)


def ler_do_par(nome: str) -> dict[str, Any]:
    return json.loads((PAR_DO_SETOR / nome).read_text(encoding="utf-8"))


def _linhas_do_relatorio(relatorio: dict[str, Any]) -> list[dict[str, Any]]:
    linhas = [
        linha
        for secao in relatorio["secoes"]
        if not secao.get("trancada")
        for linha in en._linhas_da_secao({"pontos": [], **secao})
    ]
    # Os limites do relatório não são uma seção: entram como parágrafos, para a análise citá-los
    linhas += [
        {
            "secao": "limites",
            "id": f"limites.paragrafos.{i}",
            "tipo": "paragrafo",
            "texto": texto,
        }
        for i, texto in enumerate(relatorio["limites"])
    ]
    return linhas


def entrada_do_setor(relatorio: dict[str, Any]) -> dict[str, Any]:
    """O relatório do setor como o modelo receberia: uma linha por número, tabela e parágrafo."""
    linhas = _linhas_do_relatorio(relatorio)
    ids = [linha["id"] for linha in linhas]
    if len(ids) != len(set(ids)):
        raise ValueError("id repetido na entrada")
    en.conferir_corte(linhas, CORTE)
    entrada = {
        "versao": VERSAO,
        "setor": relatorio["setor"],
        "nome": relatorio["nome"],
        "corte": CORTE.isoformat(),
        "fontes": relatorio["fontes"],
        "secoes": {s["chave"]: s["titulo"] for s in relatorio["secoes"]},
        "linhas": linhas,
    }
    en.conferir_sem_nome_com_cargo(entrada)
    return entrada


def partes_do_gabarito() -> tuple[saida.Parte, ...]:
    """As partes do gabarito no formato de `saida`, com o roteiro do setor.

    `saida.ler_analise` recusa chave fora das partes de uma empresa; os parágrafos (tipo, frases,
    notas e contas) passam pela mesma leitura da resposta do modelo.
    """
    return tuple(
        saida.Parte(
            parte["chave"],
            tuple(saida._paragrafo(p) for p in parte["paragrafos"]),
        )
        for parte in ler_do_par("gabarito.json")["analise"]["partes"]
    )


if __name__ == "__main__":
    texto = json.dumps(
        entrada_do_setor(ler_do_par("relatorio.json")), ensure_ascii=False, indent=1
    )
    (PAR_DO_SETOR / "entrada.json").write_text(texto + "\n", encoding="utf-8")
