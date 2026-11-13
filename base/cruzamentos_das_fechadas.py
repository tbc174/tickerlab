"""Os cruzamentos de empresa fechada da página inicial (linha 925, ordem da Diretoria de 13/11/2026).

Cada cartão é uma contagem medida pela porta (`base.porta`), só com o que era público no dia da medição, e
sai como "parte de um todo" (`CartaoMedido`); o texto, a fonte e a conta recolhida saem de `fatos_das_fechadas`,
um lugar só. Nenhum nome de empresa, sócio ou pessoa entra na medição: só contagens de raízes de CNPJ.

**Definições** (escritas antes de medir; valem para todos os cartões):

- **Empresa fechada:** a raiz de CNPJ que está na lista sem pessoa da Receita (`cnpj_empresas_pj`, linha 584: sem
  MEI, sem empresário individual e sem as naturezas de pessoa física) no retrato que valia no dia e que nunca
  entregou o formulário cadastral à CVM (`fca_geral`) até o dia;
- **segue ativa:** tem ao menos um estabelecimento em situação ativa (`02`) no mesmo retrato;
- **12 meses:** do dia da medição menos 12 meses (exclusive) até o dia (inclusive);
- **porte médio:** a Receita não tem "médio"; o mais perto que as colunas fecham é o porte `demais` (acima do
  limite da empresa de pequeno porte), e a indústria é a de transformação (CNAE principal da matriz nas divisões
  10 a 33);
- **três níveis:** a empresa tem uma sócia empresa, que tem uma sócia empresa, que tem uma sócia empresa, no
  quadro de sócios que valia no dia (`entradas_de_socio_pj`: entrou e não saiu até o dia).

**Travas:**

- tabela fora do catálogo, que a licença não deixa mostrar, cuja fonte não é vendável ou que não está montada na
  porta derruba o cartão inteiro (`motivo_da_tabela`): nenhum número parcial sai;
- só pessoa jurídica: as tabelas que também guardam pessoa (BNDES, Finep, RDE-IED) só contam a linha com a marca
  `trata_como_pessoa` falsa e a raiz que está na lista sem pessoa da Receita; na PGFN e no INPI, só CNPJ de 14
  dígitos;
- contagem abaixo de `MINIMO_DA_CONTAGEM` (a parte ou o todo) derruba o cartão;
- **sem olhar o futuro:** cada tabela só entra com o que já era público no dia (`publico_em`); a versão que vale
  é a mais nova já vista no dia (arquivista e históricos do CNPJ).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Protocol

import duckdb
import pandas as pd

from base.dicionario import TABELAS
from base.porta.duckdb import nome_da_view
from base.porta.rede import views
from src.banco.coletas import MOSTRAR, pode_usar, revenda_da_fonte

MINIMO_DA_CONTAGEM = (
    10  # contagem menor não sai: com poucas empresas, o número aponta para alguém
)
MINIMO_DE_CARTOES = (
    8  # menos que isso de pé, a fotografia não é gravada (ordem da Diretoria)
)
MESES_DA_JANELA = 12
ATIVA = "02"
PORTE_ACIMA_DA_EPP = "demais"
DIVISOES_DA_INDUSTRIA = (10, 33)  # a indústria de transformação no CNAE
FILIAIS_NA_JANELA = 3
BNDES_DESDE = date(2015, 1, 1)
DIGITOS_DO_CNPJ = 14
DIGITOS_DA_RAIZ = 8
RECUPERACAO_JUDICIAL = "recuperacao_judicial"

EMPRESAS, ESTABELECIMENTOS = "cnpj_empresas_pj", "cnpj_estabelecimentos_pj"
FCA = "fca_geral"
SIMPLES = "cnpj_simples_historico"
SOCIAS = "entradas_de_socio_pj"
BNDES, FINEP, RDE = "financiamentos_bndes", "financiamentos_finep", "bcb_rde_ied"
PGFN = "pgfn_divida"
ANVISA = "anvisa_por_empresa"
SITUACAO_ESPECIAL = "cnpj_situacao_especial"
MARCAS, PATENTES = "inpi_marcas_titulares", "inpi_patentes_depositantes"
SANCOES, CONTRATOS_DOS_TCES = "sancoes_cgu", "tce_pe_contratos"
# sem estas, não há empresa fechada nem ativa: todos os cartões caem
TABELAS_DA_BASE = (EMPRESAS, ESTABELECIMENTOS, FCA)


class PortaDeConsulta(Protocol):
    """O que a medição usa da porta: a conexão DuckDB com uma view por tabela."""

    con: duckdb.DuckDBPyConnection


@dataclass(frozen=True)
class CartaoMedido:
    """Um cartão de pé: `parte` das `todo` empresas."""

    chave: str
    parte: int
    todo: int


@dataclass(frozen=True)
class CartaoCaido:
    """Um cartão que não sai, com o motivo (vai para a Diretoria, nunca para a página)."""

    chave: str
    motivo: str


@dataclass(frozen=True)
class MedicaoDasFechadas:
    medido_em: str
    cartoes: tuple[CartaoMedido, ...]
    caidos: tuple[CartaoCaido, ...]


@dataclass(frozen=True)
class Grupo:
    chave: str
    pergunta: str
    cartoes: tuple[str, ...]


GRUPOS = (
    Grupo("crescendo", "Quem está crescendo", ("saiu_do_simples", "tres_filiais", "bndes_e_finep")),
    Grupo("se_mexeu", "Quem já se mexeu", ("socia_entrou", "capital_estrangeiro", "tres_niveis")),
    Grupo(
        "diligencia",
        "O que a diligência acharia",
        ("bndes_e_divida", "tce_e_sancao", "anvisa_e_divida"),
    ),
    Grupo("antes", "O sinal aparece antes", ("recuperacao_e_divida",)),
    Grupo("fora_do_balanco", "O que não está no balanço", ("industria_e_marca", "finep_e_patente")),
)  # fmt: skip


# --- as travas ----------------------------------------------------------------------------------------


def motivo_da_tabela(nome: str, catalogo: dict, na_porta: set[str]) -> str | None:
    """Por que a tabela derruba o cartão (None: pode contar). A ordem é a do mais grave."""
    tabela = TABELAS.get(nome)
    if nome not in catalogo["tabelas"] or tabela is None:
        return f"{nome}: fora do catálogo"
    familia = tabela.familia_da_fonte
    if not pode_usar(MOSTRAR, familia):
        return f"{nome}: a licença não deixa mostrar"
    if not revenda_da_fonte(familia).startswith("vendável"):
        return f"{nome}: a fonte não é vendável (só uso interno ou sem resposta)"
    if tabela.pessoa and "trata_como_pessoa" not in tabela.colunas:
        return f"{nome}: guarda pessoa sem a marca que separa a empresa"
    if nome_da_view(nome) not in na_porta:
        return f"{nome}: não está montada na porta"
    return None


def _motivo(tabelas: Sequence[str], catalogo: dict, na_porta: set[str]) -> str | None:
    motivos = [m for t in tabelas if (m := motivo_da_tabela(t, catalogo, na_porta))]
    return "; ".join(motivos) or None


# --- o SQL --------------------------------------------------------------------------------------------


def _v(tabela: str) -> str:
    return '"' + nome_da_view(tabela).replace('"', '""') + '"'


def _raiz_de_cnpj(coluna: str) -> str:
    """A raiz (8 dígitos) de um CNPJ de 14 dígitos, com ou sem pontuação; vazio se não tem 14."""
    digitos = f"regexp_replace(CAST({coluna} AS VARCHAR), '[^0-9]', '', 'g')"
    return f"CASE WHEN length({digitos}) = {DIGITOS_DO_CNPJ} THEN left({digitos}, {DIGITOS_DA_RAIZ}) END"


def _vigentes_do_arquivista(tabela: str, dia: str = "$dia") -> str:
    """A linha mais nova de cada id já vista no dia, que ainda constava na fonte e não é de pessoa."""
    return (
        f"SELECT * FROM (SELECT * FROM {_v(tabela)} WHERE publico_em <= CAST({dia} AS DATE) "
        "QUALIFY row_number() OVER (PARTITION BY id_na_fonte ORDER BY visto_em DESC) = 1) "
        "WHERE coalesce(consta, false) AND NOT coalesce(trata_como_pessoa, true)"
    )


def _raizes_com_contrato(tabela: str, desde: str | None = None) -> str:
    """As raízes com crédito contratado até o dia (e desde `desde`, se dado), só CNPJ de empresa."""
    raiz = _raiz_de_cnpj("cnpj")
    piso = "" if desde is None else f" AND contratado_em >= CAST({desde} AS DATE)"
    return (
        f"SELECT DISTINCT {raiz} AS raiz FROM ({_vigentes_do_arquivista(tabela)}) "
        f"WHERE contratado_em <= CAST($dia AS DATE){piso} AND {raiz} IS NOT NULL"
    )


def _raizes_do_inpi(tabela: str) -> str:
    raiz = _raiz_de_cnpj("cnpj")
    return f"SELECT DISTINCT {raiz} AS raiz FROM ({_vigentes_do_arquivista(tabela)}) WHERE {raiz} IS NOT NULL"


def _divida_no_retrato(dia: str = "$dia") -> str:
    """As raízes na lista da PGFN do retrato mais novo já público no dia (só CNPJ de 14 dígitos)."""
    raiz = _raiz_de_cnpj("cnpj")
    return (
        f"SELECT DISTINCT {raiz} AS raiz FROM {_v(PGFN)} WHERE publico_em <= CAST({dia} AS DATE) "
        f"AND data_do_retrato = (SELECT max(data_do_retrato) FROM {_v(PGFN)} "
        f"WHERE publico_em <= CAST({dia} AS DATE)) AND {raiz} IS NOT NULL"
    )


def _simples_em(dia: str) -> str:
    """A opção pelo Simples de cada raiz como a Receita a publicava no dia (a versão mais nova já pública)."""
    return (
        f"SELECT cnpj_basico AS raiz, optante_simples, consta FROM {_v(SIMPLES)} "
        f"WHERE publico_em <= CAST({dia} AS DATE) "
        "QUALIFY row_number() OVER (PARTITION BY cnpj_basico ORDER BY mes_do_retrato DESC) = 1"
    )


def _parte_e_todo(todo: str, parte: str) -> str:
    """`todo` e `parte` são SQL de raízes (`raiz`); a parte só conta dentro do todo."""
    return (
        f"WITH todo AS ({todo}), parte AS ({parte}) SELECT (SELECT count(*) FROM todo), "
        "(SELECT count(*) FROM todo WHERE raiz IN (SELECT raiz FROM parte))"
    )


ATIVAS = "SELECT raiz FROM ativas"


def _saiu_do_simples() -> str:
    return _parte_e_todo(
        f"SELECT a.raiz FROM ativas a JOIN ({_simples_em('$dia12')}) s USING (raiz) "
        "WHERE coalesce(s.consta, false) AND s.optante_simples",
        f"SELECT raiz FROM ({_simples_em('$dia')}) WHERE coalesce(consta, false) "
        "AND optante_simples IS FALSE",
    )


def _tres_filiais() -> str:
    return _parte_e_todo(
        ATIVAS,
        f"SELECT cnpj_basico AS raiz FROM {_v(ESTABELECIMENTOS)} WHERE mes_do_retrato = $mes "
        "AND NOT coalesce(matriz, true) AND data_inicio_atividade > CAST($dia12 AS DATE) "
        f"AND data_inicio_atividade <= CAST($dia AS DATE) GROUP BY 1 HAVING count(*) >= {FILIAIS_NA_JANELA}",
    )


def _bndes_e_finep() -> str:
    return _parte_e_todo(
        f"SELECT raiz FROM ativas WHERE raiz IN ({_raizes_com_contrato(BNDES)})",
        _raizes_com_contrato(FINEP),
    )


def _socia_entrou() -> str:
    return _parte_e_todo(
        ATIVAS,
        f"SELECT DISTINCT cnpj_basico AS raiz FROM {_v(SOCIAS)} WHERE movimento = 'entrou' "
        "AND publico_em <= CAST($dia AS DATE) AND data_entrada > CAST($dia12 AS DATE) "
        "AND data_entrada <= CAST($dia AS DATE)",
    )


def _capital_estrangeiro() -> str:
    return _parte_e_todo(
        ATIVAS,
        f"SELECT DISTINCT cnpj_basico AS raiz FROM ({_vigentes_do_arquivista(RDE)})",
    )


def _socias_no_dia() -> str:
    """Quem era sócia empresa de quem no dia: o último movimento já público do par é a entrada."""
    return (
        f"SELECT cnpj_basico AS empresa, raiz_socio_pj AS socia FROM {_v(SOCIAS)} "
        "WHERE movimento IN ('entrou', 'saiu') AND publico_em <= CAST($dia AS DATE) "
        "AND cnpj_basico <> raiz_socio_pj QUALIFY row_number() OVER (PARTITION BY cnpj_basico, "
        "raiz_socio_pj ORDER BY mes_do_retrato DESC, movimento = 'saiu' DESC) = 1 AND movimento = 'entrou'"
    )


def _tres_niveis() -> str:
    pares = _socias_no_dia()
    return (
        f"WITH pares AS ({pares}), "
        "um AS (SELECT DISTINCT empresa AS raiz FROM pares), "
        "dois AS (SELECT DISTINCT empresa AS raiz FROM pares WHERE socia IN (SELECT raiz FROM um)), "
        "tres AS (SELECT DISTINCT empresa AS raiz FROM pares WHERE socia IN (SELECT raiz FROM dois)) "
        "SELECT (SELECT count(*) FROM ativas WHERE raiz IN (SELECT raiz FROM um)), "
        "(SELECT count(*) FROM ativas WHERE raiz IN (SELECT raiz FROM tres))"
    )


def _bndes_e_divida() -> str:
    return _parte_e_todo(
        f"SELECT raiz FROM ativas WHERE raiz IN ({_raizes_com_contrato(BNDES, '$bndes_desde')})",
        _divida_no_retrato(),
    )


def _anvisa_e_divida() -> str:
    return _parte_e_todo(
        f"SELECT raiz FROM ativas WHERE raiz IN (SELECT cnpj_basico FROM {_v(ANVISA)} "
        "WHERE publico_em <= CAST($dia AS DATE) QUALIFY row_number() OVER "
        "(PARTITION BY cnpj_basico ORDER BY publico_em DESC) = 1 AND coalesce(afe_ativos, 0) > 0)",
        _divida_no_retrato(),
    )


def _recuperacao_e_divida() -> str:
    """A entrada em recuperação judicial (a data da situação especial na Receita) e a dívida que a lista da
    PGFN já mostrava naquele dia, inscrita ao menos 12 meses antes. Sem retrato da PGFN público na entrada,
    a empresa fica de fora (não dá para saber sem olhar o futuro)."""
    raiz = _raiz_de_cnpj("p.cnpj")
    return (
        "WITH rj AS (SELECT cnpj_basico AS raiz, min(CAST(data_situacao_especial AS DATE)) AS entrada "
        f"FROM {_v(SITUACAO_ESPECIAL)} WHERE rotulo = '{RECUPERACAO_JUDICIAL}' "
        "AND publico_em <= CAST($dia AS DATE) AND cnpj_basico IN (SELECT raiz FROM fechadas) GROUP BY 1), "
        f"retratos AS (SELECT data_do_retrato, min(publico_em) AS publico_em FROM {_v(PGFN)} GROUP BY 1), "
        "com_retrato AS (SELECT rj.raiz, rj.entrada, (SELECT max(r.data_do_retrato) FROM retratos r "
        "WHERE r.publico_em <= rj.entrada) AS retrato FROM rj WHERE rj.entrada <= CAST($dia AS DATE)), "
        f"devia AS (SELECT DISTINCT c.raiz FROM com_retrato c JOIN {_v(PGFN)} p "
        f"ON p.data_do_retrato = c.retrato AND {raiz} = c.raiz "
        "AND p.publico_em <= c.entrada "
        f"AND CAST(p.primeira_inscricao AS DATE) <= c.entrada - INTERVAL {MESES_DA_JANELA} MONTH) "
        "SELECT (SELECT count(*) FROM com_retrato WHERE retrato IS NOT NULL), (SELECT count(*) FROM devia)"
    )


def _industria_e_marca() -> str:
    menor, maior = DIVISOES_DA_INDUSTRIA
    return _parte_e_todo(
        f"SELECT a.raiz FROM ativas a JOIN fechadas f USING (raiz) WHERE f.porte = '{PORTE_ACIMA_DA_EPP}' "
        f"AND a.raiz IN (SELECT cnpj_basico FROM {_v(ESTABELECIMENTOS)} WHERE mes_do_retrato = $mes "
        f"AND matriz AND TRY_CAST(left(cnae_principal, 2) AS INTEGER) BETWEEN {menor} AND {maior})",
        _raizes_do_inpi(MARCAS),
    )


def _finep_e_patente() -> str:
    return _parte_e_todo(
        f"SELECT raiz FROM ativas WHERE raiz IN ({_raizes_com_contrato(FINEP)})",
        _raizes_do_inpi(PATENTES),
    )


@dataclass(frozen=True)
class Molde:
    """Um cartão: as tabelas que ele lê (além das da base) e o SQL que devolve (todo, parte)."""

    chave: str
    tabelas: tuple[str, ...]
    sql: Callable[[], str] | None


MOLDES = (
    Molde("saiu_do_simples", (SIMPLES,), _saiu_do_simples),
    Molde("tres_filiais", (), _tres_filiais),
    Molde("bndes_e_finep", (BNDES, FINEP), _bndes_e_finep),
    Molde("socia_entrou", (SOCIAS,), _socia_entrou),
    Molde("capital_estrangeiro", (RDE,), _capital_estrangeiro),
    Molde("tres_niveis", (SOCIAS,), _tres_niveis),
    Molde("bndes_e_divida", (BNDES, PGFN), _bndes_e_divida),
    # a lista de punidas da CGU é só de uso interno: a trava derruba o cartão antes de qualquer SQL
    Molde("tce_e_sancao", (CONTRATOS_DOS_TCES, SANCOES), None),
    Molde("anvisa_e_divida", (ANVISA, PGFN), _anvisa_e_divida),
    Molde("recuperacao_e_divida", (SITUACAO_ESPECIAL, PGFN), _recuperacao_e_divida),
    Molde("industria_e_marca", (MARCAS,), _industria_e_marca),
    Molde("finep_e_patente", (FINEP, PATENTES), _finep_e_patente),
)


# --- a medição ----------------------------------------------------------------------------------------


def _mes_do_retrato(cursor: duckdb.DuckDBPyConnection, dia: str) -> str | None:
    """O retrato da Receita mais novo já público no dia, o mesmo nas duas listas sem pessoa."""
    meses = [
        cursor.execute(
            f"SELECT max(mes_do_retrato) FROM {_v(t)} WHERE publico_em <= CAST($dia AS DATE)",
            {"dia": dia},
        ).fetchone()
        for t in (EMPRESAS, ESTABELECIMENTOS)
    ]
    valores = [None if m is None else m[0] for m in meses]
    return None if None in valores else min(valores)  # type: ignore[type-var]


def _montar_a_base(
    cursor: duckdb.DuckDBPyConnection, parametros: Mapping[str, object]
) -> None:
    """As empresas fechadas e as ativas no dia, uma vez só, para todos os cartões."""
    raiz_da_cvm = _raiz_de_cnpj("cnpj")
    cursor.execute(
        "CREATE OR REPLACE TEMP TABLE fechadas AS SELECT cnpj_basico AS raiz, any_value(porte) AS porte "
        f"FROM {_v(EMPRESAS)} e WHERE mes_do_retrato = $mes AND NOT EXISTS (SELECT 1 FROM {_v(FCA)} "
        f"WHERE publico_em <= CAST($dia AS DATE) AND {raiz_da_cvm} = e.cnpj_basico) GROUP BY 1",
        {k: parametros[k] for k in ("mes", "dia")},
    )
    cursor.execute(
        "CREATE OR REPLACE TEMP TABLE ativas AS SELECT DISTINCT cnpj_basico AS raiz "
        f"FROM {_v(ESTABELECIMENTOS)} WHERE mes_do_retrato = $mes AND situacao_cadastral = '{ATIVA}' "
        "AND cnpj_basico IN (SELECT raiz FROM fechadas)",
        {"mes": parametros["mes"]},
    )


def _parametros_usados(sql: str, parametros: Mapping[str, object]) -> dict[str, object]:
    return {k: v for k, v in parametros.items() if f"${k}" in sql}


def _medir_um(
    cursor: duckdb.DuckDBPyConnection, molde: Molde, parametros: Mapping[str, object]
) -> CartaoMedido | CartaoCaido:
    assert molde.sql is not None
    sql = molde.sql()
    linha = cursor.execute(sql, _parametros_usados(sql, parametros)).fetchone()
    todo, parte = (0, 0) if linha is None else (int(linha[0] or 0), int(linha[1] or 0))
    if min(todo, parte) < MINIMO_DA_CONTAGEM:
        return CartaoCaido(molde.chave, f"contagem abaixo de {MINIMO_DA_CONTAGEM}")
    return CartaoMedido(molde.chave, parte=parte, todo=todo)


def doze_meses_antes(dia: date) -> date:
    return (pd.Timestamp(dia) - pd.DateOffset(months=MESES_DA_JANELA)).date()


def medir_fechadas(
    porta: PortaDeConsulta, catalogo: dict, ate: date
) -> MedicaoDasFechadas:
    """Mede os cartões de empresa fechada pela porta, só com o que era público em `ate`. O cartão cuja tabela
    não passa nas travas, ou cuja contagem fica abaixo do mínimo, cai com o motivo; os outros seguem."""
    cursor = porta.con.cursor()
    try:
        return _medir(cursor, catalogo, ate)
    finally:
        cursor.close()


def _medir(
    cursor: duckdb.DuckDBPyConnection, catalogo: dict, ate: date
) -> MedicaoDasFechadas:
    na_porta = views(cursor)
    dia = ate.isoformat()
    motivo_da_base = _motivo(TABELAS_DA_BASE, catalogo, na_porta)
    mes = None if motivo_da_base else _mes_do_retrato(cursor, dia)
    if motivo_da_base is None and mes is None:
        motivo_da_base = "sem retrato da Receita público no dia"
    parametros = {
        "dia": dia,
        "dia12": doze_meses_antes(ate).isoformat(),
        "mes": mes,
        "bndes_desde": BNDES_DESDE.isoformat(),
    }
    if motivo_da_base is None:
        _montar_a_base(cursor, parametros)
    cartoes, caidos = [], []
    for molde in MOLDES:
        motivo = motivo_da_base or _motivo(molde.tabelas, catalogo, na_porta)
        if motivo is None and molde.sql is None:
            motivo = "o molde não fecha com as colunas"
        if motivo is not None:
            caidos.append(CartaoCaido(molde.chave, motivo))
            continue
        medido = _medir_um(cursor, molde, parametros)
        (cartoes if isinstance(medido, CartaoMedido) else caidos).append(medido)
    return MedicaoDasFechadas(
        medido_em=dia, cartoes=tuple(cartoes), caidos=tuple(caidos)
    )


def de_pe_o_bastante(medicao: MedicaoDasFechadas) -> bool:
    return len(medicao.cartoes) >= MINIMO_DE_CARTOES


def fechadas_da_fotografia(dados: Mapping) -> MedicaoDasFechadas:
    """A medição gravada de volta; campo a mais ou a menos é erro."""
    return MedicaoDasFechadas(
        medido_em=dados["medido_em"],
        cartoes=tuple(CartaoMedido(**c) for c in dados["cartoes"]),
        caidos=tuple(CartaoCaido(**c) for c in dados["caidos"]),
    )


def para_a_fotografia(medicao: MedicaoDasFechadas) -> dict:
    return asdict(medicao)
