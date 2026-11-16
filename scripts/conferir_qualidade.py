"""Mede a qualidade (exigência 7 da prontidão) das tabelas que a API serve e grava o resultado do dia.

    python -m scripts.conferir_qualidade [--tabela NOME]

Para cada tabela com regra em `base/qualidade_automatica.py` pede à porta as medidas (`Porta.perfil`),
aplica a regra e grava `<acervo>/placar/<dia>/qualidade.json` (só nomes de tabela, contagens e
as explicações escritas na regra: nada de linha, nome ou documento). Sai com 1 se alguma tabela ficou
vermelha (achado sem explicação); a prova dura 90 dias (`base/prontidao.py`).

Roda: manual, a cada rodada de prova da exigência 7 (a prova vale 90 dias).
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from base import porta
from base.parquet import gravar_atomico
from base.qualidade_automatica import REGRAS, Achado, avaliar, sem_explicacao
from src import acervo

BRASILIA = ZoneInfo("America/Sao_Paulo")


def medir(p: porta.Porta, tabela: str) -> dict[str, object]:
    regra = REGRAS[tabela]
    perfil = p.perfil(tabela, regra.chave, regra.periodo, regra.valor)
    achados: list[Achado] = avaliar(regra, perfil)
    return {
        "tabela": tabela,
        "linhas": perfil["linhas"],
        "vermelho": bool(sem_explicacao(achados)),
        "achados": [{"texto": a.texto, "explicacao": a.explicacao} for a in achados],
    }


def _juntar_com_o_do_dia(
    destino: Path, novos: list[dict[str, object]]
) -> list[dict[str, object]]:
    """`--tabela` mede uma só: as outras do mesmo dia continuam no arquivo (a prova de cada uma é o registro dele)."""
    if not destino.exists():
        return novos
    try:
        antigos = json.loads(destino.read_text(encoding="utf-8"))["tabelas"]
    except (OSError, ValueError, KeyError, TypeError):
        return novos
    nomes = {r["tabela"] for r in novos}
    return [r for r in antigos if r.get("tabela") not in nomes] + novos


def gravar(dia: str, resultados: list[dict[str, object]]) -> Path:
    raiz = acervo.pasta_do_acervo()
    if raiz is None:
        raise SystemExit("o acervo está desligado: defina TICKERLAB_ACERVO")
    pasta = raiz / "placar" / dia
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "qualidade.json"
    resultados = _juntar_com_o_do_dia(destino, resultados)
    texto = json.dumps(
        {
            "dia": dia,
            "vermelho": any(r["vermelho"] for r in resultados),
            "tabelas": resultados,
        },
        ensure_ascii=False,
        indent=2,
    )
    gravar_atomico(destino, lambda t: t.write_text(texto, encoding="utf-8"))
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tabela", choices=sorted(REGRAS))
    args = parser.parse_args(argv)
    dia = datetime.now(BRASILIA).date().isoformat()
    resultados = []
    with porta.abrir() as p:
        for tabela in [args.tabela] if args.tabela else sorted(REGRAS):
            resultado = medir(p, tabela)
            resultados.append(resultado)
            cor = "VERMELHO" if resultado["vermelho"] else "verde"
            print(f"{tabela}: {resultado['linhas']} linhas, {cor}")
            for a in resultado["achados"]:  # type: ignore[attr-defined]
                print(
                    f"  {'explicado' if a['explicacao'] else 'SEM EXPLICACAO'}: {a['texto']}"
                )
    print(f"gravado em {gravar(dia, resultados)}")
    return 1 if any(r["vermelho"] for r in resultados) else 0


if __name__ == "__main__":
    sys.exit(main())
