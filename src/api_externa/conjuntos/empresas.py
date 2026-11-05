"""A situação cadastral das empresas na API externa (B-32a, PR 4): `cnpj_situacao_cadastral` pelo portão.

`LeitorDeEmpresas(porta, permitido).empresa(cnpj, como_era_em)` devolve, em tipos simples e com as chaves em
português (a rota traduz na saída), a situação cadastral do estabelecimento no retrato mensal da Receita mais
novo que já era público em `como_era_em`. O retrato do mês vale pelo último dia do mês em que foi baixado (a
porta faz o corte): o CNPJ baixado em junho e publicado em julho continua ativo até 31/07.

Só a situação sai (decisão do Tiago em 04/11/2026). Nome, natureza jurídica e Simples a base só guarda como
são hoje; servi-los numa data passada mostraria o futuro, e eles esperam o histórico datado (linha dos Dados).

Pessoa não sai (ADR 0108 D2.2): o CNPJ só é servido se a rede o conhece como empresa e não o trata como
pessoa (MEI, empresário individual e as naturezas de pessoa física, `trata_como_pessoa`). O que a rede não
conhece, o que é fundo ou outra coisa, e o conflito (o mesmo CNPJ em duas entidades) saem como
`not_available`, igual a um CNPJ que não existe: a resposta não diz qual foi o motivo. A rede usada é a de
hoje: quem hoje se sabe pessoa não sai nem numa data em que ainda não se sabia.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from base import cnpj as cnpj_
from base.porta import Porta
from base.porta.rede import resolver, views
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo

CONJUNTO = "companies"
TABELA = "cnpj_situacao_cadastral"
FONTE = "rfb-cnpj"
CAMPOS = (
    "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao", "matriz", "mes_do_retrato",
)  # fmt: skip
DATAS = ("data_situacao_cadastral",)
PUBLICADO_EM = (
    "publico_em"  # o apelido da porta: o último dia do mês em que o retrato foi baixado
)
EMPRESA = "empresa"
PREFIXO_DE_PESSOA = "P"  # id de pessoa na rede (`base/rede`): nunca sai


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
    if nome == "matriz":
        return bool(valor)
    return str(valor)


def _sim(valor: object) -> bool:
    """Verdadeiro, ou vazio (que conta como verdadeiro: na dúvida, é pessoa)."""
    return valor is None or bool(pd.isna(valor)) or bool(valor)  # type: ignore[arg-type]


class LeitorDeEmpresas:
    """Lê a situação cadastral de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido

    def _e_empresa(self, cnpj: str) -> bool:
        """A rede de hoje conhece o CNPJ como uma só empresa que não é pessoa; qualquer dúvida é não."""
        con = self.porta.con
        if "entidades" not in views(con):
            return False
        try:
            id_entidade = resolver(con, cnpj, None)
        except LookupError:
            return False
        if id_entidade.startswith(PREFIXO_DE_PESSOA):
            return False
        achadas = con.execute(
            "SELECT tipo, mei, trata_como_pessoa FROM entidades WHERE id_entidade = $id",
            {"id": id_entidade},
        ).fetchall()
        if len(achadas) != 1:
            return False
        tipo, mei, trata_como_pessoa = achadas[0]
        return tipo == EMPRESA and not _sim(mei) and not _sim(trata_como_pessoa)

    def empresa(self, cnpj: str, como_era_em: date) -> EmpresaServida | None:
        """A situação cadastral do CNPJ no retrato mais novo já público em `como_era_em`, só com o que o
        portão libera; None se o CNPJ não é de empresa ou se nada sai."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        if not self._e_empresa(normal):
            return None
        retratos = self.porta.ler(
            TABELA,
            como_era_em=como_era_em,
            filtros={"cnpj": cnpj_.formatar(normal)},
            colunas=[*CAMPOS, PUBLICADO_EM],
        )
        if retratos.empty:
            return None
        retrato = retratos.sort_values(["mes_do_retrato", PUBLICADO_EM]).iloc[-1]
        publico_em = pd.Timestamp(retrato[PUBLICADO_EM]).date()
        servidos = {
            nome: campo(_simples(nome, retrato[nome]), fonte=FONTE, publico_em=publico_em, visto_em=None)
            for nome in CAMPOS
            if self.permitido(FONTE, nome, False)
        }  # fmt: skip
        if not servidos:
            return None
        corpo = {"cnpj": normal, "como_era_em": como_era_em.isoformat(), **servidos}
        return EmpresaServida(corpo, {FONTE}, 1)
