"""O perfil de um setor por CNAE (linha 903, tela de setor): só contagens, só pessoa jurídica.

`LeitorDoPerfilDoSetor(porta, permitido).perfil(cnae, como_era_em)` conta, no retrato da Receita que valia no
dia, as empresas do CNAE principal pedido (classe de 5 dígitos ou subclasse de 7, o mesmo recorte da lista de
compradores, `cnae_do_parametro`):

- `empresas_ativas`: as raízes de CNPJ com ao menos um estabelecimento ativo do CNAE. É a mesma conta do
  `empresas_ativas` da lista de compradores (`compradores.py`, `_Consulta.setor`), para os dois números baterem
  na tela;
- `por_uf`: a mesma conta em cada UF (a empresa conta em cada UF onde tem estabelecimento ativo do CNAE, como a
  lista de compradores pedida com a UF), da maior para a menor;
- `aberturas_por_ano`: por ano, as empresas cujo estabelecimento mais antigo do CNAE começou a atividade naquele
  ano, de qualquer situação (as baixadas entram: contar só as ativas mostraria só quem sobreviveu), nos
  `ANOS_DE_ABERTURAS` anos antes do dia e no ano do dia, em ordem de ano.

Não sai nenhuma empresa, nenhum nome e nenhuma pessoa: só números. A rota não existe ainda; a tela de setor do
analista chama o leitor com o portão da tela (`leitura.permitido_na_tela`) do conjunto `buyers`, o mesmo da lista
de compradores, que lê a mesma tabela. Uma rota da API por chave o serviria como `GET /data/v1/buyers/sector`.

**Sem pessoa:** só a lista sem pessoa da Receita (`cnpj_estabelecimentos_pj`, linha 584): MEI, empresário
individual e as outras naturezas de pessoa física (grupo 4) não estão nela e não entram em nenhuma conta, o mesmo
critério do `empresas_ativas` de hoje.

**Sem olhar o futuro:** o retrato é o mais novo já público no dia, o mesmo mês das duas tabelas sem pessoa
(`compradores.mes_do_retrato`); a abertura só conta com o início de atividade até o dia.

**Portão:** o bloco cujo campo o portão não libera não sai como zero: vem None e o nome dele vai em
`blocos_nao_disponiveis` (linha 882); sem o CNAE liberado ou sem as tabelas na porta, não há perfil (None).

**Custo** (medido em 13/11/2026 no retrato vigente inteiro, com MEI, 73 milhões de estabelecimentos, num
DuckDB do PC): no CNAE com mais empresas medido (a classe 56112, 1,05 milhão de ativas), cada contagem levou
menos de 1 s; não precisa de resumo pronto na carga.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from base.porta import Porta
from base.porta.duckdb import nome_da_view
from base.porta.rede import views
from src.api_externa import nao_disponivel
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.compradores import (
    ATIVA,
    CONJUNTO,
    EMPRESAS,
    ESTABELECIMENTOS,
    MES,
    RECEITA,
    cnae_do_parametro,
    mes_do_retrato,
)

__all__ = ["CONJUNTO", "LeitorDoPerfilDoSetor", "PerfilServido", "cnae_do_parametro"]

ANOS_DE_ABERTURAS = (
    10  # os anos completos antes do ano do dia (o ano do dia vai junto, até o dia)
)
CNAE, UF, ABERTURA = "cnae_principal", "uf", "data_inicio_atividade"
POR_UF, ABERTURAS = "por_uf", "aberturas_por_ano"
# o campo que cada bloco precisa liberado pelo portão (além do CNAE, sem o qual não há perfil)
CAMPO_DO_BLOCO = {POR_UF: UF, ABERTURAS: ABERTURA}
NAO_DISPONIVEIS = "blocos_nao_disponiveis"
PUBLICO_EM = "publico_em"

LIMITES_GERAIS = (
    (
        "Só contagens, sem nenhuma empresa. O setor é o das empresas com estabelecimento do CNAE principal "
        "pedido no retrato da Receita que valia em known_at (o CNAE é o atual de cada estabelecimento). Só "
        "pessoa jurídica: MEI, empresário individual e as outras naturezas de pessoa física não entram em "
        "nenhuma conta, o mesmo recorte do empresas_ativas da lista de compradores."
    ),
    (
        "Empresas ativas: as raízes de CNPJ com ao menos um estabelecimento ativo do CNAE, a mesma conta da "
        "lista de compradores."
    ),
    (
        "Fonte: o cadastro do CNPJ da Receita Federal (dados abertos), o retrato do mês em data_do_retrato, "
        "público desde publico_em. Nada aqui é recomendação de investimento."
    ),
)
GERAIS_ANTES_DOS_BLOCOS = 2  # o recorte e a frase do total
LIMITES_DO_BLOCO = {
    POR_UF: (
        "Por UF: a empresa conta em cada UF onde tem estabelecimento ativo do CNAE, então a soma das UFs pode "
        "passar do total; EX é estabelecimento no exterior."
    ),
    ABERTURAS: (
        "Aberturas por ano: o ano de início de atividade do estabelecimento mais antigo da empresa com esse "
        "CNAE, de qualquer situação (as baixadas entram, para não contar só quem sobreviveu). Quem mudou de "
        "atividade conta no ano em que abriu o estabelecimento, não no da mudança; o ano de known_at vai só "
        "até o dia."
    ),
}
LIMITE_DO_BLOCO_NAO_DISPONIVEL = nao_disponivel.aviso(
    NAO_DISPONIVEIS, "blocos", "o perfil do setor"
)


def limites(servidos: Sequence[str], nao_disponiveis: Sequence[str]) -> list[str]:
    """Os limites de uma resposta: os gerais, a frase de cada bloco servido e o aviso do bloco de fora."""
    return nao_disponivel.limites(
        LIMITES_GERAIS,
        LIMITES_DO_BLOCO,
        servidos,
        nao_disponiveis,
        LIMITE_DO_BLOCO_NAO_DISPONIVEL,
        antes=GERAIS_ANTES_DOS_BLOCOS,
    )


@dataclass(frozen=True)
class PerfilServido:
    """O que sai de um pedido: o corpo, as fontes usadas e as linhas servidas (o perfil conta como uma)."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 1


