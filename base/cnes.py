"""CNES por competência (B4 da rodada de fontes de 03/11/2026): estabelecimentos de saúde com o CNPJ do
estabelecimento e o da mantenedora.

**Fonte escolhida: a API de dados abertos do DATASUS** (`/assistencia-a-saude/cnes-estabelecimentos`, JSON,
`nu_comp=AAAAMM`, `limit` até 1000 e `offset` em itens). O FTP em DBC (`CNES/200508_/Dados/ST`) chega duas
competências à frente (2609, contra 202607 da API em 03/11/2026), mas nunca foi lido: exige descompressão
PKWare (blast) e o layout não foi conferido. A API tem os dois CNPJs, formato conferido ao vivo e nada a
instalar; o FTP fica para a B4b.

- **Os dois CNPJs são campos diferentes.** `nu_cnpj` é do estabelecimento (vem nulo na unidade pública, que
  não tem CNPJ próprio) e `nu_cnpj_mantenedora` é de quem mantém (a prefeitura, a rede). Um não substitui o
  outro: cada um vai para a sua coluna, normalizado, e o que não tem 14 caracteres fica vazio.
- **Competência vazia não é "sem estabelecimentos".** A API devolve lista vazia para competência ainda não
  publicada (202608 e 202609 em 03/11/2026). `situacao_da_competencia` registra `vazia`, e quem consome não
  pode ler isso como "fechou tudo".
- **Paginação por `offset` em itens:** a próxima página começa em `offset + itens recebidos`. Item repetido
  ou página que não avança é erro, nunca dado.
- **Sem pessoa física:** estabelecimento sem nenhum CNPJ (consultório de pessoa física) fica sem nome
  empresarial e sem nome fantasia. Endereço, telefone e e-mail da fonte nunca entram.

**Sem olhar o futuro:** a API não dá a data de publicação da competência (o FTP publica por volta do dia 15
do mês seguinte). `disponivel_em` é a data da coleta; `nu_comp` nunca serve de disponibilidade.

Sem Streamlit; pandas só.
"""

import ftplib
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

import pandas as pd

from base import cnpj, dbc

FONTE = "ms-cnes-estabelecimentos-competencia"
ATRIBUICAO = (
    "Fonte: Ministério da Saúde, DATASUS, CNES (API de dados abertos), "
    "https://apidadosabertos.saude.gov.br/assistencia-a-saude/cnes-estabelecimentos"
)
AVISO_CNPJ = (
    "O CNES traz dois CNPJs: o do estabelecimento e o da mantenedora. Unidade pública costuma ter só o da "
    "mantenedora (a prefeitura ou o estado), e uma mantenedora não é dona de tudo o que mantém."
)
URL_DA_API = (
    "https://apidadosabertos.saude.gov.br/assistencia-a-saude/cnes-estabelecimentos"
)
ITENS_POR_PAGINA = 1000  # o máximo que a API aceita em `limit`
MAXIMO_DE_PAGINAS = (
    500  # 500 mil estabelecimentos numa competência: bem acima dos ~400 mil de hoje
)
CHAVE_DA_LISTA = "cnes_estabelecimentos"

SERVIDOR_FTP = "ftp.datasus.gov.br"
PASTA_NO_FTP = "/dissemin/publicos/CNES/200508_/Dados/ST"
TEMPO_LIMITE_DO_FTP = 120
DIA_DE_PUBLICACAO_NO_FTP = 15
UFS = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE",
    "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)  # fmt: skip
COLUNAS_DO_DBC = ("CNES", "CODUFMUN", "CNPJ_MAN", "TPGESTAO", "TP_UNID", "NAT_JUR")
COLUNAS_DO_CNPJ_DO_DBC = (
    "CNPJ",
    "CPF_CNPJ",
)  # o nome muda com a versão do layout; CPF_CNPJ mistura CPF

COMPETENCIA_COM_DADOS = "com_dados"
COMPETENCIA_VAZIA = "vazia"

COLUNAS = (
    "competencia", "codigo_cnes", "cnpj", "cnpj_mantenedora", "razao_social", "nome_fantasia",
    "codigo_ibge_municipio", "gestao", "tipo_unidade", "classificacao", "natureza_juridica",
    "grupo_natureza_juridica", "latitude", "longitude", "situacao_cnes", "disponivel_em",
)  # fmt: skip
CHAVE = ["competencia", "codigo_cnes"]
COLUNAS_DA_SITUACAO = ("competencia", "linhas", "situacao", "coletado_em")

