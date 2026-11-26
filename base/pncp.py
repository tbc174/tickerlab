"""Contratos do PNCP nos lotes JSONL do arquivista, sem baixar nada.

As duas coletas trazem janelas parciais, nunca retratos completos: a ausência não é exclusão.
Cada mudança observada vira versão; repetições consecutivas entre lotes não duplicam o contrato.
A tabela é um histórico de versões, não uma soma de contratos vigentes. A primeira versão usa
a maior data pública da fonte; retificação sem data e mudanças posteriores valem desde a coleta.
Nomes, objeto, subcontratados, contatos e demais textos livres ficam fora. MEI, empresário
individual e CNPJ desconhecido da Receita são marcados para a porta retirar (ADR 0075).
"""

import json
import math
import re
from collections.abc import Collection
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato as cadastros
from base import cnpj as cnpjs
from base import retratos as motor
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

FONTES = ("pncp-contratos", "pncp-contratos-atualizados")
TABELA = "pncp_contratos"
CONTROLE = re.compile(r"[0-9]{14}-2-[0-9]{1,6}/[0-9]{4}")
PONTUACAO = str.maketrans("", "", "./- ")
DATAS = {
    "assinado_em": "dataAssinatura",
    "vigencia_inicio": "dataVigenciaInicio",
    "vigencia_fim": "dataVigenciaFim",
    "publicado_em": "dataPublicacaoPncp",
    "atualizado_em": "dataAtualizacao",
    "atualizado_global_em": "dataAtualizacaoGlobal",
}
VALORES = {
    "valor_inicial": "valorInicial",
    "valor_global": "valorGlobal",
    "valor_acumulado": "valorAcumulado",
}
COLUNAS = (
    "numero_controle_pncp",
    "cnpj",
    "cnpj_basico",
    "cnpj_orgao",
    "numero_retificacao",
    *DATAS,
    *VALORES,
    "receita",
    "disponivel_em",
)
ORDEM = ["numero_controle_pncp", "visto_em"]
OBRIGATORIAS = {"numeroControlePNCP", "tipoPessoa", "niFornecedor"}


def _cnpj(valor: object) -> str | None:
    if not isinstance(valor, str):
        return None
    limpo = valor.translate(PONTUACAO)
    if not re.fullmatch(r"[0-9]{14}", limpo):
        return None
    return limpo if cnpjs.dv_confere(limpo) else None


def _data(valor: object) -> date | None:
    if not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor).date()
    except ValueError:
        return None


def _numero(valor: object) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        return None
    return float(valor) if math.isfinite(valor) else None


def _publico_em(linha: dict, coleta: date, atualizados: bool) -> date:
    publicacao = linha["publicado_em"]
    atualizacoes = [
        linha[c] for c in ("atualizado_em", "atualizado_global_em") if linha[c]
    ]
    retificada = atualizados or linha["numero_retificacao"] != 0
    conhecidas = [*atualizacoes, *([publicacao] if publicacao else [])]
    if publicacao is None or (retificada and not atualizacoes):
        return max([coleta, *conhecidas])
    return max(conhecidas)


def _linha(item: dict, cnpj: str, coleta: date, atualizados: bool) -> dict:
    controle = item["numeroControlePNCP"]
    if (
        not isinstance(controle, str)
        or not CONTROLE.fullmatch(controle)
        or not _cnpj(controle[:14])
    ):
        raise ValueError("PNCP: identificador de contrato inválido")
    retificacao = item.get("numeroRetificacao")
    linha = {
        "numero_controle_pncp": controle,
        "cnpj": cnpj,
        "cnpj_basico": cnpj[:8],
        "cnpj_orgao": controle[:14],
        "numero_retificacao": retificacao
        if type(retificacao) is int and retificacao >= 0
        else None,
        **{nome: _data(item.get(fonte)) for nome, fonte in DATAS.items()},
        **{nome: _numero(item.get(fonte)) for nome, fonte in VALORES.items()},
        "receita": item.get("receita") if type(item.get("receita")) is bool else None,
    }
    linha["assinado_em"] = linha["assinado_em"] or linha["vigencia_inicio"]
    linha["disponivel_em"] = _publico_em(linha, coleta, atualizados)
    return linha


def _tipar(tabela: pd.DataFrame) -> pd.DataFrame:
    return tabela.astype(
        {
            **dict.fromkeys(
                ("numero_controle_pncp", "cnpj", "cnpj_basico", "cnpj_orgao"), "string"
            ),
            "numero_retificacao": "Int64",
            **dict.fromkeys(VALORES, "Float64"),
            "receita": "boolean",
        }
    )


