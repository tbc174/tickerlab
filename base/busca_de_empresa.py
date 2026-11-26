"""Achar uma empresa pelo nome (linhas 1033 e 1037): o que o modo dono e o conector procuram do mesmo jeito.

Procura na razão social, no nome fantasia e na razão social antiga (`cnpj_nomes_pj`, `base/nomes_de_empresa.py`),
com UF, município e CNAE **da matriz**. É busca de **empresa**: as listas não têm empresário individual nem MEI,
e sócio ou pessoa não se acha por aqui.

**Ordem:** o nome igual ao pedido (sem "LTDA", "SA"...) vem antes; depois o que começa por ele; depois o que tem
todas as palavras inteiras; por último o que as tem como pedaço de palavra ("rometa" dentro de "eletrometalurgica").
Dentro de cada grupo, a ativa antes da baixada e a de maior capital. Se nenhum nome tem todas as palavras, cada
uma é procurada sozinha e os achados se alternam (`por_palavra`): quem digita duas marcas acha as duas.

**Sem a tabela de nomes** (base sem a carga, ou nada publicado no dia) a busca é só pela razão social, como antes
(`com_outros_nomes` falso). **Sem olhar o futuro:** só entra o retrato já público no dia.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import zip_longest

import pandas as pd

from base import nomes_de_empresa as nomes
from base.porta import Porta
from base.porta.rede import views

NOMES = "cnpj_nomes_pj"
EMPRESAS = "cnpj_empresas_pj"
ESTABELECIMENTOS = "cnpj_estabelecimentos_pj"
LIMITE_PADRAO = 20
MAXIMO_DE_PALAVRAS = 6
MINIMO_DE_LETRAS = 3  # "ltd" não é um nome: seria a base inteira
DIGITOS_DE_UM_DOCUMENTO = 8  # o nome com tantos números é um CNPJ ou um CPF
CARACTERES_DO_NOME = re.compile(r"^[^\W_&.'/-]*(?:[&.'/-]+[^\W_&.'/-]*)*$")
ATIVA = "02"
COLUNAS_DA_LINHA = (
    "cnpj", "cnpj_basico", "razao_social", "casou_com", "casou_nome", "trocado_em_mes",
    "situacao_cadastral", "cnae_principal", "uf", "municipio", "data_inicio_atividade",
    "porte", "capital_social", "n_estabelecimentos", "mesma_razao_social_de",
)  # fmt: skip


class EntradaInvalida(ValueError):
    """Pedido fora da forma; a mensagem não repete o que entrou."""


@dataclass(frozen=True)
class Busca:
    """O que a busca achou: as linhas (até o limite), quantas empresas casaram e de que retrato."""

    linhas: list[dict[str, object]]
    achadas: int
    mes_do_retrato: str | None
    com_outros_nomes: bool
    por_palavra: bool = False


@dataclass(frozen=True)
class _Filtros:
    uf: str | None
    municipios: Sequence[str]
    cnaes: Sequence[str]
    limite: int


def palavras_do_nome(nome: str | None) -> list[str]:
    """As palavras do pedido, como são procuradas; `EntradaInvalida` se não é um nome de empresa."""
    digitadas = (nome or "").split()
    if not digitadas:
        raise EntradaInvalida(
            "diga o nome da empresa, ou parte dele (como 'padaria estrela')"
        )
    if len(digitadas) > MAXIMO_DE_PALAVRAS:
        raise EntradaInvalida(f"o nome pode ter até {MAXIMO_DE_PALAVRAS} palavras")
    if not all(CARACTERES_DO_NOME.match(p) for p in digitadas):
        raise EntradaInvalida(
            "o nome só pode ter letras, números, espaço e os sinais & . ' - /"
        )
    if sum(c.isdigit() for c in "".join(digitadas)) >= DIGITOS_DE_UM_DOCUMENTO:
        raise EntradaInvalida(
            "isto parece um CNPJ ou um CPF: a busca é pelo nome da empresa; para o CNPJ, abra a ficha dele"
        )
    palavras = nomes.normalizar(" ".join(digitadas)).split()
    if sum(len(p) for p in palavras) < MINIMO_DE_LETRAS:
        raise EntradaInvalida(
            f"o nome precisa de pelo menos {MINIMO_DE_LETRAS} letras ou números"
        )
    return palavras


def _mes_publico(porta: Porta, tabela: str, dia: date) -> str | None:
    linha = (
        porta.con.cursor()
        .execute(
            f'SELECT max(mes_do_retrato) FROM "{tabela}" WHERE publico_em <= CAST($dia AS DATE)',
            {"dia": dia.isoformat()},
        )
        .fetchone()
    )
    return None if linha is None or linha[0] is None else str(linha[0])


def _meses(porta: Porta, dia: date) -> tuple[str | None, str | None, str | None]:
    """O mês já público de cada lista (empresas, estabelecimentos, nomes); None quando não há."""
    existem = views(porta.con)
    return tuple(  # type: ignore[return-value]
        _mes_publico(porta, tabela, dia) if tabela in existem else None
        for tabela in (EMPRESAS, ESTABELECIMENTOS, NOMES)
    )


def _do_retrato(parametro: str) -> str:
    return f"publico_em <= CAST($dia AS DATE) AND mes_do_retrato = ${parametro}"


def _fontes_dos_nomes(mes: str, mes_dos_nomes: str | None) -> list[str]:
    """As consultas que dão (raiz, tipo, nome, nome para busca, mês da troca) dos nomes a procurar.

    A razão social vem da tabela de nomes só quando ela é do mesmo mês da lista de empresas; senão vem da lista
    de hoje (a tabela atrasada não esconde empresa nova nem nome trocado), e da de nomes ficam os outros dois.
    """
    consultas = []
    em_dia = mes_dos_nomes == mes
    if mes_dos_nomes is not None:
        so_os_outros = "" if em_dia else f" AND tipo_de_nome <> '{nomes.RAZAO_SOCIAL}'"
        consultas.append(
            "SELECT cnpj_basico, tipo_de_nome, nome_de_empresa, nome_para_busca, trocado_em_mes "
            f'FROM "{NOMES}" WHERE {_do_retrato("mes_dos_nomes")}{so_os_outros}'
        )
    if not em_dia:
        normalizada = "trim(regexp_replace(strip_accents(upper(razao_social)), '[^A-Z0-9]+', ' ', 'g'))"
        consultas.append(
            f"SELECT cnpj_basico, '{nomes.RAZAO_SOCIAL}' AS tipo_de_nome, razao_social AS nome_de_empresa, "
            f"{normalizada} AS nome_para_busca, '' AS trocado_em_mes FROM empresas"
        )
    return consultas


def _casados(palavras: Sequence[str]) -> str:
    """Os nomes que têm todas as palavras, com a classe da ordem (0 igual, 1 começa, 2 inteiras, 3 pedaço)."""
    tem = " AND ".join(
        f"contains(nome_para_busca, $p{i})" for i in range(len(palavras))
    )
    inteiras = " AND ".join(
        f"contains(' ' || nome_para_busca || ' ', ' ' || $p{i} || ' ')"
        for i in range(len(palavras))
    )
    sem_forma = f"regexp_replace(nome_para_busca, '{nomes.FORMA_JURIDICA_NO_FIM}', '')"
    return (
        f"SELECT *, CASE WHEN {sem_forma} = $pedido THEN 0 "
        "WHEN starts_with(nome_para_busca || ' ', $pedido || ' ') THEN 1 "
        f"WHEN {inteiras} THEN 2 ELSE 3 END AS classe FROM todos WHERE {tem}"
    )


def _condicoes_da_matriz(filtros: _Filtros, parametros: dict[str, object]) -> str:
    condicoes = []
    if filtros.uf:
        condicoes.append("uf = $uf")
        parametros["uf"] = filtros.uf
    if filtros.municipios:
        condicoes.append("list_contains($municipios, municipio)")
        parametros["municipios"] = list(filtros.municipios)
    if filtros.cnaes:
        prefixos = []
        for i, cnae in enumerate(filtros.cnaes):
            prefixos.append(f"starts_with(cnae_principal, $cnae{i})")
            parametros[f"cnae{i}"] = cnae
        condicoes.append(f"({' OR '.join(prefixos)})")
    return "".join(f" AND {c}" for c in condicoes)


def _consultar(
    porta: Porta,
    palavras: Sequence[str],
    filtros: _Filtros,
    dia: date,
    meses: tuple[str, str, str | None],
) -> pd.DataFrame:
    mes, mes_das_matrizes, mes_dos_nomes = meses
    pedido = nomes.sem_forma_juridica(" ".join(palavras))
    parametros: dict[str, object] = {
        "dia": dia.isoformat(), "mes": mes, "mes_das_matrizes": mes_das_matrizes,
        "pedido": pedido, "limite": filtros.limite,
    }  # fmt: skip
    if mes_dos_nomes is not None:
        parametros["mes_dos_nomes"] = mes_dos_nomes
    parametros.update({f"p{i}": p for i, p in enumerate(palavras)})
    da_matriz = _condicoes_da_matriz(filtros, parametros)
    ordem_do_tipo = f"CASE tipo_de_nome WHEN '{nomes.RAZAO_SOCIAL}' THEN 0 WHEN '{nomes.NOME_FANTASIA}' THEN 1 ELSE 2 END"
    sql = f"""
    WITH empresas AS (
        SELECT cnpj_basico, razao_social, porte, capital_social, n_estabelecimentos
        FROM "{EMPRESAS}" WHERE {_do_retrato("mes")}
    ),
    todos AS ({" UNION ALL ".join(_fontes_dos_nomes(mes, mes_dos_nomes))}),
    casados AS ({_casados(palavras)}),
    melhor AS (
        SELECT * FROM casados QUALIFY row_number() OVER (
            PARTITION BY cnpj_basico ORDER BY classe, {ordem_do_tipo}, nome_de_empresa) = 1
    ),
    achadas AS (
        SELECT m.*, e.razao_social, e.porte, e.capital_social, e.n_estabelecimentos,
            count(*) OVER (PARTITION BY strip_accents(upper(e.razao_social))) - 1 AS mesma_razao_social_de
        FROM melhor m JOIN empresas e USING (cnpj_basico)
    ),
    matrizes AS (
        SELECT cnpj, cnpj_basico, situacao_cadastral, data_inicio_atividade, cnae_principal, uf, municipio
        FROM "{ESTABELECIMENTOS}"
        WHERE {_do_retrato("mes_das_matrizes")} AND matriz{da_matriz}
            AND cnpj_basico IN (SELECT cnpj_basico FROM achadas)
    )
    SELECT m.cnpj, a.cnpj_basico, a.razao_social, a.tipo_de_nome AS casou_com, a.nome_de_empresa AS casou_nome,
        a.trocado_em_mes, m.situacao_cadastral, m.cnae_principal, m.uf, m.municipio, m.data_inicio_atividade,
        a.porte, a.capital_social, a.n_estabelecimentos, a.mesma_razao_social_de,
        count(*) OVER () AS total
    FROM achadas a JOIN matrizes m USING (cnpj_basico)
    ORDER BY a.classe, lpad(m.situacao_cadastral, 2, '0') <> '{ATIVA}', a.capital_social DESC NULLS LAST, m.cnpj
    LIMIT $limite
    """
    usados = {k: v for k, v in parametros.items() if re.search(rf"\${k}\b", sql)}
    return porta.con.cursor().execute(sql, usados).df()


def _linhas(achadas: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {coluna: (None if pd.isna(linha[coluna]) else linha[coluna]) for coluna in COLUNAS_DA_LINHA}
        for _, linha in achadas.iterrows()
    ]  # fmt: skip


def _por_palavra(
    porta: Porta,
    palavras: Sequence[str],
    filtros: _Filtros,
    dia: date,
    meses: tuple[str, str, str | None],
) -> tuple[list[dict[str, object]], int]:
    """Cada palavra sozinha, com os achados alternados (o melhor de cada uma, depois o segundo de cada uma)."""
    listas, total = [], 0
    for palavra in (p for p in palavras if len(p) >= MINIMO_DE_LETRAS):
        achadas = _consultar(porta, [palavra], filtros, dia, meses)
        total += 0 if achadas.empty else int(achadas["total"].iloc[0])
        listas.append(_linhas(achadas))
    alternadas = [linha for rodada in zip_longest(*listas) for linha in rodada if linha]
    sem_repetir = {linha["cnpj"]: linha for linha in reversed(alternadas)}
    em_ordem = [c for c in dict.fromkeys(linha["cnpj"] for linha in alternadas)]
    return [sem_repetir[c] for c in em_ordem][: filtros.limite], total


def procurar(
    porta: Porta,
    *,
    palavras: Sequence[str],
    dia: date,
    uf: str | None = None,
    municipios: Sequence[str] = (),
    cnaes: Sequence[str] = (),
    limite: int = LIMITE_PADRAO,
) -> Busca:
    """As empresas cujo nome tem as `palavras` (de `palavras_do_nome`), na ordem do módulo, como eram em `dia`."""
    mes, mes_das_matrizes, mes_dos_nomes = _meses(porta, dia)
    com_outros = mes_dos_nomes is not None
    if mes is None or mes_das_matrizes is None:
        return Busca([], 0, None, com_outros)
    meses = (mes, mes_das_matrizes, mes_dos_nomes)
    filtros = _Filtros(uf, municipios, cnaes, limite)
    achadas = _consultar(porta, palavras, filtros, dia, meses)
    if not achadas.empty:
        total = int(achadas["total"].iloc[0])
        return Busca(_linhas(achadas), total, mes, com_outros)
    if len(palavras) < 2:
        return Busca([], 0, mes, com_outros)
    linhas, total = _por_palavra(porta, palavras, filtros, dia, meses)
    return Busca(linhas, total, mes, com_outros, por_palavra=bool(linhas))
