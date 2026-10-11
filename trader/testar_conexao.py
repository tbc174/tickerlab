"""Confere a ligação do Python com o MetaTrader 5 e baixa uma amostra de candles diários.

Roda no PC, com o terminal MetaTrader 5 aberto e logado numa conta DEMO:

    python -m trader.testar_conexao

Só lê. Se a conta logada for real, recusa e não faz nada.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from trader.dados import verificar_qualidade
from trader.mt5 import (
    ConexaoMT5,
    ContaRealRecusadaError,
    MT5IndisponivelError,
    SimboloIndisponivelError,
)

SIMBOLOS_DE_AMOSTRA = ("EURUSD", "USDJPY", "GBPUSD")


def main() -> int:
    try:
        with ConexaoMT5() as mt5:
            conta = mt5.conta
            print(
                f"Conectado: servidor {conta.servidor}, conta {conta.modo}, moeda {conta.moeda}"
            )
            todos = mt5.simbolos()
            print(
                f"O corretor oferece {len(todos)} símbolos (primeiros: {', '.join(todos[:8])})"
            )
            inicio = datetime.now(UTC) - timedelta(days=365)
            for simbolo in SIMBOLOS_DE_AMOSTRA:
                try:
                    candles = mt5.candles(simbolo, "D1", inicio)
                except SimboloIndisponivelError as erro:
                    print(f"  {simbolo}: indisponível ({erro})")
                    continue
                q = verificar_qualidade(candles, "D1")
                situacao = "ok" if q.aprovada else "COM PROBLEMAS"
                print(
                    f"  {simbolo}: {q.linhas} candles de {q.inicio:%d/%m/%Y} a {q.fim:%d/%m/%Y} ({situacao})"
                )
    except ContaRealRecusadaError as erro:
        print(f"RECUSADO: {erro}")
        return 2
    except MT5IndisponivelError as erro:
        print(f"Não deu para conectar: {erro}")
        return 1
    print("Tudo certo: leitura de dados funcionando.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
