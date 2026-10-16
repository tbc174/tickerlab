"""A rede de uma entidade pela porta (ADR 0077, item 9; plano da rede, PR 4, tarefa 4.2).

`rede(...)` parte de um id, CNPJ, raiz ou outro identificador (ticker, LEI, ISIN, código do emissor),
anda pelas ligações nos dois sentidos até `profundidade` saltos e devolve as ligações, as entidades
e os identificadores encontrados. Com `como_era_em`, só o que já era público no dia e ainda valia
(D5), sem o fim que só veio depois; um identificador que já tinha acabado no dia continua (é a
história conhecida, como o ticker antigo).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

import duckdb
import pandas as pd

from base.cnpj import SEPARADORES
from base.porta.duckdb import condicao_como_era, dia_de, sem_o_fim_futuro
from base.rede.ligacoes import CHAVE

ID_DE_ENTIDADE = re.compile(r"^[EP][0-9a-f]{20}$")
OUTROS_SISTEMAS = ("ticker", "lei", "isin", "emissor")
_LISTA = "(SELECT unnest(${}))"  # um parâmetro com lista, como tabela


@dataclass(frozen=True)
class Rede:
    centro: str  # o id_entidade de onde a rede partiu
    ligacoes: pd.DataFrame  # as colunas de `ligacoes` e `salto` (1 = ligada ao centro)
    entidades: pd.DataFrame  # as colunas de `entidades` e `salto` (0 = o centro)
    identificadores: pd.DataFrame  # os identificadores das entidades da rede


def views(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {nome for (nome,) in con.execute("SHOW TABLES").fetchall()}


def colunas(con: duckdb.DuckDBPyConnection, view: str) -> list[str]:
    return [c for (c, *_) in con.execute(f'DESCRIBE "{view}"').fetchall()]


def _com_dia(sql: str, parametros: dict[str, object], dia: str | None) -> str:
    if dia is None:
        return sql.replace("{publico}", "")
    parametros["dia"] = dia
    return sql.replace("{publico}", "AND publico_em <= CAST($dia AS DATE)")


def _procurar(
    con: duckdb.DuckDBPyConnection, pares: list[tuple[str, str]], dia: str | None
) -> list[str]:
    """Os ids com algum dos (sistema, valor), entre os identificadores já públicos no dia."""
    parametros: dict[str, object] = {"pares": [list(p) for p in pares]}
    sql = _com_dia(
        "SELECT DISTINCT id_entidade FROM identificadores "
        "WHERE list_contains($pares, [sistema, valor]) {publico} ORDER BY id_entidade",
        parametros,
        dia,
    )
    return [i for (i,) in con.execute(sql, parametros).fetchall()]


def resolver(con: duckdb.DuckDBPyConnection, id_ou_cnpj: str, dia: str | None) -> str:
    """O id_entidade de um id, CNPJ (14 ou raiz de 8) ou outro identificador; erro se nenhum ou
    mais de um."""
    existem = views(con)
    if "entidades" in existem and con.execute(
        "SELECT count(*) FROM entidades WHERE id_entidade = $id", {"id": id_ou_cnpj}
    ).fetchone() != (0,):
        return id_ou_cnpj
    if ID_DE_ENTIDADE.match(id_ou_cnpj) or "identificadores" not in existem:
        raise LookupError(f"{id_ou_cnpj}: nenhuma entidade com este id na base")
    texto = SEPARADORES.sub("", id_ou_cnpj.strip()).upper()
    tentativas: list[list[tuple[str, str]]] = []
    if len(texto) == 14:  # o fundo é o CNPJ inteiro; a empresa, a raiz
        tentativas += [[("cnpj", texto)], [("cnpj_raiz", texto[:8])]]
    elif len(texto) == 8:
        tentativas.append([("cnpj_raiz", texto)])
    tentativas.append([(sistema, texto) for sistema in OUTROS_SISTEMAS])
    for pares in tentativas:
        achados = _procurar(con, pares, dia)
        if len(achados) > 1:
            raise LookupError(
                f"{id_ou_cnpj}: mais de uma entidade ({', '.join(achados)})"
            )
        if achados:
            return achados[0]
    quando = "" if dia is None else f" pública até {dia}"
    raise LookupError(f"{id_ou_cnpj}: nenhuma entidade{quando} com este identificador")


def _vizinhas(
    con: duckdb.DuckDBPyConnection,
    fronteira: list[str],
    tipos: list[str] | None,
    dia: str | None,
) -> pd.DataFrame:
    # `IN (SELECT unnest(...))` vira junção por hash: com 10 mil ids na fronteira, 0,3 s em vez
    # de 9 s do `list_contains` (que compara cada ligação com cada id), medido em 16/10/2026
    condicoes = [
        f"(de IN {_LISTA.format('fronteira')} OR para IN {_LISTA.format('fronteira')})"
    ]
    parametros: dict[str, object] = {"fronteira": fronteira}
    if tipos is not None:
        condicoes.append(f"tipo IN {_LISTA.format('tipos')}")
        parametros["tipos"] = tipos
    if dia is not None:
        condicoes.append(condicao_como_era(colunas(con, "ligacoes"), "ligacoes"))
        parametros["dia"] = dia
    return con.execute(
        f"SELECT * FROM ligacoes WHERE {' AND '.join(condicoes)}", parametros
    ).df()


def _entidades(con: duckdb.DuckDBPyConnection, saltos: dict[str, int]) -> pd.DataFrame:
    tabela = pd.DataFrame({"id_entidade": list(saltos), "salto": list(saltos.values())})
    if "entidades" in views(con):
        dados = con.execute(
            f"SELECT * FROM entidades WHERE id_entidade IN {_LISTA.format('ids')}",
            {"ids": list(saltos)},
        ).df()
        tabela = tabela.merge(dados, on="id_entidade", how="left")
    return tabela.sort_values(["salto", "id_entidade"], ignore_index=True)


def _identificadores(
    con: duckdb.DuckDBPyConnection, ids: list[str], dia: str | None
) -> pd.DataFrame:
    parametros: dict[str, object] = {"ids": ids}
    sql = _com_dia(
        f"SELECT * FROM identificadores WHERE id_entidade IN {_LISTA.format('ids')} "
        "{publico} "
        "ORDER BY id_entidade, sistema, valor",
        parametros,
        dia,
    )
    tabela = con.execute(sql, parametros).df()
    if dia is not None:
        # o fim que só veio depois do dia não aparece; o que já tinha acabado fica (a história)
        tabela["ate"] = tabela["ate"].mask(tabela["ate"] > pd.Timestamp(dia))
    return tabela


def rede(
    con: duckdb.DuckDBPyConnection,
    id_ou_cnpj: str,
    tipos: Iterable[str] | None = None,
    como_era_em: object = None,
    profundidade: int = 1,
) -> Rede:
    if profundidade < 1:
        raise ValueError(f"profundidade {profundidade}: use 1 ou mais saltos")
    if "ligacoes" not in views(con):
        raise LookupError("a base não tem a tabela `ligacoes`")
    dia = None if como_era_em is None else dia_de(como_era_em)
    lista_de_tipos = None if tipos is None else list(tipos)
    centro = resolver(con, id_ou_cnpj, dia)
    saltos = {centro: 0}
    fronteira = {centro}
    partes: list[pd.DataFrame] = []
    for salto in range(1, profundidade + 1):
        vizinhas = _vizinhas(con, sorted(fronteira), lista_de_tipos, dia)
        partes.append(vizinhas.assign(salto=salto))
        fronteira = (set(vizinhas["de"]) | set(vizinhas["para"])) - set(saltos)
        saltos.update(dict.fromkeys(fronteira, salto))
        if not fronteira:
            break
    ligacoes = (
        pd.concat(partes, ignore_index=True)
        .drop_duplicates(CHAVE, keep="first")  # a mesma ligação fica no menor salto
        .reset_index(drop=True)
    )
    if dia is not None:
        ligacoes = sem_o_fim_futuro(ligacoes)
    return Rede(
        centro,
        ligacoes,
        _entidades(con, saltos),
        _identificadores(con, list(saltos), dia),
    )