def ler(
    conteudo: bytes, coletado_em: datetime, *, atualizados: bool = False
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Lê o JSONL UTF-8 descomprimido do acervo; recusa layout desconhecido sem expor a linha."""
    linhas = []
    resumo = {"linhas": 0, "tipo_nao_pj": 0, "cnpj_invalido": 0}
    for texto in conteudo.decode("utf-8-sig").splitlines():
        if not texto.strip():
            continue
        try:
            item = json.loads(texto)
        except json.JSONDecodeError:
            raise ValueError("PNCP: JSONL inválido") from None
        if not isinstance(item, dict) or not item.keys() >= OBRIGATORIAS:
            raise ValueError("PNCP: faltam campos obrigatórios do contrato")
        if item["tipoPessoa"] != "PJ":
            resumo["tipo_nao_pj"] += 1
            continue
        cnpj = _cnpj(item["niFornecedor"])
        if cnpj is None:
            resumo["cnpj_invalido"] += 1
            continue
        linhas.append(_linha(item, cnpj, coletado_em.date(), atualizados))
    resumo["linhas"] = len(linhas)
    return _tipar(pd.DataFrame(linhas, columns=COLUNAS)), resumo


def _versoes(
    achados: list[tuple[str, motor.Retrato]],
) -> tuple[pd.DataFrame, dict[str, int]]:
    anteriores: dict[str, tuple[str, str]] = {}
    linhas = []
    resumo: dict[str, int] = {"repetidas": 0}
    for fonte, retrato in achados:
        tabela, contagem = ler(
            motor.original(retrato.caminho),
            retrato.baixado_em,
            atualizados=fonte == FONTES[1],
        )
        for nome, quantidade in contagem.items():
            resumo[nome] = resumo.get(nome, 0) + quantidade
        for linha in (
            tabela.astype(object).where(tabela.notna(), None).to_dict("records")
        ):
            controle = str(linha["numero_controle_pncp"])
            assinatura = json.dumps(
                {c: linha[c] for c in COLUNAS if c != "disponivel_em"},
                default=str,
                sort_keys=True,
            )
            visto = retrato.baixado_em.isoformat()
            anterior = anteriores.get(controle)
            if anterior and anterior[0] == assinatura:
                resumo["repetidas"] += 1
                continue
            if anterior:
                if anterior[1] == visto:
                    raise ValueError("PNCP: versões conflitantes na mesma coleta")
                # Mudança vista hoje não reescreve o passado, mesmo com data antiga na fonte.
                linha["disponivel_em"] = max(linha["disponivel_em"], retrato.dia)
            anteriores[controle] = (assinatura, visto)
            linhas.append(
                {
                    **linha,
                    "visto_em": visto,
                    "origem_sha256": retrato.sha256,
                    "origem_coletada_em": visto,
                }
            )
    return _tipar(
        pd.DataFrame(
            linhas,
            columns=[*COLUNAS, "visto_em", "origem_sha256", "origem_coletada_em"],
        )
    ), resumo


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """Grava as versões em `pncp_contratos/contratos.parquet`, com manifesto e proteção de pessoa."""
    achados = sorted(
        [(fonte, r) for fonte in FONTES for r in motor.retratos(conexao, fonte)],
        key=lambda par: (pd.Timestamp(par[1].baixado_em), par[0], par[1].url),
    )
    if not achados:
        return {}
    destino = pasta / TABELA / "contratos"
    origens = [{"url": r.url, "sha256": r.sha256} for _, r in achados]
    if not refazer and origens_gravadas(destino) == origens:
        return {"contratos": cadastros.JA_MONTADO}
    tabela, resumo = _versoes(achados)
    sabidas = (
        pessoas_pela_receita(
            conexao, cnpjs.ordenados(cnpjs.raizes_em_numeros(tabela["cnpj_basico"]))
        )
        if pessoas is None
        else cadastros.como_numeros(pessoas)
    )
    tabela = tabela.assign(
        trata_como_pessoa=cadastros.de_pessoa(tabela, sabidas),
        montado_em=agora.isoformat(),
        versao_do_codigo=versao_do_codigo(),
    )
    gravar_se_mudou(tabela, destino, origens, ORDEM, carimbos=LINHAGEM)
    return {"contratos": {**resumo, "arquivos": len(achados), "na_tabela": len(tabela)}}
