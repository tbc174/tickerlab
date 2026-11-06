"""A entrada do modelo para o relatório do setor (molde D, PR 6): o relatório com um id por número.

Os ids são os da análise de uma empresa (`{seção}.{chave}`, `{seção}.{tabela}.{i}`,
`{seção}.paragrafos.{i}`); os limites do relatório não são uma seção e entram como parágrafos, para a
análise citá-los. O ano que a agência ainda não fechou (a linha com menos de 12 meses) não é fato do
setor: a linha ganha `ano_parcial` com o id da lacuna que avisa isso, e o número do topo e a frase por
regra que saíram dela também. A lacuna é obrigatória (a análise tem de dizer) e a porta 1 reprova a
frase que cita a linha parcial sem citar a lacuna (o erro da linha 167 da fila não passa para o texto).
"""

import re
from collections.abc import Iterator
from datetime import date
from typing import Any

from src.analise_escrita import entrada as en
from src.analise_escrita import saida
from src.analise_escrita.porta1 import ANO_PARCIAL

VERSAO = "setor-1"
COLUNA_DO_ANO = "Ano"
COLUNA_DOS_MESES = "Meses no ano"
COLUNA_DO_FIM = "Até"
MESES_DO_ANO = 12
SECAO_DAS_FRASES = "o_que_os_dados_mostram"  # as frases por regra do relatório


def _linhas_do_relatorio(relatorio: dict[str, Any]) -> list[dict[str, Any]]:
    linhas = [
        linha
        for secao in relatorio["secoes"]
        if not secao.get("trancada")
        for linha in en.linhas_da_secao({"pontos": [], **secao})
    ]
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


def _meses(linha: dict[str, Any]) -> int | None:
    texto = (linha.get("celulas") or {}).get(COLUNA_DOS_MESES)
    return int(texto) if texto and str(texto).isdigit() else None


def _parciais(linhas: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """As linhas de tabela de um ano com menos de 12 meses."""
    for linha in linhas:
        meses = _meses(linha)
        if linha["tipo"] == "linha" and meses is not None and meses < MESES_DO_ANO:
            yield linha


def _id_da_lacuna(ano: str) -> str:
    return f"lacuna.ano_parcial.{ano}"


def _lacuna(ano: str, meses: int, fim: str) -> dict[str, Any]:
    texto = (
        f"O ano de {ano} ainda está aberto na base: as linhas dele cobrem {meses} meses, até {fim}. "
        f"Elas não se comparam com os anos inteiros, e o que sai delas (o número do topo e a frase "
        f"por regra de {ano}) não é o retrato do setor no ano."
    )
    return {
        "secao": "lacuna",
        "id": _id_da_lacuna(ano),
        "tipo": "lacuna",
        "texto": texto,
    }


def _menciona_o_ano(texto: str, ano: str) -> bool:
    """O ano solto na frase ("Em 2026, ..."), não dentro de uma data ("21/10/2026")."""
    return re.search(rf"(?<![/\d]){ano}(?!\d)", texto) is not None


def _marcar_ano_parcial(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Marca as linhas que saem do ano parcial e devolve as lacunas (uma por ano)."""
    lacunas: dict[str, dict[str, Any]] = {}
    fins: dict[str, str] = {}  # "ago/2026" -> "2026": o `medido_em` do número do topo
    for linha in _parciais(linhas):
        celulas = linha["celulas"]
        ano, fim = celulas[COLUNA_DO_ANO], celulas[COLUNA_DO_FIM]
        linha[ANO_PARCIAL] = _id_da_lacuna(ano)
        lacunas.setdefault(ano, _lacuna(ano, _meses(linha) or 0, fim))
        fins[fim] = ano
    for linha in linhas:
        if linha["tipo"] == "numero" and linha.get("medido_em") in fins:
            linha[ANO_PARCIAL] = _id_da_lacuna(fins[linha["medido_em"]])
        elif linha["tipo"] == "paragrafo" and linha["secao"] == SECAO_DAS_FRASES:
            ano = next((a for a in lacunas if _menciona_o_ano(linha["texto"], a)), None)
            if ano is not None:
                linha[ANO_PARCIAL] = _id_da_lacuna(ano)
    return list(lacunas.values())


def entrada_do_setor(relatorio: dict[str, Any], corte: date) -> dict[str, Any]:
    """O relatório do setor (`RelatorioDoSetor.como_dict()`) como o modelo recebe.

    `corte` é o dia da noite e do banco de onde o relatório saiu: nenhuma data passa dele.
    """
    linhas = _linhas_do_relatorio(relatorio)
    lacunas = _marcar_ano_parcial(linhas)
    linhas += lacunas
    ids = [linha["id"] for linha in linhas]
    if len(ids) != len(set(ids)):
        raise ValueError("id repetido na entrada")
    en.conferir_corte(linhas, corte)
    entrada = {
        "versao": VERSAO,
        "tipo": saida.TIPO_SETOR,
        "setor": relatorio["setor"],
        "nome": relatorio["nome"],
        "corte": corte.isoformat(),
        "fontes": relatorio["fontes"],
        "secoes": {s["chave"]: s["titulo"] for s in relatorio["secoes"]},
        "linhas": linhas,
        "obrigatorias": [lacuna["id"] for lacuna in lacunas],
    }
    en.conferir_sem_nome_com_cargo(entrada)
    return entrada