# campo da fonte -> coluna; endereço, CEP, telefone e e-mail (`no_logradouro`, `nu_cep`, `nu_telefone`,
# `ds_email`...) ficam de fora de propósito
_TEXTOS = {
    "co_cnes": "codigo_cnes",
    "tp_gestao": "gestao",
    "tp_unidade": "tipo_unidade",
    "ds_class_estab": "classificacao",
    "ds_natureza_juridica": "natureza_juridica",
    "no_grupo_nat_jur": "grupo_natureza_juridica",
    "ds_status": "situacao_cnes",
}

Buscador = Callable[[int, int, int], dict[str, Any]]
"""`(competencia, offset, limit)` -> JSON da página; quem chama a internet entra aqui, os testes não."""


def _texto(valor: object) -> str:
    return "" if valor is None else str(valor).strip()


def _numero(valor: object) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return float("nan")


def itens_da_pagina(pagina: dict[str, Any]) -> list[dict[str, Any]]:
    """A lista de estabelecimentos do JSON; formato diferente do esperado é TypeError, não página vazia."""
    itens = pagina.get(CHAVE_DA_LISTA) if isinstance(pagina, dict) else None
    if not isinstance(itens, list):
        raise TypeError(f"CNES: a resposta não tem a lista {CHAVE_DA_LISTA!r}")
    return itens


def buscar_competencia(
    buscar: Buscador, competencia: int, por_pagina: int = ITENS_POR_PAGINA
) -> list[dict[str, Any]]:
    """Todos os itens da competência, página a página por `offset` em itens.

    Pára na primeira página vazia. Um `co_cnes` que se repete (a paginação voltou ou pulou de lugar) ou
    mais páginas que `MAXIMO_DE_PAGINAS` levanta ValueError.
    """
    itens: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for _ in range(MAXIMO_DE_PAGINAS):
        pagina = itens_da_pagina(buscar(competencia, len(itens), por_pagina))
        if not pagina:
            return itens
        for item in pagina:
            codigo = _texto(item.get("co_cnes"))
            if codigo in vistos:
                raise ValueError(
                    f"CNES {competencia}: o estabelecimento {codigo} veio duas vezes na paginação"
                )
            vistos.add(codigo)
        itens.extend(pagina)
    raise ValueError(f"CNES {competencia}: mais de {MAXIMO_DE_PAGINAS} páginas")


def _linha(
    item: dict[str, Any], competencia: int, coletado_em: date
) -> dict[str, object]:
    cnpj_estabelecimento = cnpj.completo(_texto(item.get("nu_cnpj"))) or ""
    cnpj_mantenedora = cnpj.completo(_texto(item.get("nu_cnpj_mantenedora"))) or ""
    pessoa_juridica = bool(cnpj_estabelecimento or cnpj_mantenedora)
    linha: dict[str, object] = {
        "competencia": int(item.get("nu_comp") or competencia),
        "cnpj": cnpj_estabelecimento,
        "cnpj_mantenedora": cnpj_mantenedora,
        "razao_social": _texto(item.get("no_empresarial")) if pessoa_juridica else "",
        "nome_fantasia": _texto(item.get("no_fantasia")) if pessoa_juridica else "",
        "codigo_ibge_municipio": _texto(item.get("co_ibge")),
        "latitude": _numero(item.get("nu_latitude")),
        "longitude": _numero(item.get("nu_longitude")),
        "disponivel_em": pd.Timestamp(coletado_em),
    }
    linha.update({coluna: _texto(item.get(campo)) for campo, coluna in _TEXTOS.items()})
    return linha


def tabela_da_competencia(
    itens: Iterable[dict[str, Any]], competencia: int, coletado_em: date
) -> pd.DataFrame:
    """Uma linha por estabelecimento da competência, com as colunas de `COLUNAS`."""
    linhas = [_linha(item, competencia, coletado_em) for item in itens]
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS))
    if tabela.duplicated(CHAVE).any():
        raise ValueError(f"CNES {competencia}: estabelecimento repetido na competência")
    return tabela.reset_index(drop=True)


def disponivel_em_da_competencia(competencia: int) -> date:
    """O dia 15 do mês seguinte à competência: quando o FTP costuma publicar (sem olhar o futuro)."""
    ano, mes = divmod(competencia, 100)
    return date(ano + (mes == 12), mes % 12 + 1, DIA_DE_PUBLICACAO_NO_FTP)