def _view(tabela: str) -> str:
    return '"' + nome_da_view(tabela).replace('"', '""') + '"'


class LeitorDoPerfilDoSetor:
    """Conta as empresas de um CNAE numa porta, com o portão do conjunto de compradores."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido
        self.tabelas = set(views(porta.con))

    def perfil(self, cnae: str, como_era_em: date) -> PerfilServido | None:
        """O perfil do CNAE como era no dia; None se o portão não libera o CNAE, se a porta não tem as tabelas
        ou se ainda não havia retrato público. O CNAE é conferido aqui de novo (`cnae_do_parametro`): um CNAE
        vazio ou curto casaria com o país inteiro; fora da forma, `PedidoInvalido("invalid_cnae")`."""
        cnae = cnae_do_parametro(cnae)
        tabelas = {ESTABELECIMENTOS, EMPRESAS}
        if not self.permitido(RECEITA, CNAE, True) or not tabelas <= self.tabelas:
            return None
        mes = mes_do_retrato(self.porta, como_era_em)
        if mes is None:
            return None
        servidos = [
            b for b, c in CAMPO_DO_BLOCO.items() if self.permitido(RECEITA, c, True)
        ]
        nao_disponiveis = [b for b in CAMPO_DO_BLOCO if b not in servidos]
        parametros = {"mes": mes, "cnae": cnae}
        corpo: dict[str, object] = {
            "como_era_em": como_era_em.isoformat(),
            "cnae_principal": cnae,
            "fonte": RECEITA,
            "data_do_retrato": mes,
            "publico_em": self._publico_em(mes),
            "empresas_ativas": self._ativas(parametros),
            POR_UF: self._por_uf(parametros) if POR_UF in servidos else None,
            ABERTURAS: (
                self._aberturas(parametros, como_era_em)
                if ABERTURAS in servidos
                else None
            ),
            NAO_DISPONIVEIS: nao_disponiveis,
            "limites": limites(servidos, nao_disponiveis),
        }
        return PerfilServido(corpo, {RECEITA})

    def _uma(self, sql: str, parametros: dict[str, object]) -> list[tuple]:
        """Uma consulta num cursor próprio: a conexão da porta é dividida entre as threads do servidor."""
        cursor = self.porta.con.cursor()
        try:
            return cursor.execute(sql, parametros).fetchall()
        finally:
            cursor.close()

    def _publico_em(self, mes: str) -> str | None:
        (achado,) = self._uma(
            f"SELECT max({PUBLICO_EM}) FROM {_view(ESTABELECIMENTOS)} WHERE {MES} = $mes",
            {"mes": mes},
        )
        return None if achado[0] is None else achado[0].isoformat()

    def _do_setor(self, ativas: bool) -> str:
        """O recorte do setor no retrato: o CNAE (classe ou subclasse) e, se pedido, só os ativos."""
        situacao = f" AND situacao_cadastral = '{ATIVA}'" if ativas else ""
        return f"FROM {_view(ESTABELECIMENTOS)} WHERE {MES} = $mes AND starts_with({CNAE}, $cnae){situacao}"

    def _ativas(self, parametros: dict[str, object]) -> int:
        (achado,) = self._uma(
            f"SELECT count(DISTINCT cnpj_basico) {self._do_setor(ativas=True)}",
            parametros,
        )
        return int(achado[0])

    def _por_uf(self, parametros: dict[str, object]) -> list[dict[str, object]]:
        linhas = self._uma(
            f"SELECT {UF}, count(DISTINCT cnpj_basico) AS n {self._do_setor(ativas=True)} "
            f"AND {UF} IS NOT NULL GROUP BY {UF} ORDER BY n DESC, {UF}",
            parametros,
        )
        return [{"uf": uf, "empresas_ativas": int(n)} for uf, n in linhas]

    def _aberturas(
        self, parametros: dict[str, object], como_era_em: date
    ) -> list[dict[str, int]]:
        ate = como_era_em.year  # o ano do dia, até o dia
        desde = ate - ANOS_DE_ABERTURAS
        linhas = self._uma(
            "SELECT year(abertura) AS ano, count(*) FROM ("
            f"SELECT cnpj_basico, min({ABERTURA}) AS abertura {self._do_setor(ativas=False)} "
            f"AND {ABERTURA} <= CAST($dia AS DATE) GROUP BY cnpj_basico"
            ") WHERE year(abertura) >= $desde GROUP BY ano",
            {**parametros, "dia": como_era_em, "desde": desde},
        )
        por_ano = {int(ano): int(n) for ano, n in linhas}
        return [
            {"ano": ano, "aberturas": por_ano.get(ano, 0)}
            for ano in range(desde, ate + 1)
        ]
