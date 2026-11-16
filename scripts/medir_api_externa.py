"""Mede a API externa (TickerLab Data) de fora: latência, vazão e erros por rota e por chave (linha 567, API A7).

    TICKERLAB_CHAVE_MEDIDA=<chave de teste> python -m scripts.medir_api_externa \
        --base http://127.0.0.1:8001 --cnpjs-fundos fundos.txt --cnpjs-empresas empresas.txt \
        --chamadas 200 --concorrencia 1 4 8 --saida medicao.json
    ... --lote-carteiras 2000 --ativos-por-carteira 15     (a carga do cliente-norte)

Para cada rota, `--chamadas` pedidos com cada `--concorrencia` e, por rota, p50/p95/p99/máximo em ms, vazão
(pedidos por segundo), contagem por código HTTP e bytes por resposta. A chave vem da variável de ambiente
(nunca da linha de comando, para não ir ao histórico) e nunca é gravada na saída: o resumo traz só o
prefixo de 8 caracteres. Para sozinho se a taxa de 5xx passar de `--parar-em-5xx` (padrão 2%) ou se o
arquivo `--parar-se-existir` aparecer (freio manual). O lote do norte manda uma carteira de
`--ativos-por-carteira` CNPJs por chamada (o teto da rota é 100) e conta os CNPJs pedidos.

Só chama a API pela porta dada em `--base`; não toca no banco. Aponte para uma instância de medição, não
para a produção.

Roda: manual no servidor (instância descartável de medição), com o "pode" da Diretoria.
"""

import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PREFIXO_DA_CHAVE = 8
TIMEOUT_S = 30
MINIMO_PARA_O_FREIO = 20  # pedidos antes de a taxa de 5xx valer

Resultado = tuple[int, float, int]  # código HTTP, ms, bytes


