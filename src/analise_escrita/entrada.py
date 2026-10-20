"""A entrada do modelo: a ficha da empresa (`relatorio_empresa.montar`) com um id por número.

Cada item vira uma linha com o contrato do número (valor, medido em, fonte, comparação ou o motivo de
faltar), cada linha de tabela, parágrafo e ponto também ganha id, e as lacunas da base entram como
linhas próprias: o modelo cita o que falta do mesmo jeito que cita um número. A porta 1 confere a
análise contra estas linhas, e o hash diz se a análise guardada ainda vale para a ficha de agora.

Fora da entrada: a seção de valuation, o dividend yield e o preço da ação (a D3 mudada em 20/10/2026
liberou o preço do Yahoo na tela e no PDF da ficha, não no texto publicado da análise).
"""

import hashlib
import json
from collections.abc import Iterator
from datetime import date
from typing import Any

from base import dossie as dossie_da_base
from src.analise_escrita import numeros
from src.relatorio_empresa import (
    COMO_SAI_O_DY,
    FONTE_DOS_MULTIPLOS,
    Relatorio,
    nome_da_tabela,
)
from src.rotulos_ia import mascarar_pessoas
from src.setores import grupo_do_setor

VERSAO = 1
SECOES_FORA = ("valuation",)  # números com o preço da ação
TRECHO_DO_PRECO = (
    "Preço da ação"  # o parágrafo da metodologia que diz de onde vem o preço
)
GRUPOS_DE_CONCESSAO = ("energia", "saneamento", "transporte")
CONTROLADOR = "ficha_tecnica.controlador"
LACUNA_SEGMENTOS = "lacuna.segmentos"
LACUNA_CONCESSAO = "lacuna.concessao"
LACUNAS = {
    LACUNA_SEGMENTOS: (
        "A base não separa a receita nem o lucro por segmento de negócio: as demonstrações da ficha "
        "são as consolidadas da companhia."
    ),
    LACUNA_CONCESSAO: (
        "A base não separa o investimento na concessão (ativo de contrato e intangível de "
        "concessão) do capex: o capex da ficha pode não mostrar todo o investimento na rede."
    ),
}
# o item vira só estes campos (a nota em letra miúda e a chave interna ficam de fora)
CAMPOS_DO_ITEM = {
    "nome": "nome",
    "texto": "texto",
    "valor": "valor",
    "unidade": "unidade",
    "base": "medido_em",
    "fonte": "fonte",
    "comparacao": "comparacao",
    "sem_comparacao": "sem_comparacao",
    "motivo": "motivo",
    "nota": "nota",
    "nota_texto": "nota_texto",
}

PessoaNaEntradaError = dossie_da_base.PessoaNaFichaError


class DataDepoisDoCorteError(ValueError):
    """A ficha tem uma data depois do corte: o texto de "como era em D" não pode ver o futuro (0077)."""


def _sem_vazios(campos: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in campos.items() if v not in (None, "", [], {})}


def _linha_do_item(secao: str, item: dict[str, Any]) -> dict[str, Any]:
    campos = {destino: item.get(origem) for origem, destino in CAMPOS_DO_ITEM.items()}
    return {"id": f"{secao}.{item['chave']}", "tipo": "numero", **_sem_vazios(campos)}


def _usa_o_preco(item: dict[str, Any]) -> bool:
    """O número sai do preço da ação (o DY, fora da seção de valuation)."""
    return item.get("fonte") == FONTE_DOS_MULTIPLOS


def _linhas_da_secao(secao: dict[str, Any]) -> Iterator[dict[str, Any]]:
    chave = secao["chave"]
    for item in secao["itens"]:
        if not _usa_o_preco(item):
            yield {"secao": chave, **_linha_do_item(chave, item)}
    for tabela, linhas in secao["tabelas"].items():
        for i, celulas in enumerate(linhas):
            yield {
                "secao": chave,
                "id": f"{chave}.{tabela}.{i}",
                "tipo": "linha",
                "tabela": nome_da_tabela(tabela),
                "celulas": celulas,
            }
    for i, texto in enumerate(secao["paragrafos"]):
        if TRECHO_DO_PRECO not in texto and texto != COMO_SAI_O_DY:
            linha = {
                "id": f"{chave}.paragrafos.{i}",
                "tipo": "paragrafo",
                "texto": texto,
            }
            yield {"secao": chave, **linha}
    for i, ponto in enumerate(secao["pontos"]):
        yield {"secao": chave, "id": f"{chave}.pontos.{i}", "tipo": "ponto", **ponto}


def _linhas_da_ficha(ficha: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        linha
        for secao in ficha["secoes"]
        if secao["chave"] not in SECOES_FORA and not secao["trancada"]
        for linha in _linhas_da_secao(secao)
    ]


