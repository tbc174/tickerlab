"""Negócios do pregão da B3: barras de 1 minuto e o selo por ativo e por dia (ADR 0073; plano
`planos/2026-10-14-intradiarios-gratis-com-confianca.md`, PR 2). Só pesquisa (ADR 0019): nada daqui
vai para o app, o banco do app ou a exportação.

O arquivo grátis (`arquivos.b3.com.br/rapinegocios/tickercsv/AAAA-MM-DD`, guardado pelo arquivista
como fonte `b3-negocios`) tem ~14 milhões de linhas e ~1 GB aberto: é lido em pedaços. O que se
mediu em 14/10/2026, contra os boletins oficiais dos 20 pregões no ar:

- **Boletim de referência: o PR (BVBG.086)**, para todos os instrumentos (à vista, termo, opções e
  futuros). Nas sextas de vencimento de opções (18/09, 25/09 e 02/10) o COTAHIST do dia tem menos
  negócios que o arquivo em ~11% das ações, mas o PR bate com o arquivo: quem fica para trás é o
  COTAHIST (registros tardios, às 19h, não entram nele). O COTAHIST serve para dizer se houve pregão
  e quais instrumentos são do mercado à vista (tipo de mercado 010 e 020).
- **Pregão do negócio: `DataNegocio`**, não a data do arquivo. Futuros negociados à noite (agrícolas
  e cripto, depois das 17h) vêm no arquivo do dia com `DataNegocio` do pregão seguinte, e o boletim
  conta esses negócios no pregão seguinte. As barras de um pregão juntam as linhas dele no próprio
  arquivo e no arquivo do pregão anterior. O minuto da barra é a hora de verdade (sexta às 17h05).
- O PR tem várias linhas para o mesmo código no termo (uma por vencimento) e em alguns futuros:
  negócios e volume somados, máxima e mínima de todas; abertura e fechamento ficam sem conferir.
- Diferença que o estudo não explicou vira `incompleto`, nunca tolerância: as estratégias de dois
  vencimentos (DI1F27F28) têm o volume do boletim em outra unidade (as pernas) e saem `incompleto`
  no volume todo dia.
"""

import io
import json
import re
import zipfile
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

from src import acervo
from src.barras_intradiarias import (
    FUSO_DA_B3,
    barras_parciais_b3,
    juntar_barras_b3,
    remover_cancelados,
)

# barras e selo ficam no acervo, ao lado do original: `<acervo>/intradiario/b3/{barras,selo}/`
PASTA_NO_ACERVO = Path("intradiario") / "b3"
# ~100 MB na memória por pedaço (o servidor de casa tem 8 GB)
LINHAS_POR_PEDACO = 1_000_000
FINAL_DO_ARQUIVO_DE_NEGOCIOS = "_NEGOCIOSAVISTA.txt"
COLUNAS_LIDAS = {
    "DataReferencia": "str",
    "CodigoInstrumento": "str",
    "AcaoAtualizacao": "int8",
    "PrecoNegocio": "float64",
    "QuantidadeNegociada": "int64",
    "HoraFechamento": "int64",  # HHMMSSmmm; às 9h vem com 8 algarismos
    "CodigoIdentificadorNegocio": "int64",
    "TipoSessaoPregao": "int8",
    "DataNegocio": "str",
}
ACAO_CANCELAMENTO = 2
COLUNAS_DOS_NEGOCIOS = [
    "instante",
    "pregao",
    "simbolo",
    "preco",
    "quantidade",
    "sessao",
    "cancelado",
    "identificador",
]

# sobe a cada mudança na regra das barras ou do selo: o script diário refaz os pregões já feitos
# (2: negócios inseridos depois herdam o instante do negócio de dezena, 14/10/2026)
VERSAO_DA_REGRA = 2
SELO_COMPLETO = "completo"
SELO_INCOMPLETO = "incompleto"
SELO_AUSENTE = "ausente"
SELO_SEM_BOLETIM = "sem_boletim"
CAMPOS_CONFERIDOS = ["abertura", "maxima", "minima", "fechamento", "volume", "negocios"]
CASAS_DOS_PRECOS = (
    6  # só para o mesmo número em float e em texto ser igual; não é tolerância
)

