"""As empresas na API externa (B-32a, PR 4, e linha 686): o cadastro da Receita pelo portão, como era na data.

`LeitorDeEmpresas(porta, permitido).empresa(cnpj, como_era_em)` devolve, em tipos simples e com as chaves em
português (a rota traduz na saída), a situação cadastral do estabelecimento no retrato mensal da Receita mais
novo que já era público em `como_era_em`. O retrato do mês vale pelo último dia do mês em que foi baixado (a
porta faz o corte): o CNPJ baixado em junho e publicado em julho continua ativo até 31/07.

Da empresa (a raiz do CNPJ) saem também a razão social, a natureza jurídica e a opção pelo Simples, cada uma
da versão do histórico datado (`cnpj_empresas_historico` e `cnpj_simples_historico`, `base/cnpj_historico.py`)
que já era pública em `como_era_em`, com a data dela no envelope ("pode 8" do Tiago em 05/11/2026). Campo sem
versão pública na data, de raiz que tinha saído do arquivo ou de tabela que a base não tem fica de fora; a
situação cadastral continua sendo a âncora: sem ela, a empresa não sai.

Sem o histórico do nome na base (o VPS não o tem, linha 861), a razão social e a natureza saem do retrato da
lista sem pessoa (`cnpj_empresas_pj`), na leitura estreita do "sem olhar o futuro": só se o retrato já era
público em `como_era_em` (a porta corta pelo último dia do mês) e a raiz está nele uma só vez, com natureza
informada que não é de pessoa. A resposta diz de que retrato saíram (`mes_do_retrato_do_cadastro`): é o retrato
daquele mês, não "como era" no dia. Com o histórico na base, ele manda e o retrato não é lido. O Simples não tem
lista sem pessoa: sem o histórico dele, não sai.

Pessoa não sai (ADR 0108 D2.2). Quando a rede conhece o CNPJ (algum identificador dela tem o CNPJ ou a raiz),
decide ela: só sai se ela o conhece como uma só empresa que não trata como pessoa (MEI, empresário individual e
as naturezas de pessoa física, `trata_como_pessoa`); fundo ou outra coisa e conflito (o mesmo CNPJ em duas
entidades) saem como `not_available`, igual a um CNPJ que não existe, e **não** caem para as listas. A rede
usada é a de hoje: quem hoje se sabe pessoa não sai nem numa data em que ainda não se sabia.

O que a rede não conhece (a empresa fechada: ela só tem as companhias da CVM e dos reguladores, linha 843) e,
onde ela não está, qualquer CNPJ, decidem as listas sem pessoa da Receita do retrato mais novo, o mesmo nas
duas (linha 584): o estabelecimento tem de estar em `cnpj_estabelecimentos_pj` (sem MEI) e a raiz em
`cnpj_empresas_pj` (sem empresário individual nem grupo 4), com a natureza informada (a natureza vazia conta
como pessoa, como na rede desde a linha 787). Sem a rede nem as duas listas, nada sai.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.cnpj import SEPARADORES
from base.porta import Porta
from base.porta.duckdb import nome_da_view
from base.porta.rede import ID_DE_ENTIDADE, OUTROS_SISTEMAS, resolver, views
from base.rede.entidades import natureza_de_pessoa
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo

CONJUNTO = "companies"
TABELA = "cnpj_situacao_cadastral"
FONTE = "rfb-cnpj"
CAMPOS = (
    "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao", "matriz", "mes_do_retrato",
)  # fmt: skip
PUBLICADO_EM = (
    "publico_em"  # o apelido da porta: o último dia do mês em que o retrato foi baixado
)
EMPRESA = "empresa"
PREFIXO_DE_PESSOA = "P"  # id de pessoa na rede (`base/rede`): nunca sai
RAIZ = "cnpj_basico"
MES = "mes_do_retrato"
CONSTA = "consta"
TAMANHO_DA_RAIZ = 8
# as listas sem pessoa de `scripts/montar_empresas_pj.py`, a trava onde a rede não está
LISTA_DE_EMPRESAS = "cnpj_empresas_pj"
LISTA_DE_ESTABELECIMENTOS = "cnpj_estabelecimentos_pj"
_LISTA = "(SELECT unnest(${}))"  # um parâmetro com lista, como tabela (junção por hash)


@dataclass(frozen=True)
class Historico:
    """Uma tabela do histórico datado do CNPJ e os campos dela que a rota serve."""

    tabela: str
    campos: tuple[str, ...]


HISTORICOS = (
    Historico("cnpj_empresas_historico", ("razao_social", "natureza_juridica")),
    Historico(
        "cnpj_simples_historico",
        ("optante_simples", "data_opcao_simples", "data_exclusao_simples"),
    ),
)
HISTORICO_DO_NOME = HISTORICOS[0].tabela
# sem o histórico do nome: do retrato da lista sem pessoa, com o mês dele (linha 861)
CAMPOS_DO_RETRATO_PJ = HISTORICOS[0].campos
RETRATO_DO_CADASTRO = "mes_do_retrato_do_cadastro"
TABELAS = (TABELA, *(historico.tabela for historico in HISTORICOS), LISTA_DE_EMPRESAS)
CAMPOS_DATADOS = tuple(campo for historico in HISTORICOS for campo in historico.campos)
DATAS = ("data_situacao_cadastral", "data_opcao_simples", "data_exclusao_simples")
SIM_OU_NAO = ("matriz", "optante_simples")


@dataclass(frozen=True)
class EmpresaServida:
    """O que sai de uma empresa: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _simples(nome: str, valor: object) -> object:
    """O valor da base num tipo que vira JSON: data em ISO, booleano do NumPy em booleano, vazio em None."""
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    if nome in DATAS:
        return pd.Timestamp(valor).date().isoformat()  # type: ignore[arg-type]
    if nome in SIM_OU_NAO:
        return bool(valor)
    return str(valor)


