"""Teste de carga leve: dispara várias requisições ao mesmo tempo e mostra tempos e erros.

Uso:
    python scripts/carga_leve.py http://localhost:8000/saude --total 300 --simultaneas 20

Serve para ter uma ideia de como o serviço se comporta sob uso simultâneo (por exemplo, a API
pelo túnel SSH). Não é um teste de estresse: não o aponte para serviços de terceiros.
"""

import argparse
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def uma_requisicao(url: str, limite: float) -> tuple[bool, float]:
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=limite) as resposta:
            resposta.read()
            ok = 200 <= resposta.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        ok = False
    return ok, time.perf_counter() - inicio


def percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    posicao = min(len(ordenados) - 1, round(p / 100 * (len(ordenados) - 1)))
    return ordenados[posicao]


def resumir(resultados: list[tuple[bool, float]], duracao: float) -> dict:
    tempos = [t for _, t in resultados]
    erros = sum(1 for ok, _ in resultados if not ok)
    return {
        "requisicoes": len(resultados),
        "erros": erros,
        "por_segundo": round(len(resultados) / duracao, 1) if duracao else 0.0,
        "p50_ms": round(statistics.median(tempos) * 1000, 1),
        "p95_ms": round(percentil(tempos, 95) * 1000, 1),
        "maximo_ms": round(max(tempos) * 1000, 1),
    }


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("url")
    analisador.add_argument("--total", type=int, default=200)
    analisador.add_argument("--simultaneas", type=int, default=10)
    analisador.add_argument(
        "--limite", type=float, default=10.0, help="segundos por requisição"
    )
    args = analisador.parse_args(argv)
    if not 1 <= args.total <= 5000 or not 1 <= args.simultaneas <= 100:
        print("Use --total de 1 a 5000 e --simultaneas de 1 a 100.")
        return 2
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.simultaneas) as pool:
        resultados = list(
            pool.map(lambda _: uma_requisicao(args.url, args.limite), range(args.total))
        )
    resumo = resumir(resultados, time.perf_counter() - inicio)
    for chave, valor in resumo.items():
        print(f"{chave}: {valor}")
    return 1 if resumo["erros"] else 0


if __name__ == "__main__":
    sys.exit(main())
