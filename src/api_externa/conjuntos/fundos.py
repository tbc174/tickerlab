"""O raio-x de fundo na API externa (B-32a, PR 5): `base/raio_x_de_fundo.py` campo a campo, pelo portão.

`LeitorDeFundos(porta, permitido).fundo(cnpj, como_era_em, retorno_suposto)` monta, em tipos simples e com
as chaves em português (a rota traduz na saída):

- **cadastro** (taxas, classe, situação, patrimônio): o cadastro da CVM é um retrato sem data por linha.
  A data de publicação de cada campo é o dia em que o TickerLab baixou o arquivo pela primeira vez (o
  registro de coletas, pela linhagem da tabela): a CVM o publicou no máximo nesse dia. Com `como_era_em`
  antes dele, o cadastro não sai (o histórico por data vem depois, com a A3b). Sem coleta registrada
  também não: sem data de publicação, o campo não sai.
- **custo_da_taxa** em 5 e 20 anos, só com o retorno suposto que o cliente dá (nada de retorno escondido
  nem promessa): a conta de `src/ferramentas/custos.py` sobre a taxa do cadastro, um campo derivado.
- **carteira**: as posições da competência mais nova já pública em `como_era_em` (`disponivel_em`). A
  fonte de cada posição é `cvm-cda-recente` quando o arquivista a viu aparecer (`visto_em`) e
  `cvm-hist-cda` antes disso.

`permitido(fonte, campo, derivado)` é o portão (a rota o liga ao contrato e ao `portao_externo`): campo
negado não aparece. Sem nada liberado, `None`, e a rota responde o mesmo de um fundo que não existe.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from base import cnpj as cnpj_
from base.porta import Porta
from base.raio_x_de_fundo import (
    CADASTRO,
    CAPITAL_DO_EXEMPLO,
    PRAZOS_DO_CUSTO,
    raio_x_de_fundo,
    taxas_do_fundo,
)
from src.api_externa.conjuntos import Permitido
from src.api_externa.envelope import campo
from src.ferramentas.custos import custo_da_taxa

CONJUNTO = "funds"
FONTE_DO_CADASTRO = "cvm-cadastros"
FONTE_DA_CDA_HISTORICA = "cvm-hist-cda"
FONTE_DA_CDA_RECENTE = "cvm-cda-recente"
CAMPOS_DA_POSICAO = (
    "competencia", "codigo", "isin", "emissor", "tipo", "quantidade", "valor",
)  # fmt: skip
CAMPOS_DO_CUSTO = ("sem_taxa", "com_taxa", "ficou_com_a_taxa", "fracao_do_resultado")
TAXA_DE_ADMINISTRACAO = "taxa_administracao_pct_ao_ano"
PERCENTUAL = 100


@dataclass(frozen=True)
class FundoServido:
    """O que sai de um fundo: o corpo, as fontes usadas (para a atribuição) e as linhas servidas."""

    corpo: dict
    fontes: set[str] = field(default_factory=set)
    linhas: int = 0


@dataclass
class _Retrato:
    momento: datetime | None


def _dia(texto: object) -> date | None:
    return None if texto is None else date.fromisoformat(str(texto)[:10])


def _momento_do_retrato(porta: Porta, cnpj_formatado: str) -> datetime | None:
    """Quando o TickerLab baixou o cadastro que a base serve; None sem coleta registrada.

    A tabela tem um arquivo só: a linhagem de qualquer linha dele é a da tabela inteira. A conferência do
    hash lê a tabela toda, por isso o leitor guarda a resposta enquanto dura o pedido.
    """
    if porta.banco is None:
        return None
    try:
        linhagem = porta.linhagem(CADASTRO, {"CNPJ_FUNDO": cnpj_formatado})
    except (KeyError, LookupError, OSError):
        return None
    momentos = [origem.baixado_em for origem in linhagem.originais()]
    if not linhagem.base_confere or not momentos or None in momentos:
        return None
    maior = max(m for m in momentos if m is not None)
    # o registro grava em UTC; o SQLite devolve sem o fuso
    return maior if maior.tzinfo is not None else maior.replace(tzinfo=UTC)


class LeitorDeFundos:
    """Lê fundos de uma porta para um pedido (ou um lote): o retrato do cadastro é conferido uma vez."""

    def __init__(self, porta: Porta, permitido: Permitido, linhas_maximas: int) -> None:
        self.porta = porta
        self.permitido = permitido
        self.linhas_maximas = linhas_maximas
        self._retrato: _Retrato | None = None

    def _momento_do_retrato(self, cnpj_formatado: str) -> datetime | None:
        if self._retrato is None:
            self._retrato = _Retrato(_momento_do_retrato(self.porta, cnpj_formatado))
        return self._retrato.momento

    def _cadastro(
        self, cnpj_formatado: str, como_era_em: date
    ) -> tuple[dict, datetime] | None:
        taxas = taxas_do_fundo(self.porta, cnpj_formatado)
        if taxas is None:
            return None
        momento = self._momento_do_retrato(cnpj_formatado)
        if momento is None or momento.date() > como_era_em:
            return None
        return taxas, momento

    def _campos_do_cadastro(self, taxas: dict, momento: datetime) -> dict:
        return {
            nome: campo(valor, fonte=FONTE_DO_CADASTRO, publico_em=momento.date(), visto_em=momento)
            for nome, valor in taxas.items()
            if self.permitido(FONTE_DO_CADASTRO, nome, False)
        }  # fmt: skip

    def _custo(
        self, taxas: dict, momento: datetime, retorno_suposto: float
    ) -> dict | None:
        taxa = taxas.get(TAXA_DE_ADMINISTRACAO)
        if not isinstance(taxa, int | float) or not 0 <= taxa < PERCENTUAL:
            return (
                None  # sem taxa informada (ou NaN, ou fora do possível): não há conta
            )
        campos = [
            c for c in CAMPOS_DO_CUSTO if self.permitido(FONTE_DO_CADASTRO, c, True)
        ]
        if not campos:
            return None
        prazos = []
        for anos in PRAZOS_DO_CUSTO:
            conta = custo_da_taxa(
                CAPITAL_DO_EXEMPLO, retorno_suposto, taxa / PERCENTUAL, anos
            )
            prazos.append(
                {"anos": anos}
                | {
                    c: campo(getattr(conta, c), fonte=FONTE_DO_CADASTRO, publico_em=momento.date(), visto_em=momento)
                    for c in campos
                }
            )  # fmt: skip
        return {
            "hipotese": {
                "capital_inicial": CAPITAL_DO_EXEMPLO,
                "retorno_suposto": retorno_suposto,
            },
            "prazos": prazos,
        }

    def _posicao(self, linha: dict) -> tuple[dict, str] | None:
        visto_em = _dia(linha.get("visto_em"))
        fonte = FONTE_DA_CDA_RECENTE if visto_em is not None else FONTE_DA_CDA_HISTORICA
        publico_em = _dia(linha.get("disponivel_em"))
        posicao = {
            nome: campo(linha.get(nome), fonte=fonte, publico_em=publico_em, visto_em=visto_em)
            for nome in CAMPOS_DA_POSICAO
            if self.permitido(fonte, nome, False)
        }  # fmt: skip
        return (posicao, fonte) if posicao else None

    def _carteira(
        self, cnpj_formatado: str, como_era_em: date
    ) -> tuple[dict, set[str]]:
        raio = raio_x_de_fundo(self.porta, cnpj_formatado, como_era_em)
        servidas = [p for p in map(self._posicao, raio.carteira) if p is not None]
        cortadas = servidas[: self.linhas_maximas]
        carteira = {
            "posicoes": [posicao for posicao, _fonte in cortadas],
            "cortada": len(servidas) > len(cortadas),
        }
        return carteira, {fonte for _posicao, fonte in cortadas}

    def fundo(
        self, cnpj: str, como_era_em: date, retorno_suposto: float | None
    ) -> FundoServido | None:
        """O fundo como era em `como_era_em`, só com o que o portão libera; None se nada sai.

        `retorno_suposto`: o retorno bruto ao ano que o cliente supõe; sem ele, não há custo da taxa.
        """
        normal = cnpj_.normalizar_cnpj(cnpj)
        if not normal:
            raise ValueError(f"CNPJ inválido: {cnpj!r}")
        formatado = cnpj_.formatar(normal)
        corpo: dict = {"cnpj": normal, "como_era_em": como_era_em.isoformat()}
        fontes: set[str] = set()
        linhas = 0
        cadastro = self._cadastro(formatado, como_era_em)
        if cadastro is not None:
            taxas, momento = cadastro
            campos = self._campos_do_cadastro(taxas, momento)
            custo = (
                None
                if retorno_suposto is None
                else self._custo(taxas, momento, retorno_suposto)
            )
            if campos:
                corpo["cadastro"] = campos
                linhas += 1
            if custo is not None:
                corpo["custo_da_taxa"] = custo
            if campos or custo is not None:
                fontes.add(FONTE_DO_CADASTRO)
        carteira, fontes_da_carteira = self._carteira(formatado, como_era_em)
        if not fontes and not carteira["posicoes"]:
            return None
        corpo["carteira"] = carteira
        return FundoServido(
            corpo, fontes | fontes_da_carteira, linhas + len(carteira["posicoes"])
        )