def _sim(valor: object) -> bool:
    """Verdadeiro, ou vazio (que conta como verdadeiro: na dúvida, é pessoa)."""
    return valor is None or bool(pd.isna(valor)) or bool(valor)  # type: ignore[arg-type]


def e_empresa(porta: Porta, cnpj: str) -> bool:
    """O CNPJ (14 caracteres, sem pontuação) é de uma só empresa que não é pessoa; qualquer dúvida é não.

    A rede de hoje decide se conhece o CNPJ (como pessoa, conflito ou outra coisa que não empresa, não); o
    que ela não conhece decidem as listas sem pessoa da Receita, se a porta as tem; sem nenhuma, não (linha
    843: a rede do VPS só tem as companhias da CVM e dos reguladores, e a empresa fechada vem das listas).
    Também serve à rota de crédito (`conjuntos/credito.py`): as duas tiram pessoa do mesmo jeito. Para
    muitos CNPJs de uma vez, `e_empresas`: a mesma resposta (há teste), sem uma ida à base por CNPJ."""
    existem = views(porta.con)
    if "entidades" in existem:
        pela_rede = _pela_rede(porta, cnpj)
        if pela_rede is not None:
            return pela_rede
    if {LISTA_DE_EMPRESAS, LISTA_DE_ESTABELECIMENTOS} <= existem:
        return _pelas_listas_sem_pessoa(porta, cnpj)
    return False


def _pares_de_mencao(cnpj: str) -> list[tuple[str, str]]:
    """Os (sistema, valor) em que a rede pode conhecer o texto: os mesmos que o `resolver` procura."""
    texto = SEPARADORES.sub("", cnpj.strip()).upper()
    return [
        ("cnpj", texto),
        ("cnpj_raiz", texto[:TAMANHO_DA_RAIZ]),
        *((sistema, texto) for sistema in OUTROS_SISTEMAS),
    ]