def _assinatura(linha: dict[str, Any]) -> str:
    """O conteúdo da linha sem o id: parágrafo que muda de posição continua sendo o mesmo."""
    sem_id = {k: v for k, v in linha.items() if k not in ("id", "so_pro")}
    return json.dumps(sem_id, sort_keys=True, ensure_ascii=False)


def _marcar_so_pro(linhas: list[dict[str, Any]], sem_dossie: Relatorio | None) -> None:
    """`so_pro`: a linha só existe (ou só é assim) com o dossiê. Sem a ficha de comparação, tudo."""
    abertas = set()
    if sem_dossie is not None:
        abertas = {_assinatura(li) for li in _linhas_da_ficha(sem_dossie.como_dict())}
    for linha in linhas:
        linha["so_pro"] = _assinatura(linha) not in abertas


def _lacunas(setor: str) -> list[dict[str, Any]]:
    chaves = [LACUNA_SEGMENTOS]
    if grupo_do_setor(setor) in GRUPOS_DE_CONCESSAO:
        chaves.append(LACUNA_CONCESSAO)
    return [
        {
            "secao": "lacuna",
            "id": c,
            "tipo": "lacuna",
            "texto": LACUNAS[c],
            "so_pro": False,
        }
        for c in chaves
    ]


def _obrigatorias(linhas: list[dict[str, Any]]) -> list[str]:
    """O que o texto tem de dizer que falta (critério 2 do gabarito: omitir em silêncio reprova)."""
    por_id = {linha["id"]: linha for linha in linhas}
    controlador = por_id.get(CONTROLADOR, {})
    obrigatorias = [CONTROLADOR] if controlador.get("motivo") else []
    return obrigatorias + [i for i in LACUNAS if i in por_id]


def _textos(valor: object) -> Iterator[str]:
    if isinstance(valor, dict):
        for dentro in valor.values():
            yield from _textos(dentro)
    elif isinstance(valor, list):
        for dentro in valor:
            yield from _textos(dentro)
    elif isinstance(valor, str):
        yield valor


def conferir_corte(linhas: list[dict[str, Any]], corte: date) -> None:
    """Levanta `DataDepoisDoCorteError` se algum texto da entrada tem data depois do corte."""
    for linha in linhas:
        for texto in _textos(linha):
            for data in numeros.datas(texto):
                if data.depois_de(corte):
                    raise DataDepoisDoCorteError(
                        f"{linha['id']}: {data.trecho} passa do corte de {corte:%d/%m/%Y}"
                    )


def entrada_da_ficha(
    relatorio: Relatorio,
    corte: date,
    sem_dossie: Relatorio | None = None,
    pessoas: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """A ficha como o modelo recebe: uma linha por número, tabela, parágrafo, ponto e lacuna.

    `sem_dossie` é a mesma ficha montada sem o dossiê: o que muda entre as duas é `so_pro` (o
    plano grátis não vê). `pessoas` são os nomes normalizados da base que não podem aparecer.
    """
    ficha = relatorio.como_dict()
    linhas = _linhas_da_ficha(ficha)
    _marcar_so_pro(linhas, sem_dossie)
    linhas += _lacunas(relatorio.setor)
    ids = [linha["id"] for linha in linhas]
    if len(ids) != len(set(ids)):
        raise ValueError("id repetido na entrada")
    conferir_corte(linhas, corte)
    entrada = {
        "versao": VERSAO,
        "empresa": relatorio.empresa,
        "cnpj": relatorio.cnpj,
        "ticker": relatorio.ticker,
        "setor": relatorio.setor,
        "grupo": relatorio.grupo,
        "corte": corte.isoformat(),
        "fontes": [f for f in relatorio.fontes if TRECHO_DO_PRECO not in f],
        "secoes": {
            s["chave"]: s["titulo"]
            for s in ficha["secoes"]
            if s["chave"] not in SECOES_FORA
        },
        "linhas": linhas,
        "obrigatorias": _obrigatorias(linhas),
    }
    dossie_da_base.conferir_sem_pessoas(entrada, set(pessoas))
    conferir_sem_nome_com_cargo(entrada)
    return entrada


def conferir_sem_nome_com_cargo(entrada: dict[str, Any]) -> None:
    """D4 (parecer de privacidade, ADR 0088): nome de pessoa escrito junto de um cargo não vai à API.

    A lista de pessoas da base só pega o texto que é exatamente um nome; esta trava pega o nome dentro
    da frase ("CFO Maria Souza"), com a mesma heurística da rotulagem. Barra em vez de mascarar: a
    entrada tem hash e o app a remonta para conferir.
    """
    for texto in _textos(entrada):
        if mascarar_pessoas(texto) != texto:
            raise PessoaNaEntradaError("nome de pessoa junto de um cargo na entrada")


def hash_da_entrada(entrada: dict[str, Any]) -> str:
    """O mesmo texto JSON dá o mesmo hash: a análise guardada vale só para a entrada de onde saiu."""
    texto = json.dumps(
        entrada, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
