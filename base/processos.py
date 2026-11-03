"""Processos judiciais por CNPJ (plano de 03/11/2026, PR 1; ADR 0121): as comunicações do DJEN que o
arquivista guardou (`base/arquivo/djen.py`) nas tabelas `processos_comunicacoes` (uma linha por
comunicação) e `processos_partes` (as companhias abertas e os órgãos públicos de cada uma).

Lê só o que já está no acervo (não baixa nada).

- **Nenhum nome de pessoa física.** A parte vira um tipo: `companhia` (o nome bate com exatamente uma
  razão social do cadastro da CVM: guardamos o CNPJ e o nome do cadastro), `orgao_publico` (município,
  estado, União, autarquia, Ministério Público...: guardamos o nome), `pessoa_juridica` ou
  `pessoa_ou_desconhecida`. Destas duas, só a contagem: o nome de uma empresa que não é companhia
  aberta pode ser o de um empresário individual.
- **Homônimo não liga.** Nome que bate com mais de uma razão social do cadastro fica sem CNPJ (contado
  no resumo); comunicação sem nenhuma companhia entre as partes sai (a busca do DJEN também acha o nome
  no texto).
- **Sem a Justiça do Trabalho** (Resolução CNJ 121/2010; a coleta já tira, e aqui sai de novo) e sem
  número de processo com dígito errado.
- **Sem olhar o futuro:** `disponivel_em` é o dia em que a comunicação foi disponibilizada no DJEN
  (nunca depois do dia em que a vimos). `cancelada_em` é a data do cancelamento que o tribunal informou:
  antes dela, a comunicação valia.
- A mesma comunicação achada em duas consultas (a semana e o mês do histórico) fica uma vez só, com o
  que a consulta mais recente disse.

Limites: a busca é pelo nome, então processo em que a companhia aparece com outro nome (sigla, nome
antigo) não vem; companhia fechada e controlada sem registro na CVM ficam de fora; o histórico começa
em 2025 (`djen.HISTORICO_DESDE`).
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa

from base import numero_cnj
from base import retratos as motor
from base.arquivo import djen
from base.cadastro import cadastro_do_acervo
from base.cnpj import normalizar_cnpj
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from src.versao_do_codigo import versao_do_codigo

TABELA_DAS_COMUNICACOES = "processos_comunicacoes"
TABELA_DAS_PARTES = "processos_partes"
JA_MONTADO = {"ja_montado": 1}

COMPANHIA = "companhia"
ORGAO_PUBLICO = "orgao_publico"
PESSOA_JURIDICA = "pessoa_juridica"
PESSOA_OU_DESCONHECIDA = "pessoa_ou_desconhecida"
POLOS = {"A": "ativo", "P": "passivo"}
OUTRO_POLO = "outro"

# o que vem depois de " _" é o apelido que o tribunal pôs ("COMPANHIA X _CPFL")
_APELIDO = re.compile(r"\s+_.*$")
_FORA_DO_NOME = re.compile(r"[^A-Z0-9 ]")
_ESPACOS = re.compile(r"\s+")
_TROCAS = (
    (re.compile(r"\bS\s*/\s*A\b|\bS\s*\.\s*A\b\.?"), "SA"),
    (re.compile(r"\bCIA\b\.?"), "COMPANHIA"),
    (re.compile(r"\bLTDA\b\.?"), "LTDA"),
)
_RECUPERACAO = re.compile(r"\s*[-–(]?\s*EM RECUPERACAO JUDICIAL\s*\)?\s*$")
_ORGAO_PUBLICO = re.compile(
    r"^(MUNICIPIO|PREFEITURA|ESTADO D[OAE]|DISTRITO FEDERAL|UNIAO\b|FAZENDA|MINISTERIO PUBLICO|"
    r"DEFENSORIA|PROCURADORIA|ADVOCACIA GERAL|INSTITUTO NACIONAL DO SEGURO SOCIAL|INSS\b|"
    r"AGENCIA NACIONAL|AGENCIA ESTADUAL|AGENCIA REGULADORA|DEPARTAMENTO (NACIONAL|ESTADUAL)|"
    r"CONSELHO (REGIONAL|FEDERAL)|CAMARA MUNICIPAL|ASSEMBLEIA LEGISLATIVA|TRIBUNAL DE CONTAS|"
    r"AUTARQUIA|SECRETARIA)"
)
_PESSOA_JURIDICA = re.compile(
    r"\b(SA|LTDA|EIRELI|ME|EPP|COMPANHIA|BANCO|COOPERATIVA|ASSOCIACAO|CONDOMINIO|FUNDACAO|"
    r"SOCIEDADE|EMPRESA|INDUSTRIA|COMERCIO|SERVICOS|PARTICIPACOES|HOLDING|INCORPORADORA|"
    r"CONSTRUTORA|SEGURADORA|SEGUROS|FUNDO|CONSORCIO|INSTITUTO|SINDICATO|IGREJA|CLUBE)\b"
)

COLUNAS_DAS_COMUNICACOES = [
    "id_na_fonte",
    "id_djen",
    "numero_processo",
    "ano_do_processo",
    "justica",
    "tribunal",
    "orgao",
    "classe_codigo",
    "classe",
    "tipo_comunicacao",
    "tipo_documento",
    "meio",
    "link",
    "cancelada_em",
    "companhias",
    "orgaos_publicos",
    "pessoas_juridicas",
    "pessoas_ou_desconhecidas",
    "advogados",
    "disponivel_em",
    "visto_em",
]
COLUNAS_DAS_PARTES = [
    "id_na_fonte",
    "numero_processo",
    "polo",
    "tipo_parte",
    "parte",
    "cnpj",
    "empresa",
    "orgao_publico",
    "disponivel_em",
    "visto_em",
]
ORDEM_DAS_COMUNICACOES = ["disponivel_em", "id_na_fonte"]
ORDEM_DAS_PARTES = [
    "disponivel_em",
    "id_na_fonte",
    "polo",
    "parte",
]
DATAS = ["cancelada_em", "disponivel_em", "visto_em"]


def normalizar_nome(nome: object) -> str:
    """O nome em maiúsculas, sem acento, apelido, pontuação nem "em recuperação judicial"; as formas
    de S.A., Cia. e Ltda. ficam iguais."""
    texto = _APELIDO.sub("", str(nome or "")).upper()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    for padrao, troca in _TROCAS:
        texto = padrao.sub(troca, texto)
    texto = _ESPACOS.sub(" ", _FORA_DO_NOME.sub(" ", texto)).strip()
    return _RECUPERACAO.sub("", texto).strip()


def razoes_sociais(cadastro: pd.DataFrame) -> dict[str, tuple[str, str] | None]:
    """O nome normalizado de cada companhia do cadastro -> (CNPJ, razão social); None se o nome é de
    mais de um CNPJ (homônimo: não liga)."""
    achadas: dict[str, set[tuple[str, str]]] = {}
    for cnpj, empresa in zip(cadastro["cnpj"], cadastro["empresa"], strict=True):
        cnpj14 = normalizar_cnpj(cnpj)
        nome = normalizar_nome(empresa)
        if cnpj14 and nome:
            achadas.setdefault(nome, set()).add((cnpj14, str(empresa).strip()))
    return {
        nome: next(iter(dela)) if len({c for c, _ in dela}) == 1 else None
        for nome, dela in achadas.items()
    }


def tipo_da_parte(nome: str, razoes: Mapping[str, tuple[str, str] | None]) -> str:
    """`nome` já normalizado. O homônimo do cadastro conta como pessoa jurídica (sem CNPJ)."""
    if razoes.get(nome) is not None:
        return COMPANHIA
    if _ORGAO_PUBLICO.match(nome):
        return ORGAO_PUBLICO
    if nome in razoes or _PESSOA_JURIDICA.search(nome):
        return PESSOA_JURIDICA
    return PESSOA_OU_DESCONHECIDA


def _texto(valor: object) -> str | None:
    texto = str(valor or "").strip().upper()
    return texto or None


def _data(valor: object) -> pd.Timestamp | None:
    data = pd.to_datetime(str(valor or "")[:10], errors="coerce")
    return None if pd.isna(data) else data


def _partes(
    item: Mapping[str, Any], razoes: Mapping[str, tuple[str, str] | None]
) -> list[dict[str, Any]]:
    partes = []
    for destinatario in item.get("destinatarios") or []:
        nome = normalizar_nome(destinatario.get("nome"))
        tipo = tipo_da_parte(nome, razoes)
        ligada = razoes.get(nome) if tipo == COMPANHIA else None
        orgao = nome if tipo == ORGAO_PUBLICO else None
        partes.append(
            {
                "polo": POLOS.get(
                    str(destinatario.get("polo") or "").upper(), OUTRO_POLO
                ),
                "tipo_parte": tipo,
                "parte": ligada[0] if ligada else orgao,
                "cnpj": ligada[0] if ligada else None,
                "empresa": ligada[1] if ligada else None,
                "orgao_publico": orgao,
            }
        )
    return partes


def _comunicacao(
    item: Mapping[str, Any],
    numero: numero_cnj.NumeroCnj,
    partes: list[dict[str, Any]],
    visto_em: pd.Timestamp,
) -> dict[str, Any]:
    disponibilizada = _data(
        item.get("data_disponibilizacao") or item.get("datadisponibilizacao")
    )
    tipos = pd.Series([p["tipo_parte"] for p in partes], dtype=str)
    return {
        "id_na_fonte": str(item.get("hash") or item.get("id")),
        "id_djen": int(item["id"]) if item.get("id") is not None else None,
        "numero_processo": numero.formatado,
        "ano_do_processo": numero.ano,
        "justica": numero.nome_do_segmento,
        "tribunal": _texto(item.get("siglaTribunal")),
        "orgao": _texto(item.get("nomeOrgao")),
        "classe_codigo": _texto(item.get("codigoClasse")),
        "classe": _texto(item.get("nomeClasse")),
        "tipo_comunicacao": _texto(item.get("tipoComunicacao")),
        "tipo_documento": _texto(item.get("tipoDocumento")),
        "meio": _texto(item.get("meiocompleto") or item.get("meio")),
        "link": str(item.get("link") or "").strip() or None,
        "cancelada_em": _data(item.get("data_cancelamento")),
        "companhias": int((tipos == COMPANHIA).sum()),
        "orgaos_publicos": int((tipos == ORGAO_PUBLICO).sum()),
        "pessoas_juridicas": int((tipos == PESSOA_JURIDICA).sum()),
        "pessoas_ou_desconhecidas": int((tipos == PESSOA_OU_DESCONHECIDA).sum()),
        "advogados": int(item.get("quantidade_de_advogados") or 0),
        "disponivel_em": min(disponibilizada, visto_em)
        if disponibilizada
        else visto_em,
        "visto_em": visto_em,
    }


def ler_consulta(retrato: motor.Retrato) -> list[dict[str, Any]]:
    """As comunicações de uma consulta guardada, com o dia e a origem do retrato."""
    conteudo = json.loads(motor.original(retrato.caminho))
    carimbo = {
        "_visto_em": pd.Timestamp(retrato.dia),
        "origem_sha256": retrato.sha256,
        "origem_coletada_em": pd.Timestamp(retrato.baixado_em).isoformat(),
    }
    return [{**item, **carimbo} for item in conteudo.get("items") or []]


def sem_repetidas(itens: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Uma vez cada comunicação (pelo `hash`), com o que a consulta mais recente disse."""
    ultima: dict[str, dict[str, Any]] = {}
    for item in sorted(itens, key=lambda i: i["_visto_em"]):
        ultima[str(item.get("hash") or item.get("id"))] = item
    return list(ultima.values())


