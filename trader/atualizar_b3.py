"""Baixa o boletim diário de futuros da B3 e acumula em `dados_b3/futuros/`.

    python -m trader.atualizar_b3             # os últimos 30 dias (a B3 guarda ~3 semanas)
    python -m trader.atualizar_b3 --dias 10

Rode todo dia útil depois do fechamento (ou agende no Agendador de Tarefas do Windows): o
histórico só existe se for acumulado. Dias já baixados são pulados.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from trader import b3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dias", type=int, default=30, help="quantos dias para trás")
    args = parser.parse_args()
    fim = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).date()  # o pregão é em horário de Brasília
    inicio = fim - timedelta(days=args.dias)
    try:
        r = b3.atualizar(inicio, fim)
    except (RuntimeError, ValueError) as erro:
        print(f"Falhou: {erro}")
        return 1
    print(
        f"Baixados: {len(r['baixados'])} | já tinha: {len(r['ja_tinha'])} | "
        f"sem pregão ou fora da janela da B3: {len(r['sem_pregao'])}"
    )
    todos = b3.carregar()
    if not todos.empty:
        print(
            f"Acumulado: {todos['Date'].nunique()} dias, "
            f"{todos['produto'].nunique()} produtos, "
            f"de {todos['Date'].min():%d/%m/%Y} a {todos['Date'].max():%d/%m/%Y}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
