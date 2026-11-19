"""As tabelas internas do DataJud (plano de 03/11/2026 dos processos judiciais, PR 3; ADR 0121):
`processos_datajud` (um retrato de cada processo, por grau, a cada consulta guardada) e
`processos_datajud_movimentos` (os movimentos de cada processo, uma linha por movimento).

**Só uso interno.** A família "datajud" está em `coletas.FONTES_SO_INTERNAS` (o termo de uso da API
Pública veda o uso comercial e a consultoria): as duas tabelas treinam e rotulam, e nenhuma tela,
relatório, API ou exportação as lê (`dossie.pode_mostrar` é falso para elas).

Lê só o que o arquivista já guardou (`base/arquivo/datajud.py`); não baixa nada.

- **Sem olhar o futuro:** o retrato vale desde o dia da consulta (`disponivel_em` = `visto_em`), porque
  o DataJud não diz quando cada dado ficou público. O movimento vale desde o primeiro dia em que uma
  consulta o mostrou, nunca antes, mesmo que tenha acontecido antes (`aconteceu_em`).
- **Sem a Justiça do Trabalho** e sem número com dígito errado (a coleta já tira; aqui sai de novo).
- **Sem nome de pessoa:** a API Pública não traz as partes; os complementos dos movimentos são os
  tabelados do CNJ.
"""

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa

from base import numero_cnj
from base import retratos as motor
from base.arquivo import datajud
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from src.versao_do_codigo import versao_do_codigo

TABELA_DOS_RETRATOS = "processos_datajud"
TABELA_DOS_MOVIMENTOS = "processos_datajud_movimentos"
TABELAS = (TABELA_DOS_RETRATOS, TABELA_DOS_MOVIMENTOS)
ARQUIVO = "datajud"
JA_MONTADO = {"ja_montado": 1}
SEPARADOR_DOS_CODIGOS = ";"
SEPARADOR_DOS_NOMES = "; "

COLUNAS_DOS_RETRATOS = [
    "numero_processo",
    "ano_do_processo",
    "justica",
    "tribunal",
    "grau",
    "classe_codigo",
    "classe",
    "assuntos_codigos",
    "assuntos",
    "orgao_julgador_codigo",
    "orgao_julgador",
    "ajuizado_em",
    "atualizado_na_fonte_em",
    "nivel_sigilo",
    "sistema",
    "formato",
    "movimentos",
    "ultimo_movimento_codigo",
    "ultimo_movimento_em",
    "disponivel_em",
    "visto_em",
    "origem_sha256",
    "origem_coletada_em",
]
COLUNAS_DOS_MOVIMENTOS = [
    "numero_processo",
    "grau",
    "movimento_codigo",
    "movimento",
    "complementos",
    "aconteceu_em",
    "disponivel_em",
    "visto_em",
    "origem_sha256",
    "origem_coletada_em",
]
ORDEM_DOS_RETRATOS = ["disponivel_em", "numero_processo", "grau"]
ORDEM_DOS_MOVIMENTOS = [
    "numero_processo",
    "grau",
    "aconteceu_em",
    "movimento_codigo",
    "complementos",
]
DATAS = ["ajuizado_em", "disponivel_em", "visto_em"]


def _texto(valor: object) -> str | None:
    texto = str(valor if valor is not None else "").strip()
    return texto or None


def _instante(valor: object) -> pd.Timestamp | None:
    instante = pd.to_datetime(_texto(valor), errors="coerce", utc=True)
    return None if pd.isna(instante) else instante


def _codigo_e_nome(valor: object) -> tuple[str | None, str | None]:
    if not isinstance(valor, Mapping):
        return None, None
    return _texto(valor.get("codigo")), _texto(valor.get("nome"))


