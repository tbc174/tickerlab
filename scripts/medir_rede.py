"""Consulta de referência da rede, cronometrada (ADR 0077, item 1; plano da rede, PR 4, tarefa 4.4).

    python -m scripts.medir_rede                                  (as 100 maiores, 3 saltos)
    python -m scripts.medir_rede --pasta <base> --saida <arquivo.json> --quantas 100 --profundidade 4
    python -m scripts.medir_rede --cnpjs 33.256.439/0001-39,60.746.948/0001-12

Pela porta (`base.porta`), `rede(cnpj, profundidade=3)` para as maiores companhias e grava, por
empresa, o tempo, as ligações e as entidades encontradas e, no resumo, o tempo total e a memória
máxima do processo. A ADR 0077 só reabre a decisão de banco de grafos se 4 ou mais saltos não couberem
numa noite: este é o número que decide.

**As maiores pelo ativo total** (conta 1 do balanço consolidado mais novo, valor vigente): a base não
guarda o valor de mercado, e para medir a rede o que importa é ter as empresas mais ligadas, que são
as grandes. Só CNPJ e nome de companhia saem no arquivo (nenhuma pessoa).
"""

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from base import porta
from src import acervo

log = logging.getLogger(__name__)
QUANTAS = 100
PROFUNDIDADE = 3
ATIVO_TOTAL = {"conta": "1", "demonstracao": "BPA", "grupo": "con"}


def maiores(p: porta.Porta, quantas: int) -> list[tuple[str, str]]:
    """(cnpj, nome) das `quantas` companhias com o maior ativo total no balanço mais novo."""
    balancos = p.ler("demonstracoes_como_era", filtros=ATIVO_TOTAL)
    vigentes = balancos[balancos["ate"].isna()]
    mais_novo = vigentes.sort_values(["cnpj", "fim"]).drop_duplicates(
        "cnpj", keep="last"
    )
    escolhidas = mais_novo.sort_values(["valor", "cnpj"], ascending=[False, True]).head(
        quantas
    )
    return list(zip(escolhidas["cnpj"], escolhidas["empresa"], strict=True))


def _memoria_mb() -> float:
    try:
        import psutil
    except (
        ImportError
    ):  # fora do ambiente de desenvolvimento: a medida fica sem memória
        return 0.0
    return psutil.Process().memory_info().rss / 1024**2


def medir(p: porta.Porta, empresas: list[tuple[str, str]], profundidade: int) -> dict:
    medidas, memoria_maxima = [], _memoria_mb()
    inicio_de_tudo = time.perf_counter()
    for cnpj, nome in empresas:
        inicio = time.perf_counter()
        try:
            rede = p.rede(cnpj, profundidade=profundidade)
            medida = {
                "ligacoes": len(rede.ligacoes),
                "entidades": len(rede.entidades),
                "saltos": int(rede.entidades["salto"].max()),
            }
        except LookupError as erro:
            medida = {"erro": str(erro)}
        memoria_maxima = max(memoria_maxima, _memoria_mb())
        medidas.append(
            {
                "cnpj": cnpj,
                "empresa": nome,
                "segundos": time.perf_counter() - inicio,
                **medida,
            }
        )
        log.info("%s: %.2f s %s", cnpj, medidas[-1]["segundos"], medida)
    tempos = [m["segundos"] for m in medidas]
    return {
        "profundidade": profundidade,
        "medido_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "resumo": {
            "empresas": len(medidas),
            "sem_entidade": sum("erro" in m for m in medidas),
            "segundos_no_total": time.perf_counter() - inicio_de_tudo,
            "segundos_na_mais_lenta": max(tempos, default=0.0),
            "segundos_na_mediana": float(pd.Series(tempos).median()) if tempos else 0.0,
            "memoria_maxima_mb": round(memoria_maxima, 1),
        },
        "empresas": medidas,
    }


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--pasta", type=Path, default=None, help="a base (<acervo>/base)"
    )
    argumentos.add_argument("--saida", type=Path, default=None, help="o JSON da medida")
    argumentos.add_argument("--quantas", type=int, default=QUANTAS)
    argumentos.add_argument("--profundidade", type=int, default=PROFUNDIDADE)
    argumentos.add_argument(
        "--cnpjs", default=None, help="separados por vírgula, no lugar das maiores"
    )
    argumentos.add_argument(
        "--memoria", default=None, help="limite do DuckDB, ex.: 4GB"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    saida = opcoes.saida or pasta.parent / "relatorios" / (
        f"medir_rede_{datetime.now(UTC):%Y-%m-%d}_p{opcoes.profundidade}.json"
    )
    with porta.abrir(pasta, memoria=opcoes.memoria) as p:
        empresas = (
            [(c.strip(), "") for c in opcoes.cnpjs.split(",") if c.strip()]
            if opcoes.cnpjs
            else maiores(p, opcoes.quantas)
        )
        medida = medir(p, empresas, opcoes.profundidade)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(medida, ensure_ascii=False, indent=1), encoding="utf-8")
    resumo = medida["resumo"]
    print(
        f"rede com {opcoes.profundidade} saltos: {resumo['empresas']} empresas em "
        f"{resumo['segundos_no_total']:.1f} s (a mais lenta {resumo['segundos_na_mais_lenta']:.1f} s), "
        f"memória máxima {resumo['memoria_maxima_mb']} MB; em {saida}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
