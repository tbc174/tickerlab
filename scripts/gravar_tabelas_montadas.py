"""Grava `base/tabelas_montadas.json`: as tabelas do catálogo que têm arquivo no acervo (linha 916).

    TICKERLAB_ACERVO=/mnt/dados/tickerlab-acervo python -m scripts.gravar_tabelas_montadas

O site e a lista da API contam só tabela montada (`base.vitrine.catalogo_publico`). O CI não vê o acervo,
então a conferência roda no servidor de casa, **só leitura pela porta** (`base.porta`), e a lista vai no
commit com a data. Tabela nova do catálogo só passa a contar depois de uma nova gravação.

Roda: manual no servidor de casa, a cada lote de carga montado (próxima gravação: qui 19/11/2026).
"""

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from base import porta, vitrine

BRASILIA = ZoneInfo("America/Sao_Paulo")

# Tabelas que existem, mas não como Parquet da porta no acervo (`porta.duckdb.FORA_DA_PORTA`): as quatro
# que moram no banco do app e o cadastro das companhias, lido do original no acervo. Contam, porque os
# dados estão lá; as `cnpj_*` da carga mensal (ainda sem rodar no servidor) e as só internas não contam.
EXISTEM_FORA_DA_PORTA: frozenset[str] = frozenset(
    {
        "achados_de_qualidade",
        "padroes_setoriais",
        "fre_proventos",
        "fre_eventos_de_capital",
        "cadastro_das_companhias",
    }
)


def montadas_na_porta(hoje: date | None = None) -> dict:
    """Os nomes das tabelas do catálogo com arquivo na porta, e a data da conferência."""
    dia = hoje or datetime.now(BRASILIA).date()
    with porta.abrir() as aberta:
        catalogo = aberta.catalogo()["tabelas"]
    nomes = sorted(
        nome
        for nome, t in catalogo.items()
        if t["na_porta"] or nome in EXISTEM_FORA_DA_PORTA
    )
    return {"conferido_em": dia.isoformat(), "tabelas": nomes}


def gravar(medida: dict, destino: Path) -> None:
    texto = json.dumps(medida, ensure_ascii=False, indent=2)
    destino.write_text(texto + "\n", encoding="utf-8")


def main() -> None:
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument(
        "--destino", type=Path, default=vitrine.TABELAS_MONTADAS_ARQUIVO
    )
    argumentos = analise.parse_args()
    medida = montadas_na_porta()
    gravar(medida, argumentos.destino)
    print(f"{len(medida['tabelas'])} tabelas montadas em {medida['conferido_em']}")


if __name__ == "__main__":
    main()
