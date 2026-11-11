"""A rede só de pessoa jurídica que sai de casa para o recorte da API (linha 843): o filtro e a trava.

O conjunto `links` da API externa (`src/api_externa/conjuntos/vinculos.py`) anda pela rede (`ligacoes`,
`entidades`, `identificadores`). Em casa a rede tem pessoa: o sócio pessoa natural (id `P`), o MEI, o empresário
individual, a natureza não informada. A API por chave, a CLI e o conector remoto nunca servem pessoa (ADR 0128),
então ao VPS vai um recorte **mais estreito que a vista publicada** (`base/rede/vistas.py::vista_publicada`):

- **entidades**: só a que a rede diz que não é pessoa (`trata_como_pessoa` e `mei` falsos; vazio conta como
  pessoa), de natureza informada fora de 213-5 e do grupo 4, com pelo menos uma raiz de CNPJ e **toda** raiz na
  `cnpj_empresas_pj` da mesma saída (a lista sem pessoa da Receita, já sem o MEI de natureza de empresa). Sem a
  coluna `nome`: a `links` dá o nome datado da Receita, e o da rede é o de hoje.
- **ligacoes**: só os tipos que a `links` serve (lista fechada; tipo novo entra com a leitura da norma, linha 838)
  e só entre entidades da saída.
- **identificadores**: só das entidades da saída e dos sistemas da lista (nada de CPF nem do hash dele).

`conferir_rede_so_pj` lê **a saída** e derruba a montagem (`RedeComPessoa`) em qualquer coisa fora disso, sem
depender do filtro: é a prova de zero pessoa que acompanha o pedido de envio. A mensagem leva só contagens, nunca
um id ou um valor (vai ao log e ao aviso do Kuma).
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb

from base.dossie import COLUNAS_DE_PESSOA
from base.rede.entidades import (
    EMPRESARIO_INDIVIDUAL,
    GRUPO_DAS_PESSOAS_FISICAS,
    NAO_INFORMADA,
)
from base.rede.ids import PREFIXO_DE_PESSOA

REDE = ("entidades", "identificadores", "ligacoes")
# Os tipos que a `links` serve (`vinculos.TIPOS`; há teste que confere as duas listas).
TIPOS_DE_LIGACAO = ("controlada_de", "coligada_de", "participada_de", "audita")
SISTEMAS_DE_CNPJ = ("cnpj", "cnpj_raiz")
SISTEMAS_DE_IDENTIFICADOR = (*SISTEMAS_DE_CNPJ, "lei", "isin", "ticker", "emissor")
PREFIXO_DOS_CODIGOS = "codigo_"  # os códigos dos reguladores (codigo_bcb_ifdata...)
COLUNA_DO_NOME = "nome"
TAMANHO_DA_RAIZ = 8
# Sem estas, não dá para saber quem é pessoa: a trava falha.
COLUNAS_OBRIGATORIAS: dict[str, tuple[str, ...]] = {
    "entidades": ("id_entidade", "tipo", "natureza_juridica", "mei", "trata_como_pessoa"),
    "identificadores": ("id_entidade", "sistema", "valor"),
    "ligacoes": ("de", "para", "tipo"),
}  # fmt: skip
COLUNAS_PROIBIDAS = frozenset({COLUNA_DO_NOME, *COLUNAS_DE_PESSOA})


class RedeComPessoa(Exception):
    """A saída da rede tem (ou pode ter) pessoa: nada sai de casa."""


def _aspas(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _ler(arquivos: Sequence[Path]) -> str:
    lista = ", ".join(_aspas(a.as_posix()) for a in arquivos)
    return f"read_parquet([{lista}], union_by_name=true)"


def _lista_sql(valores: Sequence[str]) -> str:
    return ", ".join(_aspas(v) for v in valores)


def _colunas(con: duckdb.DuckDBPyConnection, fonte: str) -> list[str]:
    return [c for (c, *_) in con.execute(f"DESCRIBE SELECT * FROM {fonte}").fetchall()]


def _contar(con: duckdb.DuckDBPyConnection, consulta: str) -> int:
    linha = con.execute(f"SELECT count(*) FROM ({consulta})").fetchone()
    return int(linha[0]) if linha else 0


def _e_pj(alias: str = "") -> str:
    """A linha de `entidades` que pode sair: id de empresa, marcas falsas (vazio é pessoa), natureza de empresa."""
    a = f"{alias}." if alias else ""
    natureza = f"trim({a}natureza_juridica)"
    return (
        f"{a}id_entidade IS NOT NULL AND NOT starts_with({a}id_entidade, {_aspas(PREFIXO_DE_PESSOA)}) "
        f"AND coalesce({a}trata_como_pessoa, true) = false AND coalesce({a}mei, true) = false "
        f"AND {natureza} IS NOT NULL AND {natureza} <> '' "  # vazia é pessoa (falha fechada)
        f"AND {natureza} <> {_aspas(EMPRESARIO_INDIVIDUAL)} "
        f"AND NOT starts_with({natureza}, {_aspas(GRUPO_DAS_PESSOAS_FISICAS)}) "
        f"AND {natureza} <> {_aspas(NAO_INFORMADA)}"
    )


def _sistema_permitido(coluna: str = "sistema") -> str:
    return (
        f"({coluna} IN ({_lista_sql(SISTEMAS_DE_IDENTIFICADOR)}) "
        f"OR starts_with({coluna}, {_aspas(PREFIXO_DOS_CODIGOS)}))"
    )


def _raiz(coluna: str = "valor") -> str:
    return f"upper(left(trim({coluna}), {TAMANHO_DA_RAIZ}))"


def _ids_pj(entidades: str, identificadores: str, empresas: str) -> str:
    """Os ids que saem: toda linha da entidade é PJ e toda raiz de CNPJ dela está na lista sem pessoa (e há uma)."""
    cnpj = _lista_sql(SISTEMAS_DE_CNPJ)
    return (
        f"WITH pj AS (SELECT DISTINCT upper(trim(cnpj_basico)) AS raiz FROM {empresas} WHERE cnpj_basico IS NOT NULL), "
        f"raizes AS (SELECT i.id_entidade, (pj.raiz IS NOT NULL) AS na_lista FROM {identificadores} i "
        f"LEFT JOIN pj ON pj.raiz = {_raiz('i.valor')} WHERE i.sistema IN ({cnpj}) AND i.id_entidade IS NOT NULL), "
        f"com_cnpj AS (SELECT id_entidade FROM raizes GROUP BY id_entidade HAVING bool_and(na_lista)), "
        f"marcadas AS (SELECT id_entidade FROM {entidades} e WHERE e.id_entidade IS NOT NULL "
        f"GROUP BY id_entidade HAVING bool_and(coalesce({_e_pj('e')}, false))) "
        f"SELECT id_entidade FROM marcadas WHERE id_entidade IN (SELECT id_entidade FROM com_cnpj)"
    )  # fmt: skip


def _copiar(con: duckdb.DuckDBPyConnection, consulta: str, destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({consulta}) TO {_aspas(destino.as_posix())} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return _contar(con, f"SELECT * FROM {_ler([destino])}")


def recortar_rede(
    con: duckdb.DuckDBPyConnection,
    origem: Mapping[str, Sequence[Path]],
    empresas_pj: Sequence[Path],
    destino: Mapping[str, Path],
    colunas: Mapping[str, Sequence[str]],
) -> dict[str, tuple[int, int]]:
    """Escreve em `destino` a rede só PJ; devolve, por tabela, (linhas na origem, linhas que saíram).

    `colunas` são as que o chamador deixa sair de cada tabela; `nome` e as colunas de pessoa saem sempre.
    """
    if not empresas_pj:
        raise RedeComPessoa(
            "sem cnpj_empresas_pj na saída: não dá para conferir as raízes"
        )
    fontes = {nome: _ler(origem[nome]) for nome in REDE}
    empresas = _ler(empresas_pj)
    con.execute(
        "CREATE OR REPLACE TEMP TABLE _ids_pj AS "
        + _ids_pj(fontes["entidades"], fontes["identificadores"], empresas)
    )
    filtros = {
        "entidades": "id_entidade IN (SELECT id_entidade FROM _ids_pj)",
        "identificadores": (
            f"id_entidade IN (SELECT id_entidade FROM _ids_pj) AND {_sistema_permitido()}"
        ),
        "ligacoes": (
            f"tipo IN ({_lista_sql(TIPOS_DE_LIGACAO)}) "
            "AND de IN (SELECT id_entidade FROM _ids_pj) AND para IN (SELECT id_entidade FROM _ids_pj)"
        ),
    }
    linhas: dict[str, tuple[int, int]] = {}
    for nome in REDE:
        mantidas = [c for c in colunas[nome] if c not in COLUNAS_PROIBIDAS]
        selecao = ", ".join(f'"{c}"' for c in mantidas)
        antes = _contar(con, f"SELECT * FROM {fontes[nome]}")
        depois = _copiar(
            con,
            f"SELECT {selecao} FROM {fontes[nome]} WHERE {filtros[nome]}",
            destino[nome],
        )
        linhas[nome] = (antes, depois)
    con.execute("DROP TABLE IF EXISTS _ids_pj")
    return linhas


# --- a trava ----------------------------------------------------------------------------------------


def _problemas_de_coluna(
    con: duckdb.DuckDBPyConnection, fontes: Mapping[str, str]
) -> list[str]:
    problemas = []
    for nome in REDE:
        colunas = set(_colunas(con, fontes[nome]))
        if proibidas := sorted(colunas & COLUNAS_PROIBIDAS):
            problemas.append(f"{nome} com coluna de nome ou de pessoa {proibidas}")
        if faltam := sorted(set(COLUNAS_OBRIGATORIAS[nome]) - colunas):
            problemas.append(f"{nome} sem {faltam}: não dá para saber quem é pessoa")
    return problemas


def _problemas_de_linha(
    con: duckdb.DuckDBPyConnection, fontes: Mapping[str, str], empresas: str
) -> list[str]:
    ent, ids, lig = fontes["entidades"], fontes["identificadores"], fontes["ligacoes"]
    cnpj = _lista_sql(SISTEMAS_DE_CNPJ)
    pj = f"SELECT DISTINCT upper(trim(cnpj_basico)) AS raiz FROM {empresas} WHERE cnpj_basico IS NOT NULL"
    da_saida = f"SELECT id_entidade FROM {ent} WHERE id_entidade IS NOT NULL"
    consultas = {
        "entidades marcadas ou que podem ser pessoa": f"SELECT * FROM {ent} e WHERE NOT coalesce({_e_pj('e')}, false)",
        "entidades sem raiz de CNPJ": (
            f"SELECT * FROM {ent} WHERE id_entidade NOT IN "
            f"(SELECT id_entidade FROM {ids} WHERE sistema IN ({cnpj}) AND id_entidade IS NOT NULL)"
        ),
        "identificadores de entidade fora da saída": (
            f"SELECT * FROM {ids} WHERE id_entidade IS NULL OR id_entidade NOT IN ({da_saida})"
        ),
        "identificadores de sistema fora da lista": (
            f"SELECT * FROM {ids} WHERE NOT coalesce({_sistema_permitido()}, false)"
        ),
        "raízes de CNPJ fora da cnpj_empresas_pj": (
            f"SELECT * FROM {ids} WHERE sistema IN ({cnpj}) AND (valor IS NULL OR {_raiz()} NOT IN ({pj}))"
        ),
        "ligações de tipo fora da lista": (
            f"SELECT * FROM {lig} WHERE tipo IS NULL OR tipo NOT IN ({_lista_sql(TIPOS_DE_LIGACAO)})"
        ),
        "ligações com ponta vazia, de pessoa ou fora das entidades da saída": (
            f"SELECT * FROM {lig} WHERE de IS NULL OR para IS NULL "
            f"OR de NOT IN ({da_saida}) OR para NOT IN ({da_saida})"
        ),
    }  # fmt: skip
    problemas = []
    for descricao, consulta in consultas.items():
        if achadas := _contar(con, consulta):
            problemas.append(f"{achadas} {descricao}")
    return problemas


def _contagens(
    con: duckdb.DuckDBPyConnection, fonte: str, coluna: str
) -> dict[str, int]:
    linhas = con.execute(
        f'SELECT "{coluna}", count(*) FROM {fonte} GROUP BY 1 ORDER BY 1'
    ).fetchall()
    return {str(valor): int(total) for valor, total in linhas}


def conferir_rede_so_pj(
    con: duckdb.DuckDBPyConnection,
    arquivos: Mapping[str, Path],
    empresas_pj: Sequence[Path],
) -> dict[str, dict[str, int]]:
    """Lê a rede da saída e derruba (`RedeComPessoa`) em qualquer pessoa; devolve as contagens por tipo e sistema.

    Não confia no filtro: confere a saída do zero contra a `cnpj_empresas_pj` da mesma saída.
    """
    if not empresas_pj:
        raise RedeComPessoa(
            "sem cnpj_empresas_pj na saída: não dá para conferir as raízes"
        )
    fontes = {nome: _ler([arquivos[nome]]) for nome in REDE}
    problemas = _problemas_de_coluna(con, fontes)
    if problemas:
        raise RedeComPessoa("rede com pessoa: " + "; ".join(problemas))
    problemas = _problemas_de_linha(con, fontes, _ler(empresas_pj))
    if problemas:
        raise RedeComPessoa("rede com pessoa: " + "; ".join(problemas))
    return {
        "entidades": _contagens(con, fontes["entidades"], "tipo"),
        "ligacoes": _contagens(con, fontes["ligacoes"], "tipo"),
        "identificadores": _contagens(con, fontes["identificadores"], "sistema"),
    }