def _a_rede_menciona(porta: Porta, cnpj: str) -> bool:
    """Algum identificador da rede tem o CNPJ, a raiz dele ou o texto dele em outro sistema (os mesmos que o
    `resolver` procura): a rede conhece o CNPJ, ainda que em mais de uma entidade. Sem a view `identificadores`
    (rede pela metade), conta como conhecido: na dúvida, não."""
    if "identificadores" not in views(porta.con):
        return True
    achados = porta.con.execute(
        "SELECT count(*) FROM identificadores WHERE list_contains($pares, [sistema, valor])",
        {"pares": [list(par) for par in _pares_de_mencao(cnpj)]},
    ).fetchone()
    return achados != (0,)


def _e_uma_empresa(id_entidade: str | None, achadas: list[tuple]) -> bool:
    """O id é de uma só entidade (`achadas`: as linhas dela em `entidades`), do tipo empresa, que não é MEI
    nem tratada como pessoa. Id vazio (identificador sem entidade) ou de pessoa: não."""
    if id_entidade is None or id_entidade.startswith(PREFIXO_DE_PESSOA):
        return False
    if len(achadas) != 1:
        return False
    tipo, mei, trata_como_pessoa = achadas[0]
    return tipo == EMPRESA and not _sim(mei) and not _sim(trata_como_pessoa)


def _pela_rede(porta: Porta, cnpj: str) -> bool | None:
    """Se a rede conhece o CNPJ: se ele é uma só entidade, empresa, que não é MEI nem tratada como pessoa.
    None se ela não o conhece (nem em mais de uma entidade, que é conflito: não)."""
    con = porta.con
    try:
        id_entidade: str | None = resolver(con, cnpj, None)
    except LookupError:
        return False if _a_rede_menciona(porta, cnpj) else None
    if (
        id_entidade is None
    ):  # o identificador existe, mas sem entidade: a rede o conhece; na dúvida, não
        return False
    achadas = con.execute(
        "SELECT tipo, mei, trata_como_pessoa FROM entidades WHERE id_entidade = $id",
        {"id": id_entidade},
    ).fetchall()
    return _e_uma_empresa(id_entidade, achadas)


def _view(tabela: str) -> str:
    return '"' + nome_da_view(tabela) + '"'


def _retrato_das_duas_listas(porta: Porta) -> str | None:
    """O mês mais novo, se é o mesmo nas duas listas; senão None (uma lista de outro mês não tira o MEI
    nem a pessoa daquele mês)."""
    meses = {
        porta.con.execute(f"SELECT max({MES}) FROM {_view(tabela)}").fetchone()
        for tabela in (LISTA_DE_EMPRESAS, LISTA_DE_ESTABELECIMENTOS)
    }
    if len(meses) != 1:
        return None
    (mes,) = meses.pop() or (None,)
    return None if mes is None else str(mes)


def _natureza_de_empresa(naturezas: list[object]) -> bool:
    """A raiz está uma só vez na lista, com uma natureza informada que não é de pessoa."""
    if len(naturezas) != 1:
        return False
    natureza = naturezas[0]
    if natureza is None or pd.isna(natureza) or not str(natureza).strip():  # type: ignore[arg-type]
        return False
    return not natureza_de_pessoa(str(natureza).strip())


def _pelas_listas_sem_pessoa(porta: Porta, cnpj: str) -> bool:
    """No retrato mais novo, o mesmo nas duas listas, o estabelecimento está na lista sem MEI e a raiz, uma só
    vez, na lista de empresas com uma natureza informada que não é de pessoa."""
    mes = _retrato_das_duas_listas(porta)
    if mes is None:
        return False
    con = porta.con
    estabelecimentos = con.execute(
        f"SELECT count(*) FROM {_view(LISTA_DE_ESTABELECIMENTOS)} WHERE cnpj = $cnpj AND {MES} = $mes",
        {"cnpj": cnpj, "mes": mes},
    ).fetchone()
    if estabelecimentos != (1,):
        return False
    naturezas = con.execute(
        f"SELECT natureza_juridica FROM {_view(LISTA_DE_EMPRESAS)} WHERE {RAIZ} = $raiz AND {MES} = $mes",
        {"raiz": cnpj[:TAMANHO_DA_RAIZ], "mes": mes},
    ).fetchall()
    return _natureza_de_empresa([natureza for (natureza,) in naturezas])


