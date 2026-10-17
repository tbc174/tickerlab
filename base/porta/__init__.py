"""A porta de entrada da base em Python (ADR 0077, item 9; plano da rede, PR 4, tarefa 4.2).

Código novo lê a base **só por aqui** (`tests/test_porta_unica.py` cuida disso):

    from base import porta
    porta.catalogo()                                        # o que existe, versão e datas
    porta.ler("controladas", como_era_em="2020-12-31", filtros={"cnpj_companhia": "..."})
    porta.rede("33.256.439/0001-39", como_era_em="2020-12-31", profundidade=2)
    porta.linhagem("entidades", linha)                      # da linha ao original e à coleta
    porta.carteira(["33.256.439/0001-39"], desde="2024-01-01")
    with porta.abrir() as p: p.somar("anatel_acessos", ["competencia", "cnpj"], "acessos")

As funções do módulo abrem `<acervo>/base` (`TICKERLAB_ACERVO`) e fecham no fim. Para várias
consultas seguidas, `with porta.abrir() as p:` usa uma conexão só. "Como era em D" é sempre D5:
`publico_em ≤ D` e (`ate` vazio ou `ate > D`), sem mostrar o fim que só veio depois; quem decide
**no** dia D passa D − 1.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Self

import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpj_
from base.contrato import catalogo as catalogo_do_contrato
from base.dicionario import TABELAS, Tabela
from base.linhagem import Linhagem, linhagem_da_linha, linhagem_da_tabela
from base.porta.duckdb import (
    ARQUIVOS,
    FORA_DA_PORTA,
    arquivos_da_tabela,
    condicao_como_era,
    conectar,
    dia_de,
    nome_da_view,
    sem_o_fim_futuro,
)
from base.porta.rede import Rede, colunas, views
from base.porta.rede import rede as rede_
from src import acervo

__all__ = ["Porta", "Rede", "abrir", "carteira", "catalogo", "ler", "linhagem", "rede"]

POR_ANO_DE_BALANCO = (
    "demonstracoes_como_era"  # manifesto por ano (`base/ponto_no_tempo.py`)
)


def _valor(valor: object) -> object:
    """O valor de uma célula do pandas como o DuckDB entende (None no lugar de NaN e NaT)."""
    if valor is None or (not isinstance(valor, list | tuple) and pd.isna(valor)):
        return None
    item = getattr(valor, "item", None)  # número do numpy vira número do Python
    return item() if callable(item) else valor


def _nome(coluna: str) -> str:
    return '"' + coluna.replace('"', '""') + '"'


def _igualdades(
    valores: Mapping[str, object], prefixo: str
) -> tuple[list[str], dict[str, object]]:
    """`coluna = valor` (ou `IN`, ou `IS NULL`) para cada par, com os valores em parâmetros."""
    condicoes, parametros = [], {}
    for i, (coluna, valor) in enumerate(valores.items()):
        nome, parametro = _nome(coluna), f"{prefixo}{i}"
        if isinstance(valor, list | tuple | set | frozenset):
            condicoes.append(f"{nome} IN (SELECT unnest(${parametro}))")
            parametros[parametro] = [_valor(v) for v in valor]
        elif _valor(valor) is None:
            condicoes.append(f"{nome} IS NULL")
        else:
            condicoes.append(f"{nome} = ${parametro}")
            parametros[parametro] = _valor(valor)
    return condicoes, parametros


class Porta:
    """Uma conexão do DuckDB com as views da base em `pasta`; `banco` (o registro de coletas) só é
    preciso para a linhagem. `opcoes` vão para `conectar` (tabelas de mentira nos testes)."""

    def __init__(
        self,
        pasta: Path,
        banco: sa.Connection | None = None,
        *,
        memoria: str | None = None,
        threads: int | None = None,
        tabelas: Mapping[str, Tabela] = TABELAS,
        arquivos: Mapping[str, str] = ARQUIVOS,
        **opcoes: object,
    ) -> None:
        self.pasta = Path(pasta)
        self.banco = banco
        self.tabelas = tabelas
        self.arquivos = arquivos
        self.con = conectar(
            self.pasta, memoria, threads, tabelas=tabelas, arquivos=arquivos, **opcoes
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    def fechar(self) -> None:
        self.con.close()

    # --- o que existe ---------------------------------------------------------------------------
    def catalogo(self) -> dict:
        """O catálogo do contrato com, por tabela, se está nesta base (`na_porta`), as versões
        maiores que a porta serve e, se for o caso, por que fica de fora."""
        existem = views(self.con)
        resultado = catalogo_do_contrato(dict(self.tabelas))
        for nome, entrada in resultado["tabelas"].items():
            entrada["na_porta"] = nome in existem
            entrada["versoes"] = sorted(
                (v.split("__v")[1] for v in existem if v.startswith(f"{nome}__v")),
                key=int,
            )
            if nome in FORA_DA_PORTA:
                entrada["fora_da_porta"] = FORA_DA_PORTA[nome]
        return resultado

    # --- ler uma tabela -------------------------------------------------------------------------
    def _view(self, tabela: str, versao: str | None) -> str:
        if tabela not in self.tabelas:
            raise KeyError(f"tabela `{tabela}` não existe no dicionário da base")
        existem = views(self.con)
        if tabela not in existem:
            raise KeyError(
                f"tabela `{tabela}` não tem arquivo nesta base ({self.pasta})"
            )
        view = nome_da_view(tabela, versao)
        if view not in existem:
            raise KeyError(f"tabela `{tabela}` não tem a versão {versao} na porta")
        return view

    def colunas(self, tabela: str, versao: str | None = None) -> list[str]:
        """As colunas da tabela nesta base (com as datas pelos apelidos), sem ler as linhas."""
        return colunas(self.con, self._view(tabela, versao))

    def hashes(self, tabela: str) -> dict[str, str | None]:
        """Por arquivo vigente da tabela (caminho dentro da base, sem `.parquet`), o SHA-256 do
        conteúdo que o manifesto ao lado guarda (None se não há manifesto). Quem monta algo a partir
        da base anota isso, e dá para refazer e conferir (ADR 0078)."""
        self._view(tabela, None)
        hashes: dict[str, str | None] = {}
        for arquivo in arquivos_da_tabela(self.pasta, self.arquivos[tabela]):
            manifesto = arquivo.with_suffix(".json")
            nome = arquivo.relative_to(self.pasta).with_suffix("").as_posix()
            hashes[nome] = (
                json.loads(manifesto.read_text(encoding="utf-8")).get(
                    "sha256_da_tabela"
                )
                if manifesto.is_file()
                else None
            )
        return hashes

    def _onde(
        self,
        tabela: str,
        versao: str | None,
        filtros: Mapping[str, object] | None,
        como_era_em: object,
        usadas: Sequence[str],
    ) -> tuple[str, dict[str, object]]:
        """O `WHERE` (filtros de igualdade e "como era em") e os parâmetros dele; toda coluna usada
        precisa existir (o nome nunca vira código: só os que a tabela tem passam)."""
        existentes = self.colunas(tabela, versao)
        desconhecidas = [c for c in [*(filtros or {}), *usadas] if c not in existentes]
        if desconhecidas:
            raise ValueError(f"{tabela}: coluna {desconhecidas[0]!r} não existe")
        condicoes, parametros = _igualdades(filtros or {}, "f")
        if como_era_em is not None:
            condicoes.append(condicao_como_era(existentes, tabela))
            parametros["dia"] = dia_de(como_era_em)
        return " AND ".join(["true", *condicoes]), parametros

    def ler(
        self,
        tabela: str,
        versao: str | None = None,
        como_era_em: object = None,
        filtros: Mapping[str, object] | None = None,
        colunas: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """A tabela (na versão maior pedida), com filtros de igualdade (`{coluna: valor}` ou
        `{coluna: [valores]}`) e, com `como_era_em`, só o que era público no dia e ainda valia.
        `colunas` traz só essas (tabela grande: menos memória); o filtro vale do mesmo jeito."""
        view = self._view(tabela, versao)
        onde, parametros = self._onde(
            tabela, versao, filtros, como_era_em, colunas or []
        )
        selecao = "*" if colunas is None else ", ".join(_nome(c) for c in colunas)
        resultado = self.con.execute(
            f"SELECT {selecao} FROM {_nome(view)} WHERE {onde}", parametros
        ).df()
        return resultado if como_era_em is None else sem_o_fim_futuro(resultado)

    def somar(
        self,
        tabela: str,
        por: Sequence[str],
        valor: str,
        filtros: Mapping[str, object] | None = None,
        como_era_em: object = None,
    ) -> pd.DataFrame:
        """A soma de `valor` por `por`, feita no DuckDB: série de milhões de linhas (Anatel) volta só
        com o agregado. Filtros e `como_era_em` como em `ler`; as colunas saem com os mesmos nomes."""
        view = self._view(tabela, None)
        onde, parametros = self._onde(tabela, None, filtros, como_era_em, [*por, valor])
        grupos = ", ".join(_nome(c) for c in por)
        return self.con.execute(
            f"SELECT {grupos}, sum(TRY_CAST({_nome(valor)} AS DOUBLE)) AS {_nome(valor)} "
            f"FROM {_nome(view)} WHERE {onde} GROUP BY {grupos}",
            parametros,
        ).df()

    def distintos(
        self, tabela: str, coluna: str, versao: str | None = None
    ) -> set[object]:
        """Os valores diferentes de uma coluna (sem os vazios), sem trazer a tabela inteira."""
        view = self._view(tabela, versao)
        if coluna not in colunas(self.con, view):
            raise ValueError(f"{tabela}: coluna {coluna!r} não existe")
        linhas = self.con.execute(
            f"SELECT DISTINCT {_nome(coluna)} FROM {_nome(view)} "
            f"WHERE {_nome(coluna)} IS NOT NULL"
        ).fetchall()
        return {linha[0] for linha in linhas}

    # --- rede, linhagem e carteira --------------------------------------------------------------
    def rede(
        self,
        id_ou_cnpj: str,
        tipos: Iterable[str] | None = None,
        como_era_em: object = None,
        profundidade: int = 1,
    ) -> Rede:
        """As ligações, entidades e identificadores em volta de uma entidade (`base/porta/rede.py`)."""
        return rede_(self.con, id_ou_cnpj, tipos, como_era_em, profundidade)

    def linhagem(
        self, tabela: str, linha: Mapping[str, object] | pd.Series
    ) -> Linhagem:
        """De uma linha da tabela ao arquivo original, à coleta e à versão do código.

        `linha` precisa das chaves da tabela (uma linha de `ler` serve): elas acham o arquivo de onde
        a linha veio, e o manifesto dele diz o resto.
        """
        if self.banco is None:
            raise ValueError(
                "a linhagem precisa do banco (registro de coletas): Porta(pasta, banco)"
            )
        self._view(tabela, None)
        valores = {str(c): v for c, v in dict(linha).items()}
        chaves = [c for c in self.tabelas[tabela].chaves if c in valores] or list(
            valores
        )
        condicoes, parametros = _igualdades({c: valores[c] for c in chaves}, "c")
        parametros["arquivos"] = [
            a.as_posix() for a in arquivos_da_tabela(self.pasta, self.arquivos[tabela])
        ]
        achados = self.con.execute(
            "SELECT DISTINCT filename FROM read_parquet($arquivos, filename = true, "
            f"union_by_name = true) WHERE {' AND '.join(condicoes)}",
            parametros,
        ).fetchall()
        if len(achados) != 1:
            raise LookupError(
                f"{tabela}: a linha com {chaves} está em {len(achados)} arquivos (precisa de 1)"
            )
        arquivo = Path(achados[0][0])
        if tabela == POR_ANO_DE_BALANCO:
            return linhagem_da_linha(self.banco, arquivo.parent, pd.Series(valores))
        return linhagem_da_tabela(self.banco, arquivo)

    def carteira(self, cnpjs: Iterable[str], desde: object) -> pd.DataFrame:
        """Os eventos da rede (`eventos_da_rede`) dos CNPJs de uma carteira, públicos desde `desde`,
        com o CNPJ como veio da carteira (monitoramento de FIDC; ADR 0076, Emenda 1)."""
        carteira = []
        for valor in cnpjs:
            texto = cnpj_.SEPARADORES.sub("", str(valor).strip()).upper()
            raiz = texto if len(texto) == cnpj_.TAMANHO_DA_RAIZ else cnpj_.raiz(valor)
            if raiz is None:
                raise ValueError(f"carteira: {valor!r} não é um CNPJ")
            carteira.append({"cnpj_da_carteira": str(valor), "raiz": raiz})
        self.con.register(
            "_carteira", pd.DataFrame(carteira, columns=["cnpj_da_carteira", "raiz"])
        )
        try:
            return self.con.execute(
                "SELECT c.cnpj_da_carteira, e.* EXCLUDE (raiz), e.raiz FROM _carteira c "
                "JOIN eventos_da_rede e ON e.raiz = c.raiz "
                "WHERE e.publico_em >= CAST($desde AS DATE) "
                "ORDER BY e.publico_em, e.tabela, c.cnpj_da_carteira",
                {"desde": dia_de(desde)},
            ).df()
        finally:
            self.con.unregister("_carteira")


# --- as funções do módulo: abrem `<acervo>/base`, fazem uma coisa e fecham ----------------------
def abrir(
    pasta: Path | None = None,
    banco: sa.Connection | None = None,
    memoria: str | None = None,
    threads: int | None = None,
) -> Porta:
    """A porta da base em `pasta` (padrão: `<acervo>/base`)."""
    if pasta is None:
        raiz = acervo.pasta_do_acervo()
        if raiz is None:
            raise ValueError(
                "acervo desligado (TICKERLAB_ACERVO): a porta não tem base para ler"
            )
        pasta = raiz / "base"
    return Porta(pasta, banco, memoria=memoria, threads=threads)


def catalogo() -> dict:
    with abrir() as p:
        return p.catalogo()


def ler(
    tabela: str,
    versao: str | None = None,
    como_era_em: object = None,
    filtros: Mapping[str, object] | None = None,
    colunas: Sequence[str] | None = None,
) -> pd.DataFrame:
    with abrir() as p:
        return p.ler(tabela, versao, como_era_em, filtros, colunas)


def rede(
    id_ou_cnpj: str,
    tipos: Iterable[str] | None = None,
    como_era_em: object = None,
    profundidade: int = 1,
) -> Rede:
    with abrir() as p:
        return p.rede(id_ou_cnpj, tipos, como_era_em, profundidade)


def linhagem(tabela: str, linha: Mapping[str, object] | pd.Series) -> Linhagem:
    from src.banco.conexao import obter_engine  # o banco só quando a linhagem é pedida

    with obter_engine().connect() as banco, abrir(banco=banco) as p:
        return p.linhagem(tabela, linha)


def carteira(cnpjs: Iterable[str], desde: object) -> pd.DataFrame:
    with abrir() as p:
        return p.carteira(cnpjs, desde)
