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

Pessoa não sai (ADR 0108 D2.2): o CNPJ só é servido se a rede o conhece como empresa e não o trata como
pessoa (MEI, empresário individual e as naturezas de pessoa física, `trata_como_pessoa`). O que a rede não
conhece, o que é fundo ou outra coisa, e o conflito (o mesmo CNPJ em duas entidades) saem como
`not_available`, igual a um CNPJ que não existe: a resposta não diz qual foi o motivo. A rede usada é a de
hoje: quem hoje se sabe pessoa não sai nem numa data em que ainda não se sabia.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.cnpj import SEPARADORES
from base.porta import Porta
from base.porta.rede import ID_DE_ENTIDADE, OUTROS_SISTEMAS, resolver, views
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
TABELAS = (TABELA, *(historico.tabela for historico in HISTORICOS))
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


def _procuras(cnpjs: list[str]) -> dict[str, list[list[tuple[str, str]]]]:
    """De cada CNPJ que não tem a forma de um id da rede, as tentativas de achá-lo pelos identificadores."""
    return {
        cnpj: _tentativas(SEPARADORES.sub("", cnpj.strip()).upper())
        for cnpj in cnpjs
        if not ID_DE_ENTIDADE.match(cnpj)
    }


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


def _e_uma_empresa(id_entidade: str | None, linhas: dict[str, list[tuple]]) -> bool:
    """O id é de uma só entidade, do tipo empresa, que não é MEI nem tratada como pessoa."""
    if id_entidade is None or id_entidade.startswith(PREFIXO_DE_PESSOA):
        return False
    achadas = linhas.get(id_entidade, [])
    if len(achadas) != 1:
        return False
    tipo, mei, trata_como_pessoa = achadas[0]
    return tipo == EMPRESA and not _sim(mei) and not _sim(trata_como_pessoa)


def e_empresas(porta: Porta, cnpjs: Iterable[str]) -> dict[str, bool]:
    """De cada CNPJ, se a rede de hoje o conhece como uma só empresa que não é pessoa; qualquer dúvida é não.

    A trava de pessoa de `e_empresa` (ADR 0108 D2.2), em lote: uma consulta aos identificadores e uma às
    entidades para o lote inteiro, em vez de até cinco por CNPJ (linha 806: os comparáveis perguntam por
    todas as candidatas do grupo). O caminho é o do `resolver` da rede: o texto que já é um id de
    `entidades` vale por si; senão, vale a primeira tentativa que achar alguém (CNPJ inteiro, raiz, outros
    sistemas), e achar mais de um é conflito. A regra final (`_e_uma_empresa`) é a mesma função nos dois; o
    caminho até o id tem teste que o compara com o `resolver`, item a item
    (`tests/test_api_externa_e_empresas.py`)."""
    pedidos = list(dict.fromkeys(cnpjs))
    existem = views(porta.con)
    if not pedidos or "entidades" not in existem:
        return dict.fromkeys(pedidos, False)
    procuras = _procuras(pedidos) if "identificadores" in existem else {}
    pares = {par for tentativas in procuras.values() for t in tentativas for par in t}
    ids = _ids_por_identificador(porta, pares) if pares else {}
    candidatos = {i for achados in ids.values() for i in achados if i is not None}
    linhas = _linhas_por_id(porta, candidatos | set(pedidos))
    return {
        cnpj: _e_uma_empresa(
            cnpj
            if cnpj in linhas
            else _id_pelos_identificadores(procuras.get(cnpj, []), ids),
            linhas,
        )
        for cnpj in pedidos
    }


def e_empresa(porta: Porta, cnpj: str) -> bool:
    """A rede de hoje conhece o CNPJ como uma só empresa que não é pessoa; qualquer dúvida é não.

    Também serve à rota de crédito (`conjuntos/credito.py`): as duas tiram pessoa do mesmo jeito. Para
    muitos CNPJs de uma vez, `e_empresas`: a mesma resposta (há teste), sem uma ida à rede por CNPJ."""
    con = porta.con
    if "entidades" not in views(con):
        return False
    try:
        id_entidade = resolver(con, cnpj, None)
    except LookupError:
        return False
    achadas = con.execute(
        "SELECT tipo, mei, trata_como_pessoa FROM entidades WHERE id_entidade = $id",
        {"id": id_entidade},
    ).fetchall()
    return _e_uma_empresa(id_entidade, {id_entidade: achadas})


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

    def empresa(self, cnpj: str, como_era_em: date) -> EmpresaServida | None:
        """A situação cadastral do CNPJ no retrato mais novo já público em `como_era_em` e, da raiz, a
        versão do histórico datado que valia no dia, só com o que o portão libera; None se o CNPJ não é de
        empresa, se não há retrato público da situação ou se nada sai."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        if not e_empresa(self.porta, normal):
            return None
        retratos = self.porta.ler(
            TABELA,
            como_era_em=como_era_em,
            filtros={"cnpj": cnpj_.formatar(normal)},
            colunas=[*CAMPOS, PUBLICADO_EM],
        )
        if retratos.empty:
            return None
        retrato = retratos.sort_values([MES, PUBLICADO_EM]).iloc[-1]
        servidos = self._servidos(retrato, CAMPOS)
        for historico in HISTORICOS:
            versao = self._versao(historico, normal[:TAMANHO_DA_RAIZ], como_era_em)
            if versao is not None:
                servidos |= self._servidos(versao, historico.campos)
        if not servidos:
            return None
        corpo = {"cnpj": normal, "como_era_em": como_era_em.isoformat(), **servidos}
        return EmpresaServida(corpo, {FONTE}, 1)
