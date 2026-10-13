"""Textos do selo "dado em conferência" (série 1 da base de ML, PR 4; ADR 0028, item 2).

Um lugar só para o que o público lê sobre as regras de qualidade: a tela Fundamentos mostra o selo
ao lado de cada documento e o porquê de cada achado; o site (`metodologia.html`) lista as regras.
Os limites citados vêm das constantes de `base/regras.py`, para o texto nunca dizer um número
diferente do que a regra usa.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from base.regras import (
    FATOR_DE_SALTO,
    TOLERANCIA_EM_REAIS,
    TOLERANCIA_R1,
    TOLERANCIA_R2,
)

TITULO_DO_SELO = "Dado em conferência"
TITULO_DA_LISTA = "Dados em conferência"
# a seção do site que lista as regras (`scripts/gerar_site.py`, página de metodologia)
ANCORA_NO_SITE = "qualidade-dos-dados"
URL_DAS_REGRAS = f"https://tickerlab.com.br/metodologia.html#{ANCORA_NO_SITE}"
EXPLICACAO_DO_SELO = (
    "Uma regra automática e fixa pediu uma segunda olhada neste número. Não quer dizer que ele "
    "esteja errado: quer dizer que vale conferir no documento original antes de tirar conclusões. "
    "O TickerLab nunca corrige nem apaga o número que a empresa entregou; só aponta."
)


def _pct(fracao: float) -> str:
    return f"{fracao:.1%}".replace(".", ",")


def _vezes(fator: float) -> str:
    return f"{fator:g}".replace(".", ",")


MIL_REAIS = f"R$ {TOLERANCIA_EM_REAIS / 1000:g} mil"


@dataclass(frozen=True)
class RegraDoSelo:
    titulo: str
    o_que_confere: str


# as regras que a tarefa diária roda hoje (a R5, reapresentação, entra com o leitor do ENET)
REGRAS: dict[str, RegraDoSelo] = {
    "R1": RegraDoSelo(
        "Ativo diferente do passivo",
        "O ativo total precisa ser igual ao passivo total mais o patrimônio líquido "
        f"(tolerância de {_pct(TOLERANCIA_R1)} ou {MIL_REAIS}, o arredondamento da CVM).",
    ),
    "R2": RegraDoSelo(
        "Subtotal que não fecha",
        "No balanço, as contas de baixo precisam somar a conta de cima (tolerância de "
        f"{_pct(TOLERANCIA_R2)}). Contas de baixo zeradas não disparam: é hábito comum de "
        "preenchimento.",
    ),
    "R3": RegraDoSelo(
        "Escala suspeita",
        "O mesmo número vale cerca de mil vezes mais (ou menos) que no documento anterior: sinal "
        "de reais e milhares trocados.",
    ),
    "R4": RegraDoSelo(
        "Valor impossível", "Ativo total, ativo circulante ou caixa negativos."
    ),
    "R6": RegraDoSelo(
        "Refeito pela empresa no balanço seguinte",
        "O balanço seguinte traz, na coluna do ano anterior, um ativo total, receita, lucro ou "
        "patrimônio diferente do que a empresa tinha publicado. Vale a partir da entrega do "
        "balanço seguinte.",
    ),
    "R7": RegraDoSelo(
        "Salto fora do padrão",
        f"Receita ou ativo total que subiu ou caiu {_vezes(FATOR_DE_SALTO)} vezes ou mais em um "
        "ano, sem fato relevante ou comunicado da empresa no período que explique.",
    ),
    "R8": RegraDoSelo(
        "Balanço atrasado",
        "DFP ou ITR entregue depois do prazo da CVM, ou ainda não entregue. Esperamos o balanço de "
        "quem entregou o do ano anterior e continuava registrada na data do prazo. O prazo é "
        "calculado sem feriados: 1 ou 2 dias podem ser só um feriado.",
    ),
    "R9": RegraDoSelo(
        "Linhas repetidas no arquivo",
        "O arquivo da CVM trouxe a mesma linha mais de uma vez; o TickerLab conta cada uma só "
        "uma vez.",
    ),
    "R10": RegraDoSelo(
        "Lucro em branco",
        "O lucro do período veio zerado numa empresa que teve receita no mesmo período.",
    ),
    "R11": RegraDoSelo(
        "Conta de cima em branco",
        "Uma conta veio zerada, mas as contas abaixo dela têm valor: quem lê a conta de cima vê "
        "zero onde há dinheiro.",
    ),
}


class AchadoParaTexto(Protocol):
    """O que o texto usa de um achado (linha do banco ou `base.regras.Achado`)."""

    regra: str
    documento: str
    referencia: date
    porque: str


def texto_do_selo(achado: AchadoParaTexto) -> str:
    """ "Título da regra (DFP de 31/12/2022): porquê", a frase mostrada ao lado do número."""
    regra = REGRAS.get(achado.regra)
    titulo = regra.titulo if regra else TITULO_DO_SELO
    return f"{titulo} ({achado.documento} de {achado.referencia:%d/%m/%Y}): {achado.porque}"


def contagem_por_documento(
    achados: Iterable[AchadoParaTexto],
) -> dict[tuple[str, date], int]:
    """Quantos achados abertos cada documento (DFP ou ITR de uma data) tem."""
    return dict(Counter((a.documento, a.referencia) for a in achados))


def selo_do_documento(
    contagem: dict[tuple[str, date], int], documento: str, referencia: date
) -> str:
    """O texto curto da coluna do selo na tabela dos documentos ("" quando não há achado)."""
    quantos = contagem.get((documento, referencia), 0)
    return f"Em conferência ({quantos})" if quantos else ""