# ---------------------------------------------------------------- a mesma trava, em lote (linha 806)


def _tentativas(texto: str) -> list[list[tuple[str, str]]]:
    """Os (sistema, valor) por onde procurar o texto, na ordem do `resolver` da rede: o CNPJ inteiro (o
    fundo), a raiz (a empresa) e, por fim, os outros sistemas."""
    tentativas: list[list[tuple[str, str]]] = []
    if len(texto) == cnpj_.TAMANHO:
        tentativas += [[("cnpj", texto)], [("cnpj_raiz", texto[:TAMANHO_DA_RAIZ])]]
    elif len(texto) == TAMANHO_DA_RAIZ:
        tentativas.append([("cnpj_raiz", texto)])
    tentativas.append([(sistema, texto) for sistema in OUTROS_SISTEMAS])
    return tentativas


def _ids_por_identificador(
    porta: Porta, pares: set[tuple[str, str]]
) -> dict[tuple[str, str], set[str | None]]:
    """Os ids da rede de cada (sistema, valor) pedido, numa consulta só."""
    achados = porta.con.execute(
        "SELECT DISTINCT sistema, valor, id_entidade FROM identificadores "
        f"WHERE sistema IN {_LISTA.format('sistemas')} AND valor IN {_LISTA.format('valores')}",
        {
            "sistemas": sorted({sistema for sistema, _ in pares}),
            "valores": sorted({valor for _, valor in pares}),
        },
    ).fetchall()
    ids: dict[tuple[str, str], set[str | None]] = {}
    for sistema, valor, id_entidade in achados:
        ids.setdefault((sistema, valor), set()).add(id_entidade)
    return ids


def _linhas_por_id(porta: Porta, ids: set[str]) -> dict[str, list[tuple]]:
    """As linhas de `entidades` (tipo, MEI e pessoa) de cada id pedido, numa consulta só."""
    achadas = porta.con.execute(
        "SELECT id_entidade, tipo, mei, trata_como_pessoa FROM entidades "
        f"WHERE id_entidade IN {_LISTA.format('ids')}",
        {"ids": sorted(ids)},
    ).fetchall()
    linhas: dict[str, list[tuple]] = {}
    for id_entidade, *linha in achadas:
        linhas.setdefault(id_entidade, []).append(tuple(linha))
    return linhas


def _id_pelos_identificadores(
    tentativas: list[list[tuple[str, str]]],
    ids: dict[tuple[str, str], set[str | None]],
) -> str | None:
    """O id da primeira tentativa que acha alguém; None se nenhuma acha ou se ela acha mais de um."""
    for pares in tentativas:
        achados = set().union(*(ids.get(par, set()) for par in pares))
        if achados:
            return achados.pop() if len(achados) == 1 else None
    return None


def _pela_rede_em_lote(
    porta: Porta, pedidos: list[str], existem: set[str]
) -> dict[str, bool | None]:
    """`_pela_rede` de cada pedido, com uma consulta aos identificadores e uma às entidades para o lote."""
    com_identificadores = "identificadores" in existem
    pares = {par for cnpj in pedidos for par in _pares_de_mencao(cnpj)}
    ids = _ids_por_identificador(porta, pares) if com_identificadores else {}
    candidatos = {i for achados in ids.values() for i in achados if i is not None}
    linhas = _linhas_por_id(porta, candidatos | set(pedidos))
    respostas: dict[str, bool | None] = {}
    for cnpj in pedidos:
        if (
            cnpj in linhas
        ):  # o texto já é um id de `entidades`: vale por si, como no `resolver`
            respostas[cnpj] = _e_uma_empresa(cnpj, linhas[cnpj])
        elif not com_identificadores:  # rede pela metade: na dúvida, não
            respostas[cnpj] = False
        elif not any(par in ids for par in _pares_de_mencao(cnpj)):
            respostas[cnpj] = None  # a rede não o conhece: decidem as listas
        elif ID_DE_ENTIDADE.match(
            cnpj
        ):  # id que `entidades` não tem: o `resolver` não procura mais
            respostas[cnpj] = False
        else:
            texto = SEPARADORES.sub("", cnpj.strip()).upper()
            id_entidade = _id_pelos_identificadores(_tentativas(texto), ids)
            respostas[cnpj] = _e_uma_empresa(
                id_entidade, linhas.get(id_entidade or "", [])
            )
    return respostas


