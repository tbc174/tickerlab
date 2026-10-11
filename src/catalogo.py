"""O catálogo da busca de ativos: código, nome, bolsa e tipo (`conteudo/catalogo_de_ativos.csv`).

Gerado por `scripts/gerar_catalogo.py` a partir do cadastro público da B3 (só ativos negociados),
das empresas do S&P 500 e de uma lista fixa de índices, criptomoedas e câmbio. A busca da tela
filtra esta lista enquanto a pessoa digita; quem digita um código fora dela ainda pode usá-lo.

Regra (blueprint, SEARCH-03): nunca trocar o ativo em silêncio. O que é escolhido na lista vale
como está; um código digitado só é ligado ao catálogo quando bate exatamente com um código dele.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.dados import normalizar_ticker

ARQUIVO = Path(__file__).resolve().parent.parent / "conteudo" / "catalogo_de_ativos.csv"
EXEMPLOS = ("PETR4.SA", "VALE3.SA", "ITUB4.SA", "AAPL", "^BVSP", "BTC-USD")


@lru_cache(maxsize=1)
def carregar() -> pd.DataFrame:
    """O catálogo, com o símbolo do Yahoo como índice."""
    return pd.read_csv(ARQUIVO, comment="#", dtype=str).set_index("simbolo")


@lru_cache(maxsize=1)
def _por_codigo() -> dict[str, str]:
    catalogo = carregar()
    return {codigo.upper(): simbolo for simbolo, codigo in catalogo["codigo"].items()}


def simbolos() -> list[str]:
    return list(carregar().index)


def rotulo(simbolo: str) -> str:
    """O que a lista mostra: "PETR4 · Petroleo Brasileiro S.A. Petrobras PN · B3 · Ação"."""
    catalogo = carregar()
    if simbolo not in catalogo.index:
        return f"{simbolo} · fora do catálogo"
    linha = catalogo.loc[simbolo]
    tipo = (
        "" if linha["tipo"] in ("Índice", "Cripto", "Câmbio") else f" · {linha['tipo']}"
    )
    return f"{linha['codigo']} · {linha['nome']} · {linha['bolsa']}{tipo}"


def resolver(texto: str | None) -> str | None:
    """O símbolo do Yahoo para o que foi escolhido ou digitado (None se vazio).

    Escolhido na lista: o próprio símbolo. Digitado: o símbolo do catálogo cujo código bate
    exatamente (petr4 → PETR4.SA, usd/brl → BRL=X); senão, a regra antiga do app
    (`normalizar_ticker`), e a página avisa se não achar dados.
    """
    texto = (texto or "").strip()
    if not texto:
        return None
    if texto in carregar().index:
        return texto
    return _por_codigo().get(texto.upper(), normalizar_ticker(texto))


def opcoes(atual: str | None = None) -> list[str]:
    """As opções da busca, garantindo que o ativo atual esteja nelas (mesmo fora do catálogo)."""
    lista = simbolos()
    if atual and atual not in carregar().index:
        lista = [atual, *lista]
    return lista


def esta_no_catalogo(simbolo: str) -> bool:
    return simbolo in carregar().index
