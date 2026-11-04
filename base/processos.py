"""Processos judiciais por CNPJ (plano de 03/11/2026, PRs 1, 1b e 1c; ADR 0121): as comunicações do DJEN
que o arquivista guardou (`base/arquivo/djen.py`) nas tabelas `processos_comunicacoes` (uma linha por
comunicação), `processos_partes` (as companhias abertas e os órgãos públicos de cada uma) e `processos`
(uma linha por processo, com a classe pela TPU do CNJ, `base/tpu.py`).

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
- **Achada pelo número** (`achada_por`, o segundo passo, `djen-processos`): a comunicação do processo
  que não intima a companhia fica quando outra comunicação do mesmo processo já a liga a uma companhia.
  Ela só vale (`disponivel_em`) a partir dessa ligação: antes, nada público dizia que o processo era de
  uma companhia. O dia em que saiu no DJEN fica em `disponibilizada_em`.
- **A tabela `processos`** guarda só o que a primeira comunicação diz (tribunal, órgão, classe) e o
  dia da ligação: o que muda com o tempo (a classe que vira cumprimento de sentença, a última
  comunicação) se lê nas comunicações.
- **Citados nas notas da DFP** (`processos_nas_notas`, PR 1c): o número de processo que a própria
  companhia escreveu nas notas explicativas (`notas_dfp`), conferido pelo dígito, vale a partir da
  entrega daquela versão da DFP. Numa amostra de 29 DFPs de 2025, 9 citavam números (37 no total): é o
  processo que a companhia achou grande o bastante para contar. Número da Justiça do Trabalho fica de
  fora também aqui.
- **Contagens** (`contagens`): por companhia e por ano da ligação, sem olhar o futuro, para a ficha.

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

from base import conferencia_processos, numero_cnj, porta, processos_teor, tpu
from base import retratos as motor
from base.arquivo import djen
from base.cadastro import cadastro_do_acervo
from base.cnpj import normalizar_cnpj
from base.parquet import (
    LINHAGEM,
    arquivos_atuais,
    gravar_se_mudou,
    origem_de_tabela,
    origens_gravadas,
)
from src.versao_do_codigo import versao_do_codigo

TABELA_DAS_COMUNICACOES = "processos_comunicacoes"
TABELA_DAS_PARTES = "processos_partes"
TABELA_DOS_PROCESSOS = "processos"
TABELA_DAS_CITACOES = "processos_nas_notas"
TABELA_DAS_NOTAS = "notas_dfp"
ACHADA_PELO_NOME = "nome"
ACHADA_PELO_NUMERO = "numero"
SEPARADOR_DO_CAMINHO = " > "
JA_MONTADO = {"ja_montado": 1}

COMPANHIA = "companhia"
ORGAO_PUBLICO = "orgao_publico"
PESSOA_JURIDICA = "pessoa_juridica"
PESSOA_OU_DESCONHECIDA = "pessoa_ou_desconhecida"
POLOS = {"A": "ativo", "P": "passivo"}
OUTRO_POLO = "outro"

# o número como o PDF entrega: com a máscara (às vezes quebrada por espaço ou linha) ou só os algarismos
_NUMERO_COM_MASCARA = re.compile(
    r"(?<!\d)\d{7}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4}(?!\d)"
)
_NUMERO_SEM_MASCARA = re.compile(r"(?<!\d)\d{20}(?!\d)")
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
    r"^(MUNICIPIO|PREFEITURA|ESTADO D[OAE]|DISTRITO FEDERAL|UNIAO\b|MINISTERIO PUBLICO|"
    # só a Fazenda pública: "FAZENDA BOA VISTA" é imóvel rural, às vezes de pessoa física
    r"FAZENDA (NACIONAL|PUBLICA|DO ESTADO|DO MUNICIPIO|ESTADUAL|MUNICIPAL)\b|"
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
    "tipo_de_ato",
    "resultado",
    "resultado_trecho",
    "valor_citado",
    "teor_conferido_em",
    "achada_por",
    "disponibilizada_em",
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
COLUNAS_DOS_PROCESSOS = [
    "numero_processo",
    "ano_do_processo",
    "justica",
    "tribunal",
    "orgao",
    "classe_codigo",
    "classe",
    "classe_tpu",
    "classe_caminho",
    "ramo",
    "primeira_comunicacao",
    "disponivel_em",
    "visto_em",
]
COLUNAS_DAS_CITACOES = [
    "numero_processo",
    "ano_do_processo",
    "justica",
    "cnpj",
    "empresa",
    "referencia",
    "versao",
    "pagina",
    "link",
    "disponivel_em",
    "origem_sha256",
    "origem_coletada_em",
]
ORDEM_DAS_COMUNICACOES = ["disponivel_em", "id_na_fonte"]
ORDEM_DAS_CITACOES = [
    "disponivel_em",
    "cnpj",
    "referencia",
    "versao",
    "pagina",
    "numero_processo",
]
ORDEM_DOS_PROCESSOS = ["disponivel_em", "numero_processo"]
ORDEM_DAS_PARTES = [
    "disponivel_em",
    "id_na_fonte",
    "polo",
    "parte",
]
DATAS = [
    "referencia",
    "cancelada_em",
    "teor_conferido_em",
    "disponibilizada_em",
    "primeira_comunicacao",
    "disponivel_em",
    "visto_em",
]


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
    leitura = processos_teor.ler(item)
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
        # o teor lido pela regra; `montar` só deixa o que a conferência aprovou
        "tipo_de_ato": leitura.tipo_de_ato,
        "resultado": leitura.resultado,
        "resultado_trecho": leitura.resultado_trecho,
        "valor_citado": leitura.valor_citado,
        "teor_conferido_em": None,
        "achada_por": item.get("_achada_por", ACHADA_PELO_NOME),
        "disponibilizada_em": disponibilizada,
        "disponivel_em": min(disponibilizada, visto_em)
        if disponibilizada
        else visto_em,
        "visto_em": visto_em,
    }


def ler_consulta(
    retrato: motor.Retrato, achada_por: str = ACHADA_PELO_NOME
) -> list[dict[str, Any]]:
    """As comunicações de uma consulta guardada, com o dia, a origem do retrato e se a consulta foi
    pelo nome ou pelo número."""
    conteudo = json.loads(motor.original(retrato.caminho))
    carimbo = {
        "_visto_em": pd.Timestamp(retrato.dia),
        "_achada_por": achada_por,
        "origem_sha256": retrato.sha256,
        "origem_coletada_em": pd.Timestamp(retrato.baixado_em).isoformat(),
    }
    return [{**item, **carimbo} for item in conteudo.get("items") or []]


def sem_repetidas(itens: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Uma vez cada comunicação (pelo `hash`), com o que a consulta mais recente disse; achada pelo
    nome se alguma consulta pelo nome a achou."""
    ultima: dict[str, dict[str, Any]] = {}
    pelo_nome: set[str] = set()
    for item in sorted(itens, key=lambda i: i["_visto_em"]):
        chave = str(item.get("hash") or item.get("id"))
        ultima[chave] = item
        if item.get("_achada_por", ACHADA_PELO_NOME) == ACHADA_PELO_NOME:
            pelo_nome.add(chave)
    return [
        {**item, "_achada_por": ACHADA_PELO_NOME} if chave in pelo_nome else item
        for chave, item in ultima.items()
    ]