def _pelas_listas_em_lote(porta: Porta, cnpjs: list[str]) -> dict[str, bool]:
    """`_pelas_listas_sem_pessoa` de cada CNPJ, com uma consulta a cada lista para o lote."""
    mes = _retrato_das_duas_listas(porta)
    if mes is None:
        return dict.fromkeys(cnpjs, False)
    con = porta.con
    contagens = dict(
        con.execute(
            f"SELECT cnpj, count(*) FROM {_view(LISTA_DE_ESTABELECIMENTOS)} "
            f"WHERE cnpj IN {_LISTA.format('cnpjs')} AND {MES} = $mes GROUP BY cnpj",
            {"cnpjs": sorted(set(cnpjs)), "mes": mes},
        ).fetchall()
    )
    naturezas: dict[str, list[object]] = {}
    for raiz, natureza in con.execute(
        f"SELECT {RAIZ}, natureza_juridica FROM {_view(LISTA_DE_EMPRESAS)} "
        f"WHERE {RAIZ} IN {_LISTA.format('raizes')} AND {MES} = $mes",
        {"raizes": sorted({cnpj[:TAMANHO_DA_RAIZ] for cnpj in cnpjs}), "mes": mes},
    ).fetchall():
        naturezas.setdefault(raiz, []).append(natureza)
    return {
        cnpj: contagens.get(cnpj) == 1
        and _natureza_de_empresa(naturezas.get(cnpj[:TAMANHO_DA_RAIZ], []))
        for cnpj in cnpjs
    }


def e_empresas(porta: Porta, cnpjs: Iterable[str]) -> dict[str, bool]:
    """De cada CNPJ, o mesmo que `e_empresa` (há teste, item a item), sem uma ida à base por CNPJ.

    A trava de pessoa em lote (ADR 0108 D2.2; linha 806: os comparáveis perguntam por todas as candidatas do
    grupo): uma consulta aos identificadores e uma às entidades para o lote inteiro e, do que a rede não
    conhece, uma a cada lista sem pessoa da Receita. Mesmo caminho e mesmas regras de `e_empresa`: a rede
    decide o que conhece (pessoa, fundo e conflito não caem para as listas); o resto, as listas (linha 843)."""
    pedidos = list(dict.fromkeys(cnpjs))
    if not pedidos:
        return {}
    existem = views(porta.con)
    respostas: dict[str, bool | None] = dict.fromkeys(pedidos)
    if "entidades" in existem:
        respostas = _pela_rede_em_lote(porta, pedidos, existem)
    resto = [cnpj for cnpj, resposta in respostas.items() if resposta is None]
    pelas_listas = (
        _pelas_listas_em_lote(porta, resto)
        if resto and {LISTA_DE_EMPRESAS, LISTA_DE_ESTABELECIMENTOS} <= existem
        else {}
    )
    return {
        cnpj: resposta if resposta is not None else pelas_listas.get(cnpj, False)
        for cnpj, resposta in respostas.items()
    }