def percentil(valores: Sequence[float], p: float) -> float:
    """O percentil `p` (0 a 100) pelo método do posto mais próximo; 0 para lista vazia."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    posto = max(1, math.ceil(p / 100 * len(ordenados)))
    return ordenados[posto - 1]


def resumir(
    tempos_ms: Sequence[float],
    codigos: Sequence[int],
    bytes_: Sequence[int],
    duracao_s: float,
) -> dict:
    """O resumo de uma rota: latência, vazão, códigos HTTP e tamanho médio da resposta."""
    por_codigo: dict[str, int] = {}
    for codigo in codigos:
        por_codigo[str(codigo)] = por_codigo.get(str(codigo), 0) + 1
    return {
        "pedidos": len(codigos),
        "p50_ms": round(percentil(tempos_ms, 50), 1),
        "p95_ms": round(percentil(tempos_ms, 95), 1),
        "p99_ms": round(percentil(tempos_ms, 99), 1),
        "max_ms": round(max(tempos_ms, default=0.0), 1),
        "pedidos_por_s": round(len(codigos) / duracao_s, 2) if duracao_s > 0 else 0.0,
        "codigos": por_codigo,
        "bytes_medio": round(sum(bytes_) / len(bytes_)) if bytes_ else 0,
    }


def taxa_de_5xx(codigos: Sequence[int]) -> float:
    return sum(1 for c in codigos if c >= 500) / len(codigos) if codigos else 0.0


def chamar(
    base: str, chave: str, metodo: str, caminho: str, corpo: object = None
) -> Resultado:
    """Um pedido. Erro de rede conta como código 0."""
    dados = None if corpo is None else json.dumps(corpo).encode()
    pedido = urllib.request.Request(
        base + caminho,
        data=dados,
        method=metodo,
        headers={
            "Authorization": f"Bearer {chave}",
            "Content-Type": "application/json",
        },
    )
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as resposta:
            lido, codigo = resposta.read(), resposta.status
    except urllib.error.HTTPError as erro:
        lido, codigo = erro.read(), erro.code
    except (urllib.error.URLError, TimeoutError, OSError):
        lido, codigo = b"", 0
    return codigo, (time.perf_counter() - inicio) * 1000, len(lido)


def carteiras(cnpjs: Sequence[str], quantas: int, ativos: int) -> list[list[str]]:
    """`quantas` carteiras de `ativos` CNPJs, girando pela lista dada."""
    if not cnpjs:
        return []
    return [
        [cnpjs[(i * ativos + j) % len(cnpjs)] for j in range(ativos)]
        for i in range(quantas)
    ]


def medir_rota(
    nome: str,
    tarefas: Sequence[Callable[[], Resultado]],
    concorrencia: int,
    parar_em_5xx: float,
    freio: Path | None,
) -> dict:
    """Roda as tarefas com `concorrencia` clientes; para se passar de `parar_em_5xx` ou se o freio existir."""
    resultados: list[Resultado] = []
    trava = threading.Lock()
    parou = threading.Event()

    def uma(tarefa: Callable[[], Resultado]) -> None:
        if parou.is_set():
            return
        resultado = tarefa()
        with trava:
            resultados.append(resultado)
            if freio is not None and freio.exists():
                parou.set()
            codigos = [r[0] for r in resultados]
            if (
                len(codigos) >= MINIMO_PARA_O_FREIO
                and taxa_de_5xx(codigos) > parar_em_5xx
            ):
                parou.set()

    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concorrencia) as pool:
        list(pool.map(uma, tarefas))
    duracao = time.perf_counter() - inicio
    resumo = resumir(
        [r[1] for r in resultados],
        [r[0] for r in resultados],
        [r[2] for r in resultados],
        duracao,
    )
    return resumo | {
        "rota": nome,
        "concorrencia": concorrencia,
        "parou_antes": parou.is_set(),
    }


def ler_lista(caminho: str | None) -> list[str]:
    if not caminho:
        return []
    linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    return [linha.strip() for linha in linhas if linha.strip()]


def _rotas_soltas(
    args: argparse.Namespace, chave: str, freio: Path | None
) -> list[dict]:
    fundos, empresas = ler_lista(args.cnpjs_fundos), ler_lista(args.cnpjs_empresas)

    def get(caminho: str) -> Callable[[], Resultado]:
        return lambda: chamar(args.base, chave, "GET", caminho)

    def girando(modelo: str, cnpjs: list[str]) -> list[Callable[[], Resultado]]:
        return [get(modelo.format(cnpjs[i % len(cnpjs)])) for i in range(args.chamadas)]

    conjuntos = {
        "GET /data/v1/catalog": [get("/data/v1/catalog")] * args.chamadas,
        "GET /data/v1/usage": [get("/data/v1/usage")] * args.chamadas,
    }
    if fundos:
        conjuntos["GET /data/v1/funds/{cnpj}"] = girando("/data/v1/funds/{}", fundos)
    if empresas:
        conjuntos["GET /data/v1/companies/{cnpj}"] = girando(
            "/data/v1/companies/{}", empresas
        )
        conjuntos["GET /data/v1/companies/{cnpj}/financials"] = girando(
            "/data/v1/companies/{}/financials", empresas
        )
    return [
        medir_rota(nome, tarefas, c, args.parar_em_5xx, freio)
        for c in args.concorrencia
        for nome, tarefas in conjuntos.items()
    ]


def _lote_do_norte(
    args: argparse.Namespace, chave: str, freio: Path | None
) -> list[dict]:
    saidas = []
    listas = (
        ("/data/v1/funds/batch", ler_lista(args.cnpjs_fundos)),
        ("/data/v1/companies/batch", ler_lista(args.cnpjs_empresas)),
    )
    for rota, cnpjs in listas:
        if not cnpjs:
            continue
        pedidos = [
            lambda cs=carteira, r=rota: chamar(
                args.base, chave, "POST", r, {"cnpjs": cs}
            )
            for carteira in carteiras(
                cnpjs, args.lote_carteiras, args.ativos_por_carteira
            )
        ]
        resumo = medir_rota(
            f"POST {rota} (uma carteira por chamada)",
            pedidos,
            4,
            args.parar_em_5xx,
            freio,
        )
        saidas.append(
            resumo | {"cnpjs_pedidos": resumo["pedidos"] * args.ativos_por_carteira}
        )
    return saidas


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--cnpjs-fundos")
    ap.add_argument("--cnpjs-empresas")
    ap.add_argument("--chamadas", type=int, default=200)
    ap.add_argument("--concorrencia", type=int, nargs="+", default=[1, 4, 8])
    ap.add_argument("--lote-carteiras", type=int, default=0)
    ap.add_argument("--ativos-por-carteira", type=int, default=15)
    ap.add_argument("--parar-em-5xx", type=float, default=0.02)
    ap.add_argument("--parar-se-existir")
    ap.add_argument("--saida", required=True)
    args = ap.parse_args(argv)

    chave = os.environ.get("TICKERLAB_CHAVE_MEDIDA", "")
    if not chave:
        print("defina TICKERLAB_CHAVE_MEDIDA", file=sys.stderr)
        return 2
    freio = Path(args.parar_se_existir) if args.parar_se_existir else None
    rotas = _rotas_soltas(args, chave, freio)
    if args.lote_carteiras:
        rotas += _lote_do_norte(args, chave, freio)
    saida = {"chave": chave[:PREFIXO_DA_CHAVE] + "…", "base": args.base, "rotas": rotas}
    Path(args.saida).write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(saida, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