def tabelas(
    itens: Iterable[dict[str, Any]], razoes: Mapping[str, tuple[str, str] | None]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """As comunicações e as partes, e quantas saíram por cada motivo."""
    contagem = dict.fromkeys(
        (
            "lidas",
            "do_trabalho",
            "numero_invalido",
            "sem_companhia",
            "ligadas_pelo_processo",
            "homonimos",
        ),
        0,
    )
    validas: list[tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
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
        linha = _comunicacao(item, numero, partes, item["_visto_em"])
        linhagem = {c: item[c] for c in ("origem_sha256", "origem_coletada_em")}
        validas.append((linha, partes, linhagem))
    ligacao = _dia_da_ligacao(linha for linha, _, _ in validas)
    comunicacoes: list[dict[str, Any]] = []
    linhas_das_partes: list[dict[str, Any]] = []
    for linha, partes, linhagem in validas:
        if not linha["companhias"]:
            ligado_em = ligacao.get(linha["numero_processo"])
            if ligado_em is None:
                contagem["sem_companhia"] += 1
                continue
            contagem["ligadas_pelo_processo"] += 1
            linha["disponivel_em"] = max(linha["disponivel_em"], ligado_em)
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


def _dia_da_ligacao(linhas: Iterable[dict[str, Any]]) -> dict[str, pd.Timestamp]:
    """Cada processo -> o primeiro dia em que uma comunicação dele saiu com uma companhia entre as
    partes."""
    ligacao: dict[str, pd.Timestamp] = {}
    for linha in linhas:
        if linha["companhias"]:
            numero = linha["numero_processo"]
            ligacao[numero] = min(
                linha["disponivel_em"], ligacao.get(numero, linha["disponivel_em"])
            )
    return ligacao


def _classe_pela_tpu(
    codigo: object, classes: Mapping[int, tpu.Classe] | None
) -> dict[str, str | None]:
    numero = str(codigo or "").strip()
    if classes is None or not numero.isdigit() or int(numero) not in classes:
        return {"classe_tpu": None, "classe_caminho": None, "ramo": None}
    return {
        "classe_tpu": classes[int(numero)].nome,
        "classe_caminho": SEPARADOR_DO_CAMINHO.join(tpu.caminho(int(numero), classes)),
        "ramo": tpu.ramo(int(numero), classes),
    }


def tabela_dos_processos(
    comunicacoes: pd.DataFrame, classes: Mapping[int, tpu.Classe] | None
) -> pd.DataFrame:
    """Uma linha por processo: o que a primeira comunicação dele diz, e desde quando vale (a primeira
    comunicação com uma companhia entre as partes). `classes`: a TPU (`base/tpu.py`); sem ela, a
    classe fica só com o que o DJEN escreve."""
    colunas = [*COLUNAS_DOS_PROCESSOS, *LINHAGEM[:2]]
    if comunicacoes.empty:
        return pd.DataFrame(columns=colunas)
    visto = comunicacoes["visto_em"]
    saiu = comunicacoes["disponibilizada_em"].fillna(visto)
    em_ordem = comunicacoes.assign(
        primeira_comunicacao=saiu.where(saiu <= visto, visto)
    )
    primeiras = (
        em_ordem.sort_values(
            ["primeira_comunicacao", "visto_em", "id_na_fonte"], kind="stable"
        )
        .groupby("numero_processo", sort=False)
        .head(1)
        .drop(columns=["disponivel_em", "visto_em"])
    )
    ligacoes = (
        em_ordem[em_ordem["companhias"] > 0]
        .sort_values(["disponivel_em", "visto_em", "id_na_fonte"], kind="stable")
        .groupby("numero_processo", sort=False)
        .head(1)[["numero_processo", "disponivel_em", "visto_em"]]
    )
    tabela = primeiras.merge(ligacoes, on="numero_processo", how="inner")
    da_tpu = pd.DataFrame(
        [_classe_pela_tpu(codigo, classes) for codigo in tabela["classe_codigo"]],
        columns=["classe_tpu", "classe_caminho", "ramo"],
        index=tabela.index,
    )
    return tabela.assign(**{c: da_tpu[c] for c in da_tpu})[colunas]


# --- os processos citados nas notas da DFP e as contagens (PR 1c) ---------------------------------


def numeros_no_texto(texto: str) -> list[str]:
    """Os números de processo do texto com o dígito certo, com a máscara e sem repetir; sem os da
    Justiça do Trabalho."""
    candidatos = {
        *_NUMERO_COM_MASCARA.findall(texto),
        *_NUMERO_SEM_MASCARA.findall(texto),
    }
    numeros = set()
    for candidato in candidatos:
        try:
            numero = numero_cnj.decodificar(candidato)
        except numero_cnj.NumeroInvalido:
            continue
        if numero.segmento != numero_cnj.JUSTICA_DO_TRABALHO:
            numeros.add(numero.formatado)
    return sorted(numeros)


def tabela_das_citacoes(notas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por número de processo e página das notas da DFP (`notas_dfp`), sem o texto.

    Cada versão da DFP é um documento: a reapresentação cita de novo e vale a partir da própria
    entrega (`disponivel_em` da página)."""
    da_pagina = [c for c in COLUNAS_DAS_CITACOES if c in notas.columns]
    linhas = []
    for pagina in notas.to_dict("records"):
        for formatado in numeros_no_texto(str(pagina.get("texto") or "")):
            numero = numero_cnj.decodificar(formatado)
            linhas.append(
                {c: pagina[c] for c in da_pagina}
                | {
                    "numero_processo": formatado,
                    "ano_do_processo": numero.ano,
                    "justica": numero.nome_do_segmento,
                }
            )
    return (
        pd.DataFrame(linhas, columns=COLUNAS_DAS_CITACOES)
        .sort_values(ORDEM_DAS_CITACOES, kind="stable")
        .reset_index(drop=True)
    )


def contagens(
    partes: pd.DataFrame,
    dos_processos: pd.DataFrame,
    citacoes: pd.DataFrame,
    como_era_em: object,
) -> pd.DataFrame:
    """Por companhia e por ano: quantos processos, em que polo, de que ramo e quantos citados nas
    notas da DFP, só com o que era público em `como_era_em`.

    O processo conta no ano da primeira comunicação que o liga à companhia, com o polo dela nessa
    comunicação; citado é o que a própria companhia citou numa DFP entregue até o dia."""
    dia = pd.Timestamp(como_era_em)
    ramos = sorted(set(tpu.RAMOS.values()))
    contados = [
        "processos",
        "como_autora",
        "como_re",
        *ramos,
        "sem_ramo",
        "citados_na_dfp",
    ]
    da_companhia = partes[
        (partes["tipo_parte"] == COMPANHIA)
        & partes["cnpj"].notna()
        & (pd.to_datetime(partes["disponivel_em"]) <= dia)
    ]
    if da_companhia.empty:
        return pd.DataFrame(columns=["cnpj", "ano", *contados])
    ligacoes = (
        da_companhia.assign(disponivel_em=pd.to_datetime(da_companhia["disponivel_em"]))
        .sort_values("disponivel_em", kind="stable")
        .drop_duplicates(["cnpj", "numero_processo"])
        .merge(
            dos_processos[["numero_processo", "ramo"]], on="numero_processo", how="left"
        )
    )
    citados = citacoes[pd.to_datetime(citacoes["disponivel_em"]) <= dia]
    ja_citados = set(zip(citados["cnpj"], citados["numero_processo"], strict=True))
    ligacoes = ligacoes.assign(
        ano=ligacoes["disponivel_em"].dt.year,
        processos=True,
        como_autora=ligacoes["polo"] == POLOS["A"],
        como_re=ligacoes["polo"] == POLOS["P"],
        **{ramo: ligacoes["ramo"] == ramo for ramo in ramos},
        sem_ramo=ligacoes["ramo"].isna(),
        citados_na_dfp=[
            par in ja_citados
            for par in zip(ligacoes["cnpj"], ligacoes["numero_processo"], strict=True)
        ],
    )
    return ligacoes.groupby(["cnpj", "ano"])[contados].sum().astype(int).reset_index()


def montar_citacoes(pasta: Path, agora: datetime) -> dict[str, int]:
    """`<pasta>/processos_nas_notas/dfp.parquet`, das notas da DFP lidas pela porta, um ano por vez.

    Vazio (nada gravado) se a base ainda não tem `notas_dfp`; `JA_MONTADO` se as notas não mudaram."""
    anos = arquivos_atuais(pasta / TABELA_DAS_NOTAS)
    if not anos:
        return {}
    origens = [origem_de_tabela(ano, pasta) for ano in anos]
    destino = pasta / TABELA_DAS_CITACOES / "dfp"
    if origens_gravadas(destino) == origens:
        return JA_MONTADO
    da_nota = [
        c
        for c in COLUNAS_DAS_CITACOES
        if c not in ("numero_processo", "ano_do_processo", "justica")
    ]
    paginas, por_ano = 0, []
    with porta.abrir(pasta) as base:
        for ano in anos:
            notas = base.ler(
                TABELA_DAS_NOTAS,
                filtros={"ano_do_arquivo": int(ano.stem)},
                colunas=[*da_nota, "texto"],
            )
            paginas += len(notas)
            por_ano.append(tabela_das_citacoes(notas))
    citacoes = pd.concat(por_ano, ignore_index=True)
    gravar_se_mudou(
        _para_gravar(citacoes, ORDEM_DAS_CITACOES, agora),
        destino,
        origens,
        ORDEM_DAS_CITACOES,
        carimbos=LINHAGEM,
    )
    return {
        "paginas": paginas,
        "citacoes": len(citacoes),
        "processos": citacoes["numero_processo"].nunique(),
        "companhias": citacoes["cnpj"].nunique(),
    }


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


def _cadastro_do_acervo(conexao: sa.Connection) -> tuple[pd.DataFrame, dict[str, str]]:
    do_acervo = cadastro_do_acervo(conexao)
    if do_acervo is None:
        raise ValueError(
            "sem o cadastro da CVM no acervo não há como ligar as partes ao CNPJ"
        )
    return do_acervo


def _itens(
    pelo_nome: Iterable[motor.Retrato], pelo_numero: Iterable[motor.Retrato]
) -> list[dict[str, Any]]:
    return [
        *(i for r in pelo_nome for i in ler_consulta(r, ACHADA_PELO_NOME)),
        *(i for r in pelo_numero for i in ler_consulta(r, ACHADA_PELO_NUMERO)),
    ]


def comunicacoes_da_tabela(
    conexao: sa.Connection, cadastro: pd.DataFrame | None = None
) -> dict[str, dict[str, Any]]:
    """As comunicações como o DJEN entregou (com o teor) que entram em `processos_comunicacoes`,
    pelo `id_na_fonte`: de onde a conferência do teor (`base/conferencia_processos.py`) sorteia. Vazio
    se nenhuma consulta pelo nome foi guardada."""
    pelo_nome = motor.retratos(conexao, djen.ID)
    if not pelo_nome:
        return {}
    if cadastro is None:
        cadastro = _cadastro_do_acervo(conexao)[0]
    itens = _itens(pelo_nome, motor.retratos(conexao, djen.ID_DOS_PROCESSOS))
    da_tabela = set(tabelas(itens, razoes_sociais(cadastro))[0]["id_na_fonte"])
    unicas = {str(i.get("hash") or i.get("id")): i for i in sem_repetidas(itens)}
    return {chave: item for chave, item in unicas.items() if chave in da_tabela}


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    cadastro: pd.DataFrame | None = None,
    refazer: bool = False,
) -> dict[str, int]:
    """`processos_comunicacoes`, `processos_partes` e `processos` em `<pasta>/<tabela>/djen.parquet`.

    Lê as consultas pelo nome (`djen-partes`) e pelo número (`djen-processos`). Vazio se nenhuma
    consulta pelo nome foi guardada; `JA_MONTADO` se nada mudou desde a última montagem (`refazer`
    relê mesmo assim). `cadastro`: o da CVM (`base/cadastro.py`); sem ele, o do acervo. A TPU do CNJ
    (`base/tpu.py`) dá a classe e o ramo; sem ela no acervo, os processos ficam sem o ramo.
    """
    pelo_nome = motor.retratos(conexao, djen.ID)
    if not pelo_nome:
        return {}
    pelo_numero = motor.retratos(conexao, djen.ID_DOS_PROCESSOS)
    origens = [{"url": r.url, "sha256": r.sha256} for r in (*pelo_nome, *pelo_numero)]
    if cadastro is None:
        cadastro, origem_do_cadastro = _cadastro_do_acervo(conexao)
        origens.append(origem_do_cadastro)
    origens.extend(conferencia_processos.origens(pasta))
    da_tpu = tpu.classes_do_acervo(conexao)
    classes = None
    if da_tpu is not None:
        classes, origem_da_tpu = da_tpu
        origens.append(origem_da_tpu)
    destinos = {
        nome: pasta / nome / "djen"
        for nome in (TABELA_DAS_COMUNICACOES, TABELA_DAS_PARTES, TABELA_DOS_PROCESSOS)
    }
    if not refazer and all(origens_gravadas(d) == origens for d in destinos.values()):
        return JA_MONTADO
    itens = _itens(pelo_nome, pelo_numero)
    comunicacoes, partes, contagem = tabelas(itens, razoes_sociais(cadastro))
    comunicacoes = conferencia_processos.aplicar(
        comunicacoes, conferencia_processos.vigente(pasta)
    )
    dos_processos = tabela_dos_processos(comunicacoes, classes)
    for nome, tabela, ordem in (
        (TABELA_DAS_COMUNICACOES, comunicacoes, ORDEM_DAS_COMUNICACOES),
        (TABELA_DAS_PARTES, partes, ORDEM_DAS_PARTES),
        (TABELA_DOS_PROCESSOS, dos_processos, ORDEM_DOS_PROCESSOS),
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
        "consultas": len(pelo_nome) + len(pelo_numero),
        "comunicacoes": len(comunicacoes),
        "partes": len(partes),
        "processos": len(dos_processos),
        "sem_ramo": int(dos_processos["ramo"].isna().sum()),
    }