def tabelas(
    itens: Iterable[dict[str, Any]], razoes: Mapping[str, tuple[str, str] | None]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """As comunicações e as partes, e quantas saíram por cada motivo."""
    contagem = dict.fromkeys(
        ("lidas", "do_trabalho", "numero_invalido", "sem_companhia", "homonimos"), 0
    )
    comunicacoes: list[dict[str, Any]] = []
    linhas_das_partes: list[dict[str, Any]] = []
    for item in sem_repetidas(itens):
        contagem["lidas"] += 1
        if djen.da_justica_do_trabalho(item):
            contagem["do_trabalho"] += 1
            continue
        try:
            numero = numero_cnj.decodificar(str(item.get("numero_processo") or ""))
        except numero_cnj.NumeroInvalido:
            contagem["numero_invalido"] += 1
            continue
        partes = _partes(item, razoes)
        contagem["homonimos"] += sum(
            1
            for d in item.get("destinatarios") or []
            if razoes.get(normalizar_nome(d.get("nome")), ()) is None
        )
        if not any(p["tipo_parte"] == COMPANHIA for p in partes):
            contagem["sem_companhia"] += 1
            continue
        linha = _comunicacao(item, numero, partes, item["_visto_em"])
        linhagem = {c: item[c] for c in ("origem_sha256", "origem_coletada_em")}
        comunicacoes.append({**linha, **linhagem})
        comuns = {
            c: linha[c]
            for c in ("id_na_fonte", "numero_processo", "disponivel_em", "visto_em")
        }
        linhas_das_partes.extend(
            {**comuns, **p, **linhagem}
            for p in partes
            if p["tipo_parte"] in (COMPANHIA, ORGAO_PUBLICO)
        )
    da_comunicacao = pd.DataFrame(
        comunicacoes, columns=[*COLUNAS_DAS_COMUNICACOES, *LINHAGEM[:2]]
    )
    das_partes = pd.DataFrame(
        linhas_das_partes, columns=[*COLUNAS_DAS_PARTES, *LINHAGEM[:2]]
    ).drop_duplicates()
    return da_comunicacao, das_partes, contagem


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
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    cadastro: pd.DataFrame | None = None,
    refazer: bool = False,
) -> dict[str, int]:
    """`<pasta>/processos_comunicacoes/djen.parquet` e `<pasta>/processos_partes/djen.parquet`.

    Vazio se nenhuma consulta foi guardada; `JA_MONTADO` se nada mudou desde a última montagem
    (`refazer` relê mesmo assim). `cadastro`: o da CVM (`base/cadastro.py`); sem ele, o do acervo.
    """
    achados = motor.retratos(conexao, djen.ID)
    if not achados:
        return {}
    origens = [{"url": r.url, "sha256": r.sha256} for r in achados]
    if cadastro is None:
        do_acervo = cadastro_do_acervo(conexao)
        if do_acervo is None:
            raise ValueError(
                "sem o cadastro da CVM no acervo não há como ligar as partes ao CNPJ"
            )
        cadastro, origem_do_cadastro = do_acervo
        origens.append(origem_do_cadastro)
    destinos = {
        TABELA_DAS_COMUNICACOES: pasta / TABELA_DAS_COMUNICACOES / "djen",
        TABELA_DAS_PARTES: pasta / TABELA_DAS_PARTES / "djen",
    }
    if not refazer and all(origens_gravadas(d) == origens for d in destinos.values()):
        return JA_MONTADO
    itens = [item for retrato in achados for item in ler_consulta(retrato)]
    comunicacoes, partes, contagem = tabelas(itens, razoes_sociais(cadastro))
    for nome, tabela, ordem in (
        (TABELA_DAS_COMUNICACOES, comunicacoes, ORDEM_DAS_COMUNICACOES),
        (TABELA_DAS_PARTES, partes, ORDEM_DAS_PARTES),
    ):
        gravar_se_mudou(
            _para_gravar(tabela, ordem, agora),
            destinos[nome],
            origens,
            ordem,
            carimbos=LINHAGEM,
        )
    return {
        **contagem,
        "consultas": len(achados),
        "comunicacoes": len(comunicacoes),
        "partes": len(partes),
    }
