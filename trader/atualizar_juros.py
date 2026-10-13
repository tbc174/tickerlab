"""Baixa as taxas básicas dos bancos centrais (BIS) e guarda em `dados_juros/`.

    python -m trader.atualizar_juros

Uma requisição só, ~60 MB, alguns segundos. Rode de vez em quando (as taxas mudam devagar).
"""

from __future__ import annotations

import sys

import requests

from trader import juros


def main() -> int:
    try:
        tabela = juros.baixar_do_bis()
    except (requests.RequestException, ValueError) as erro:
        print(f"Falhou: {erro}")
        return 1
    caminho = juros.salvar(tabela)
    preenchida = tabela.ffill()
    print(
        f"{len(tabela.columns)} moedas, de {tabela.index.min():%d/%m/%Y} a {tabela.index.max():%d/%m/%Y}."
    )
    print("Última taxa (% ao ano):", preenchida.iloc[-1].round(2).to_dict())
    print(f"Gravado em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
