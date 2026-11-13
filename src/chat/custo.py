"""Quanto custa uma pergunta ao chat (linha 903) e quanto o teto do mês vale em dólar.

Preços da tabela oficial da Anthropic, lidos na skill `claude-api` (`shared/models.md` e
`shared/prompt-caching.md`) em 13/11/2026, em dólares por milhão de tokens:

| Modelo            | Entrada | Saída | Leitura do cache | Gravação do cache (5 min, 1,25x a entrada) |
|-------------------|---------|-------|------------------|--------------------------------------------|
| claude-opus-5-5   | 4,00    | 20,00 | 0,20             | 5,00                                       |
| claude-sonnet-5-5 | 2,00    | 10,00 | 0,10             | 2,50                                       |

Dólar por milhão de tokens é o mesmo que microdólar por token; aqui ficam em milésimos de microdólar por
token, para a conta ser só de inteiros. Modelo fora da tabela não sobe: sem preço não há como conferir o teto.
"""

from dataclasses import dataclass

from src.planos import LimitesDoChat

MILESIMOS = 1_000
MICRODOLARES_POR_DOLAR = 1_000_000
CENTAVOS_POR_REAL = 100


@dataclass(frozen=True)
class PrecoDoModelo:
    """Milésimos de microdólar por token (US$ 4,00 por milhão = 4.000)."""

    entrada: int
    saida: int
    cache_lido: int
    cache_gravado: int


PRECOS: dict[str, PrecoDoModelo] = {
    "claude-opus-5-5": PrecoDoModelo(
        entrada=4_000, saida=20_000, cache_lido=200, cache_gravado=5_000
    ),
    "claude-sonnet-5-5": PrecoDoModelo(
        entrada=2_000, saida=10_000, cache_lido=100, cache_gravado=2_500
    ),
}


@dataclass(frozen=True)
class UsoDoModelo:
    """Os tokens de uma ou mais voltas, como o modelo informa (a entrada sem o que veio do cache)."""

    entrada: int = 0
    saida: int = 0
    cache_lido: int = 0
    cache_gravado: int = 0

    def __add__(self, outro: "UsoDoModelo") -> "UsoDoModelo":
        return UsoDoModelo(
            entrada=self.entrada + outro.entrada,
            saida=self.saida + outro.saida,
            cache_lido=self.cache_lido + outro.cache_lido,
            cache_gravado=self.cache_gravado + outro.cache_gravado,
        )


def tem_preco(modelo: str) -> bool:
    return modelo in PRECOS


def custo_em_microdolares(modelo: str, uso: UsoDoModelo) -> int:
    """O custo, arredondado para cima (o teto erra para o lado de gastar menos)."""
    preco = PRECOS[modelo]
    milesimos = (
        uso.entrada * preco.entrada
        + uso.saida * preco.saida
        + uso.cache_lido * preco.cache_lido
        + uso.cache_gravado * preco.cache_gravado
    )
    return -(-milesimos // MILESIMOS)


def teto_em_microdolares(limites: LimitesDoChat) -> int:
    """O teto do mês, em reais, convertido em dólar pelo câmbio de cautela dos limites."""
    centavos = limites.teto_do_mes_em_reais * CENTAVOS_POR_REAL
    return centavos * MICRODOLARES_POR_DOLAR // limites.centavos_por_dolar
