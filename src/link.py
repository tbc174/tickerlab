"""Link compartilhável: guarda as escolhas do topo do app nos parâmetros do endereço (URL).

Quem abrir o endereço copiado da barra do navegador cai na mesma tela. O que vem da URL é
tratado como texto não confiável: só entram valores conhecidos e tickers com caracteres
comuns, e a lista de favoritos tem tamanho máximo.
"""

import re

from src.dados import PERIODOS_VALIDOS

MODOS_DA_TAXA = ("Zero", "CDI (Banco Central)", "Digitar")
MAX_FAVORITOS = 20  # o maior limite entre os planos (src/planos.py)
PADRAO_DE_TICKER = re.compile(r"[A-Z0-9.^=\-]{1,15}")
VERDADEIROS = ("1", "true", "sim")


def ticker_valido(texto: str | None) -> bool:
    return bool(PADRAO_DE_TICKER.fullmatch((texto or "").strip().upper()))


def montar_parametros(
    ticker: str,
    periodo: str,
    modo_da_taxa: str,
    em_reais: bool,
    usar_exemplo: bool,
    favoritos: list[str],
) -> dict[str, str]:
    """Os parâmetros que descrevem a tela atual (as caixas desligadas ficam de fora)."""
    parametros = {"ticker": ticker, "periodo": periodo, "taxa": modo_da_taxa}
    if em_reais:
        parametros["reais"] = "1"
    if usar_exemplo:
        parametros["exemplo"] = "1"
    if favoritos:
        parametros["fav"] = ",".join(favoritos[:MAX_FAVORITOS])
    return parametros


def ler_parametros(parametros: dict[str, str]) -> dict:
    """Valida os parâmetros da URL. Devolve só o que for aceitável (o resto é ignorado)."""
    lidos: dict = {}
    ticker = (parametros.get("ticker") or "").strip().upper()
    if ticker_valido(ticker):
        lidos["ticker"] = ticker
    if parametros.get("periodo") in PERIODOS_VALIDOS:
        lidos["periodo"] = parametros["periodo"]
    if parametros.get("taxa") in MODOS_DA_TAXA:
        lidos["taxa"] = parametros["taxa"]
    for chave, nome in (("reais", "em_reais"), ("exemplo", "usar_exemplo")):
        if parametros.get(chave, "").lower() in VERDADEIROS:
            lidos[nome] = True
    favoritos: list[str] = []
    for pedaco in (parametros.get("fav") or "").split(","):
        pedaco = pedaco.strip().upper()
        if ticker_valido(pedaco) and pedaco not in favoritos:
            favoritos.append(pedaco)
    if favoritos:
        lidos["favoritos"] = favoritos[:MAX_FAVORITOS]
    return lidos


def alternar_favorito(
    favoritos: list[str], ticker: str, maximo: int = MAX_FAVORITOS
) -> list[str]:
    """Põe o ticker na lista se não estiver, ou tira se estiver. Devolve uma lista nova."""
    ticker = (ticker or "").strip().upper()
    if not ticker_valido(ticker):
        raise ValueError("Digite um ticker válido antes de favoritar.")
    if ticker in favoritos:
        return [f for f in favoritos if f != ticker]
    if len(favoritos) >= maximo:
        raise ValueError(f"O limite é de {maximo} favoritos. Remova algum antes.")
    return [*favoritos, ticker]
