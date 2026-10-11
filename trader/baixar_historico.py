"""Baixa o histórico diário de todo o universo (M1) e grava em Parquet em `dados_mt5/`.

Roda no PC, com o MetaTrader 5 aberto numa conta DEMO (só para a parte forex/metais):

    python -m trader.baixar_historico            # tudo
    python -m trader.baixar_historico --so yfinance

Só lê dados. Escreve `dados_mt5/relatorio_de_qualidade.csv` com o resultado de cada série.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from trader.dados import (
    PASTA_PADRAO,
    Qualidade,
    detectar_saltos,
    limpo_desde,
    marcar_incoerentes,
    reparar_candles,
    salvar,
    verificar_qualidade,
)
from trader.mt5 import (
    ConexaoMT5,
    ContaRealRecusadaError,
    MT5IndisponivelError,
)
from trader.universo import UNIVERSO, Ativo

ANOS_MT5 = 25  # o corretor entrega o que tiver
TENTATIVAS_MT5 = 3
COLUNAS = ["Open", "High", "Low", "Close", "Volume"]


def baixar_yfinance(simbolo: str) -> pd.DataFrame:
    """Histórico diário completo, com preços ajustados por dividendos e desdobramentos."""
    import yfinance as yf

    bruto = yf.Ticker(simbolo).history(period="max", interval="1d", auto_adjust=True)
    if bruto.empty:
        raise ValueError(f"O yfinance não devolveu nada para {simbolo}.")
    candles = bruto[COLUNAS].copy()
    candles.index = pd.to_datetime(candles.index).tz_localize(None).normalize()
    candles.index.name = "Date"
    candles = candles[~candles.index.duplicated(keep="last")].sort_index()
    return candles.dropna(subset=["Open", "High", "Low", "Close"])


def _linha(
    ativo: Ativo, q: Qualidade | str, extras: dict[str, object] | None = None
) -> dict[str, object]:
    base = {
        "arquivo": ativo.arquivo,
        "simbolo": ativo.simbolo,
        "fonte": ativo.fonte,
        "classe": ativo.classe,
        "papel": ativo.papel,
    }
    if isinstance(q, str):
        return {**base, "situacao": q}
    extras = extras or {}
    return {
        **base,
        "situacao": _situacao(ativo, q, int(extras.get("reparados", 0))),
        "linhas": q.linhas,
        "inicio": q.inicio.date() if q.inicio is not None else None,
        "fim": q.fim.date() if q.fim is not None else None,
        "duplicadas": q.indice_repetido,
        "vazios": q.valores_vazios,
        "precos_nao_positivos": q.precos_nao_positivos,
        "candles_incoerentes": q.candles_incoerentes,
        "maior_lacuna_dias": (
            max(p.days for _, p in q.maiores_lacunas) if q.maiores_lacunas else 0
        ),
        "aviso": ativo.aviso,
        **extras,
    }


def _situacao(ativo: Ativo, q: Qualidade, reparados: int) -> str:
    """ok / reparada (OHLC consertado, fechamento intacto) / ok com aviso / COM PROBLEMAS."""
    if q.aprovada:
        return "reparada" if reparados else "ok"
    so_preco_negativo_conhecido = (
        bool(ativo.aviso)
        and q.precos_nao_positivos > 0
        and q.indice_repetido == 0
        and not q.fora_de_ordem
        and q.valores_vazios == 0
        and q.candles_incoerentes == 0
    )
    return "ok com aviso" if so_preco_negativo_conhecido else "COM PROBLEMAS"


def _da_fonte(ativos: list[Ativo], fonte: str) -> list[Ativo]:
    return [a for a in ativos if a.fonte == fonte]


def _guardar(
    ativo: Ativo, bruto: pd.DataFrame, pasta: Path
) -> tuple[Qualidade, dict[str, object]]:
    """Repara o OHLC, grava e mede. As contagens do bruto vão para o relatório."""
    desde = limpo_desde(bruto)
    candles, reparados = reparar_candles(bruto)
    saltos = detectar_saltos(candles["Close"])
    salvar(candles, ativo.arquivo, "D1", pasta)
    extras: dict[str, object] = {
        "incoerentes_no_bruto": int(marcar_incoerentes(bruto).sum()),
        "reparados": reparados,
        "limpo_desde": desde.date() if desde is not None else None,
        "saltos_suspeitos": len(saltos),
    }
    return verificar_qualidade(candles, "D1"), extras


def baixar_tudo(
    fontes: tuple[str, ...],
    pasta: Path = PASTA_PADRAO,
    ativos: list[Ativo] | None = None,
    abrir_mt5: Callable[[], ConexaoMT5] = ConexaoMT5,
    baixar_yf: Callable[[str], pd.DataFrame] = baixar_yfinance,
) -> pd.DataFrame:
    """Baixa cada ativo da lista (o universo inteiro por padrão) e grava o relatório."""
    lista = UNIVERSO if ativos is None else ativos
    linhas: list[dict[str, object]] = []

    if "yfinance" in fontes:
        for ativo in _da_fonte(lista, "yfinance"):
            q: Qualidade | str
            extras: dict[str, object] = {}
            try:
                q, extras = _guardar(ativo, baixar_yf(ativo.simbolo), pasta)
            except Exception as erro:  # noqa: BLE001 (uma série ruim não derruba as outras)
                q = f"falhou: {erro}"
            linhas.append(_linha(ativo, q, extras))
            print(f"  {ativo.simbolo}: {linhas[-1]['situacao']}")

    if "mt5" in fontes:
        inicio = datetime.now(UTC) - timedelta(days=365 * ANOS_MT5)
        with abrir_mt5() as mt5:
            print(f"MT5: {mt5.conta.servidor} ({mt5.conta.modo})")
            for ativo in _da_fonte(lista, "mt5"):
                q = "não tentou"
                extras = {}
                # Na primeira vez o terminal baixa o histórico do corretor e pode falhar com
                # "Call failed"; tentar de novo costuma funcionar quando o cache já avançou.
                for tentativa in range(1, TENTATIVAS_MT5 + 1):
                    try:
                        candles = mt5.candles(ativo.simbolo, "D1", inicio)
                        q, extras = _guardar(ativo, candles, pasta)
                        break
                    except Exception as erro:  # noqa: BLE001
                        q = f"falhou: {erro}"
                        print(f"  {ativo.simbolo}: tentativa {tentativa} falhou")
                linhas.append(_linha(ativo, q, extras))
                print(f"  {ativo.simbolo}: {linhas[-1]['situacao']}")

    relatorio = pd.DataFrame(linhas)
    pasta.mkdir(parents=True, exist_ok=True)
    relatorio.to_csv(pasta / "relatorio_de_qualidade.csv", index=False)
    return relatorio


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--so", choices=["mt5", "yfinance"], help="baixar só uma fonte")
    args = parser.parse_args()
    fontes = (args.so,) if args.so else ("yfinance", "mt5")
    print(f"Universo: {len(UNIVERSO)} ativos. Fontes: {', '.join(fontes)}.")
    try:
        relatorio = baixar_tudo(fontes)
    except ContaRealRecusadaError as erro:
        print(f"RECUSADO: {erro}")
        return 2
    except MT5IndisponivelError as erro:
        print(f"Não deu para conectar ao MT5: {erro}")
        return 1
    usaveis = relatorio["situacao"].isin(["ok", "reparada", "ok com aviso"]).sum()
    print(f"\n{usaveis} de {len(relatorio)} séries utilizáveis.")
    print(relatorio["situacao"].value_counts().to_string())
    print("Relatório: dados_mt5/relatorio_de_qualidade.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
