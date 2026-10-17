"""Quando cada negócio de M&A ficou público, provado, e a confirmação por fonte oficial (ADR 0082, série
5 do plano de M&A, passo 4).

**`conhecido_em` = a prova mais antiga guardada** (testes em `tests/test_base_ma_datas.py`), entre:
1. a primeira cópia da página no Internet Archive que respondeu 200 (`base/arquivo/wayback.py`; a
   prova é a resposta da API CDX guardada no acervo);
2. o arquivo de sócios do CNPJ da Receita em que a compradora aparece como **sócia pessoa jurídica**
   da alvo (a prova é o ZIP guardado; a data, a de quando o baixamos);
3. sem nenhuma das duas, a nossa primeira coleta da página.
Empate: nessa ordem. **Nunca uma data contada**: a data de entrada na sociedade é a do fechamento (a
etapa), não a de quando o negócio ficou público; ela vai para `fechamento_em` e não entra na conta.

**`conferencia = "confirmado"`** só quando o CNPJ confirma, e a linha aponta a prova (endereço, SHA-256
e data do arquivo). Só sócio pessoa jurídica (identificador 1 da Receita): do arquivo de sócios saem a
raiz da empresa, a raiz da sócia e a data de entrada; nome de sócio, CPF e representante nunca são lidos
(ADRs 0075 e 0077). Sem fonte oficial, fica `assessoria` (fonte única: o que a assessoria declarou).

CADE no Diário Oficial e juntas comerciais ficaram fora: o INLABS pede conta (é do Tiago criar) e as
juntas não têm fonte aberta.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from base.arquivo.wayback import pagina_da_consulta
from base.ma_ligacao import Arquivo, partes_do_zip

WAYBACK, RECEITA, COLETA = "wayback", "rfb-cnpj", "coleta"
PREFERENCIA = (WAYBACK, RECEITA, COLETA)  # no empate de datas, nessa ordem
ASSESSORIA, CONFIRMADO = "assessoria", "confirmado"
COPIA = "https://web.archive.org/web/{momento}/{original}"
RESPONDEU = "200"
FORMATO_DO_WAYBACK = "%Y%m%d%H%M%S"  # sempre em UTC


@dataclass(frozen=True)
class Guardado:
    """Um original do acervo que serve de prova: o endereço, o SHA-256 e quando o baixamos."""

    url: str
    sha256: str
    baixado_em: datetime


# --- Wayback ---------------------------------------------------------------------------------------
COLUNAS_DAS_COPIAS = (
    "url",
    "wayback_em",
    "wayback_copia",
    "wayback_consulta",
    "wayback_sha256",
)


def primeira_copia(cdx: bytes) -> tuple[str, datetime] | None:
    """(momento como o Wayback escreve, em UTC) da cópia mais antiga que respondeu 200, ou None."""
    linhas = json.loads(cdx or b"[]")
    if not linhas:
        return None
    cabecalho, *copias = linhas
    momento, situacao = cabecalho.index("timestamp"), cabecalho.index("statuscode")
    boas = sorted(c[momento] for c in copias if c[situacao] == RESPONDEU)
    if not boas:
        return None
    return boas[0], datetime.strptime(boas[0], FORMATO_DO_WAYBACK).replace(tzinfo=UTC)


def _original(cdx: bytes, momento: str) -> str:
    cabecalho, *copias = json.loads(cdx)
    i_momento, i_original = cabecalho.index("timestamp"), cabecalho.index("original")
    return next(c[i_original] for c in copias if c[i_momento] == momento)


def copias_do_wayback(consultas: Iterable[tuple[Guardado, bytes]]) -> pd.DataFrame:
    """Uma linha por consulta guardada: a página, a cópia mais antiga (se houver) e a prova."""
    linhas = []
    for guardado, cdx in consultas:
        achada = primeira_copia(cdx)
        linhas.append(
            {
                "url": pagina_da_consulta(guardado.url),
                "wayback_em": achada[1] if achada else None,
                "wayback_copia": (
                    COPIA.format(momento=achada[0], original=_original(cdx, achada[0]))
                    if achada
                    else None
                ),
                "wayback_consulta": guardado.url,
                "wayback_sha256": guardado.sha256,
            }
        )
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS_DAS_COPIAS)).astype(object)
    return tabela.assign(wayback_em=pd.to_datetime(tabela["wayback_em"], utc=True))


# --- sócios da Receita -----------------------------------------------------------------------------
COLUNAS_DOS_SOCIOS = (
    "raiz",
    "socio_raiz",
    "entrada_em",
    "prova_url",
    "prova_sha256",
    "prova_em",
)
# colunas dos `Socios*.zip` (layout da Receita, conferido no servidor em 16/10/2026): 0 CNPJ básico,
# 1 identificador (1 PJ, 2 PF, 3 estrangeiro), 2 nome, 3 CNPJ ou CPF do sócio, 5 data de entrada;
# a 2 (nome) e as 7 a 10 (representante, faixa etária) nunca são lidas
BASICO, IDENTIFICADOR, DOCUMENTO, ENTRADA = 0, 1, 3, 5
PESSOA_JURIDICA = "1"
DIGITOS_DA_RAIZ, DIGITOS_DO_CNPJ = 8, 14


def _raiz_do_documento(documentos: pd.Series) -> pd.Series:
    """A raiz da sócia: hoje a Receita publica só os 8 dígitos; com o CNPJ inteiro, os 8 primeiros."""
    digitos = documentos.str.replace(r"\D", "", regex=True)
    return digitos.where(
        digitos.str.len() <= DIGITOS_DA_RAIZ,
        digitos.str.zfill(DIGITOS_DO_CNPJ).str[:DIGITOS_DA_RAIZ],
    ).str.zfill(DIGITOS_DA_RAIZ)


def _data(texto: str) -> date | None:
    try:
        return date.fromisoformat(texto)  # "20081104" (formato básico da ISO)
    except ValueError:  # "00000000" ou vazio
        return None


def ler_socios_pj(
    arquivos: Sequence[tuple[Arquivo, Guardado]], raizes: set[str]
) -> pd.DataFrame:
    """As sócias pessoa jurídica das `raizes`, com a data de entrada e o arquivo que prova."""
    achados = []
    for arquivo, guardado in arquivos:
        for parte in partes_do_zip(
            arquivo, [BASICO, IDENTIFICADOR, DOCUMENTO, ENTRADA]
        ):
            parte = parte[
                (parte[IDENTIFICADOR] == PESSOA_JURIDICA) & parte[BASICO].isin(raizes)
            ]
            achados.append(
                pd.DataFrame(
                    {
                        "raiz": parte[BASICO],
                        "socio_raiz": _raiz_do_documento(parte[DOCUMENTO]),
                        "entrada_em": parte[ENTRADA].map(_data),
                        "prova_url": guardado.url,
                        "prova_sha256": guardado.sha256,
                        "prova_em": guardado.baixado_em,
                    }
                )
            )
    if not achados:
        return pd.DataFrame(columns=list(COLUNAS_DOS_SOCIOS))
    return pd.concat(achados, ignore_index=True)[list(COLUNAS_DOS_SOCIOS)].astype(
        object
    )


# --- as datas --------------------------------------------------------------------------------------
COLUNAS = (
    "assessoria",
    "url",
    "id_negocio",
    "coletado_em",
    "wayback_em",
    "wayback_copia",
    "wayback_consulta",
    "wayback_sha256",
    "confirmado_por",
    "confirmacao_url",
    "confirmacao_sha256",
    "confirmacao_em",
    "fechamento_em",
    "conhecido_em",
    "conhecido_por",
    "prova_url",
    "prova_sha256",
    "conhecido_em_do_negocio",
    "conferencia",
)
CHAVE = ["assessoria", "url"]
MOMENTOS = (
    "coletado_em",
    "wayback_em",
    "confirmacao_em",
    "conhecido_em",
    "conhecido_em_do_negocio",
)


def _confirmacoes(partes: pd.DataFrame, socios: pd.DataFrame) -> pd.DataFrame:
    """Por página: a compradora sócia PJ da alvo no CNPJ (a entrada mais antiga, se várias)."""
    com_raiz = partes[partes["cnpj_raiz"].notna()]
    alvos = com_raiz.loc[com_raiz["papel"] == "alvo", [*CHAVE, "cnpj_raiz"]]
    compradores = com_raiz.loc[com_raiz["papel"] == "comprador", [*CHAVE, "cnpj_raiz"]]
    pares = alvos.rename(columns={"cnpj_raiz": "raiz"}).merge(
        compradores.rename(columns={"cnpj_raiz": "socio_raiz"}), on=CHAVE
    )
    pares = pares[pares["raiz"] != pares["socio_raiz"]]
    achados = pares.merge(socios, on=["raiz", "socio_raiz"]).sort_values(
        ["entrada_em", "prova_em", "prova_url"], na_position="last"
    )
    achados = achados.drop_duplicates(CHAVE)
    return pd.DataFrame(
        {
            **{c: achados[c] for c in CHAVE},
            "confirmado_por": RECEITA,
            "confirmacao_url": achados["prova_url"],
            "confirmacao_sha256": achados["prova_sha256"],
            "confirmacao_em": achados["prova_em"],
            "fechamento_em": achados["entrada_em"],
        }
    )


def _provas(linha: pd.Series) -> list[tuple[pd.Timestamp, int, str, str, str]]:
    """(data, preferência, por, endereço, SHA-256) de cada prova que a linha tem."""
    provas = [
        (
            linha["coletado_em"],
            PREFERENCIA.index(COLETA),
            COLETA,
            linha["url"],
            linha["sha256"],
        )
    ]
    if pd.notna(linha["wayback_em"]):
        provas.append(
            (
                linha["wayback_em"],
                PREFERENCIA.index(WAYBACK),
                WAYBACK,
                linha["wayback_consulta"],
                linha["wayback_sha256"],
            )
        )
    if pd.notna(linha["confirmacao_em"]):
        provas.append(
            (
                linha["confirmacao_em"],
                PREFERENCIA.index(RECEITA),
                RECEITA,
                linha["confirmacao_url"],
                linha["confirmacao_sha256"],
            )
        )
    return provas


def datar(
    tabela: pd.DataFrame,
    partes: pd.DataFrame,
    negocios: pd.DataFrame,
    copias: pd.DataFrame,
    socios: pd.DataFrame,
) -> pd.DataFrame:
    """Uma linha por página: as provas, o `conhecido_em` (a mais antiga) e a conferência."""
    linhas = (
        tabela[[*CHAVE, "sha256", "coletado_em"]]
        .merge(negocios[[*CHAVE, "id_negocio"]], on=CHAVE, how="left")
        .merge(copias, on="url", how="left")
        .merge(_confirmacoes(partes, socios), on=CHAVE, how="left")
    )
    for coluna in MOMENTOS[:3]:
        linhas[coluna] = pd.to_datetime(linhas[coluna], utc=True)
    escolhidas = [min(_provas(linha)) for _, linha in linhas.iterrows()]
    linhas["conhecido_em"] = pd.to_datetime([p[0] for p in escolhidas], utc=True)
    linhas["conhecido_por"] = [p[2] for p in escolhidas]
    linhas["prova_url"] = [p[3] for p in escolhidas]
    linhas["prova_sha256"] = [p[4] for p in escolhidas]
    grupo = linhas["id_negocio"].fillna("pagina:" + linhas["url"])
    linhas["conhecido_em_do_negocio"] = linhas.groupby(grupo)["conhecido_em"].transform(
        "min"
    )
    linhas["conferencia"] = linhas["confirmado_por"].map(
        lambda por: CONFIRMADO if isinstance(por, str) else ASSESSORIA
    )
    texto = [c for c in COLUNAS if c not in MOMENTOS]
    return (
        linhas[list(COLUNAS)]
        .astype({c: object for c in texto})
        .sort_values(CHAVE, ignore_index=True)
    )


def resumo(saida: pd.DataFrame) -> str:
    """Os números da conferência: de onde veio cada `conhecido_em` e quantas confirmações."""
    por = saida["conhecido_por"].value_counts()
    confirmadas = saida["conferencia"] == CONFIRMADO
    return (
        f"{len(saida)} páginas; {saida['wayback_em'].notna().sum()} com cópia no Wayback; "
        f"conhecido_em pelo wayback {por.get(WAYBACK, 0)}, pelo rfb-cnpj {por.get(RECEITA, 0)}, "
        f"pela coleta {por.get(COLETA, 0)}; {confirmadas.sum()} confirmadas pelo CNPJ "
        f"({(confirmadas & saida['fechamento_em'].notna()).sum()} com data de fechamento)"
    )
