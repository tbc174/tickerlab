"""A ficha de crédito na API externa (linha 754, PR 2): `/data/v1/credit`, os fatos de um CNPJ como eram.

`LeitorDeCredito(porta, permitido).ficha(cnpj, como_era_em)` monta a ficha de `src/credito/ficha.py` e
devolve, em tipos simples e com as chaves em português (a rota traduz na saída), só os fatos que têm linha
de direito no portão (`FATOS`) e que o portão libera no pedido, cada um no envelope com a fonte e o dia em
que ficou público. Fato não observado, ou sem a data em que ficou público, não sai.

Ficam fora desta rota, na leitura mais estreita das travas:
- os resultados das regras de elegibilidade (o papel de cedente ou sacado): sobre quem emite valor
  mobiliário, dizer "elegível" ou "inelegível" seria opinião sobre a qualidade de crédito do emissor, que
  é de agência registrada (Resolução CVM 9/2020, art. 1º; regra da casa de 06/11/2026 em
  `docs/virada-empresas-fechadas.md`); e uma regra que aciona revelaria um sinal que o portão nega.
  Entram depois, só para quem não emite, com a conferência de emissor;
- o que o portão nunca deixa sair: rating, insolvência e o SCR (só agregado), e as fontes cujas marcas
  não deixam (CGU, MTE e IBAMA de uso interno; PGFN, Sefa-PR e SEF-MG sem a guarda dita);
- a ordem cronológica de pagamentos de PE e do ES: as tabelas têm credor pessoa (ADR 0106).

Pessoa não sai (ADR 0108 D2.2): o CNPJ só é servido se a rede o conhece como empresa que não é pessoa
(`empresas.e_empresa`, a mesma trava de `companies`); o resto sai `not_available`, sem dizer o motivo.
"""

from dataclasses import dataclass, field
from datetime import date

from base import cnpj as cnpj_
from base.porta import Porta
from src.api_externa.conjuntos import Permitido
from src.api_externa.conjuntos.empresas import e_empresa
from src.api_externa.envelope import campo
from src.credito.elegibilidade import CEDENTE
from src.credito.features import Feature
from src.credito.ficha import ficha_de_credito
from src.credito.sinais import DO_FIDC

CONJUNTO = "credit"
# as regras ficam fora desta rota e os fatos não mudam com o papel: a ficha pede um, qualquer um
PAPEL_DA_FICHA = CEDENTE


@dataclass(frozen=True)
class OrigemDoFato:
    """De que coleta (a do acervo, como na linha de direito) e de que tabela da base o fato sai."""

    fonte: str
    tabela: str


# Os fatos da ficha que têm linha de direito no portão (`DIREITOS_DA_API_EXTERNA`); há teste que confere
# que as duas listas são a mesma.
FATOS: dict[str, OrigemDoFato] = {
    "situacao_cadastral_na_receita": OrigemDoFato(
        "rfb-cnpj", "cnpj_situacao_cadastral"
    ),
    "situacao_especial_na_receita": OrigemDoFato("rfb-cnpj", "cnpj_situacao_especial"),
    "fatos_relevantes_12_meses": OrigemDoFato("cvm-hist-ipe", "eventos"),
    **dict.fromkeys(DO_FIDC, OrigemDoFato("cvm-fidc", "fidc_informe")),
}

LIMITES = (
    "Cada fato traz a fonte e o dia em que ficou público: nada publicado depois de known_at entra.",
    (
        "Só saem fatos de fontes que podem ser redistribuídas; um fato que não aparece não quer dizer "
        "que o evento não aconteceu."
    ),
    (
        "São fatos, não nota nem opinião de crédito, e nada aqui é recomendação de investimento: a "
        "decisão de crédito é de quem pergunta."
    ),
    "Pessoa natural (MEI, empresário individual) não é servida.",
)


@dataclass(frozen=True)
class FichaServida:
    """O que sai de uma ficha: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


def _servivel(fato: Feature) -> bool:
    """Tem linha de direito, foi observado e tem o dia em que ficou público (sem ele, não há corte)."""
    return (
        fato.chave in FATOS
        and fato.valor is not None
        and fato.disponivel_em is not None
    )


class LeitorDeCredito:
    """Lê a ficha de crédito de uma empresa de uma porta para um pedido."""

    def __init__(self, porta: Porta, permitido: Permitido) -> None:
        self.porta = porta
        self.permitido = permitido

    def _liberados(self, fatos: tuple[Feature, ...]) -> list[Feature]:
        """Os fatos que o portão libera; todos são contas nossas sobre a fonte (derivados)."""
        return [
            fato
            for fato in fatos
            if _servivel(fato)
            and self.permitido(FATOS[fato.chave].fonte, fato.chave, True)
        ]

    def ficha(self, cnpj: str, como_era_em: date) -> FichaServida | None:
        """Os fatos da ficha do CNPJ como eram em `como_era_em`, só os que o portão libera; None se o
        CNPJ não é de empresa ou se nada sai."""
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        if not e_empresa(self.porta, normal):
            return None
        ficha = ficha_de_credito(self.porta, normal, PAPEL_DA_FICHA, como_era_em)
        liberados = self._liberados(ficha.fatos)
        if not liberados:
            return None
        servidos = {
            fato.chave: campo(
                fato.valor,
                fonte=FATOS[fato.chave].fonte,
                publico_em=fato.disponivel_em,
                visto_em=None,
            )
            for fato in liberados
        }
        corpo = {
            "cnpj": normal,
            "como_era_em": como_era_em.isoformat(),
            **servidos,
            "limites": list(LIMITES),
        }
        fontes = {FATOS[fato.chave].fonte for fato in liberados}
        return FichaServida(corpo, fontes, 1)