def caminho_no_ftp(uf: str, competencia: int) -> str:
    """O arquivo `ST<UF><AAMM>.dbc` da competência `AAAAMM` no FTP do DATASUS."""
    if uf not in UFS:
        raise ValueError(f"CNES: UF desconhecida: {uf!r}")
    return f"{PASTA_NO_FTP}/ST{uf}{competencia % 10000:04d}.dbc"


def baixar_dbc(
    uf: str, competencia: int, abrir: Callable[..., ftplib.FTP] = ftplib.FTP
) -> bytes:
    """O DBC inteiro da UF e da competência. O FTP não passa por `rede.get_com_agente` (que é HTTP)."""
    caminho = caminho_no_ftp(uf, competencia)
    pedaços: list[bytes] = []
    with abrir(SERVIDOR_FTP, timeout=TEMPO_LIMITE_DO_FTP) as ftp:
        ftp.login()
        ftp.retrbinary(f"RETR {caminho}", pedaços.append)
    return b"".join(pedaços)


def _coluna_do_cnpj(nomes: list[str]) -> str:
    for candidata in COLUNAS_DO_CNPJ_DO_DBC:
        if candidata in nomes:
            return candidata
    raise dbc.DbcInvalido(
        f"CNES DBC: sem coluna de CNPJ entre {COLUNAS_DO_CNPJ_DO_DBC}"
    )


def tabela_do_dbc(conteudo: bytes, competencia: int) -> pd.DataFrame:
    """As linhas do DBC no mesmo formato de `tabela_da_competencia`.

    Só CNPJ de 14 caracteres entra: o CPF do consultório de pessoa física (11 dígitos) e qualquer valor
    fora da forma ficam vazios. O DBC não traz razão social, nome fantasia nem coordenadas: ficam vazios.
    `disponivel_em` é o dia 15 do mês seguinte à competência.
    """
    coluna_cnpj = _coluna_do_cnpj(dbc.nomes_das_colunas(conteudo))
    pedidas = (*COLUNAS_DO_DBC, coluna_cnpj)
    disponivel_em = pd.Timestamp(disponivel_em_da_competencia(competencia))
    linhas = [
        {
            "competencia": competencia,
            "codigo_cnes": registro["CNES"],
            "cnpj": cnpj.completo(registro[coluna_cnpj]) or "",
            "cnpj_mantenedora": cnpj.completo(registro["CNPJ_MAN"]) or "",
            "codigo_ibge_municipio": registro["CODUFMUN"],
            "gestao": registro["TPGESTAO"],
            "tipo_unidade": registro["TP_UNID"],
            "natureza_juridica": registro["NAT_JUR"],
            "disponivel_em": disponivel_em,
        }
        for registro in dbc.ler_dbc(conteudo, pedidas)
    ]
    tabela = pd.DataFrame(linhas).reindex(columns=list(COLUNAS))
    for coluna in (
        "razao_social",
        "nome_fantasia",
        "classificacao",
        "grupo_natureza_juridica",
        "situacao_cnes",
    ):
        tabela[coluna] = ""
    for coluna in ("latitude", "longitude"):
        tabela[coluna] = float("nan")
    if tabela.duplicated(CHAVE).any():
        raise ValueError(
            f"CNES DBC {competencia}: estabelecimento repetido na competência"
        )
    return tabela.reset_index(drop=True)


def situacao_da_competencia(
    competencia: int, linhas: int, coletado_em: date
) -> dict[str, object]:
    """O registro de que a competência foi olhada: `vazia` quando a fonte ainda não publicou."""
    return {
        "competencia": competencia,
        "linhas": linhas,
        "situacao": COMPETENCIA_COM_DADOS if linhas else COMPETENCIA_VAZIA,
        "coletado_em": pd.Timestamp(coletado_em),
    }


def coletar_competencia(
    buscar: Buscador, competencia: int, coletado_em: date
) -> tuple[pd.DataFrame, dict[str, object]]:
    """A tabela da competência e o registro da situação dela (vazia ou com dados)."""
    itens = buscar_competencia(buscar, competencia)
    tabela = tabela_da_competencia(itens, competencia, coletado_em)
    return tabela, situacao_da_competencia(competencia, len(tabela), coletado_em)