# boletim PR (BVBG.086): mensagem BVMF.217, um PricRpt por instrumento
ESPACO_DO_PR = "{urn:bvmf.217.01.xsd}"
CAMPOS_DO_PR = {
    "FrstPric": "abertura",
    "MaxPric": "maxima",
    "MinPric": "minima",
    "LastPric": "fechamento",
    "FinInstrmQty": "volume",
}


def _hora_em_tempo(hora: pd.Series) -> pd.Series:
    milissegundos = (
        (hora // 10_000_000) * 3_600_000
        + (hora // 100_000 % 100) * 60_000
        + (hora // 1000 % 100) * 1000
        + hora % 1000
    )
    return pd.to_timedelta(milissegundos, unit="ms")


def _nome_do_arquivo_de_negocios(arquivo: zipfile.ZipFile) -> str:
    nomes = [n for n in arquivo.namelist() if n.endswith(FINAL_DO_ARQUIVO_DE_NEGOCIOS)]
    if len(nomes) != 1:
        raise ValueError(
            f"o zip devia ter um arquivo *{FINAL_DO_ARQUIVO_DE_NEGOCIOS}; tem {arquivo.namelist()}"
        )
    return nomes[0]


def _ler_em_pedacos(
    caminho_zip: Path, colunas: dict[str, str], linhas_por_pedaco: int
) -> Iterator[pd.DataFrame]:
    with zipfile.ZipFile(caminho_zip) as arquivo:
        nome = _nome_do_arquivo_de_negocios(arquivo)
        with arquivo.open(nome) as texto:
            yield from pd.read_csv(
                texto,
                sep=";",
                decimal=",",
                usecols=list(colunas),
                dtype=colunas,  # type: ignore[arg-type]
                chunksize=linhas_por_pedaco,
            )


def ler_negocios(
    caminho_zip: Path, linhas_por_pedaco: int = LINHAS_POR_PEDACO
) -> Iterator[pd.DataFrame]:
    """Os negócios do arquivo da B3, em pedaços de `linhas_por_pedaco` linhas, na ordem do arquivo.

    Colunas: instante (com o fuso de São Paulo; a data é a do arquivo, a hora de verdade), pregao
    (`DataNegocio`, à meia-noite), simbolo, preco, quantidade, sessao (1 regular, 6 after),
    cancelado e identificador (por instrumento).
    """
    for pedaco in _ler_em_pedacos(caminho_zip, COLUNAS_LIDAS, linhas_por_pedaco):
        yield _negocios_do_pedaco(pedaco)


def _negocios_do_pedaco(pedaco: pd.DataFrame) -> pd.DataFrame:
    dia = pd.to_datetime(pedaco["DataReferencia"], format="%Y-%m-%d")
    instante = (dia + _hora_em_tempo(pedaco["HoraFechamento"])).dt.tz_localize(
        FUSO_DA_B3
    )
    return pd.DataFrame(
        {
            "instante": instante,
            "pregao": pd.to_datetime(pedaco["DataNegocio"], format="%Y-%m-%d"),
            "simbolo": pedaco["CodigoInstrumento"],
            "preco": pedaco["PrecoNegocio"],
            "quantidade": pedaco["QuantidadeNegociada"],
            "sessao": pedaco["TipoSessaoPregao"],
            "cancelado": pedaco["AcaoAtualizacao"] == ACAO_CANCELAMENTO,
            "identificador": pedaco["CodigoIdentificadorNegocio"],
        }
    )[COLUNAS_DOS_NEGOCIOS]


COLUNAS_DOS_AJUSTES = {
    nome: COLUNAS_LIDAS[nome]
    for nome in [
        "CodigoInstrumento",
        "AcaoAtualizacao",
        "CodigoIdentificadorNegocio",
        "DataNegocio",
    ]
}


# Identificadores andam de 10 em 10 por instrumento. Final diferente de 0 é negócio inserido depois:
# correção (PETR4 em 25/09/2026: o 346910 cancelado às 17h06 e o 346911 lançado no lugar, com a
# quantidade certa) ou registro tardio (PETR4 em 18/09/2026: o 312415 às 19h04, entre dois negócios
# do leilão das 17h10). Ele vem com a hora do lançamento, mas ocupa o lugar do negócio de dezena
# logo antes dele: herda o instante dele (senão viraria o "último negócio" e mudaria o fechamento).
PASSO_DO_IDENTIFICADOR = 10


def _ajustes(
    caminho_zip: Path, pregao: date, linhas_por_pedaco: int
) -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
    """Os pares (símbolo, identificador) cancelados no pregão e os negócios de dezena que têm um
    inserido depois deles; lê só 4 colunas (mais rápido)."""
    cancelados: set[tuple[str, int]] = set()
    referencias: set[tuple[str, int]] = set()
    for pedaco in _ler_em_pedacos(caminho_zip, COLUNAS_DOS_AJUSTES, linhas_por_pedaco):
        do_pregao = pedaco[pedaco["DataNegocio"] == pregao.isoformat()]
        simbolo = do_pregao["CodigoInstrumento"]
        identificador = do_pregao["CodigoIdentificadorNegocio"]
        cancelamento = do_pregao["AcaoAtualizacao"] == ACAO_CANCELAMENTO
        cancelados |= set(
            zip(simbolo[cancelamento], identificador[cancelamento], strict=True)
        )
        resto = identificador % PASSO_DO_IDENTIFICADOR
        inserido = (resto != 0) & ~cancelamento
        referencias |= set(
            zip(
                simbolo[inserido],
                (identificador - resto)[inserido],
                strict=True,
            )
        )
    return cancelados, referencias


def _chaves(negocios: pd.DataFrame) -> pd.MultiIndex:
    return pd.MultiIndex.from_arrays([negocios["simbolo"], negocios["identificador"]])


def _no_lugar_da_referencia(
    inseridos: pd.DataFrame, instantes: dict[tuple[str, int], pd.Timestamp]
) -> pd.DataFrame:
    """Os inseridos com o instante do negócio de dezena antes deles (se ele está no arquivo)."""
    if inseridos.empty:
        return inseridos
    referencia = zip(
        inseridos["simbolo"],
        inseridos["identificador"]
        - inseridos["identificador"] % PASSO_DO_IDENTIFICADOR,
        strict=True,
    )
    herdado = [instantes.get(chave) for chave in referencia]
    instante = [
        proprio if novo is None else novo
        for proprio, novo in zip(inseridos["instante"], herdado, strict=True)
    ]
    return inseridos.assign(
        instante=pd.Series(
            instante, index=inseridos.index, dtype=inseridos["instante"].dtype
        )
    )


def barras_do_pregao(
    pregao: date,
    arquivos: Sequence[Path],
    linhas_por_pedaco: int = LINHAS_POR_PEDACO,
) -> pd.DataFrame:
    """Barras de 1 minuto de todos os instrumentos de um pregão.

    `arquivos`: o zip do pregão e, se houver, o do pregão anterior (que traz os negócios da noite
    anterior com `DataNegocio` deste pregão). Duas leituras: a primeira só junta os cancelamentos
    e os negócios inseridos depois (poucos, mas longe do negócio a que se referem), a segunda monta
    as barras em pedaços; os inseridos ficam para o fim, com o instante herdado.
    """
    cancelados: set[tuple[str, int]] = set()
    referencias: set[tuple[str, int]] = set()
    for caminho in arquivos:
        do_arquivo, com_insercao = _ajustes(caminho, pregao, linhas_por_pedaco)
        cancelados |= do_arquivo
        referencias |= com_insercao
    dia = pd.Timestamp(pregao)
    partes, inseridos = [], []
    instantes: dict[tuple[str, int], pd.Timestamp] = {}
    for caminho in arquivos:
        for pedaco in ler_negocios(caminho, linhas_por_pedaco):
            do_pregao = pedaco[pedaco["pregao"] == dia]
            inserido = do_pregao["identificador"] % PASSO_DO_IDENTIFICADOR != 0
            if referencias:
                e_referencia = (
                    _chaves(do_pregao).isin(list(referencias)) & ~do_pregao["cancelado"]
                )
                for linha in do_pregao[e_referencia].itertuples():
                    instantes[(linha.simbolo, linha.identificador)] = linha.instante
            inseridos.append(do_pregao[inserido])
            normais = remover_cancelados(do_pregao[~inserido], cancelados)
            partes.append(barras_parciais_b3(normais))
    if inseridos:
        juntos = _no_lugar_da_referencia(pd.concat(inseridos), instantes)
        partes.append(barras_parciais_b3(remover_cancelados(juntos, cancelados)))
    return juntar_barras_b3(partes)


def _ultima_versao(interno: zipfile.ZipFile) -> str:
    """A versão mais nova do boletim (a B3 republica de noite: 18h39, 19h14, 19h25, 21h00)."""
    return max(
        interno.infolist(), key=lambda info: (info.date_time, info.filename)
    ).filename


def _relatorio_do_pr(elemento: ET.Element) -> dict[str, object] | None:
    negocios = elemento.findtext(f"{ESPACO_DO_PR}TradDtls/{ESPACO_DO_PR}TradQty")
    if not negocios:
        return None  # instrumento sem negócio no dia
    linha: dict[str, object] = {
        "simbolo": elemento.findtext(f"{ESPACO_DO_PR}SctyId/{ESPACO_DO_PR}TckrSymb"),
        "negocios": int(negocios),
    }
    atributos = elemento.find(f"{ESPACO_DO_PR}FinInstrmAttrbts")
    for filho in atributos if atributos is not None else []:
        campo = CAMPOS_DO_PR.get(filho.tag.removeprefix(ESPACO_DO_PR))
        if campo and filho.text:
            linha[campo] = float(filho.text)
    return linha


def ler_boletim_pr(caminho_zip: Path) -> pd.DataFrame:
    """O boletim PR do dia (BVBG.086, um zip dentro de outro), um instrumento negociado por linha.

    Código com várias linhas (termo, por vencimento): negócios e volume somados, máxima e mínima de
    todas, abertura e fechamento vazios (não dá para saber qual linha veio antes).
    """
    with zipfile.ZipFile(caminho_zip) as externo:
        conteudo = externo.read(externo.namelist()[0])
    linhas = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as interno:
        for _, elemento in ET.iterparse(interno.open(_ultima_versao(interno))):
            if elemento.tag == f"{ESPACO_DO_PR}PricRpt":
                linha = _relatorio_do_pr(elemento)
                if linha is not None:
                    linhas.append(linha)
                elemento.clear()
    return _um_por_codigo(pd.DataFrame(linhas, columns=["simbolo", *CAMPOS_CONFERIDOS]))


def _um_por_codigo(tabela: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por código. Código com várias linhas no boletim (termo, uma por vencimento):
    negócios e volume somados, máxima e mínima de todas, abertura e fechamento vazios (não dá para
    saber qual linha veio antes). Volume em reais também somado; outras colunas: a da primeira linha."""
    grupos = tabela.groupby("simbolo", sort=True)
    extras = {
        c: (c, "sum" if c == "volume_financeiro" else "first")
        for c in tabela.columns
        if c not in ["simbolo", *CAMPOS_CONFERIDOS]
    }
    boletim = grupos.agg(
        abertura=("abertura", "first"),
        maxima=("maxima", "max"),
        minima=("minima", "min"),
        fechamento=("fechamento", "first"),
        volume=("volume", "sum"),
        negocios=("negocios", "sum"),
        **extras,
    )
    varias = grupos.size() > 1
    boletim.loc[varias, ["abertura", "fechamento"]] = float("nan")
    boletim.index.name = None
    return boletim


def totais_do_dia(barras: pd.DataFrame) -> pd.DataFrame:
    """Abertura, máxima, mínima e fechamento do pregão regular; volume e negócios com o after."""
    ordenadas = barras.sort_values(["simbolo", "minuto"])
    grupos = ordenadas.groupby("simbolo", sort=True)
    totais = grupos.agg(
        abertura=("abertura", "first"),  # first pula o minuto só de after (sem preço)
        maxima=("maxima", "max"),
        minima=("minima", "min"),
        fechamento=("fechamento", "last"),
        volume=("volume", "sum"),
        negocios=("negocios", "sum"),
        volume_after=("volume_after", "sum"),
        negocios_after=("negocios_after", "sum"),
    )
    totais["volume"] += totais.pop("volume_after")
    totais["negocios"] += totais.pop("negocios_after")
    return totais


def _iguais(arquivo: pd.Series, boletim: pd.Series) -> pd.Series:
    """Igual, ou o boletim não tem o campo (não conferido)."""
    return (
        arquivo.round(CASAS_DOS_PRECOS) == boletim.round(CASAS_DOS_PRECOS)
    ) | boletim.isna()


def conferir_dia(barras: pd.DataFrame, boletim: pd.DataFrame | None) -> pd.DataFrame:
    """Uma linha por instrumento (do arquivo ou do boletim) com o selo e os dois lados de cada campo.

    Selos: `completo` (todo campo que o boletim tem bate), `incompleto` (algum não bate;
    `campos_diferentes` diz quais), `ausente` (negociado no boletim, fora do arquivo) e
    `sem_boletim` (no arquivo e não no boletim, ou dia sem boletim).
    """
    arquivo = totais_do_dia(barras)
    oficial = (
        boletim
        if boletim is not None
        else pd.DataFrame(columns=CAMPOS_CONFERIDOS, dtype="float64")
    )
    juntos = arquivo[CAMPOS_CONFERIDOS].join(
        oficial[CAMPOS_CONFERIDOS].astype("float64"),
        how="outer",
        lsuffix="_no_arquivo",
        rsuffix="_no_boletim",
    )
    no_arquivo = juntos.index.isin(arquivo.index)
    no_boletim = juntos.index.isin(oficial.index)
    diferentes = pd.DataFrame(
        {
            campo: ~_iguais(
                juntos[f"{campo}_no_arquivo"], juntos[f"{campo}_no_boletim"]
            )
            for campo in CAMPOS_CONFERIDOS
        },
        index=juntos.index,
    )
    juntos["campos_diferentes"] = (
        diferentes.apply(lambda linha: ",".join(linha.index[linha]), axis=1)
        if len(juntos)
        else pd.Series(dtype="str")
    )
    juntos["selo"] = SELO_COMPLETO
    juntos.loc[juntos["campos_diferentes"] != "", "selo"] = SELO_INCOMPLETO
    juntos.loc[no_boletim & ~no_arquivo, "selo"] = SELO_AUSENTE
    juntos.loc[no_arquivo & ~no_boletim, "selo"] = SELO_SEM_BOLETIM
    juntos.loc[juntos["selo"] != SELO_INCOMPLETO, "campos_diferentes"] = ""
    return juntos.rename_axis("simbolo").reset_index()


def selo_do_dia(conferencia: pd.DataFrame, a_vista: set[str]) -> str:
    """`completo` se todo instrumento do mercado à vista negociado no dia (lista do COTAHIST) é
    `completo`; `incompleto` se algum não é; `sem_boletim` se falta o PR ou o COTAHIST."""
    if not a_vista or (conferencia["selo"] == SELO_SEM_BOLETIM).all():
        return SELO_SEM_BOLETIM
    do_a_vista = conferencia[conferencia["simbolo"].isin(list(a_vista))]
    if do_a_vista.empty or (do_a_vista["selo"] != SELO_COMPLETO).any():
        return SELO_INCOMPLETO
    return SELO_COMPLETO


def caminho_do_resumo(pregao: date, pasta_do_acervo: Path) -> Path:
    """O resumo do selo do pregão (JSON): selo do dia e o SHA-256 de cada arquivo lido."""
    return pasta_do_acervo / PASTA_NO_ACERVO / "selo" / f"{pregao.isoformat()}.json"


def resumo_guardado(pregao: date) -> dict | None:
    """O resumo do selo do pregão no acervo, ou None (ainda não processado ou acervo desligado)."""
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        return None
    caminho = caminho_do_resumo(pregao, pasta)
    if not caminho.is_file():
        return None
    return json.loads(caminho.read_text("utf-8"))


# COTAHIST: registro "01" de 245 posições; preços em centavos
TIPO_DE_REGISTRO_DE_COTACAO = "01"
MERCADOS_A_VISTA = {"010", "020"}  # lote padrão e fracionário
CENTAVOS = 100


def _registro_do_cotahist(linha: str) -> dict[str, object]:
    return {
        "simbolo": linha[12:24].strip(),
        "mercado": linha[24:27],
        "abertura": int(linha[56:69]) / CENTAVOS,
        "maxima": int(linha[69:82]) / CENTAVOS,
        "minima": int(linha[82:95]) / CENTAVOS,
        "fechamento": int(linha[108:121]) / CENTAVOS,
        "negocios": int(linha[147:152]),
        "volume": int(linha[152:170]),  # quantidade de papéis (QUATOT), como no PR
        "volume_financeiro": int(linha[170:188]) / CENTAVOS,  # em reais (VOLTOT)
    }


def ler_cotahist(caminho_zip: Path) -> pd.DataFrame:
    """O COTAHIST do dia, um código por linha, com os campos do PR e o tipo de `mercado`."""
    with zipfile.ZipFile(caminho_zip) as arquivo:
        texto = arquivo.read(arquivo.namelist()[0]).decode("latin-1")
    registros = [
        _registro_do_cotahist(linha)
        for linha in texto.splitlines()
        if linha[:2] == TIPO_DE_REGISTRO_DE_COTACAO
    ]
    return _um_por_codigo(
        pd.DataFrame(
            registros,
            columns=["simbolo", "mercado", *CAMPOS_CONFERIDOS, "volume_financeiro"],
        )
    )


def a_vista(cotahist: pd.DataFrame) -> set[str]:
    """Os códigos do mercado à vista (lote padrão e fracionário) do COTAHIST."""
    return set(cotahist.index[cotahist["mercado"].isin(list(MERCADOS_A_VISTA))])


def boletim_do_dia(
    pr: pd.DataFrame | None, cotahist: pd.DataFrame | None
) -> pd.DataFrame | None:
    """O PR, completado pelo COTAHIST nos códigos que faltam nele (KNUQ12 em 17/09/2026)."""
    partes = [
        b.reindex(columns=CAMPOS_CONFERIDOS) for b in (pr, cotahist) if b is not None
    ]
    if not partes:
        return None
    juntos = pd.concat(partes)
    return juntos[~juntos.index.duplicated(keep="first")].sort_index()


_DATA_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})$")
_DATA_DO_PR = re.compile(r"PR(\d{6})\.zip$")
_DATA_DO_COTAHIST = re.compile(r"COTAHIST_D(\d{8})\.ZIP$")


def pregao_do_endereco(endereco: str) -> date:
    """O pregão de um endereço da B3: negócios `AAAA-MM-DD`, PR `PRAAMMDD.zip`, COTAHIST
    `COTAHIST_DDDMMAAAA.ZIP`."""
    if achado := _DATA_ISO.search(endereco):
        return date(*map(int, achado.groups()))
    if achado := _DATA_DO_PR.search(endereco):
        aammdd = achado.group(1)
        return date(2000 + int(aammdd[:2]), int(aammdd[2:4]), int(aammdd[4:]))
    if achado := _DATA_DO_COTAHIST.search(endereco):
        ddmmaaaa = achado.group(1)
        return date(int(ddmmaaaa[4:]), int(ddmmaaaa[2:4]), int(ddmmaaaa[:2]))
    raise ValueError(f"endereço sem data de pregão conhecida: {endereco}")


# --- PR 3: houve pregão? e o alarme da janela ---------------------------------------------------
# Na B3, "houve pregão" é "existe o COTAHIST do dia" (guardado pelo arquivista como
# `b3-cotahist-dia`): feriado (12/10/2026) responde 404 e não entra na lista. O arquivo de negócios
# só fica no ar nos últimos 20 pregões; quem não for salvo some para sempre.
JANELA_DE_PREGOES = 20
MARGEM_DO_ALARME = 5  # avisa quando faltam 5 pregões ou menos para o dia sumir
# a B3 nunca fica mais que 5 dias corridos sem pregão (Carnaval: sábado a terça; Natal e Ano-Novo:
# duas folgas com fim de semana no meio). Mais que isso sem COTAHIST novo = a coleta parou
DIAS_SEM_PREGAO_NO_MAXIMO = 5


def dias_em_risco(
    pregoes: Sequence[date],
    salvos: set[date],
    janela: int = JANELA_DE_PREGOES,
    margem: int = MARGEM_DO_ALARME,
) -> list[tuple[date, int]]:
    """Pregões ainda no ar que não estão salvos e somem em até `margem` pregões.

    Devolve (pregão, em quantos pregões ele some), do mais urgente ao menos. O mais antigo da
    janela some no próximo pregão (1). O que já saiu da janela não entra: não há mais o que fazer.
    """
    # contado do mais novo (0) para trás: o pregão na posição p some daqui a `janela - p` pregões
    no_ar = sorted(pregoes, reverse=True)[:janela]
    em_risco = [
        (pregao, janela - posicao)
        for posicao, pregao in enumerate(no_ar)
        if janela - posicao <= margem and pregao not in salvos
    ]
    return sorted(em_risco, key=lambda par: par[1])


def cotahist_atrasado(
    pregoes: Sequence[date], hoje: date, limite: int = DIAS_SEM_PREGAO_NO_MAXIMO
) -> bool:
    """O COTAHIST mais novo é de mais de `limite` dias atrás (ou não há nenhum)?"""
    return not pregoes or (hoje - max(pregoes)).days > limite