def _assuntos(processo: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Os códigos e os nomes dos assuntos, na ordem da fonte (o assunto pode vir aninhado numa lista)."""
    planos: list[Mapping[str, Any]] = []
    for assunto in processo.get("assuntos") or []:
        planos.extend(assunto if isinstance(assunto, list) else [assunto])
    pares = [_codigo_e_nome(a) for a in planos]
    codigos = [c for c, _ in pares if c]
    nomes = [n for _, n in pares if n]
    return (
        SEPARADOR_DOS_CODIGOS.join(codigos) or None,
        SEPARADOR_DOS_NOMES.join(nomes) or None,
    )


def _complementos(movimento: Mapping[str, Any]) -> str:
    """Os complementos tabelados, `nome: descrição`; texto vazio (não nulo) sem complemento, porque a
    coluna entra na chave (o mesmo movimento, na mesma hora, com outro complemento é outra linha)."""
    partes = [
        f"{c.get('nome')}: {c.get('descricao')}"
        for c in movimento.get("complementosTabelados") or []
        if isinstance(c, Mapping) and c.get("nome")
    ]
    return SEPARADOR_DOS_NOMES.join(partes)


def _numero(processo: Mapping[str, Any]) -> numero_cnj.NumeroCnj | None:
    try:
        numero = numero_cnj.decodificar(str(processo.get("numeroProcesso") or ""))
    except numero_cnj.NumeroInvalido:
        return None
    return None if numero.segmento == numero_cnj.JUSTICA_DO_TRABALHO else numero


def ler_consulta(retrato: motor.Retrato) -> list[dict[str, Any]]:
    """Os processos de uma consulta guardada, com o dia e a origem do retrato."""
    conteudo = json.loads(motor.original(retrato.caminho))
    carimbo = {
        "_visto_em": pd.Timestamp(retrato.dia),
        "origem_sha256": retrato.sha256,
        "origem_coletada_em": pd.Timestamp(retrato.baixado_em).isoformat(),
    }
    return [{**p, **carimbo} for p in conteudo.get("processos") or []]


def _movimentos(processo: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [m for m in processo.get("movimentos") or [] if isinstance(m, Mapping)]


def _retrato(
    processo: Mapping[str, Any], numero: numero_cnj.NumeroCnj
) -> dict[str, Any]:
    classe_codigo, classe = _codigo_e_nome(processo.get("classe"))
    orgao_codigo, orgao = _codigo_e_nome(processo.get("orgaoJulgador"))
    assuntos_codigos, assuntos = _assuntos(processo)
    movimentos = sorted(
        _movimentos(processo),
        key=lambda m: (
            _instante(m.get("dataHora")) or pd.Timestamp.min.tz_localize("UTC")
        ),
    )
    ultimo = movimentos[-1] if movimentos else {}
    ajuizado = _instante(processo.get("dataAjuizamento"))
    return {
        "numero_processo": numero.formatado,
        "ano_do_processo": numero.ano,
        "justica": numero.nome_do_segmento,
        "tribunal": _texto(processo.get("tribunal")),
        "grau": _texto(processo.get("grau")),
        "classe_codigo": classe_codigo,
        "classe": classe,
        "assuntos_codigos": assuntos_codigos,
        "assuntos": assuntos,
        "orgao_julgador_codigo": orgao_codigo,
        "orgao_julgador": orgao,
        "ajuizado_em": ajuizado.date() if ajuizado is not None else None,
        "atualizado_na_fonte_em": _instante(processo.get("dataHoraUltimaAtualizacao")),
        "nivel_sigilo": pd.to_numeric(processo.get("nivelSigilo"), errors="coerce"),
        "sistema": _codigo_e_nome(processo.get("sistema"))[1],
        "formato": _codigo_e_nome(processo.get("formato"))[1],
        "movimentos": len(movimentos),
        "ultimo_movimento_codigo": _texto(ultimo.get("codigo")),
        "ultimo_movimento_em": _instante(ultimo.get("dataHora")),
        "disponivel_em": processo["_visto_em"],
        "visto_em": processo["_visto_em"],
        "origem_sha256": processo["origem_sha256"],
        "origem_coletada_em": processo["origem_coletada_em"],
    }


def _linhas_de_movimento(
    processo: Mapping[str, Any], numero: numero_cnj.NumeroCnj
) -> list[dict[str, Any]]:
    return [
        {
            "numero_processo": numero.formatado,
            "grau": _texto(processo.get("grau")),
            "movimento_codigo": _texto(movimento.get("codigo")),
            "movimento": _texto(movimento.get("nome")),
            "complementos": _complementos(movimento),
            "aconteceu_em": _instante(movimento.get("dataHora")),
            "disponivel_em": processo["_visto_em"],
            "visto_em": processo["_visto_em"],
            "origem_sha256": processo["origem_sha256"],
            "origem_coletada_em": processo["origem_coletada_em"],
        }
        for movimento in _movimentos(processo)
    ]


def tabelas(itens: Iterable[Mapping[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Os retratos (um por processo, grau e dia de consulta) e os movimentos (cada um uma vez, do primeiro
    dia em que uma consulta o mostrou)."""
    retratos: list[dict[str, Any]] = []
    movimentos: list[dict[str, Any]] = []
    for processo in itens:
        numero = _numero(processo)
        if numero is None:
            continue
        retratos.append(_retrato(processo, numero))
        movimentos.extend(_linhas_de_movimento(processo, numero))
    dos_retratos = pd.DataFrame(retratos, columns=COLUNAS_DOS_RETRATOS)
    dos_retratos = dos_retratos.drop_duplicates(
        ["numero_processo", "grau", "visto_em"], keep="last"
    )
    dos_movimentos = pd.DataFrame(movimentos, columns=COLUNAS_DOS_MOVIMENTOS)
    dos_movimentos = dos_movimentos.sort_values(
        "visto_em", kind="stable"
    ).drop_duplicates(ORDEM_DOS_MOVIMENTOS, keep="first")
    return dos_retratos, dos_movimentos


def _para_gravar(
    tabela: pd.DataFrame, ordem: list[str], agora: datetime
) -> pd.DataFrame:
    datas = {c: pd.to_datetime(tabela[c]).dt.date for c in DATAS if c in tabela}
    return (
        tabela.assign(
            **datas, montado_em=agora.isoformat(), versao_do_codigo=versao_do_codigo()
        )
        .sort_values(ordem, kind="stable", na_position="first")
        .reset_index(drop=True)
    )


def montar(
    conexao: sa.Connection, pasta: Path, agora: datetime, refazer: bool = False
) -> dict[str, int]:
    """`processos_datajud` e `processos_datajud_movimentos` em `<pasta>/<tabela>/datajud.parquet`.

    Vazio se nenhuma consulta foi guardada; `JA_MONTADO` se nada mudou desde a última montagem
    (`refazer` relê mesmo assim)."""
    guardadas = motor.retratos(conexao, datajud.ID)
    if not guardadas:
        return {}
    origens = [{"url": r.url, "sha256": r.sha256} for r in guardadas]
    destinos = {nome: pasta / nome / ARQUIVO for nome in TABELAS}
    if not refazer and all(origens_gravadas(d) == origens for d in destinos.values()):
        return JA_MONTADO
    itens = [p for r in guardadas for p in ler_consulta(r)]
    dos_retratos, dos_movimentos = tabelas(itens)
    for nome, tabela, ordem in (
        (TABELA_DOS_RETRATOS, dos_retratos, ORDEM_DOS_RETRATOS),
        (TABELA_DOS_MOVIMENTOS, dos_movimentos, ORDEM_DOS_MOVIMENTOS),
    ):
        gravar_se_mudou(
            _para_gravar(tabela, ordem, agora),
            destinos[nome],
            origens,
            ordem,
            carimbos=LINHAGEM,
        )
    return {
        "consultas": len(guardadas),
        "retratos": len(dos_retratos),
        "movimentos": len(dos_movimentos),
    }