class LeitorDeEmpresas:
    """Lê a situação cadastral de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido

    def _versao(
        self, historico: Historico, raiz: str, como_era_em: date
    ) -> pd.Series | None:
        """A versão da raiz que valia em `como_era_em` (a do retrato mais novo já público); None se a base
        não tem a tabela, se nada era público ainda ou se a raiz tinha saído do arquivo."""
        if historico.tabela not in views(self.porta.con):
            return None
        versoes = self.porta.ler(
            historico.tabela,
            como_era_em=como_era_em,
            filtros={RAIZ: raiz},
            colunas=[*historico.campos, MES, CONSTA, PUBLICADO_EM],
        )
        if versoes.empty:
            return None
        versao = versoes.sort_values([MES, PUBLICADO_EM]).iloc[-1]
        return versao if bool(versao[CONSTA]) else None

    def _servidos(self, linha: pd.Series, campos: tuple[str, ...]) -> dict[str, dict]:
        """Os campos da linha que o portão libera, cada um no envelope com a data em que ficou público."""
        publico_em = pd.Timestamp(linha[PUBLICADO_EM]).date()
        return {
            nome: campo(_simples(nome, linha[nome]), fonte=FONTE, publico_em=publico_em, visto_em=None)
            for nome in campos
            if self.permitido(FONTE, nome, False)
        }  # fmt: skip

    def _do_retrato_pj(self, raiz: str, como_era_em: date) -> dict[str, dict]:
        """Sem o histórico do nome: a razão social e a natureza do retrato mais novo de `cnpj_empresas_pj` já
        público em `como_era_em`, com o mês dele; nada se a base não tem a lista, se o retrato ainda não era
        público ou se a raiz não está nele uma só vez com natureza de empresa (na dúvida, não)."""
        if LISTA_DE_EMPRESAS not in views(self.porta.con):
            return {}
        linhas = self.porta.ler(
            LISTA_DE_EMPRESAS,
            como_era_em=como_era_em,
            filtros={RAIZ: raiz},
            colunas=[*CAMPOS_DO_RETRATO_PJ, MES, PUBLICADO_EM],
        )
        if linhas.empty:
            return {}
        do_mes = linhas[linhas[MES] == linhas[MES].max()]
        if not _natureza_de_empresa(list(do_mes["natureza_juridica"])):
            return {}
        linha = do_mes.iloc[0].copy()
        linha[RETRATO_DO_CADASTRO] = linha[MES]
        return self._servidos(linha, (*CAMPOS_DO_RETRATO_PJ, RETRATO_DO_CADASTRO))

    def empresa(self, cnpj: str, como_era_em: date) -> EmpresaServida | None:
        """A situação cadastral do CNPJ na versão mais nova já pública em `como_era_em` e, da raiz, a
        versão do histórico datado que valia no dia, só com o que o portão libera; None se o CNPJ não é de
        empresa, se não há versão pública da situação, se o estabelecimento tinha saído do arquivo ou se
        nada sai."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        if not e_empresa(self.porta, normal):
            return None
        retratos = self.porta.ler(
            TABELA,
            como_era_em=como_era_em,
            filtros={"cnpj": cnpj_.formatar(normal)},
            colunas=[*CAMPOS, CONSTA, PUBLICADO_EM],
        )
        if retratos.empty:
            return None
        retrato = retratos.sort_values([MES, PUBLICADO_EM]).iloc[-1]
        if not bool(retrato[CONSTA]):
            return None  # o estabelecimento tinha saído do arquivo da Receita no dia pedido
        servidos = self._servidos(retrato, CAMPOS)
        raiz = normal[:TAMANHO_DA_RAIZ]
        for historico in HISTORICOS:
            versao = self._versao(historico, raiz, como_era_em)
            if versao is not None:
                servidos |= self._servidos(versao, historico.campos)
        if HISTORICO_DO_NOME not in views(self.porta.con):
            servidos |= self._do_retrato_pj(raiz, como_era_em)
        if not servidos:
            return None
        corpo = {"cnpj": normal, "como_era_em": como_era_em.isoformat(), **servidos}
        return EmpresaServida(corpo, {FONTE}, 1)
